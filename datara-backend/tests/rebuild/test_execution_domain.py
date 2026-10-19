"""R9 execution-domain tests — design §9 run tables + 纠偏方案 §5.4 stat idempotency.

Covered: three-state instance creation (TRIAL/FORMAL/STREAM), legal/illegal
state transitions (batch vs stream machines), DB-generated timestamps (no
application-side writes), attempt_no isolated increment, attempt-scoped
log/output isolation, execution_event append, and the idempotent
record_result_stat write-back into the metrics workflow_result_stat aggregate.
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.execution.models import (
    ExecutionEventRecord,
    RunLogRecord,
    RunOutputRecord,
    TaskAttemptRecord,
    TaskInstanceRecord,
    WorkflowInstanceRecord,
)
from rebuild.execution.repository import RESULT_STAT_EVENT_KIND, ExecutionDomainError, ExecutionRepository
from rebuild.metrics.models import WorkflowResultStatRecord


def _repo():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    return ExecutionRepository(session), session


def _scalars(session, model):
    session.expire_all()
    return list(session.scalars(select(model)).all())


# ---- instance creation -------------------------------------------------------


def test_create_workflow_instance_accepts_three_types():
    repo, session = _repo()
    for expected in ("TRIAL", "FORMAL", "STREAM"):
        record = repo.create_workflow_instance(workflow_id=7, workflow_version_id=3, instance_type=expected)
        assert record.id is not None
        assert record.instance_type == expected and record.status == "PENDING"
    assert {row.instance_type for row in _scalars(session, WorkflowInstanceRecord)} == {"TRIAL", "FORMAL", "STREAM"}


def test_create_workflow_instance_rejects_unknown_type_and_trigger():
    repo, _session = _repo()
    with pytest.raises(ExecutionDomainError) as err:
        repo.create_workflow_instance(workflow_id=1, workflow_version_id=1, instance_type="DEBUG")
    assert err.value.code == 4101
    with pytest.raises(ExecutionDomainError):
        repo.create_workflow_instance(
            workflow_id=1, workflow_version_id=1, instance_type="FORMAL", trigger_type="TELEPORT"
        )


def test_workflow_version_id_is_plain_integer_column():
    repo, session = _repo()
    record = repo.create_workflow_instance(workflow_id=7, workflow_version_id=42, instance_type="TRIAL")
    assert record.workflow_version_id == 42
    column = WorkflowInstanceRecord.__table__.columns["workflow_version_id"]
    assert len(column.foreign_keys) == 0  # no cross-domain FK coupling


# ---- §9 timestamp contract ----------------------------------------------------


def test_run_table_contract_timestamps_are_db_generated():
    repo, session = _repo()
    instance = repo.create_workflow_instance(workflow_id=7, workflow_version_id=3, instance_type="FORMAL")
    task = repo.create_task_instance(workflow_instance_id=instance.id, task_id="sql_1")
    attempt = repo.append_attempt(task.id)
    log = repo.append_run_log(task_instance_id=task.id, attempt_no=attempt.attempt_no, message="hello")
    output = repo.append_run_output(task_instance_id=task.id, attempt_no=attempt.attempt_no, output_json='{"rows":1}')
    event = repo.append_execution_event(workflow_instance_id=instance.id, event_kind="SUBMITTED")

    session.expire_all()
    for record in (instance, task, attempt, log, output, event):
        assert record.created_at is not None and record.updated_at is not None and record.generated_at is not None
    assert event.event_time is not None
    # Execution-side stamps only appear on state transitions, never at insert.
    assert instance.started_at is None and instance.finished_at is None


# ---- state machines -------------------------------------------------------------


def test_batch_instance_legal_transitions_stamp_execution_times():
    repo, _session = _repo()
    instance = repo.create_workflow_instance(workflow_id=7, workflow_version_id=3, instance_type="FORMAL")
    assert instance.started_at is None and instance.finished_at is None

    repo.transition_workflow_instance(instance.id, "RUNNING")
    assert instance.status == "RUNNING" and instance.started_at is not None and instance.finished_at is None

    repo.transition_workflow_instance(instance.id, "SUCCEEDED")
    assert instance.status == "SUCCEEDED" and instance.finished_at is not None


def test_batch_instance_rejects_illegal_transitions():
    repo, _session = _repo()
    instance = repo.create_workflow_instance(workflow_id=7, workflow_version_id=3, instance_type="TRIAL")
    with pytest.raises(ExecutionDomainError) as err:
        repo.transition_workflow_instance(instance.id, "SUCCEEDED")
    assert err.value.code == 4103  # PENDING -> SUCCEEDED is not a legal batch move

    repo.transition_workflow_instance(instance.id, "RUNNING")
    repo.transition_workflow_instance(instance.id, "CANCELED")
    with pytest.raises(ExecutionDomainError):
        repo.transition_workflow_instance(instance.id, "RUNNING")  # terminal is terminal


def test_stream_instance_shuns_batch_completion_semantics():
    repo, _session = _repo()
    instance = repo.create_workflow_instance(workflow_id=7, workflow_version_id=3, instance_type="STREAM")
    repo.transition_workflow_instance(instance.id, "RUNNING")
    with pytest.raises(ExecutionDomainError):
        repo.transition_workflow_instance(instance.id, "SUCCEEDED")  # streams never "succeed" (§13.3)
    repo.transition_workflow_instance(instance.id, "STOPPED")
    assert instance.status == "STOPPED" and instance.finished_at is not None


def test_task_instance_lifecycle_and_attempt_pointer():
    repo, _session = _repo()
    instance = repo.create_workflow_instance(workflow_id=7, workflow_version_id=3, instance_type="FORMAL")
    task = repo.create_task_instance(workflow_instance_id=instance.id, task_id="sync_1")
    assert task.status == "PENDING" and task.current_attempt_no == 0

    repo.transition_task_instance(task.id, "RUNNING")
    repo.transition_task_instance(task.id, "FAILED")
    assert task.status == "FAILED" and task.started_at is not None and task.finished_at is not None

    attempt = repo.append_attempt(task.id)
    assert task.current_attempt_no == 1 and attempt.attempt_no == 1


# ---- attempts / logs / outputs / events -------------------------------------------


def test_attempt_no_isolated_increment():
    repo, session = _repo()
    instance = repo.create_workflow_instance(workflow_id=7, workflow_version_id=3, instance_type="FORMAL")
    task = repo.create_task_instance(workflow_instance_id=instance.id, task_id="shell_1")
    first = repo.append_attempt(task.id)
    repo.transition_attempt(first.id, "RUNNING")
    repo.transition_attempt(first.id, "FAILED")
    second = repo.append_attempt(task.id)
    repo.transition_attempt(second.id, "RUNNING")
    repo.transition_attempt(second.id, "SUCCEEDED")

    assert (first.attempt_no, second.attempt_no) == (1, 2)
    assert task.current_attempt_no == 2
    attempts = _scalars(session, TaskAttemptRecord)
    assert sorted(a.attempt_no for a in attempts) == [1, 2]  # isolated rows, never merged
    by_no = {a.attempt_no: a.status for a in attempts}
    assert by_no == {1: "FAILED", 2: "SUCCEEDED"}  # statuses tracked per attempt


def test_run_logs_and_outputs_are_attempt_scoped():
    repo, session = _repo()
    instance = repo.create_workflow_instance(workflow_id=7, workflow_version_id=3, instance_type="TRIAL")
    task = repo.create_task_instance(workflow_instance_id=instance.id, task_id="python_1")
    attempt_one = repo.append_attempt(task.id)
    attempt_two = repo.append_attempt(task.id)

    repo.append_run_log(
        task_instance_id=task.id, attempt_no=attempt_one.attempt_no, message="first try", level="WARN"
    )
    repo.append_run_log(task_instance_id=task.id, attempt_no=attempt_two.attempt_no, message="second try")
    repo.append_run_output(
        task_instance_id=task.id, attempt_no=attempt_one.attempt_no, output_json='{"attempt":1}'
    )
    repo.append_run_output(
        task_instance_id=task.id, attempt_no=attempt_two.attempt_no, output_json='{"attempt":2}'
    )

    logs_one = session.scalars(
        select(RunLogRecord).where(RunLogRecord.task_instance_id == task.id, RunLogRecord.attempt_no == 1)
    ).all()
    assert [log.message for log in logs_one] == ["first try"] and logs_one[0].level == "WARN"
    outputs_two = session.scalars(
        select(RunOutputRecord).where(RunOutputRecord.task_instance_id == task.id, RunOutputRecord.attempt_no == 2)
    ).all()
    assert [row.output_json for row in outputs_two] == ['{"attempt":2}']  # verbatim passthrough


def test_log_and_output_writes_require_existing_attempt_and_valid_payload():
    repo, _session = _repo()
    instance = repo.create_workflow_instance(workflow_id=7, workflow_version_id=3, instance_type="FORMAL")
    task = repo.create_task_instance(workflow_instance_id=instance.id, task_id="sql_2")

    with pytest.raises(ExecutionDomainError) as err:
        repo.append_run_log(task_instance_id=task.id, attempt_no=9, message="orphan")
    assert err.value.code == 4404  # attempt must exist first (isolation is real, not decorative)
    with pytest.raises(ExecutionDomainError):
        repo.append_run_output(task_instance_id=task.id, attempt_no=1, output_json="")
    with pytest.raises(ExecutionDomainError):
        repo.append_run_log(task_instance_id=task.id, attempt_no=1, message="x", level="LOUD")


def test_execution_event_append_and_event_time_db_generated():
    repo, session = _repo()
    instance = repo.create_workflow_instance(workflow_id=7, workflow_version_id=3, instance_type="STREAM")
    event = repo.append_execution_event(
        workflow_instance_id=instance.id, event_kind="CHECKPOINT", payload_json='{"offset":42}'
    )
    session.expire_all()
    assert event.event_kind == "CHECKPOINT" and event.payload_json == '{"offset":42}'
    assert event.event_time is not None  # DB-generated, not application-stamped
    assert event.task_instance_id is None and event.attempt_no is None


# ---- result-stat write-back contract (纠偏方案 §5.4) --------------------------------


def test_record_result_stat_accumulates_into_metrics_aggregate():
    repo, session = _repo()
    instance = repo.create_workflow_instance(workflow_id=7, workflow_version_id=3, instance_type="FORMAL")
    task = repo.create_task_instance(workflow_instance_id=instance.id, task_id="sync_1")
    attempt = repo.append_attempt(task.id)

    result = repo.record_result_stat(
        workflow_instance_id=instance.id,
        task_instance_id=task.id,
        attempt_no=attempt.attempt_no,
        success_count=10,
        failed_count=2,
        skipped_count=1,
    )
    assert result["recorded"] is True and result["duplicate"] is False
    (aggregate,) = _scalars(session, WorkflowResultStatRecord)
    assert aggregate.workflow_id == 7
    assert (aggregate.success_count, aggregate.failure_count, aggregate.skipped_count) == (10, 2, 1)


def test_record_result_stat_is_idempotent_per_instance_task_attempt():
    repo, session = _repo()
    instance = repo.create_workflow_instance(workflow_id=7, workflow_version_id=3, instance_type="FORMAL")
    task = repo.create_task_instance(workflow_instance_id=instance.id, task_id="sync_1")
    attempt = repo.append_attempt(task.id)
    payload = dict(
        workflow_instance_id=instance.id, task_instance_id=task.id, attempt_no=attempt.attempt_no
    )

    assert repo.record_result_stat(**payload, success_count=10, failed_count=2, skipped_count=1)["recorded"]
    replay = repo.record_result_stat(**payload, success_count=10, failed_count=2, skipped_count=1)
    assert replay["recorded"] is False and replay["duplicate"] is True

    (aggregate,) = _scalars(session, WorkflowResultStatRecord)  # repeated write must not re-accumulate
    assert (aggregate.success_count, aggregate.failure_count, aggregate.skipped_count) == (10, 2, 1)
    receipts = _scalars(session, ExecutionEventRecord)
    assert [row.event_kind for row in receipts] == [RESULT_STAT_EVENT_KIND]  # exactly one receipt


def test_record_result_stat_distinct_attempts_accumulate_separately():
    repo, session = _repo()
    instance = repo.create_workflow_instance(workflow_id=7, workflow_version_id=3, instance_type="FORMAL")
    task = repo.create_task_instance(workflow_instance_id=instance.id, task_id="sync_1")
    first = repo.append_attempt(task.id)
    second = repo.append_attempt(task.id)

    repo.record_result_stat(
        workflow_instance_id=instance.id, task_instance_id=task.id, attempt_no=first.attempt_no,
        success_count=10, failed_count=0, skipped_count=0,
    )
    repo.record_result_stat(
        workflow_instance_id=instance.id, task_instance_id=task.id, attempt_no=second.attempt_no,
        success_count=3, failed_count=5, skipped_count=2,
    )
    (aggregate,) = _scalars(session, WorkflowResultStatRecord)
    # Retries stay traceable per attempt (§9) and the aggregate never double counts one attempt.
    assert (aggregate.success_count, aggregate.failure_count, aggregate.skipped_count) == (13, 5, 2)


def test_record_result_stat_task_level_and_workflow_level_are_independent():
    repo, session = _repo()
    instance = repo.create_workflow_instance(workflow_id=7, workflow_version_id=3, instance_type="FORMAL")
    task = repo.create_task_instance(workflow_instance_id=instance.id, task_id="sync_1")
    attempt = repo.append_attempt(task.id)

    repo.record_result_stat(
        workflow_instance_id=instance.id, task_instance_id=task.id, attempt_no=attempt.attempt_no,
        success_count=4, failed_count=1, skipped_count=0,
    )
    workflow_level = repo.record_result_stat(
        workflow_instance_id=instance.id, task_instance_id=None, attempt_no=attempt.attempt_no,
        success_count=4, failed_count=1, skipped_count=0,
    )
    assert workflow_level["recorded"] is True  # NULL task slot is its own idempotency slot
    (aggregate,) = _scalars(session, WorkflowResultStatRecord)
    assert (aggregate.success_count, aggregate.failure_count) == (8, 2)


def test_record_result_stat_rejects_invalid_counts():
    repo, _session = _repo()
    instance = repo.create_workflow_instance(workflow_id=7, workflow_version_id=3, instance_type="FORMAL")
    for bad in (-1, "3", 1.5, True):
        with pytest.raises(ExecutionDomainError) as err:
            repo.record_result_stat(
                workflow_instance_id=instance.id, attempt_no=1,
                success_count=bad, failed_count=0, skipped_count=0,
            )
        assert err.value.code == 4107  # counts come from the executor contract, strictly validated
