"""Persistence records for the R8-STREAM stream domain.

Contract source (frozen): docs/increments/2026-10-14-datara-platform-rebuild-design.md
§8 (realtime observation chain, producer node modes, observation metrics)
+ §13.7 (stream runtime tables and the eight job states).

- Five domain tables per design §13.7: stream_job / stream_job_attempt /
  stream_checkpoint / stream_metric_snapshot / stream_failure_event. DEP-05
  user ruling (2026-10-19, 方案 A 独立建表): attempt slices persist in the
  independent stream_job_attempt table; stream_job.attempt_no remains only
  the current-attempt pointer so failure samples and snapshots stay
  attempt-attributed, and restart increments the attempt while opening a new
  stream_job_attempt row.
- stream_job carries the eight-state machine (CREATED/STARTING/RUNNING/PAUSED/
  STOPPING/STOPPED/FAILED/RECOVERING); legal transitions are enforced by the
  repository (see rebuild.stream.repository.STREAM_TRANSITIONS), not by triggers.
- runtime_config holds the §8 producer-node mode configuration verbatim as JSON
  (fixed_rate/random/abnormal/duplicate/delayed/out_of_order/burst) — no side
  derives or reinterprets the mode payload.
- Every table carries DB-generated non-null created_at/updated_at (design §9 /
  §13.13 timestamp contract); runtime rows add event_time for stream-time reads.
- Sensitive/crypt: none — checkpoints and samples are pipeline diagnostics.
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base


class StreamJobRecord(Base):
    """stream_job — one streaming job, independent of batch workflow instances."""

    __tablename__ = "stream_job"
    __table_args__ = (
        Index("x_stream_job_state", "state"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    workflow_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # Explicit crosswalk to legacy common.models.StreamJob.id. Nullable keeps
    # new-domain jobs independent; unique prevents ambiguous dual writes.
    legacy_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True, index=True)
    mq_topic: Mapped[str] = mapped_column(String(256), nullable=False)
    # §8 producer-node mode config stored verbatim as JSON.
    runtime_config: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # Eight-state machine (design §13.7); transition legality lives in the repository.
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="CREATED")
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )

class StreamJobAttemptRecord(Base):
    """stream_job_attempt — per-retry execution slice, isolated by attempt_no.

    DEP-05: Design §13.7 lists stream_job_attempt as one of five runtime tables.
    Implementation had folded attempt into stream_job.attempt_no counter (4+1 model).
    User ruling (2026-10-19, DEPLOY): 独立建表 (方案 A) — this independent table
    restores the design contract; every legal ``start`` transition opens a row
    and terminal transitions stamp its status/finished_at.
    """

    __tablename__ = "stream_job_attempt"
    __table_args__ = (
        UniqueConstraint("job_id", "attempt_no", name="uq_sja_job_attempt"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )


class StreamCheckpointRecord(Base):
    """stream_checkpoint — per-partition consumer offsets for failure recovery."""

    __tablename__ = "stream_checkpoint"
    __table_args__ = (
        Index("x_stream_ckpt_job_partition", "job_id", "partition_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    partition_id: Mapped[str] = mapped_column(String(128), nullable=False)
    offset_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Recovery payload (consumer group / processor state) stored verbatim as JSON.
    payload: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    event_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )


class StreamMetricSnapshotRecord(Base):
    """stream_metric_snapshot — one observation snapshot per job (design §8 metrics).

    Snapshot rows are point-in-time captures; observation aggregation reads the
    latest row in the window verbatim plus window-aggregated failure samples.
    """

    __tablename__ = "stream_metric_snapshot"
    __table_args__ = (
        Index("x_stream_snap_job_captured", "job_id", "captured_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Rates (records per second) and cumulative counters.
    produce_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consume_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    process_rate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    backlog: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    offset_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Window aggregation result (§8 窗口结果) stored verbatim as JSON.
    window_result: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )


class StreamFailureEventRecord(Base):
    """stream_failure_event — error sample rows for the observation page."""

    __tablename__ = "stream_failure_event"
    __table_args__ = (
        Index("x_stream_fail_job_time", "job_id", "event_time"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_type: Mapped[str] = mapped_column(String(64), nullable=False)
    sample_data: Mapped[str] = mapped_column(Text, nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )


class StreamRecoveryEventRecord(Base):
    """Recovery lifecycle events exposed by the stream observation API."""

    __tablename__ = "stream_recovery_event"
    __table_args__ = (Index("x_stream_recovery_job_time", "job_id", "event_time"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False, default="")
    event_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )


STREAM_TABLES = (
    StreamJobRecord.__table__,
    StreamJobAttemptRecord.__table__,
    StreamCheckpointRecord.__table__,
    StreamMetricSnapshotRecord.__table__,
    StreamFailureEventRecord.__table__,
    StreamRecoveryEventRecord.__table__,
)


