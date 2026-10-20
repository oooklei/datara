"""Persistent, immutable SQL result snapshots for R5-A pagination."""

from __future__ import annotations

import base64
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Sequence
from uuid import uuid4

from sqlalchemy import DateTime, Integer, JSON, String, select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base

RESULT_SNAPSHOT_TTL = timedelta(hours=24)
EXPORT_JOB_TTL = timedelta(hours=1)
DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 200  # A5 contract §2.2/§3#12: limit 1..200 (DEP-03 user ruling S109: unified 200)
# Deployment limits are provisional pending D8 per-profile measurement.
DEFAULT_EXPORT_MAX_ROWS = 100_000
DEFAULT_EXPORT_MAX_BYTES = 50 * 1024 * 1024


class SqlIdeResultSetRecord(Base):
    """One immutable result set, keyed by history and statement identity."""

    __tablename__ = "sql_ide_result_sets"
    result_set_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    history_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    stmt_index: Mapped[int] = mapped_column(Integer, nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    columns: Mapped[list] = mapped_column(JSON, nullable=False)
    rows: Mapped[list] = mapped_column(JSON, nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class SqlIdeExportJobRecord(Base):
    """Short-lived generic export task handles with measured size limits."""

    __tablename__ = "sql_ide_export_job_handles"

    export_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class PersistentResultPageStore:
    """SQLAlchemy-backed result snapshots; page reads never execute source SQL."""

    def __init__(self, *, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def save_snapshot(
        self,
        *,
        project_id: int,
        user_id: int,
        history_id: str,
        stmt_index: int,
        columns: Sequence[str],
        rows: Sequence[Sequence[Any]],
        total_rows: int | None = None,
        now: datetime | None = None,
    ) -> str:
        if not history_id or project_id < 0 or user_id < 0 or stmt_index < 0:
            raise ValueError("snapshot identity is invalid")
        stored_rows = [[_json_value(value) for value in row] for row in rows]
        if total_rows is not None and total_rows < len(stored_rows):
            raise ValueError("total_rows cannot be less than stored rows")
        current = _utc_naive(now or datetime.now(timezone.utc))
        record = SqlIdeResultSetRecord(
            result_set_id=str(uuid4()),
            history_id=history_id,
            stmt_index=stmt_index,
            project_id=project_id,
            user_id=user_id,
            columns=[str(column) for column in columns],
            rows=stored_rows,
            total_rows=total_rows if total_rows is not None else len(stored_rows),
            created_at=current,
            expires_at=current + RESULT_SNAPSHOT_TTL,
        )
        try:
            with self._session_factory() as session, session.begin():
                session.add(record)
                session.flush()
        except IntegrityError as exc:
            raise ValueError("result snapshot is immutable for this history statement") from exc
        return record.result_set_id

    def fetch_page(
        self,
        *,
        project_id: int,
        user_id: int,
        history_id: str,
        stmt_index: int | None = None,
        result_set_id: str | None = None,
        offset: int,
        limit: int = DEFAULT_PAGE_LIMIT,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not history_id or (result_set_id is None and stmt_index is None):
            raise ValueError("history_id and result_set_id or stmt_index are required")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if not 1 <= limit <= MAX_PAGE_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_PAGE_LIMIT}")
        current = _utc_naive(now or datetime.now(timezone.utc))
        with self._session_factory() as session:
            query = select(SqlIdeResultSetRecord).where(
                    SqlIdeResultSetRecord.project_id == project_id,
                    SqlIdeResultSetRecord.user_id == user_id,
                    SqlIdeResultSetRecord.history_id == history_id,
                )
            if result_set_id is not None:
                query = query.where(SqlIdeResultSetRecord.result_set_id == result_set_id)
            else:
                query = query.where(SqlIdeResultSetRecord.stmt_index == stmt_index)
            records = session.scalars(query.limit(2)).all()
            if len(records) > 1:
                raise LookupError("result snapshot identity is ambiguous")
            record = records[0] if records else None
            if record is None:
                # Same response for absent and cross-project/user resources.
                raise LookupError("result snapshot is not available")
            if record.expires_at <= current:
                raise LookupError("result snapshot expired")
            page_rows = record.rows[offset : offset + limit]
            return {
                "resultSetId": record.result_set_id,
                "columns": list(record.columns),
                "rows": page_rows,
                "page": {
                    "offset": offset,
                    "limit": limit,
                    "hasMore": offset + len(page_rows) < len(record.rows),
                },
                "totalRows": record.total_rows,
                "expiresAt": _iso_utc(record.expires_at),
            }

    def get_snapshot_meta(
        self,
        *,
        project_id: int,
        user_id: int,
        history_id: str,
        stmt_index: int | None = None,
        result_set_id: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = _utc_naive(now or datetime.now(timezone.utc))
        with self._session_factory() as session:
            query = select(SqlIdeResultSetRecord).where(
                    SqlIdeResultSetRecord.project_id == project_id,
                    SqlIdeResultSetRecord.user_id == user_id,
                    SqlIdeResultSetRecord.history_id == history_id,
                )
            if result_set_id is not None:
                query = query.where(SqlIdeResultSetRecord.result_set_id == result_set_id)
            elif stmt_index is not None:
                query = query.where(SqlIdeResultSetRecord.stmt_index == stmt_index)
            else:
                raise ValueError("history_id and result_set_id or stmt_index are required")
            records = session.scalars(query.limit(2)).all()
            if len(records) > 1:
                raise LookupError("result snapshot identity is ambiguous")
            record = records[0] if records else None
            if record is None:
                raise LookupError("result snapshot is not available")
            if record.expires_at <= current:
                raise LookupError("result snapshot expired")
            return {
                "resultSetId": record.result_set_id,
                "columns": list(record.columns),
                "totalRows": record.total_rows,
                "expiresAt": _iso_utc(record.expires_at),
            }

    def cleanup_expired(self, *, now: datetime | None = None) -> int:
        current = _utc_naive(now or datetime.now(timezone.utc))
        with self._session_factory() as session, session.begin():
            result = session.execute(
                delete(SqlIdeResultSetRecord).where(SqlIdeResultSetRecord.expires_at <= current)
            )
            return int(result.rowcount or 0)


class PersistentExportJobStore:
    """SQLAlchemy-backed export handles with fail-closed size limits."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Any],
        max_rows: int = DEFAULT_EXPORT_MAX_ROWS,
        max_bytes: int = DEFAULT_EXPORT_MAX_BYTES,
    ) -> None:
        if max_rows <= 0 or max_bytes <= 0:
            raise ValueError("export limits must be positive")
        self._session_factory = session_factory
        self.max_rows = max_rows
        self.max_bytes = max_bytes

    def create_job(
        self,
        *,
        project_id: int,
        user_id: int,
        task_id: str,
        format: str,
        row_count: int,
        byte_count: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not task_id or project_id < 0 or user_id < 0 or format not in {"csv", "json", "xlsx"}:
            raise ValueError("export job identity or format is invalid")
        if row_count < 0 or byte_count < 0:
            raise ValueError("export size cannot be negative")
        if row_count > self.max_rows or byte_count > self.max_bytes:
            raise ValueError("export limit exceeded")
        current = _utc_naive(now or datetime.now(timezone.utc))
        record = SqlIdeExportJobRecord(
            export_id=str(uuid4()),
            project_id=project_id,
            user_id=user_id,
            task_id=task_id,
            format=format,
            status="queued",
            row_count=row_count,
            byte_count=byte_count,
            created_at=current,
            expires_at=current + EXPORT_JOB_TTL,
        )
        try:
            with self._session_factory() as session, session.begin():
                session.add(record)
                session.flush()
                return _export_job_dict(record)
        except IntegrityError as exc:
            raise ValueError("export task already has a job") from exc

    def get_job(self, *, export_id: str, now: datetime | None = None) -> dict[str, Any]:
        current = _utc_naive(now or datetime.now(timezone.utc))
        with self._session_factory() as session:
            record = session.get(SqlIdeExportJobRecord, export_id)
            if record is None:
                raise LookupError("export job is not available")
            if record.expires_at <= current:
                raise LookupError("export job expired")
            return _export_job_dict(record)

    def cleanup_expired(self, *, before: str) -> int:
        cutoff = _utc_naive(datetime.fromisoformat(before.replace("Z", "+00:00")))
        with self._session_factory() as session, session.begin():
            result = session.execute(
                delete(SqlIdeExportJobRecord).where(SqlIdeExportJobRecord.expires_at <= cutoff)
            )
            return int(result.rowcount or 0)


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _iso_utc(value: datetime) -> str:
    return _utc_naive(value).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _export_job_dict(record: SqlIdeExportJobRecord) -> dict[str, Any]:
    return {
        "export_id": record.export_id,
        "project_id": record.project_id,
        "user_id": record.user_id,
        "task_id": record.task_id,
        "format": record.format,
        "status": record.status,
        "row_count": record.row_count,
        "byte_count": record.byte_count,
        "expires_at": _iso_utc(record.expires_at),
    }


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"$binary": base64.b64encode(value).decode("ascii")}
    raise TypeError(f"result value type is not JSON serializable: {type(value).__name__}")
