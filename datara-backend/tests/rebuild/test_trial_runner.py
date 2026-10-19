"""WF-14 TrialRunner tests — design §4.1/§4.2.

Covers: TRIAL instance creation (instance_type=TRIAL, trigger=TRIAL), task count
matches snapshot nodes, terminal status SUCCEEDED/FAILED, topological execution.
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.execution.models import TaskInstanceRecord, WorkflowInstanceRecord
from rebuild.trial.models import WorkflowDraftSnapshotRecord
from rebuild.trial.repository import TrialSnapshotRepository
from rebuild.trial.runner import TrialRunner, TrialRunnerError, TrialRunOptions
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


def test_trial_run_validation_failure_rejects():
    session = _session()
    definition_id = _make_definition(session)
    # No START node → validation error.
    _add_node(session, definition_id, "a", params={"sql": "SELECT 1"})
    _add_node(session, definition_id, "b", params={"sql": "SELECT 2"})
    _add_edge(session, definition_id, "a", "b")
    session.commit()

    snapshot = TrialSnapshotRepository(session).create_from_draft(definition_id)

    with pytest.raises(TrialRunnerError) as excinfo:
        TrialRunner(session).run(
            definition_id=definition_id,
            snapshot_id=snapshot["snapshot_id"],
            project_id=1,
        )
    assert excinfo.value.code == "WF_TRIAL_INVALID"
    assert "START" in excinfo.value.msg


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
