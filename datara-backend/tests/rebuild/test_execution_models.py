"""Schema contract checks for the six §9 execution tables."""

from sqlalchemy import UniqueConstraint

from rebuild.execution.models import (
    EXECUTION_TABLES,
    ExecutionEventRecord,
    RunLogRecord,
    RunOutputRecord,
    RunTimestampsMixin,
    TaskAttemptRecord,
    TaskInstanceRecord,
    WorkflowInstanceRecord,
)


def test_execution_models_cover_the_six_run_tables_and_db_timestamps():
    assert {table.name for table in EXECUTION_TABLES} == {
        "workflow_instance",
        "task_instance",
        "task_instance_attempt",
        "task_instance_log",
        "task_instance_output",
        "execution_event",
    }
    models = (
        WorkflowInstanceRecord,
        TaskInstanceRecord,
        TaskAttemptRecord,
        RunLogRecord,
        RunOutputRecord,
        ExecutionEventRecord,
    )
    for model in models:
        assert issubclass(model, RunTimestampsMixin)
        for name in ("created_at", "updated_at", "generated_at"):
            column = model.__table__.columns[name]
            assert column.nullable is False
            assert column.server_default is not None
            assert column.default is None


def test_attempt_log_output_and_event_constraints_and_indexes():
    attempt_constraints = [
        constraint
        for constraint in TaskAttemptRecord.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    ]
    assert any(tuple(column.name for column in constraint.columns) == ("task_instance_id", "attempt_no")
               for constraint in attempt_constraints)

    def has_index(model, columns):
        return any(tuple(column.name for column in index.columns) == columns for index in model.__table__.indexes)

    assert has_index(RunLogRecord, ("task_instance_id", "attempt_no"))
    assert has_index(RunOutputRecord, ("task_instance_id", "attempt_no"))
    assert has_index(ExecutionEventRecord, ("workflow_instance_id", "event_kind"))


def test_task_instance_has_runtime_timestamps_and_trial_binding_is_optional():
    assert "started_at" in TaskInstanceRecord.__table__.columns
    assert "finished_at" in TaskInstanceRecord.__table__.columns
    assert WorkflowInstanceRecord.__table__.columns["trial_snapshot_id"].nullable
    assert WorkflowInstanceRecord.__table__.columns["workflow_version_id"].nullable is False
