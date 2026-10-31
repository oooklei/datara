"""Persistence records for the R9 execution domain (run instances / attempts / logs / events).

Contract source (frozen): docs/designs/2026-10-29-dbx-unified-target-design.md
§9 (run-table roster + DB-generated timestamp contract + attempt_no isolation) +
§4.1/§4.2 (instance_type FORMAL/STREAM; the legacy TRIAL 试运行 domain was
retired — 海豚 has no 试运行, its canvas 空跑 is DS dryRun=1) + §13.3 (batch vs
stream lifecycle split) + 纠偏方案 §5.4 (result-stat idempotency; counts reported
by the executor result contract, never derived from logs).

- Six original run tables plus the execution-owned workflow_run_stat and
  workflow_run_reconcile_detail result records. Historical aggregates
  (workflow_result_stat, task_instance_data_stat, ...) remain in the metrics
  domain and are not duplicated here. task_instance_variable_runtime
  belongs to the variables-domain runtime slice and is out of scope here.
- Every table carries the three DB-generated non-null contract timestamps
  created_at/updated_at/generated_at (server_default only; application code is
  forbidden from writing them). Execution-side extra columns (§9):
  started_at/finished_at are stamped by repository transitions with SQL-side
  CURRENT_TIMESTAMP (still database-generated, never a Python datetime);
  execution_event carries event_time the same way; attempt_no lives on
  task_instance_attempt (unique per task_instance) and denormalizes onto
  task_instance.current_attempt_no.
- workflow_version_id is a plain integer column reference — no import from the
  workflow domain (cross-domain decoupling).
- State machines: batch instances (FORMAL) have a finite lifecycle;
  STREAM instances are long-running and do not share batch completion semantics
  (no SUCCEEDED — §13.3). Task instances and attempts keep the batch lifecycle;
  stream job runtime state (heartbeat/checkpoint/offset) is the I8 stream-table
  slice.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base

INSTANCE_TYPES = ("FORMAL", "STREAM")
TRIGGER_TYPES = ("MANUAL", "CRON", "DEPENDENCY", "EVENT")

# Batch: finite lifecycle instance (design §13.3). PENDING may fail outright
# (submission/validation failure) or be canceled before it starts.
# SKIPPED is a distinct terminal state for nodes excluded from execution
# (WF-27): the task was never attempted, not failed.
BATCH_TRANSITIONS = {
    # CANCELED is retained as a legacy API spelling.  New execution APIs use
    # CANCELLED, but the legacy instances facade must remain wire-compatible.
    "PENDING": {"RUNNING", "CANCELLED", "CANCELED", "CANCEL_FAILED", "FAILED", "SKIPPED"},
    "RUNNING": {"SUCCEEDED", "FAILED", "CANCELLED", "CANCELED", "CANCEL_FAILED"},
}
# Stream: long-running STREAM_JOB — start/stop/failure only, no batch completion.
STREAM_TRANSITIONS = {
    "PENDING": {"RUNNING", "FAILED"},
    "RUNNING": {"STOPPED", "FAILED"},
}
TERMINAL_STATUSES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED", "CANCELED", "CANCEL_FAILED", "STOPPED", "SKIPPED"})


class RunTimestampsMixin:
    """The three §9 contract timestamps — DB-generated non-null, app never writes."""

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class WorkflowInstanceRecord(RunTimestampsMixin, Base):
    """workflow_instance — one workflow run (FORMAL / STREAM)."""

    __tablename__ = "workflow_instance"
    __table_args__ = (Index("x_wi_workflow_type", "workflow_id", "instance_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # Plain integer reference to the immutable workflow version — no workflow-domain import.
    workflow_version_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Legacy column retained for pre-retirement rows only; the 试运行(trial)
    # domain is retired and no execution writes this value any more.
    trial_snapshot_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    instance_type: Mapped[str] = mapped_column(String(16), nullable=False)  # FORMAL | STREAM
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # §13.3 trigger kinds (MANUAL/CRON/DEPENDENCY/EVENT), when known at creation.
    trigger_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TaskInstanceRecord(RunTimestampsMixin, Base):
    """task_instance — one task within a workflow run; reruns are attempts."""

    __tablename__ = "task_instance"
    __table_args__ = (UniqueConstraint("workflow_instance_id", "task_id", name="uq_ti_instance_task"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_instance_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # Denormalized pointer to the latest attempt (0 = none appended yet).
    current_attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TaskAttemptRecord(RunTimestampsMixin, Base):
    """task_instance_attempt — per-retry execution slice, isolated by attempt_no."""

    __tablename__ = "task_instance_attempt"
    __table_args__ = (UniqueConstraint("task_instance_id", "attempt_no", name="uq_tia_task_attempt"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_instance_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RunLogRecord(RunTimestampsMixin, Base):
    """task_instance_log — diagnostic log lines, attempt-scoped (not a stat source)."""

    __tablename__ = "task_instance_log"
    __table_args__ = (Index("x_til_task_attempt", "task_instance_id", "attempt_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_instance_id: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)


class RunOutputRecord(RunTimestampsMixin, Base):
    """task_instance_output — executor output payload, attempt-scoped, verbatim."""

    __tablename__ = "task_instance_output"
    __table_args__ = (Index("x_tio_task_attempt", "task_instance_id", "attempt_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_instance_id: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    # Executor output stored verbatim (JSON passthrough, no derivation).
    output_json: Mapped[str] = mapped_column(Text, nullable=False)


class ExecutionEventRecord(RunTimestampsMixin, Base):
    """execution_event — append-only run event stream; doubles as the §5.4 stat receipt."""

    __tablename__ = "execution_event"
    __table_args__ = (
        Index("x_ee_instance_kind", "workflow_instance_id", "event_kind"),
        UniqueConstraint(
            "workflow_instance_id",
            "receipt_identity",
            "attempt_no",
            "event_kind",
            name="uq_ee_result_receipt",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_instance_id: Mapped[int] = mapped_column(Integer, nullable=False)
    task_instance_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # A non-null identity closes the NULL-distinct loophole for workflow-level
    # RESULT_STAT receipts (``__workflow__``); task receipts use ``task:<id>``.
    receipt_identity: Mapped[str] = mapped_column(String(64), nullable=False, server_default="__workflow__")
    attempt_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class WorkflowRunStatRecord(RunTimestampsMixin, Base):
    """Log-independent executor result for one workflow/task attempt."""

    __tablename__ = "workflow_run_stat"
    __table_args__ = (
        UniqueConstraint("workflow_instance_id", name="uq_wrs_workflow_instance"),
        Index("x_wrs_project_created", "project_id", "created_at"),
        Index("x_wrs_workflow_started", "workflow_id", "started_at"),
        Index("x_wrs_type_started", "instance_type", "started_at"),
        CheckConstraint("success_count >= 0", name="ck_wrs_success_nonnegative"),
        CheckConstraint("failure_count >= 0", name="ck_wrs_failure_nonnegative"),
        CheckConstraint("skipped_count >= 0", name="ck_wrs_skipped_nonnegative"),
        CheckConstraint("total_count = success_count + failure_count", name="ck_wrs_total_consistent"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    workflow_id: Mapped[int] = mapped_column(Integer, nullable=False)
    workflow_version_id: Mapped[int] = mapped_column(Integer, nullable=False)
    workflow_instance_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_instance.id", ondelete="CASCADE"), nullable=False
    )
    instance_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    dag_name: Mapped[str] = mapped_column(String(256), nullable=False)
    data_param_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    success_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    failure_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    skipped_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    total_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WorkflowRunReconcileDetailRecord(RunTimestampsMixin, Base):
    """Optional source/target object reconciliation for a run-stat attempt."""

    __tablename__ = "workflow_run_reconcile_detail"
    __table_args__ = (
        UniqueConstraint("run_stat_id", "source_object", "target_object", name="uq_wrrd_object_pair"),
        Index("x_wrrd_run_stat", "run_stat_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_stat_id: Mapped[int] = mapped_column(ForeignKey("workflow_run_stat.id", ondelete="CASCADE"), nullable=False)
    source_object: Mapped[str] = mapped_column(String(256), nullable=False)
    target_object: Mapped[str] = mapped_column(String(256), nullable=False)
    source_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    success_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    failure_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    skipped_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    difference_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    data_param_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


EXECUTION_TABLES = (
    WorkflowInstanceRecord.__table__,
    TaskInstanceRecord.__table__,
    TaskAttemptRecord.__table__,
    RunLogRecord.__table__,
    RunOutputRecord.__table__,
    ExecutionEventRecord.__table__,
    WorkflowRunStatRecord.__table__,
    WorkflowRunReconcileDetailRecord.__table__,
)
