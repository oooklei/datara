"""SQLAlchemy persistence for SQL IDE result snapshots and short-lived events."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping
from uuid import uuid4

from sqlalchemy import DateTime, JSON, String, delete
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base
from rebuild.sql_ide.result_store import PersistentExportJobStore as ExportJobStore
from rebuild.sql_ide.result_store import PersistentResultPageStore as ResultPageStore

EVENT_TTL = timedelta(days=7)


class SqlIdeEventRecord(Base):
    """Append-only event payload retained for seven days."""

    __tablename__ = "sql_ide_events"

    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class SqlIdeEventStore:
    """Append SQL IDE events and prune them only after their retention window."""

    def __init__(self, *, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def append(
        self,
        *,
        event_type: str,
        payload: Mapping[str, Any],
        now: datetime | None = None,
    ) -> str:
        if not event_type or len(event_type) > 128:
            raise ValueError("event_type is required and must be at most 128 characters")
        current = _utc_naive(now or datetime.now(timezone.utc))
        event_id = str(uuid4())
        record = SqlIdeEventRecord(
            event_id=event_id,
            event_type=event_type,
            payload=dict(payload),
            created_at=current,
            expires_at=current + EVENT_TTL,
        )
        with self._session_factory() as session, session.begin():
            session.add(record)
            session.flush()
        return event_id

    def cleanup_expired(self, *, now: datetime | None = None) -> int:
        current = _utc_naive(now or datetime.now(timezone.utc))
        with self._session_factory() as session, session.begin():
            result = session.execute(delete(SqlIdeEventRecord).where(SqlIdeEventRecord.expires_at <= current))
            return int(result.rowcount or 0)


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
