"""SQL IDE history and shared-script persistence.

History is private to its creator inside a project and is soft-deleted until the
retention window elapses. Scripts are shared by project members and updates use
revision compare-and-swap. Audit rows contain SQL digests, never SQL text.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, delete, or_, select, update
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base

HISTORY_TTL = timedelta(days=365)
HISTORY_TOMBSTONE_TTL = timedelta(days=30)
SCRIPT_TOMBSTONE_TTL = timedelta(days=30)
AUDIT_MIN_TTL = timedelta(days=365)


class SqlIdeHistoryRecord(Base):
    """One executed SQL history item."""

    __tablename__ = "sql_ide_history"

    history_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    datasource_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    db: Mapped[str | None] = mapped_column(String(256), nullable=True)
    sql_text: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    stmt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    elapsed_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class SqlIdeScriptRecord(Base):
    """Project-shared saved SQL; revision is incremented with CAS on writes."""

    __tablename__ = "sql_ide_scripts"

    script_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    sql_text: Mapped[str] = mapped_column(String, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_by: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class SqlIdeHistoryAuditRecord(Base):
    """Durable append-only audit metadata for history and script operations."""

    __tablename__ = "sql_ide_history_audit"

    audit_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    actor_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sql_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    retain_until: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class SqlIdeHistoryStore:
    """Persistence API for SQL history and project-shared scripts."""

    def __init__(self, *, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def create_history(
        self,
        *,
        project_id: int,
        user_id: int,
        datasource_id: int,
        db: str | None,
        sql_text: str,
        status: str,
        stmt_count: int,
        elapsed_ms: int,
        now: datetime | None = None,
    ) -> str:
        _validate_identity(project_id, user_id)
        if datasource_id < 0 or status not in {
            "succeeded", "failed", "partial_failure", "canceled", "timed_out"
        }:
            raise ValueError("history datasource or status is invalid")
        if not sql_text or stmt_count < 0 or elapsed_ms < 0:
            raise ValueError("history SQL and counters are invalid")
        current = _utc_naive(now or datetime.now(timezone.utc))
        history_id = str(uuid4())
        with self._session_factory() as session, session.begin():
            session.add(
                SqlIdeHistoryRecord(
                    history_id=history_id,
                    project_id=project_id,
                    user_id=user_id,
                    datasource_id=datasource_id,
                    db=db,
                    sql_text=sql_text,
                    status=status,
                    stmt_count=stmt_count,
                    elapsed_ms=elapsed_ms,
                    created_at=current,
                    expires_at=current + HISTORY_TTL,
                )
            )
            _append_audit(session, project_id, user_id, "history.created", history_id, sql_text, current)
        return history_id

    def list_history(
        self, *, project_id: int, user_id: int, datasource_id: int, limit: int = 100
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        with self._session_factory() as session:
            rows = session.scalars(
                select(SqlIdeHistoryRecord)
                .where(
                    SqlIdeHistoryRecord.project_id == project_id,
                    SqlIdeHistoryRecord.user_id == user_id,
                    SqlIdeHistoryRecord.datasource_id == datasource_id,
                    SqlIdeHistoryRecord.deleted_at.is_(None),
                    SqlIdeHistoryRecord.expires_at > _utc_naive(datetime.now(timezone.utc)),
                )
                .order_by(SqlIdeHistoryRecord.created_at.desc(), SqlIdeHistoryRecord.history_id.desc())
                .limit(limit)
            ).all()
            return [_history_dict(row) for row in rows]

    def delete_history(
        self, *, project_id: int, user_id: int, history_id: str, now: datetime | None = None
    ) -> bool:
        current = _utc_naive(now or datetime.now(timezone.utc))
        with self._session_factory() as session, session.begin():
            row = session.scalar(
                select(SqlIdeHistoryRecord).where(
                    SqlIdeHistoryRecord.history_id == history_id,
                    SqlIdeHistoryRecord.project_id == project_id,
                    SqlIdeHistoryRecord.user_id == user_id,
                    SqlIdeHistoryRecord.deleted_at.is_(None),
                )
            )
            if row is None:
                return False
            row.deleted_at = current
            row.expires_at = min(row.expires_at, current + HISTORY_TOMBSTONE_TTL)
            _append_audit(session, project_id, user_id, "history.deleted", history_id, row.sql_text, current)
            return True

    def get_history_record(self, *, history_id: str) -> SqlIdeHistoryRecord | None:
        with self._session_factory() as session:
            return session.get(SqlIdeHistoryRecord, history_id)

    def save_script(
        self,
        *,
        project_id: int,
        user_id: int,
        name: str,
        sql_text: str,
        script_id: str | None = None,
        expected_revision: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        _validate_identity(project_id, user_id)
        _validate_script(name, sql_text)
        current = _utc_naive(now or datetime.now(timezone.utc))
        with self._session_factory() as session, session.begin():
            if script_id is None:
                if expected_revision is not None:
                    raise ValueError("revision must be omitted when creating a script")
                script_id = str(uuid4())
                record = SqlIdeScriptRecord(
                    script_id=script_id,
                    project_id=project_id,
                    name=name.strip(),
                    sql_text=sql_text,
                    revision=1,
                    created_by=user_id,
                    updated_by=user_id,
                    created_at=current,
                    updated_at=current,
                    expires_at=None,
                )
                session.add(record)
                session.flush()
                _append_audit(session, project_id, user_id, "script.created", script_id, sql_text, current)
            else:
                if expected_revision is None or expected_revision < 1:
                    raise ValueError("expected revision is required for script updates")
                result = session.execute(
                    update(SqlIdeScriptRecord)
                    .where(
                        SqlIdeScriptRecord.script_id == script_id,
                        SqlIdeScriptRecord.project_id == project_id,
                        SqlIdeScriptRecord.revision == expected_revision,
                        or_(
                            SqlIdeScriptRecord.expires_at.is_(None),
                            SqlIdeScriptRecord.expires_at > current,
                        ),
                    )
                    .values(
                        name=name.strip(),
                        sql_text=sql_text,
                        revision=expected_revision + 1,
                        updated_by=user_id,
                        updated_at=current,
                        deleted_at=None,
                        expires_at=None,
                    )
                )
                if result.rowcount != 1:
                    raise ValueError("script revision conflict or script is unavailable")
                _append_audit(session, project_id, user_id, "script.updated", script_id, sql_text, current)
            record = session.get(SqlIdeScriptRecord, script_id)
            assert record is not None
            session.flush()
            return _script_dict(record)

    def list_scripts(self, *, project_id: int, user_id: int | None = None) -> list[dict[str, Any]]:
        del user_id  # Membership authorization is enforced at the service boundary.
        with self._session_factory() as session:
            rows = session.scalars(
                select(SqlIdeScriptRecord)
                .where(
                    SqlIdeScriptRecord.project_id == project_id,
                    SqlIdeScriptRecord.deleted_at.is_(None),
                )
                .order_by(SqlIdeScriptRecord.name, SqlIdeScriptRecord.script_id)
            ).all()
            return [_script_dict(row) for row in rows]

    def delete_script(
        self,
        *,
        project_id: int,
        user_id: int,
        script_id: str,
        expected_revision: int,
        now: datetime | None = None,
    ) -> bool:
        if expected_revision < 1:
            raise ValueError("expected revision must be positive")
        current = _utc_naive(now or datetime.now(timezone.utc))
        with self._session_factory() as session, session.begin():
            row = session.scalar(
                select(SqlIdeScriptRecord).where(
                    SqlIdeScriptRecord.script_id == script_id,
                    SqlIdeScriptRecord.project_id == project_id,
                    SqlIdeScriptRecord.revision == expected_revision,
                    SqlIdeScriptRecord.deleted_at.is_(None),
                )
            )
            if row is None:
                return False
            result = session.execute(
                update(SqlIdeScriptRecord)
                .where(
                    SqlIdeScriptRecord.script_id == script_id,
                    SqlIdeScriptRecord.project_id == project_id,
                    SqlIdeScriptRecord.revision == expected_revision,
                    SqlIdeScriptRecord.deleted_at.is_(None),
                )
                .values(
                    deleted_at=current,
                    revision=expected_revision + 1,
                    updated_by=user_id,
                    updated_at=current,
                    expires_at=current + SCRIPT_TOMBSTONE_TTL,
                )
            )
            if result.rowcount != 1:
                return False
            _append_audit(session, project_id, user_id, "script.deleted", script_id, row.sql_text, current)
            return True

    def get_script_record(self, *, script_id: str) -> SqlIdeScriptRecord | None:
        with self._session_factory() as session:
            return session.get(SqlIdeScriptRecord, script_id)

    def list_audit(self, *, project_id: int, limit: int = 200) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(SqlIdeHistoryAuditRecord)
                .where(SqlIdeHistoryAuditRecord.project_id == project_id)
                .order_by(SqlIdeHistoryAuditRecord.created_at, SqlIdeHistoryAuditRecord.audit_id)
                .limit(limit)
            ).all()
            return [_audit_dict(row) for row in rows]

    def get_audit_records(self, *, project_id: int) -> list[SqlIdeHistoryAuditRecord]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(SqlIdeHistoryAuditRecord).where(SqlIdeHistoryAuditRecord.project_id == project_id)
                ).all()
            )

    def cleanup_expired(self, *, now: datetime | None = None) -> int:
        current = _utc_naive(now or datetime.now(timezone.utc))
        with self._session_factory() as session, session.begin():
            history_result = session.execute(
                delete(SqlIdeHistoryRecord).where(SqlIdeHistoryRecord.expires_at <= current)
            )
            script_result = session.execute(
                delete(SqlIdeScriptRecord).where(
                    SqlIdeScriptRecord.deleted_at.is_not(None),
                    SqlIdeScriptRecord.expires_at <= current,
                )
            )
            return int(history_result.rowcount or 0) + int(script_result.rowcount or 0)


def _append_audit(session: Any, project_id: int, user_id: int, action: str, target_id: str,
                  sql_text: str, created_at: datetime) -> None:
    session.add(
        SqlIdeHistoryAuditRecord(
            audit_id=str(uuid4()),
            project_id=project_id,
            actor_user_id=user_id,
            action=action,
            target_id=target_id,
            sql_digest=hashlib.sha256(sql_text.encode("utf-8")).hexdigest(),
            created_at=created_at,
            retain_until=created_at + AUDIT_MIN_TTL,
        )
    )


def _validate_identity(project_id: int, user_id: int) -> None:
    if project_id < 0 or user_id < 0:
        raise ValueError("project and user identity must be non-negative")


def _validate_script(name: str, sql_text: str) -> None:
    if not name.strip() or len(name.strip()) > 256 or not sql_text.strip():
        raise ValueError("script name and SQL text are required")


def _history_dict(record: SqlIdeHistoryRecord) -> dict[str, Any]:
    return {
        "history_id": record.history_id,
        "datasource_id": record.datasource_id,
        "db": record.db,
        "sql_text": record.sql_text,
        "status": record.status,
        "stmt_count": record.stmt_count,
        "elapsed_ms": record.elapsed_ms,
        "created_at": _iso_utc(record.created_at),
    }


def _script_dict(record: SqlIdeScriptRecord) -> dict[str, Any]:
    return {
        "script_id": record.script_id,
        "name": record.name,
        "sql_text": record.sql_text,
        "revision": record.revision,
        "updated_at": _iso_utc(record.updated_at),
    }


def _audit_dict(record: SqlIdeHistoryAuditRecord) -> dict[str, Any]:
    return {
        "audit_id": record.audit_id,
        "project_id": record.project_id,
        "actor_user_id": record.actor_user_id,
        "action": record.action,
        "target_id": record.target_id,
        "sql_digest": record.sql_digest,
        "created_at": _iso_utc(record.created_at),
    }


def _utc_naive(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _iso_utc(value: datetime) -> str:
    return _utc_naive(value).replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
