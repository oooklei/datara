"""R5-A production AuditWriter (Track A Gap 3).

DB-backed audit writer that persists SQL execution audit records to the
rebuild database via SQLAlchemy ORM. Replaces the PoC SQLite writer.

Satisfies the AuditWriter Protocol (rebuild.sql_ide.contracts):
- write_execution_start: persists a "running" record, returns audit_id
- write_execution_end: updates the record with final status/elapsed/error

Design input: docs/increments/2026-10-18-P2-2-R5-A-SQL-IDE后端设计草案.md §9.
Supervisor dispatch: #263 Track A / #265 domain boundary ruling.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base


class SqlIdeAuditRecord(Base):
    """DB-backed audit record for SQL IDE execution."""

    __tablename__ = "rebuild_sql_ide_audit"

    audit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, index=True)
    user_id: Mapped[int] = mapped_column(Integer)
    datasource_id: Mapped[int] = mapped_column(Integer)
    sql_digest: Mapped[str] = mapped_column(String(64))
    task_id: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="running")
    stmt_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: _now_shanghai())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: _now_shanghai(), onupdate=lambda: _now_shanghai()
    )


def _now_shanghai() -> datetime:
    return datetime.now().replace(tzinfo=None)


class DbBackedAuditWriter:
    """Production audit writer backed by rebuild DB.

    Persists audit records via session_factory -> SQLAlchemy Session.
    write_execution_start inserts a "running" record;
    write_execution_end updates it with final status.
    """

    def __init__(self, *, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def write_execution_start(
        self,
        *,
        project_id: int,
        user_id: int,
        datasource_id: int,
        sql_digest: str,
        task_id: str,
    ) -> str:
        audit_id = uuid4().hex
        with self._session_factory() as session:
            record = SqlIdeAuditRecord(
                audit_id=audit_id,
                project_id=project_id,
                user_id=user_id,
                datasource_id=datasource_id,
                sql_digest=sql_digest,
                task_id=task_id,
                status="running",
            )
            session.add(record)
            session.commit()
        return audit_id

    def write_execution_end(
        self,
        *,
        audit_id: str,
        status: str,
        stmt_count: int,
        elapsed_ms: int,
        error_code: str | None = None,
    ) -> None:
        with self._session_factory() as session:
            record = session.query(SqlIdeAuditRecord).filter(
                SqlIdeAuditRecord.audit_id == audit_id
            ).first()
            if record is None:
                raise RuntimeError(f"audit record {audit_id} not found")
            record.status = status
            record.stmt_count = stmt_count
            record.elapsed_ms = elapsed_ms
            record.error_code = error_code
            session.commit()


def build_audit_writer(*, session_factory: Callable[[], Any]) -> DbBackedAuditWriter:
    """Factory: assemble production AuditWriter from session_factory."""
    return DbBackedAuditWriter(session_factory=session_factory)
