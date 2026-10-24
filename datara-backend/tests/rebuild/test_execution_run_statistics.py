"""Execution-owned, log-independent per-attempt run statistics."""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.execution.models import EXECUTION_TABLES, WorkflowRunReconcileDetailRecord, WorkflowRunStatRecord
from rebuild.execution.repository import ExecutionDomainError, ExecutionRepository
from rebuild.execution.run_stats import RunStatisticsService
from rebuild.metrics.models import WorkflowResultStatRecord
from rebuild.workflow.models import WorkflowDefinitionRecord


def _context(instance_type="FORMAL"):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[WorkflowDefinitionRecord.__table__, *EXECUTION_TABLES,
                                            WorkflowResultStatRecord.__table__])
    session = Session(engine)
    definition = WorkflowDefinitionRecord(project_id=9, name="daily-sync", description="")
    session.add(definition)
    session.flush()
    repo = ExecutionRepository(session)
    instance = repo.create_workflow_instance(
        workflow_id=definition.id, workflow_version_id=7, instance_type=instance_type
    )
    return session, repo, instance


def test_retry_replaces_summary_and_replay_is_idempotent():
    session, repo, instance = _context()
    task = repo.create_task_instance(workflow_instance_id=instance.id, task_id="sync")
    first = repo.append_attempt(task.id)
    repo.transition_attempt(first.id, "RUNNING")
    payload = dict(workflow_instance_id=instance.id, task_instance_id=task.id,
                   attempt_no=first.attempt_no, success_count=8, failed_count=1, skipped_count=2,
                   source_count=12, target_count=11)
    assert repo.record_result_stat(**payload)["recorded"]
    assert repo.record_result_stat(**payload)["duplicate"]
    repo.transition_attempt(first.id, "FAILED")
    second = repo.append_attempt(task.id)
    repo.transition_attempt(second.id, "RUNNING")
    repo.record_result_stat(**{**payload, "attempt_no": second.attempt_no, "success_count": 10})
    repo.transition_attempt(second.id, "SUCCEEDED")
    repo.transition_workflow_instance(instance.id, "RUNNING")
    repo.transition_workflow_instance(instance.id, "SUCCEEDED")
    record = RunStatisticsService(session).finalize(instance.id)
    rows = list(session.scalars(select(WorkflowRunStatRecord)))
    assert rows == [record]
    assert (record.workflow_version_id, record.success_count, record.failure_count,
            record.skipped_count) == (7, 10, 1, 2)


def test_reconcile_detail_and_all_counts_reject_bool_or_negative():
    session, repo, instance = _context()
    task = repo.create_task_instance(workflow_instance_id=instance.id, task_id="sync")
    attempt = repo.append_attempt(task.id)
    base = dict(workflow_instance_id=instance.id, task_instance_id=task.id, attempt_no=attempt.attempt_no,
                success_count=1, failed_count=0, skipped_count=0)
    for field, value in (("source_count", True), ("target_count", -1)):
        with pytest.raises(ExecutionDomainError, match="non-negative integer"):
            repo.record_result_stat(**base, **{field: value})
    repo.record_result_stat(**base, reconcile_details=[{
        "source_object": "ods.orders", "target_object": "dwd.orders",
        "source_count": 2, "target_count": 1, "success_count": 1,
        "failure_count": 0, "skipped_count": 0,
    }])
    detail = session.scalar(select(WorkflowRunReconcileDetailRecord))
    assert detail is not None and detail.difference_count == -1


def test_stream_updates_are_monotonic_for_one_attempt():
    session, repo, instance = _context("STREAM")
    service = RunStatisticsService(session)
    service.upsert(instance, task_instance_id=None, attempt_no=0, source_count=5, target_count=5,
                   success_count=5, failure_count=0, skipped_count=0, stream_checkpoint=True)
    updated = service.upsert(instance, task_instance_id=None, attempt_no=0, source_count=8, target_count=8,
                             success_count=8, failure_count=0, skipped_count=0, stream_checkpoint=True)
    assert updated.success_count == 8
    with pytest.raises(ExecutionDomainError) as error:
        service.upsert(instance, task_instance_id=None, attempt_no=0, source_count=7, target_count=7,
                       success_count=7, failure_count=0, skipped_count=0, stream_checkpoint=True)
    assert error.value.code == 4109


def test_finalize_without_contributions_creates_zero_snapshot():
    session, repo, instance = _context()
    repo.transition_workflow_instance(instance.id, "RUNNING")
    repo.transition_workflow_instance(instance.id, "FAILED")
    record = RunStatisticsService(session).finalize(instance.id)
    assert (record.success_count, record.failure_count, record.total_count) == (0, 0, 0)


def test_none_details_preserves_existing_but_explicit_empty_clears():
    session, repo, instance = _context("STREAM")
    service = RunStatisticsService(session)
    details = [{"source_object": "s.t", "target_object": "d.t", "source_count": 1,
                "target_count": 1, "success_count": 1, "failure_count": 0}]
    common = dict(task_instance_id=None, attempt_no=0, source_count=1, target_count=1,
                  success_count=1, failure_count=0, skipped_count=0, stream_checkpoint=True)
    service.upsert(instance, **common, reconcile_details=details)
    service.upsert(instance, **common, reconcile_details=None)
    assert session.scalar(select(WorkflowRunReconcileDetailRecord)) is not None
    service.upsert(instance, **common, reconcile_details=[])
    assert session.scalar(select(WorkflowRunReconcileDetailRecord)) is None


def test_list_and_detail_are_project_scoped_and_do_not_read_logs():
    session, repo, instance = _context()
    repo.record_result_stat(workflow_instance_id=instance.id, attempt_no=0,
                            success_count=3, failed_count=1, skipped_count=0)
    service = RunStatisticsService(session)
    rows, total = service.list(9)
    assert total == 1 and rows[0].workflow_instance_id == instance.id
    assert service.get(rows[0].id, 9)[0].id == rows[0].id
    assert service.list(10) == ([], 0)
    with pytest.raises(ExecutionDomainError) as error:
        service.get(rows[0].id, 10)
    assert error.value.code == 4404
