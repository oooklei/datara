"""Deterministic dependency-failure fixture for the high-priority workflow path.

The fixture deliberately uses the dependency mock's ``FAILED`` outcome.  It is
kept separate from the happy-path sample so failure logs, retry attempts and
the run-stat receipt are exercised without mutating any shared/remote data.
"""

import json
from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.execution.models import (
    ExecutionEventRecord,
    RunLogRecord,
    TaskAttemptRecord,
    TaskInstanceRecord,
    WorkflowInstanceRecord,
)
from rebuild.execution.repository import ExecutionRepository
from rebuild.dependency.models import DependencyConfigRecord
from rebuild.trial.repository import TrialSnapshotRepository
from rebuild.trial.runner import TrialRunOptions, TrialRunner
from rebuild.workflow.models import WorkflowDefinitionRecord, WorkflowEdgeRecord, WorkflowNodeRecord


def _failure_graph(session: Session) -> tuple[int, int]:
    definition = WorkflowDefinitionRecord(project_id=901, name="dependency-failure-fixture")
    session.add(definition)
    session.flush()
    # The validator requires a real dependency target; the mock controls its
    # outcome at execution time and does not replace this governance record.
    dependency = DependencyConfigRecord(
        project_id=901,
        workflow_id=definition.id,
        workflow_version=0,
        task_id="blocked_dependency",
        groups_json="[]",
    )
    session.add(dependency)
    session.flush()
    nodes = [
        ("start", "START", {}),
        ("blocked_dependency", "DEPENDENCY", {"dependency_id": dependency.id}),
        ("end", "END", {}),
    ]
    for code, node_type, params in nodes:
        session.add(
            WorkflowNodeRecord(
                definition_id=definition.id,
                version_id=None,
                node_code=code,
                node_type=node_type,
                name=code,
                params_json=json.dumps(params),
            )
        )
    for source, target in (("start", "blocked_dependency"), ("blocked_dependency", "end")):
        session.add(
            WorkflowEdgeRecord(
                definition_id=definition.id,
                version_id=None,
                from_node=source,
                to_node=target,
            )
        )
    session.commit()
    snapshot = TrialSnapshotRepository(session).create_from_draft(definition.id)
    return definition.id, snapshot["snapshot_id"]


def test_dependency_failure_persists_error_log_and_run_stat():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        definition_id, snapshot_id = _failure_graph(session)
        result = TrialRunner(session).run(
            definition_id=definition_id,
            snapshot_id=snapshot_id,
            project_id=901,
            options=TrialRunOptions(dependency_mock={"1": "FAILED"}),
        )
        assert result.status == "FAILED"
        instance = session.get(WorkflowInstanceRecord, result.instance_id)
        assert instance is not None and instance.status == "FAILED"
        task = session.scalar(
            select(TaskInstanceRecord).where(
                TaskInstanceRecord.workflow_instance_id == result.instance_id,
                TaskInstanceRecord.task_id == "blocked_dependency",
            )
        )
        assert task is not None and task.status == "FAILED"
        log = session.scalar(
            select(RunLogRecord).where(
                RunLogRecord.task_instance_id == task.id,
                RunLogRecord.level == "ERROR",
            )
        )
        assert log is not None and "mock=FAILED" in log.message

        repo = ExecutionRepository(session)
        stat = repo.record_result_stat(
            workflow_instance_id=result.instance_id,
            task_instance_id=task.id,
            attempt_no=1,
            success_count=0,
            failed_count=1,
            skipped_count=0,
        )
        duplicate = repo.record_result_stat(
            workflow_instance_id=result.instance_id,
            task_instance_id=task.id,
            attempt_no=1,
            success_count=99,
            failed_count=99,
            skipped_count=0,
        )
        assert stat["recorded"] is True
        assert duplicate["duplicate"] is True
        session.commit()

        receipt = session.scalar(
            select(ExecutionEventRecord).where(
                ExecutionEventRecord.workflow_instance_id == result.instance_id,
                ExecutionEventRecord.event_kind == "RESULT_STAT",
            )
        )
        assert receipt is not None
        payload = json.loads(receipt.payload_json)
        assert payload["failed_count"] == 1


def test_failed_dependency_task_can_be_rerun_as_new_attempt():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repo = ExecutionRepository(session)
        instance = repo.create_workflow_instance(
            workflow_id=901,
            workflow_version_id=1,
            instance_type="FORMAL",
            trigger_type="MANUAL",
        )
        task = repo.create_task_instance(workflow_instance_id=instance.id, task_id="blocked_dependency")
        attempt = repo.append_attempt(task.id)
        repo.transition_workflow_instance(instance.id, "RUNNING")
        repo.transition_task_instance(task.id, "RUNNING")
        repo.transition_task_instance(task.id, "FAILED")
        repo.append_run_log(task_instance_id=task.id, attempt_no=attempt.attempt_no, message="dependency failed", level="ERROR")
        session.commit()

        # This mirrors the legacy rerun-failed command's contract: append an
        # isolated attempt and move the failed task back to PENDING.
        attempt = repo.append_attempt(task.id)
        task.status = "PENDING"
        task.started_at = None
        task.finished_at = None
        session.commit()

        refreshed = session.get(TaskInstanceRecord, task.id)
        assert refreshed is not None and refreshed.status == "PENDING"
        assert refreshed.current_attempt_no == 2
        retry = session.scalar(
            select(TaskAttemptRecord).where(
                TaskAttemptRecord.task_instance_id == task.id,
                TaskAttemptRecord.attempt_no == 2,
            )
        )
        assert retry is not None and retry.status == "PENDING"
