"""Persistence records for the R9 execution domain (run instances / attempts / logs / events).

Contract source (frozen): docs/increments/2026-10-14-datara-platform-rebuild-design.md
§9 (run-table roster + DB-generated timestamp contract + attempt_no isolation) +
§4.1/§4.2 (instance_type TRIAL/FORMAL/STREAM) + §13.3 (batch vs stream lifecycle
split) + 纠偏方案 §5.4 (result-stat idempotency; counts reported by the executor
result contract, never derived from logs).

- Six run tables: workflow_instance / task_instance / task_instance_attempt /
  task_instance_log / task_instance_output / execution_event. The §9 statistic
  tables (workflow_result_stat, task_instance_data_stat, ...) already live in
  the metrics domain — this module must not re-model them. task_instance_variable_runtime
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
- State machines: batch instances (TRIAL/FORMAL) have a finite lifecycle;
  STREAM instances are long-running and do not share batch completion semantics
  (no SUCCEEDED — §13.3). Task instances and attempts keep the batch lifecycle;
  stream job runtime state (heartbeat/checkpoint/offset) is the I8 stream-table
  slice.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base

INSTANCE_TYPES = ("TRIAL", "FORMAL", "STREAM")
TRIGGER_TYPES = ("MANUAL", "CRON", "DEPENDENCY", "EVENT", "TRIAL")

# Batch: finite lifecycle instance (design §13.3). PENDING may fail outright
# (submission/validation failure) or be canceled before it starts.
BATCH_TRANSITIONS = {
    "PENDING": {"RUNNING", "CANCELED", "FAILED"},
    "RUNNING": {"SUCCEEDED", "FAILED", "CANCELED"},
}
# Stream: long-running STREAM_JOB — start/stop/failure only, no batch completion.
STREAM_TRANSITIONS = {
    "PENDING": {"RUNNING", "FAILED"},
    "RUNNING": {"STOPPED", "FAILED"},
}
TERMINAL_STATUSES = frozenset({"SUCCEEDED", "FAILED", "CANCELED", "STOPPED"})


class RunTimestampsMixin:
    """The three §9 contract timestamps — DB-generated non-null, app never writes."""

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class WorkflowInstanceRecord(RunTimestampsMixin, Base):
    """workflow_instance — one workflow run (TRIAL / FORMAL / STREAM)."""

    __tablename__ = "workflow_instance"
    __table_args__ = (Index("x_wi_workflow_type", "workflow_id", "instance_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # Plain integer reference to the immutable workflow version — no workflow-domain import.
    workflow_version_id: Mapped[int] = mapped_column(Integer, nullable=False)
    instance_type: Mapped[str] = mapped_column(String(16), nullable=False)  # TRIAL | FORMAL | STREAM
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # §13.3 trigger kinds (MANUAL/CRON/DEPENDENCY/EVENT/TRIAL), when known at creation.
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
    __table_args__ = (Index("x_ee_instance_kind", "workflow_instance_id", "event_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_instance_id: Mapped[int] = mapped_column(Integer, nullable=False)
    task_instance_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_time: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
