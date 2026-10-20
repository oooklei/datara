"""Persistent execution status and event history for the SQL IDE."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, delete, or_, select, update
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base

EXECUTION_STATUS_TTL = timedelta(days=365)
EXECUTION_EVENT_TTL = timedelta(days=7)
TERMINAL_STATUSES = frozenset({"succeeded", "failed", "partial_failure", "canceled", "timed_out"})


class SqlIdeExecutionRecord(Base):
    """Execution status, isolated by project and user for its full lifetime."""

    __tablename__ = "sql_ide_execution_status"

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class SqlIdeExecutionEventRecord(Base):
    """Execution event metadata retained through terminal time plus seven days."""

    __tablename__ = "sql_ide_execution_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sql_ide_execution_status.task_id"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class SqlIdeStatusStore:
    """Store execution state and query it without crossing owner boundaries."""

    def __init__(self, *, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def start_execution(
        self,
        *,
        task_id: str | None = None,
        project_id: int,
        user_id: int,
        status: str,
        now: datetime | None = None,
    ) -> str:
        _validate_identity(project_id, user_id)
        if not status or len(status) > 32:
            raise ValueError("status is required and must be at most 32 characters")
        current = _utc_naive(now or datetime.now(timezone.utc))
        task_id = task_id or str(uuid4())
        with self._session_factory() as session, session.begin():
            session.add(
                SqlIdeExecutionRecord(
                    task_id=task_id,
                    project_id=project_id,
                    user_id=user_id,
                    status=status,
                    created_at=current,
                    updated_at=current,
                    terminal_at=current if status in TERMINAL_STATUSES else None,
                    expires_at=current + EXECUTION_STATUS_TTL,
                )
            )
        return task_id

    def update_status(
        self,
        *,
        task_id: str,
        project_id: int,
        user_id: int,
        status: str,
        now: datetime | None = None,
    ) -> bool:
        _validate_identity(project_id, user_id)
        if not status or len(status) > 32:
            raise ValueError("status is required and must be at most 32 characters")
        current = _utc_naive(now or datetime.now(timezone.utc))
        with self._session_factory() as session, session.begin():
            result = session.execute(
                update(SqlIdeExecutionRecord)
                .where(
                    SqlIdeExecutionRecord.task_id == task_id,
                    SqlIdeExecutionRecord.project_id == project_id,
                    SqlIdeExecutionRecord.user_id == user_id,
                    SqlIdeExecutionRecord.terminal_at.is_(None),
                    SqlIdeExecutionRecord.expires_at > current,
                )
                .values(
                    status=status,
                    updated_at=current,
                    terminal_at=current if status in TERMINAL_STATUSES else None,
                )
            )
            changed = result.rowcount == 1
            if changed and status in TERMINAL_STATUSES:
                session.execute(
                    update(SqlIdeExecutionEventRecord)
                    .where(
                        SqlIdeExecutionEventRecord.task_id == task_id,
                        SqlIdeExecutionEventRecord.project_id == project_id,
                        SqlIdeExecutionEventRecord.user_id == user_id,
                        SqlIdeExecutionEventRecord.expires_at.is_(None),
                    )
                    .values(expires_at=current + EXECUTION_EVENT_TTL)
                )
            return changed

    def get_execution_status(
        self,
        *,
        task_id: str,
        project_id: int,
        user_id: int,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        _validate_identity(project_id, user_id)
        current = _utc_naive(now or datetime.now(timezone.utc))
        with self._session_factory() as session:
            record = session.scalar(
                select(SqlIdeExecutionRecord).where(
                    SqlIdeExecutionRecord.task_id == task_id,
                    SqlIdeExecutionRecord.project_id == project_id,
                    SqlIdeExecutionRecord.user_id == user_id,
                    SqlIdeExecutionRecord.expires_at > current,
                )
            )
            if record is None:
                return None
            return {
                "task_id": record.task_id,
                "status": record.status,
                "created_at": _iso_utc(record.created_at),
                "updated_at": _iso_utc(record.updated_at),
            }

    def append_event(
        self,
        *,
        task_id: str,
        project_id: int,
        user_id: int,
        event_type: str,
        payload: Mapping[str, Any],
        now: datetime | None = None,
    ) -> str | None:
        _validate_identity(project_id, user_id)
        if not event_type or len(event_type) > 128:
            raise ValueError("event_type is required and must be at most 128 characters")
        current = _utc_naive(now or datetime.now(timezone.utc))
        event_id = str(uuid4())
        with self._session_factory() as session, session.begin():
            owner = session.scalar(
                select(SqlIdeExecutionRecord).where(
                    SqlIdeExecutionRecord.task_id == task_id,
                    SqlIdeExecutionRecord.project_id == project_id,
                    SqlIdeExecutionRecord.user_id == user_id,
                    SqlIdeExecutionRecord.expires_at > current,
                )
            )
            if owner is None:
                return None
            event_expires_at = (
                owner.terminal_at + EXECUTION_EVENT_TTL if owner.terminal_at is not None else None
            )
            if event_expires_at is not None and event_expires_at <= current:
                return None
            session.add(
                SqlIdeExecutionEventRecord(
                    event_id=event_id,
                    task_id=task_id,
                    project_id=project_id,
                    user_id=user_id,
                    event_type=event_type,
                    payload=dict(payload),
                    created_at=current,
                    expires_at=event_expires_at,
                )
            )
        return event_id

    def list_execution_events(
        self,
        *,
        task_id: str,
        project_id: int,
        user_id: int,
        limit: int = 100,
        offset: int = 0,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        _validate_identity(project_id, user_id)
        if not 1 <= limit <= 200 or offset < 0:
            raise ValueError("limit must be between 1 and 200 and offset must be non-negative")
        current = _utc_naive(now or datetime.now(timezone.utc))
        with self._session_factory() as session:
            rows = session.scalars(
                select(SqlIdeExecutionEventRecord)
                .join(
                    SqlIdeExecutionRecord,
                    SqlIdeExecutionRecord.task_id == SqlIdeExecutionEventRecord.task_id,
                )
                .where(
                    SqlIdeExecutionRecord.task_id == task_id,
                    SqlIdeExecutionRecord.project_id == project_id,
                    SqlIdeExecutionRecord.user_id == user_id,
                    SqlIdeExecutionRecord.expires_at > current,
                    SqlIdeExecutionEventRecord.project_id == project_id,
                    SqlIdeExecutionEventRecord.user_id == user_id,
                    or_(
                        SqlIdeExecutionEventRecord.expires_at.is_(None),
                        SqlIdeExecutionEventRecord.expires_at > current,
                    ),
                )
                .order_by(SqlIdeExecutionEventRecord.created_at, SqlIdeExecutionEventRecord.event_id)
                .offset(offset)
                .limit(limit)
            ).all()
            return [
                {
                    "event_id": row.event_id,
                    "event_type": row.event_type,
                    "payload": row.payload,
                    "created_at": _iso_utc(row.created_at),
                }
                for row in rows
            ]

    def get_execution_record(
        self, *, task_id: str, project_id: int, user_id: int
    ) -> SqlIdeExecutionRecord | None:
        _validate_identity(project_id, user_id)
        with self._session_factory() as session:
            return session.scalar(
                select(SqlIdeExecutionRecord).where(
                    SqlIdeExecutionRecord.task_id == task_id,
                    SqlIdeExecutionRecord.project_id == project_id,
                    SqlIdeExecutionRecord.user_id == user_id,
                )
            )

    def cleanup_expired(self, *, now: datetime | None = None) -> int:
        current = _utc_naive(now or datetime.now(timezone.utc))
        with self._session_factory() as session, session.begin():
            events = session.execute(
                delete(SqlIdeExecutionEventRecord).where(
                    SqlIdeExecutionEventRecord.expires_at <= current
                )
            )
            executions = session.execute(
                delete(SqlIdeExecutionRecord).where(SqlIdeExecutionRecord.expires_at <= current)
            )
            return int(events.rowcount or 0) + int(executions.rowcount or 0)


def _validate_identity(project_id: int, user_id: int) -> None:
    if project_id < 0 or user_id < 0:
        raise ValueError("project and user identity must be non-negative")


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _iso_utc(value: datetime) -> str:
    return _utc_naive(value).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
