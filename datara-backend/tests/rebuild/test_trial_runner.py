"""WF-14 TrialRunner tests — design §4.1/§4.2.

Covers: TRIAL instance creation (instance_type=TRIAL, trigger=TRIAL), task count
matches snapshot nodes, terminal status SUCCEEDED/FAILED, topological execution.
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.execution.models import RunOutputRecord, TaskInstanceRecord, WorkflowInstanceRecord, WorkflowRunStatRecord
from rebuild.resources.repository import ResourceRepository
from rebuild.trial.repository import TrialSnapshotRepository
from rebuild.trial.runner import TrialRunner, TrialRunnerError, TrialRunOptions
from rebuild.dependency.models import DependencyConfigRecord
from rebuild.project.models import ProjectRecord  # noqa: F401 - register FK target table
from rebuild.identity.models import UserRecord  # noqa: F401 - register FK target table
from rebuild.workflow.models import (
    WorkflowDefinitionRecord,
    WorkflowEdgeRecord,
    WorkflowNodeRecord,
)


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _make_definition(session, project_id=1):
    record = WorkflowDefinitionRecord(project_id=project_id, name="runner-test")
    session.add(record)
    session.flush()
    return record.id


def _add_node(session, definition_id, node_code, node_type="SQL", params=None):
    import json

    record = WorkflowNodeRecord(
        definition_id=definition_id,
        version_id=None,
        node_code=node_code,
        node_type=node_type,
        name=node_code,
        params_json=json.dumps(params or {}),
    )
    session.add(record)
    session.flush()


def _add_edge(session, definition_id, from_node, to_node):
    record = WorkflowEdgeRecord(
        definition_id=definition_id, version_id=None, from_node=from_node, to_node=to_node
    )
    session.add(record)
    session.flush()


def _setup_valid_draft(session):
    """Create a definition with START -> SQL -> END and return (definition_id, snapshot_id)."""
    definition_id = _make_definition(session)
    _add_node(session, definition_id, "start", node_type="START")
    _add_node(session, definition_id, "extract", params={"sql": "SELECT 1"})
    _add_node(session, definition_id, "end", node_type="END")
    _add_edge(session, definition_id, "start", "extract")
    _add_edge(session, definition_id, "extract", "end")
    session.commit()

    snapshot = TrialSnapshotRepository(session).create_from_draft(definition_id)
    return definition_id, snapshot["snapshot_id"]


def test_trial_run_creates_instance_and_tasks():
    session = _session()
    definition_id, snapshot_id = _setup_valid_draft(session)

    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot_id,
        project_id=1,
    )
    session.commit()

    assert result.status == "SUCCEEDED"
    assert result.task_count == 3  # start, extract, end
    assert result.instance_id > 0

    instance = session.get(WorkflowInstanceRecord, result.instance_id)
    assert instance.instance_type == "TRIAL"
    assert instance.trigger_type == "TRIAL"
    assert instance.status == "SUCCEEDED"

    tasks = session.scalars(
        select(TaskInstanceRecord).where(
            TaskInstanceRecord.workflow_instance_id == result.instance_id
        )
    ).all()
    assert len(tasks) == 3
    assert all(t.status == "SUCCEEDED" for t in tasks)
    run_stat = session.scalar(
        select(WorkflowRunStatRecord).where(
            WorkflowRunStatRecord.workflow_instance_id == result.instance_id
        )
    )
    assert run_stat is not None
    assert (run_stat.success_count, run_stat.failure_count, run_stat.skipped_count) == (3, 0, 0)


def test_trial_run_executes_python_and_shell_scripts():
    session = _session()
    definition_id = _make_definition(session)
    _add_node(session, definition_id, "start", node_type="START")
    _add_node(session, definition_id, "py", node_type="PYTHON", params={"script": "print('python-ok')"})
    _add_node(session, definition_id, "sh", node_type="SHELL", params={"command": "echo shell-ok"})
    _add_node(session, definition_id, "end", node_type="END")
    _add_edge(session, definition_id, "start", "py")
    _add_edge(session, definition_id, "py", "sh")
    _add_edge(session, definition_id, "sh", "end")
    session.commit()
    snapshot = TrialSnapshotRepository(session).create_from_draft(definition_id)

    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot["snapshot_id"],
        project_id=1,
    )
    assert result.status == "SUCCEEDED"
    outputs = session.scalars(
        select(TaskInstanceRecord).where(TaskInstanceRecord.workflow_instance_id == result.instance_id)
    ).all()
    assert all(task.status == "SUCCEEDED" for task in outputs)


def test_trial_run_executes_explicitly_bound_resource_versions(monkeypatch, tmp_path):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path))
    session = _session()
    definition_id = _make_definition(session)
    repository = ResourceRepository(session)
    uploaded = repository.save_upload(1, "python", "bound.py", b"print('resource-python-ok')")
    _add_node(session, definition_id, "py", node_type="python", params={
        "sourceMode": "resource",
        "resourceRef": {"resourceId": uploaded["resource_id"], "version": uploaded["version"]},
    })
    repository.bind(1, definition_id, 1, "py", uploaded["resource_id"], uploaded["version"])
    session.commit()
    snapshot = TrialSnapshotRepository(session).create_from_draft(definition_id)

    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot["snapshot_id"],
        project_id=1,
    )

    task = session.scalar(select(TaskInstanceRecord).where(
        TaskInstanceRecord.workflow_instance_id == result.instance_id,
        TaskInstanceRecord.task_id == "py",
    ))
    output = session.scalar(select(RunOutputRecord).where(RunOutputRecord.task_instance_id == task.id))
    assert result.status == "SUCCEEDED"
    assert "resource-python-ok" in output.output_json


@pytest.mark.parametrize(
    ("kind", "filename", "content", "expected", "options"),
    [
        ("sql", "bound.sql", b"select 7 as resource_value", '"resource_value"', TrialRunOptions(sql_execute=True)),
        ("shell", "bound.sh", b"echo resource-shell-ok", "resource-shell-ok", None),
    ],
)
def test_trial_run_executes_sql_and_shell_resource_versions(
    monkeypatch, tmp_path, kind, filename, content, expected, options
):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path))
    session = _session()
    definition_id = _make_definition(session)
    uploaded = ResourceRepository(session).save_upload(1, kind, filename, content)
    _add_node(session, definition_id, "task", node_type=kind, params={
        "sourceMode": "resource",
        "resourceRef": {"resourceId": uploaded["resource_id"], "version": uploaded["version"]},
    })
    ResourceRepository(session).bind(
        1, definition_id, 1, "task", uploaded["resource_id"], uploaded["version"]
    )
    session.commit()
    snapshot = TrialSnapshotRepository(session).create_from_draft(definition_id)

    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot["snapshot_id"],
        project_id=1,
        options=options,
    )

    task = session.scalar(select(TaskInstanceRecord).where(
        TaskInstanceRecord.workflow_instance_id == result.instance_id,
        TaskInstanceRecord.task_id == "task",
    ))
    output = session.scalar(select(RunOutputRecord).where(RunOutputRecord.task_instance_id == task.id))
    assert result.status == "SUCCEEDED"
    assert expected in output.output_json


def test_trial_run_rejects_tampered_bound_resource(monkeypatch, tmp_path):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path))
    session = _session()
    definition_id = _make_definition(session)
    repository = ResourceRepository(session)
    uploaded = repository.save_upload(1, "shell", "bound.sh", b"echo safe")
    _add_node(session, definition_id, "sh", node_type="shell", params={
        "sourceMode": "resource",
        "resourceRef": {"resourceId": uploaded["resource_id"], "version": uploaded["version"]},
    })
    repository.bind(1, definition_id, 1, "sh", uploaded["resource_id"], uploaded["version"])
    (tmp_path / "1" / "v1").write_text("echo tampered", encoding="utf-8")
    session.commit()
    snapshot = TrialSnapshotRepository(session).create_from_draft(definition_id)

    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot["snapshot_id"],
        project_id=1,
    )

    assert result.status == "FAILED"


def test_trial_run_executes_lowercase_dependent_component_with_mock():
    """Palette ``dependent`` refs must not fall through generic execution."""
    session = _session()
    definition_id = _make_definition(session)
    _add_node(session, definition_id, "sql", node_type="sql", params={"sql": "SELECT 1"})
    _add_node(session, definition_id, "dependent", node_type="dependent", params={"dependency_id": 42})
    session.add(DependencyConfigRecord(
        id=42, project_id=1, workflow_id=definition_id, workflow_version=0,
        task_id="dependent", groups_json="[]",
    ))
    _add_edge(session, definition_id, "sql", "dependent")
    session.commit()
    snapshot = TrialSnapshotRepository(session).create_from_draft(definition_id)

    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot["snapshot_id"],
        project_id=1,
        options=TrialRunOptions(dependency_mock={"42": "SUCCEEDED"}),
    )
    assert result.status == "SUCCEEDED"
    tasks = session.scalars(
        select(TaskInstanceRecord).where(TaskInstanceRecord.workflow_instance_id == result.instance_id)
    ).all()
    assert {task.task_id for task in tasks} == {"sql", "dependent"}
    assert all(task.status == "SUCCEEDED" for task in tasks)


def test_trial_run_validation_failure_rejects():
    session = _session()
    definition_id = _make_definition(session)
    # Dependency nodes must reference a saved dependency configuration.
    _add_node(session, definition_id, "a", node_type="dependent", params={"dependency_id": 9999})
    session.commit()

    snapshot = TrialSnapshotRepository(session).create_from_draft(definition_id)

    with pytest.raises(TrialRunnerError) as excinfo:
        TrialRunner(session).run(
            definition_id=definition_id,
            snapshot_id=snapshot["snapshot_id"],
            project_id=1,
        )
    assert excinfo.value.code == "WF_TRIAL_INVALID"
    assert "missing dependency" in excinfo.value.msg


def test_trial_run_with_node_subset():
    session = _session()
    definition_id, snapshot_id = _setup_valid_draft(session)

    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot_id,
        project_id=1,
        options=TrialRunOptions(node_codes=["extract"]),
    )
    session.commit()

    assert result.status == "SUCCEEDED"
    assert result.task_count == 1


def test_trial_run_from_start_node():
    session = _session()
    definition_id, snapshot_id = _setup_valid_draft(session)

    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot_id,
        project_id=1,
        options=TrialRunOptions(start_node="extract"),
    )
    session.commit()

    assert result.status == "SUCCEEDED"
    # start is upstream → skipped; extract + end are forward-reachable.
    assert result.task_count == 2


def test_trial_run_invalid_start_node_rejected():
    session = _session()
    definition_id, snapshot_id = _setup_valid_draft(session)

    with pytest.raises(TrialRunnerError) as excinfo:
        TrialRunner(session).run(
            definition_id=definition_id,
            snapshot_id=snapshot_id,
            project_id=1,
            options=TrialRunOptions(start_node="ghost"),
        )
    assert excinfo.value.code == "WF_TRIAL_INVALID"
