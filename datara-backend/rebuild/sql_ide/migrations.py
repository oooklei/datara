"""Revisioned SQL IDE snapshots schema migrations."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Callable

from sqlalchemy import DateTime, Engine, Integer, String, func, select, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from rebuild.common.db import Base
from rebuild.sql_ide.export_service import SqlIdeExportAuditRecord, SqlIdeExportJobRecord as ExportArtifactRecord
from rebuild.sql_ide.result_store import SqlIdeExportJobRecord, SqlIdeResultSetRecord

MigrationUpgrade = Callable[[Engine], None]
_LOCAL_MIGRATION_LOCK = RLock()
_MYSQL_LOCK_NAME = "datara_sql_ide_schema_migrations"


@dataclass(frozen=True)
class SqlIdeMigration:
    revision: str
    checksum: str
    upgrade: MigrationUpgrade


@dataclass(frozen=True)
class SqlIdeMigrationResult:
    applied: tuple[str, ...]
    skipped: tuple[str, ...]


class SqlIdeMigrationError(RuntimeError):
    pass


class SqlIdeMigrationChecksumConflict(SqlIdeMigrationError):
    pass


class SqlIdeMigrationRecord(Base):
    __tablename__ = "sql_ide_schema_migrations"

    revision: Mapped[str] = mapped_column(String(64), primary_key=True)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, server_default=func.current_timestamp()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(String(256), nullable=False, default="")


class SqlIdeMigrationRunner:
    def __init__(self, engine: Engine, migrations: tuple[SqlIdeMigration, ...] | list[SqlIdeMigration]):
        self.engine = engine
        self.migrations = tuple(migrations)
        revisions = [migration.revision for migration in self.migrations]
        if len(revisions) != len(set(revisions)):
            raise ValueError("migration revisions must be unique")
        if any(not migration.revision or not _is_sha256_digest(migration.checksum) for migration in self.migrations):
            raise ValueError("migration revision and lowercase SHA-256 checksum are required")

    def apply(self) -> SqlIdeMigrationResult:
        with _LOCAL_MIGRATION_LOCK:
            if self.engine.dialect.name == "mysql":
                with self.engine.connect() as connection:
                    acquired = connection.scalar(text("SELECT GET_LOCK(:lock_name, 30)"), {"lock_name": _MYSQL_LOCK_NAME})
                    if acquired != 1:
                        raise SqlIdeMigrationError("could not acquire SQL IDE schema migration lock")
                    try:
                        return self._apply_revisions()
                    finally:
                        connection.execute(text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": _MYSQL_LOCK_NAME})
            return self._apply_revisions()

    def _apply_revisions(self) -> SqlIdeMigrationResult:
        SqlIdeMigrationRecord.__table__.create(bind=self.engine, checkfirst=True)
        applied: list[str] = []
        skipped: list[str] = []
        for migration in self.migrations:
            if self._prepare_revision(migration):
                skipped.append(migration.revision)
                continue
            try:
                migration.upgrade(self.engine)
            except Exception as error:
                self._finish_revision(migration.revision, "failed", type(error).__name__)
                raise SqlIdeMigrationError(
                    f"migration {migration.revision} failed ({type(error).__name__})"
                ) from None
            self._finish_revision(migration.revision, "completed", "")
            applied.append(migration.revision)
        return SqlIdeMigrationResult(applied=tuple(applied), skipped=tuple(skipped))

    def _prepare_revision(self, migration: SqlIdeMigration) -> bool:
        with Session(self.engine) as session, session.begin():
            record = session.scalar(
                select(SqlIdeMigrationRecord).where(SqlIdeMigrationRecord.revision == migration.revision)
            )
            if record is not None and record.checksum != migration.checksum:
                raise SqlIdeMigrationChecksumConflict(f"migration checksum changed for {migration.revision}")
            if record is not None and record.status == "completed":
                return True
            if record is None:
                session.add(
                    SqlIdeMigrationRecord(
                        revision=migration.revision,
                        checksum=migration.checksum,
                        status="running",
                        attempt_count=1,
                    )
                )
            else:
                record.status = "running"
                record.attempt_count += 1
                record.started_at = text("CURRENT_TIMESTAMP")
                record.finished_at = None
                record.last_error = ""
        return False

    def _finish_revision(self, revision: str, status: str, last_error: str) -> None:
        with Session(self.engine) as session, session.begin():
            record = session.get(SqlIdeMigrationRecord, revision)
            if record is None:
                raise RuntimeError(f"migration tracking row disappeared for {revision}")
            record.status = status
            record.finished_at = text("CURRENT_TIMESTAMP")
            record.last_error = last_error


def _upgrade_snapshots(engine: Engine) -> None:
    Base.metadata.create_all(
        bind=engine,
        tables=[
            SqlIdeResultSetRecord.__table__,
            SqlIdeExportJobRecord.__table__,
            ExportArtifactRecord.__table__,
            SqlIdeExportAuditRecord.__table__,
        ],
        checkfirst=True,
    )


_DDL_MANIFEST = (
    "sql_ide_0001_snapshots_and_exports v1: sql_ide_result_sets,sql_ide_export_job_handles,"
    "sql_ide_export_jobs,sql_ide_export_audit; result snapshot 24h; export job 1h"
)
SQL_IDE_MIGRATIONS = (
    SqlIdeMigration(
        revision="sql_ide_0001_snapshots_and_exports",
        checksum=hashlib.sha256(_DDL_MANIFEST.encode("utf-8")).hexdigest(),
        upgrade=_upgrade_snapshots,
    ),
)


def _is_sha256_digest(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)
