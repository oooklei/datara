"""WF-14 TrialRunner tests — design §4.1/§4.2.

Covers: TRIAL instance creation (instance_type=TRIAL, trigger=TRIAL), task count
matches snapshot nodes, terminal status SUCCEEDED/FAILED, topological execution.
"""

import json
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from rebuild.common.db import Base
from rebuild.execution.models import RunOutputRecord, TaskInstanceRecord, WorkflowInstanceRecord, WorkflowRunStatRecord
from rebuild.resources.repository import ResourceRepository
from rebuild.trial.repository import TrialSnapshotRepository
from rebuild.trial.runner import TrialRunner, TrialRunnerError, TrialRunOptions
from rebuild.dependency.models import DependencyConfigRecord
from rebuild.datasource.models import ProjectDatasourceRecord
from rebuild.project.models import ProjectRecord  # noqa: F401 - register FK target table
from rebuild.identity.models import UserRecord  # noqa: F401 - register FK target table
from rebuild.trial.api import build_trial_router
from rebuild.workflow.models import (
    WorkflowDefinitionRecord,
    WorkflowEdgeRecord,
    WorkflowNodeRecord,
)
from rebuild.sync.executor import SyncBatchWriteResult


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
    assert all(task.status == "SUCCEEDED" for task in tasks)
    run_stat = session.scalar(
        select(WorkflowRunStatRecord).where(
            WorkflowRunStatRecord.workflow_instance_id == result.instance_id
        )
    )
    assert run_stat is not None
    assert (run_stat.success_count, run_stat.failure_count, run_stat.skipped_count) == (3, 0, 0)


@pytest.mark.parametrize(
    ("fail_write", "expected_status", "expected_counts"),
    [
        (False, "SUCCEEDED", (3, 0, 0)),
        (True, "FAILED", (2, 1, 0)),
    ],
)
def test_trial_run_materializes_endpoint_select_and_persists_sync_counts(
    fail_write, expected_status, expected_counts
):
    session = _session()
    definition_id = _make_definition(session)
    session.get(WorkflowDefinitionRecord, definition_id).workflow_type = "SYNC"
    _add_node(session, definition_id, "start", node_type="START")
    _add_node(
        session,
        definition_id,
        "endpoint",
        node_type="endpoint_select",
        params={
            "baseMode": "src_base",
            "source": {"datasource_id": 11, "schema": "src", "object": "orders"},
            "target": {"datasource_id": 12, "schema": "dw", "object": "orders_copy"},
            "target_properties": {"batch_concurrency": {"batch_size": 100, "concurrency": 1}},
        },
    )
    _add_node(
        session,
        definition_id,
        "mapping",
        node_type="field_map",
        params={"fieldMap": [{"key": "id", "value": "user_id"}]},
    )
    _add_node(
        session,
        definition_id,
        "condition",
        node_type="condition_set",
        params={"filterExpr": "id > 1"},
    )
    _add_node(session, definition_id, "end", node_type="END")
    _add_edge(session, definition_id, "start", "endpoint")
    _add_edge(session, definition_id, "endpoint", "mapping")
    _add_edge(session, definition_id, "mapping", "condition")
    _add_edge(session, definition_id, "condition", "end")
    session.flush()
    snapshot_id = TrialSnapshotRepository(session).create_from_draft(definition_id)["snapshot_id"]

    class Driver:
        conditions = []

        def read_rows(self, spec, *, batch_size):
            return ({"id": 1}, {"id": 2})

        def include_row(self, condition, row):
            self.conditions.append(condition)
            return row["id"] > 1

        def transform_value(self, expression, row):
            raise AssertionError("no transform expected")

        def write_batch(self, spec, rows):
            if fail_write:
                raise RuntimeError("target write failed")
            return SyncBatchWriteResult(inserted=len(rows), success=len(rows))

        def write_statistics(self, context, metrics):
            pass

        def write_lineage(self, context, edges):
            pass

    driver = Driver()
    result = TrialRunner(session, sync_driver_factory=lambda *_args, **_kwargs: driver).run(
        definition_id=definition_id,
        snapshot_id=snapshot_id,
        project_id=1,
    )
    session.commit()

    assert result.status == expected_status
    assert result.task_count == 3
    sync_task = session.scalar(
        select(TaskInstanceRecord).where(
            TaskInstanceRecord.workflow_instance_id == result.instance_id,
            TaskInstanceRecord.task_id.like("sys_exec_%"),
        )
    )
    assert sync_task is not None
    output = session.scalar(select(RunOutputRecord).where(RunOutputRecord.task_instance_id == sync_task.id))
    if fail_write:
        assert output is None
    else:
        assert '"success": 1' in output.output_json
        assert '"failed": 0' in output.output_json
        assert driver.conditions == ["id > 1", "id > 1"]

    tasks = session.scalars(
        select(TaskInstanceRecord).where(
            TaskInstanceRecord.workflow_instance_id == result.instance_id
        )
    ).all()
    assert len(tasks) == 3
    assert sync_task.status == expected_status
    run_stat = session.scalar(
        select(WorkflowRunStatRecord).where(
            WorkflowRunStatRecord.workflow_instance_id == result.instance_id
        )
    )
    assert run_stat is not None
    assert (run_stat.success_count, run_stat.failure_count, run_stat.skipped_count) == expected_counts


def test_trial_api_uses_runtime_datasource_adapter_and_records_success_and_failure():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    source = sqlite3.connect(":memory:", check_same_thread=False)
    target = sqlite3.connect(":memory:", check_same_thread=False)
    source.execute("CREATE TABLE orders (id INTEGER NOT NULL)")
    source.executemany("INSERT INTO orders (id) VALUES (?)", [(1,), (2,)])
    source.commit()
    target.execute("CREATE TABLE orders_copy (user_id INTEGER NOT NULL)")
    target.commit()

    class TokenService:
        def verify(self, _token):
            return {"user_id": 7}

    class NonClosingConnection:
        def __init__(self, connection):
            self._connection = connection

        def __getattr__(self, name):
            return getattr(self._connection, name)

        def cursor(self):
            cursor = self._connection.cursor()

            class Cursor:
                def __getattr__(self, name):
                    return getattr(cursor, name)

                def execute(self, sql, parameters=()):
                    return cursor.execute(sql.replace("%s", "?"), parameters)

                def executemany(self, sql, parameters):
                    return cursor.executemany(sql.replace("%s", "?"), parameters)

            return Cursor()

        def close(self):
            pass

    connections = {11: source, 12: target}

    def connector_factory(_project_id, datasource_id):
        return lambda _draft: NonClosingConnection(connections[datasource_id])

    app = FastAPI()
    app.include_router(
        build_trial_router(
            sessions,
            TokenService(),
            {"test-token"},
            lambda *_args: None,
            connector_factory,
        ),
        prefix="/api/v1/rebuild/trial",
    )

    with sessions() as session:
        definition_id = _make_definition(session)
        session.get(WorkflowDefinitionRecord, definition_id).workflow_type = "SYNC"
        session.add_all(
            [
                ProjectDatasourceRecord(
                    id=11, project_id=1, name="source", kind="mysql", host="source", port=3306,
                    database_name="source", username="user", password="",
                ),
                ProjectDatasourceRecord(
                    id=12, project_id=1, name="target", kind="mysql", host="target", port=3306,
                    database_name="target", username="user", password="",
                ),
            ]
        )
        _add_node(session, definition_id, "start", node_type="START")
        _add_node(
            session,
            definition_id,
            "endpoint",
            node_type="endpoint_select",
            params={
                "baseMode": "src_base",
                "source": {"datasource_id": 11, "schema": "main", "object": "orders"},
                "target": {"datasource_id": 12, "schema": "main", "object": "orders_copy"},
            },
        )
        _add_node(
            session,
            definition_id,
            "mapping",
            node_type="field_map",
            params={"fieldMap": [{"key": "id", "value": "user_id"}]},
        )
        _add_node(
            session,
            definition_id,
            "condition",
            node_type="condition_set",
            params={"filterExpr": "id > 1"},
        )
        _add_node(session, definition_id, "end", node_type="END")
        _add_edge(session, definition_id, "start", "endpoint")
        _add_edge(session, definition_id, "endpoint", "mapping")
        _add_edge(session, definition_id, "mapping", "condition")
        _add_edge(session, definition_id, "condition", "end")
        session.flush()
        snapshot_id = TrialSnapshotRepository(session).create_from_draft(definition_id)["snapshot_id"]
        session.commit()

    client = TestClient(app)
    request = {
        "project_id": 1,
        "snapshot_id": snapshot_id,
    }
    headers = {"token": "test-token"}
    succeeded = client.post(
        f"/api/v1/rebuild/trial/definitions/{definition_id}/run", json=request, headers=headers
    ).json()["data"]
    assert succeeded["status"] == "SUCCEEDED"
    assert target.execute("SELECT user_id FROM orders_copy ORDER BY user_id").fetchall() == [(2,)]

    target.execute("DROP TABLE orders_copy")
    target.commit()
    failed = client.post(
        "/api/v1/rebuild/trial/runs",
        json={**request, "definition_id": definition_id},
        headers=headers,
    ).json()["data"]
    assert failed["status"] == "FAILED"

    with sessions() as session:
        succeeded_stat = session.scalar(
            select(WorkflowRunStatRecord).where(
                WorkflowRunStatRecord.workflow_instance_id == succeeded["instance_id"]
            )
        )
        failed_stat = session.scalar(
            select(WorkflowRunStatRecord).where(
                WorkflowRunStatRecord.workflow_instance_id == failed["instance_id"]
            )
        )
        assert (succeeded_stat.success_count, succeeded_stat.failure_count) == (3, 0)
        assert (failed_stat.success_count, failed_stat.failure_count) == (2, 1)


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


def test_priority_components_execute_in_one_six_node_workflow_sample():
    """SQL/Python/Shell/dependent must close one observable workflow together."""
    session = _session()
    definition_id = _make_definition(session)
    dependency = DependencyConfigRecord(
        project_id=1,
        workflow_id=definition_id,
        workflow_version=0,
        task_id="wait_upstream",
        groups_json="[]",
    )
    session.add(dependency)
    session.flush()

    nodes = (
        ("start", "START", None),
        ("query", "sql", {"sql": "SELECT 7 AS result", "execute": True}),
        ("transform", "python", {"script": "print('python-ok')"}),
        ("publish", "shell", {"script": "echo shell-ok"}),
        ("wait_upstream", "dependent", {"dependency_id": dependency.id}),
        ("end", "END", None),
    )
    for node_code, node_type, params in nodes:
        _add_node(session, definition_id, node_code, node_type=node_type, params=params)
    for source, target in zip(nodes, nodes[1:]):
        _add_edge(session, definition_id, source[0], target[0])
    session.commit()
    snapshot = TrialSnapshotRepository(session).create_from_draft(definition_id)

    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot["snapshot_id"],
        project_id=1,
        options=TrialRunOptions(
            sql_execute=True,
            dependency_mock={str(dependency.id): "SUCCEEDED"},
        ),
    )

    tasks = session.scalars(
        select(TaskInstanceRecord).where(TaskInstanceRecord.workflow_instance_id == result.instance_id)
    ).all()
    outputs = {
        task.task_id: json.loads(output.output_json)
        for task in tasks
        if (output := session.scalar(select(RunOutputRecord).where(RunOutputRecord.task_instance_id == task.id)))
    }
    assert result.status == "SUCCEEDED"
    assert len(tasks) == 6 and all(task.status == "SUCCEEDED" for task in tasks)
    assert outputs["query"]["rows"] == [[7]]
    assert outputs["transform"]["stdout"].strip() == "python-ok"
    assert outputs["publish"]["stdout"].strip() == "shell-ok"


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
