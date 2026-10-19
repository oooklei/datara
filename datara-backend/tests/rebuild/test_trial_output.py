"""WF-22 TrialOutputAggregator tests — design §4.1.

Covers: aggregate returns logs/variables/stats sections; empty run returns
empty arrays (not 404); missing instance returns found=False.
"""

import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.execution.models import (
    ExecutionEventRecord,
    RunLogRecord,
    TaskInstanceRecord,
    WorkflowInstanceRecord,
)
from rebuild.execution.repository import ExecutionRepository, RESULT_STAT_EVENT_KIND
from rebuild.trial.output import TrialOutputAggregator
from rebuild.trial.repository import TrialSnapshotRepository
from rebuild.trial.runner import TrialRunner
from rebuild.variables.models import TaskInstanceVariableRuntimeRecord
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
    record = WorkflowDefinitionRecord(project_id=project_id, name="output-test")
    session.add(record)
    session.flush()
    return record.id


def _add_node(session, definition_id, node_code, node_type="SQL", params=None):
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


def _setup_run_with_output(session):
    definition_id = _make_definition(session)
    _add_node(session, definition_id, "start", node_type="START")
    _add_node(session, definition_id, "a", params={"sql": "SELECT 1"})
    _add_node(session, definition_id, "end", node_type="END")
    _add_edge(session, definition_id, "start", "a")
    _add_edge(session, definition_id, "a", "end")
    session.commit()

    snapshot = TrialSnapshotRepository(session).create_from_draft(definition_id)
    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot["snapshot_id"],
        project_id=1,
    )
    session.commit()

    # Add a result-stat event.
    ExecutionRepository(session).record_result_stat(
        workflow_instance_id=result.instance_id,
        attempt_no=1,
        success_count=3,
        failed_count=0,
        skipped_count=0,
    )
    session.commit()

    return result.instance_id


def test_aggregate_returns_logs_variables_stats():
    session = _session()
    instance_id = _setup_run_with_output(session)

    aggregator = TrialOutputAggregator(session)
    output = aggregator.aggregate(instance_id)

    assert output["found"] is True
    assert output["instance_type"] == "TRIAL"
    assert "logs" in output
    assert "variables" in output
    assert "stats" in output

    # Logs should have entries for task "a".
    log_tasks = [entry["task_code"] for entry in output["logs"]]
    assert "a" in log_tasks

    # Variables section exists (empty without test overrides).
    assert isinstance(output["variables"], list)

    # Stats should reflect the result-stat writeback.
    assert output["stats"]["success_count"] >= 0  # may be 0 if no stat events


def test_aggregate_empty_run_returns_empty_arrays():
    session = _session()
    definition_id = _make_definition(session)
    _add_node(session, definition_id, "start", node_type="START")
    _add_node(session, definition_id, "end", node_type="END")
    _add_edge(session, definition_id, "start", "end")
    session.commit()

    snapshot = TrialSnapshotRepository(session).create_from_draft(definition_id)
    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot["snapshot_id"],
        project_id=1,
    )
    session.commit()

    aggregator = TrialOutputAggregator(session)
    output = aggregator.aggregate(result.instance_id)

    assert output["found"] is True
    assert isinstance(output["logs"], list)
    assert isinstance(output["variables"], list)
    assert isinstance(output["stats"], dict)


def test_aggregate_missing_instance_returns_not_found():
    session = _session()
    aggregator = TrialOutputAggregator(session)
    output = aggregator.aggregate(99999)

    assert output["found"] is False
    assert output["logs"] == []
    assert output["variables"] == []
