"""WF-15~WF-20 TrialRunner extension dimension tests.

Covers: single-node subset (WF-15), start_node subgraph (WF-16), test variable
overrides (WF-17), dependency mock (WF-18), dry run (WF-19), SQL precheck (WF-20).
"""

import json
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.execution.models import RunOutputRecord, TaskInstanceRecord, WorkflowInstanceRecord
from rebuild.trial.repository import TrialSnapshotRepository
from rebuild.trial.runner import TrialRunner, TrialRunnerError, TrialRunOptions
from rebuild.variables.models import TaskInstanceVariableRuntimeRecord
from rebuild.variables.repository import VariableRepository
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
    record = WorkflowDefinitionRecord(project_id=project_id, name="ext-test")
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


def _setup_chain(session):
    """START -> a -> b -> END."""
    definition_id = _make_definition(session)
    _add_node(session, definition_id, "start", node_type="START")
    _add_node(session, definition_id, "a", params={"sql": "SELECT 1"})
    _add_node(session, definition_id, "b", params={"sql": "SELECT 2"})
    _add_node(session, definition_id, "end", node_type="END")
    _add_edge(session, definition_id, "start", "a")
    _add_edge(session, definition_id, "a", "b")
    _add_edge(session, definition_id, "b", "end")
    session.commit()
    snapshot = TrialSnapshotRepository(session).create_from_draft(definition_id)
    return definition_id, snapshot["snapshot_id"]


# WF-15: single-node subset ---------------------------------------------------


def test_wf15_single_node_subset():
    session = _session()
    definition_id, snapshot_id = _setup_chain(session)

    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot_id,
        project_id=1,
        options=TrialRunOptions(node_codes=["a"]),
    )
    session.commit()

    assert result.status == "SUCCEEDED"
    assert result.task_count == 1
    assert result.tasks[0]["node_code"] == "a"


def test_wf15_invalid_node_code_rejected():
    session = _session()
    definition_id, snapshot_id = _setup_chain(session)

    with pytest.raises(TrialRunnerError) as excinfo:
        TrialRunner(session).run(
            definition_id=definition_id,
            snapshot_id=snapshot_id,
            project_id=1,
            options=TrialRunOptions(node_codes=["ghost"]),
        )
    assert excinfo.value.code == "WF_TRIAL_INVALID"


# WF-16: start_node subgraph ---------------------------------------------------


def test_wf16_start_node_subgraph():
    session = _session()
    definition_id, snapshot_id = _setup_chain(session)

    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot_id,
        project_id=1,
        options=TrialRunOptions(start_node="a"),
    )
    session.commit()

    assert result.status == "SUCCEEDED"
    # a + b + end are forward-reachable from a; start is skipped.
    assert result.task_count == 3
    # WF-27: skipped tasks are included in the result payload.
    codes = {t["node_code"] for t in result.tasks}
    assert "start" in codes
    start_task = next(t for t in result.tasks if t["node_code"] == "start")
    assert start_task["status"] == "SKIPPED"


# WF-17: test variable overrides ------------------------------------------------


def test_wf17_test_variables_recorded():
    session = _session()
    definition_id, snapshot_id = _setup_chain(session)

    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot_id,
        project_id=1,
        options=TrialRunOptions(test_variables={"env": "staging", "batch_size": 500}),
    )
    session.commit()

    assert result.status == "SUCCEEDED"

    variables = session.scalars(
        select(TaskInstanceVariableRuntimeRecord).where(
            TaskInstanceVariableRuntimeRecord.instance_id == result.instance_id
        )
    ).all()
    names = {v.name for v in variables}
    assert "env" in names
    assert "batch_size" in names
    env_var = next(v for v in variables if v.name == "env")
    assert env_var.resolved_value == "staging"
    assert env_var.source == "test_override"


def test_wf17_resolves_workflow_environment_global_and_run_variables_before_execution():
    session = _session()
    definition_id = _make_definition(session)
    _add_node(
        session,
        definition_id,
        "python_vars",
        node_type="PYTHON",
        params={"script": 'print("${workflow.region}|${env.region}|${global.region}|${run.batch}")'},
    )
    repository = VariableRepository(session)
    common = {"value_type": "string", "sensitive": False, "description": ""}
    repository.upsert(scope="global", project_id=None, name="region", value="global", **common)
    repository.upsert(scope="env", project_id=1, name="region", value="env", environment_group_id=9, **common)
    repository.upsert(
        scope="workflow", project_id=1, name="region", value="workflow", workflow_id=definition_id, **common
    )
    session.commit()
    snapshot = TrialSnapshotRepository(session).create_from_draft(definition_id)

    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot["snapshot_id"],
        project_id=1,
        options=TrialRunOptions(test_variables={"batch": 500}, environment_group_id=9),
    )
    session.commit()

    assert result.status == "SUCCEEDED"
    outputs = [json.loads(row.output_json) for row in session.scalars(select(RunOutputRecord)).all()]
    assert any(row.get("stdout") == "workflow|env|global|500\n" for row in outputs)
    snapshots = session.scalars(
        select(TaskInstanceVariableRuntimeRecord).where(
            TaskInstanceVariableRuntimeRecord.instance_id == result.instance_id
        )
    ).all()
    assert {row.name for row in snapshots} == {"region", "batch"}


def test_wf17_rejects_invalid_environment_group_before_creating_runtime_rows():
    session = _session()
    definition_id = _make_definition(session)
    _add_node(session, definition_id, "python_vars", node_type="PYTHON", params={"script": "print('ok')"})
    session.commit()
    snapshot = TrialSnapshotRepository(session).create_from_draft(definition_id)

    with pytest.raises(TrialRunnerError, match="environment_group_id must be a positive integer"):
        TrialRunner(session).run(
            definition_id=definition_id,
            snapshot_id=snapshot["snapshot_id"],
            project_id=1,
            options=TrialRunOptions(environment_group_id=0),
        )

    assert session.scalars(select(WorkflowInstanceRecord)).all() == []


# WF-18: dependency mock -------------------------------------------------------


def _setup_with_dependency(session):
    from rebuild.dependency.models import DependencyConfigRecord

    definition_id = _make_definition(session)
    # Create a dependency config so the DEPENDENCY node's target exists.
    dep = DependencyConfigRecord(
        project_id=1,
        workflow_id=definition_id,
        workflow_version=0,
        task_id="dep",
        groups_json="[]",
    )
    session.add(dep)
    session.flush()

    _add_node(session, definition_id, "start", node_type="START")
    _add_node(session, definition_id, "dep", node_type="DEPENDENCY", params={"dependency_id": dep.id})
    _add_node(session, definition_id, "end", node_type="END")
    _add_edge(session, definition_id, "start", "dep")
    _add_edge(session, definition_id, "dep", "end")
    session.commit()
    snapshot = TrialSnapshotRepository(session).create_from_draft(definition_id)
    return definition_id, snapshot["snapshot_id"], dep.id


def test_wf18_dependency_mock_succeeded():
    session = _session()
    definition_id, snapshot_id, dep_id = _setup_with_dependency(session)

    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot_id,
        project_id=1,
        options=TrialRunOptions(dependency_mock={str(dep_id): "SUCCEEDED"}),
    )
    session.commit()

    assert result.status == "SUCCEEDED"


def test_wf18_dependency_no_mock_skips():
    session = _session()
    definition_id, snapshot_id, dep_id = _setup_with_dependency(session)

    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot_id,
        project_id=1,
        options=TrialRunOptions(),
    )
    session.commit()

    # DEPENDENCY without mock still completes (skipped semantics via log).
    assert result.status == "SUCCEEDED"


# WF-19: dry run ---------------------------------------------------------------


def test_wf19_dry_run_returns_plan_no_side_effects():
    session = _session()
    definition_id, snapshot_id = _setup_chain(session)

    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot_id,
        project_id=1,
        options=TrialRunOptions(dry_run=True),
    )

    assert result.status == "DRY_RUN"
    assert result.plan is not None
    assert len(result.plan) == 4  # all 4 nodes
    assert result.plan[0] == "start"
    assert result.plan[-1] == "end"

    # No instance or task rows created.
    assert session.scalar(select(WorkflowInstanceRecord)) is None
    assert session.scalar(select(TaskInstanceRecord)) is None


# WF-20: SQL precheck ----------------------------------------------------------


def test_wf20_sql_precheck_passes():
    session = _session()
    definition_id, snapshot_id = _setup_chain(session)

    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot_id,
        project_id=1,
        options=TrialRunOptions(sql_precheck=True),
    )
    session.commit()

    assert result.status == "SUCCEEDED"


def test_wf20_sql_execute_returns_real_result_set():
    session = _session()
    definition_id, snapshot_id = _setup_chain(session)

    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot_id,
        project_id=1,
        options=TrialRunOptions(sql_execute=True),
    )
    session.commit()

    assert result.status == "SUCCEEDED"
    outputs = [json.loads(row.output_json) for row in session.scalars(select(RunOutputRecord)).all()]
    sql_outputs = [row for row in outputs if row.get("sql")]
    assert {row["row_count"] for row in sql_outputs} == {1}
    assert all(row["rows"] in [[[1]], [[2]]] for row in sql_outputs)
