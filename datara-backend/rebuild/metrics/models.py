"""Persistence records for the R7 metrics domain.

Contract source (frozen): datara-web/src/services/rebuild/metricsApi.ts +
docs/increments/2026-10-17-R系列GREEN接线计划.md Task 5 契约面表 + design §9.

- The four statistic tables use the design-§9 names. Metric-valued columns
  (rows_in/rows_out/error_rows/elapsed_ms/row_count) store the A7 Step 1
  wrapper ``{value, known, estimated}`` verbatim as JSON — no FE or BE side
  derives those flags (known=false=unknown, estimated is an estimate).
- Every table carries DB-generated non-null created_at/updated_at (design §9
  timestamp requirement) plus its own query time column (run_date /
  captured_at / result_at / writeback_at).
- Sensitive/crypt: none — these are aggregate statistics, no raw payloads.
"""

from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base


class WorkflowResultStatRecord(Base):
    """workflow_result_stat — per workflow per run_date aggregate row."""

    __tablename__ = "workflow_result_stat"
    __table_args__ = (
        Index("ix_wrs_workflow_run_date", "workflow_id", "run_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workflow_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    run_date: Mapped[datetime] = mapped_column(Date, nullable=False, index=True)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # No shared metrics field covers retries (contract note: retryCount passthrough).
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())


class TaskInstanceDataStatRecord(Base):
    """task_instance_data_stat — per task-instance data-volume row."""

    __tablename__ = "task_instance_data_stat"
    __table_args__ = (
        Index("x_tids_instance", "instance_id", "task_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # MetricValue JSON {value, known, estimated} stored verbatim (A7 Step 1).
    rows_in: Mapped[str] = mapped_column(Text, nullable=False)
    rows_out: Mapped[str] = mapped_column(Text, nullable=False)
    error_rows: Mapped[str] = mapped_column(Text, nullable=False)
    elapsed_ms: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())


class TaskDataStatSegmentRecord(Base):
    """task_data_stat_segment — segmented row counts per instance."""

    __tablename__ = "task_data_stat_segment"
    __table_args__ = (
        Index("x_tdss_instance_key", "instance_id", "segment_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    segment_key: Mapped[str] = mapped_column(String(128), nullable=False)
    row_count: Mapped[str] = mapped_column(Text, nullable=False)  # MetricValue JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())


class TaskDataErrorSampleRecord(Base):
    """task_data_error_sample — captured error sample rows."""

    __tablename__ = "task_data_error_sample"
    __table_args__ = (
        Index("x_tdes_instance", "instance_id", "task_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    error_type: Mapped[str] = mapped_column(String(64), nullable=False)
    sample_data: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())


class QualityRuleResultLinkRecord(Base):
    """Quality rule result → statistics/alert-chain linkage."""

    __tablename__ = "quality_rule_result_link"
    __table_args__ = (
        Index("x_qrrl_rule", "rule_id", "result_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    rule_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    # Table + primary key reference to the stat record; passed through verbatim.
    stat_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    alert_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    result_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )


class LineageWritebackRecord(Base):
    """Run writeback lineage (SQL / sync / workflow runs)."""

    __tablename__ = "lineage_writeback"
    __table_args__ = (
        Index("x_lw_kind_time", "run_kind", "writeback_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    run_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_entity: Mapped[str] = mapped_column(String(256), nullable=False)
    target_entity: Mapped[str] = mapped_column(String(256), nullable=False)
    writeback_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )
