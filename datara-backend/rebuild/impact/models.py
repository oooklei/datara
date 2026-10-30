"""Persisted daily effects derived from dbx history."""

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base


class DailyImpactRecord(Base):
    __tablename__ = "daily_sql_impact"
    __table_args__ = (UniqueConstraint("project_id", "history_id", name="uq_daily_impact_project_history"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    history_id: Mapped[str] = mapped_column(String(128), nullable=False)
    connection_id: Mapped[str] = mapped_column(String(128), nullable=False)
    database: Mapped[str] = mapped_column(String(256), nullable=False)
    executed_at: Mapped[str] = mapped_column(String(64), nullable=False)
    success: Mapped[bool] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reads: Mapped[list] = mapped_column(JSON, nullable=False)
    writes: Mapped[list] = mapped_column(JSON, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class DailyImpactRunRecord(Base):
    __tablename__ = "daily_sql_impact_run"
    __table_args__ = (UniqueConstraint("project_id", "day", name="uq_daily_impact_run_project_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
