from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from threading import RLock
from typing import Any, Callable

from sqlalchemy import CheckConstraint, DateTime, Engine, Integer, String, UniqueConstraint, func, select, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from rebuild.common.db import Base


class SchemaMigrationRecord(Base):
    """Shared migration ledger without importing any product-domain models."""

    __tablename__ = "rebuild_schema_migration"
    __table_args__ = (
        UniqueConstraint("revision", name="uq_rebuild_schema_migration_revision"),
        CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_rebuild_schema_migration_status"),
        CheckConstraint("attempt_count > 0", name="ck_rebuild_schema_migration_attempts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    revision: Mapped[str] = mapped_column(String(128), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())


MigrationUpgrade = Callable[[Engine], None]
MigrationPostflight = Callable[[Engine], dict[str, Any]]
_LOCAL_MIGRATION_LOCK = RLock()
_MYSQL_LOCK_NAME = "datara_rebuild_schema_migrations"


@dataclass(frozen=True)
class GovernanceMigration:
    revision: str
    checksum: str
    upgrade: MigrationUpgrade
    tables: tuple = ()
    postflight: MigrationPostflight | None = None


@dataclass(frozen=True)
class MigrationResult:
    applied: tuple[str, ...]
    skipped: tuple[str, ...]


class MigrationApplyError(RuntimeError):
    pass


class MigrationChecksumConflict(RuntimeError):
    pass


class MigrationRunner:
    def __init__(self, engine: Engine, migrations: tuple[GovernanceMigration, ...] | list[GovernanceMigration]):
        self.engine = engine
        self.migrations = tuple(migrations)
        revisions = [migration.revision for migration in self.migrations]
        if len(revisions) != len(set(revisions)):
            raise ValueError("migration revisions must be unique")
        if any(not migration.revision or re.fullmatch(r"[0-9a-f]{64}", migration.checksum) is None for migration in self.migrations):
            raise ValueError("migration revision and lowercase SHA-256 checksum are required")

    def apply(self) -> MigrationResult:
        with _LOCAL_MIGRATION_LOCK:
            if self.engine.dialect.name == "mysql":
                return self._apply_with_mysql_lock()
            return self._apply_revisions()

    def get_revision(self, session: Session, revision: str) -> SchemaMigrationRecord | None:
        return session.scalar(select(SchemaMigrationRecord).where(SchemaMigrationRecord.revision == revision))

    def _ensure_revision_table(self) -> None:
        SchemaMigrationRecord.__table__.create(bind=self.engine, checkfirst=True)

    def _apply_with_mysql_lock(self) -> MigrationResult:
        with self.engine.connect() as connection:
            acquired = connection.scalar(text("SELECT GET_LOCK(:lock_name, 30)"), {"lock_name": _MYSQL_LOCK_NAME})
            if acquired != 1:
                raise MigrationApplyError("could not acquire schema migration lock")
            try:
                return self._apply_revisions()
            finally:
                connection.execute(text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": _MYSQL_LOCK_NAME})

    def _apply_revisions(self) -> MigrationResult:
        self._ensure_revision_table()
        applied: list[str] = []
        skipped: list[str] = []
        for migration in self.migrations:
            if self._prepare_revision(migration):
                self._run_postflight(migration)
                skipped.append(migration.revision)
                continue
            try:
                migration.upgrade(self.engine)
                self._run_postflight(migration)
            except MigrationApplyError:
                self._finish_revision(migration.revision, status="failed", last_error="MigrationApplyError")
                raise
            except Exception as error:
                self._finish_revision(migration.revision, status="failed", last_error=type(error).__name__)
                raise MigrationApplyError(f"migration {migration.revision} failed ({type(error).__name__})") from None
            self._finish_revision(migration.revision, status="completed", last_error="")
            applied.append(migration.revision)
        return MigrationResult(applied=tuple(applied), skipped=tuple(skipped))

    def _run_postflight(self, migration: GovernanceMigration) -> None:
        if migration.postflight is None:
            return
        try:
            report = migration.postflight(self.engine)
        except Exception as error:
            raise MigrationApplyError(f"migration {migration.revision} postflight failed ({type(error).__name__})") from None
        if report.get("verdict") != "READY":
            raise MigrationApplyError(f"migration {migration.revision} postflight rejected schema")

    def _prepare_revision(self, migration: GovernanceMigration) -> bool:
        with Session(self.engine) as session, session.begin():
            record = self.get_revision(session, migration.revision)
            if record is not None and record.checksum != migration.checksum:
                raise MigrationChecksumConflict(f"migration checksum changed for {migration.revision}")
            if record is not None and record.status == "completed":
                return True
            if record is None:
                record = SchemaMigrationRecord(revision=migration.revision, checksum=migration.checksum, status="running", attempt_count=1)
                session.add(record)
            else:
                record.status = "running"
                record.attempt_count += 1
                record.started_at = text("CURRENT_TIMESTAMP")
                record.finished_at = None
                record.last_error = ""
        return False

    def _finish_revision(self, revision: str, *, status: str, last_error: str) -> None:
        with Session(self.engine) as session, session.begin():
            record = self.get_revision(session, revision)
            if record is None:
                raise RuntimeError(f"migration tracking row disappeared for {revision}")
            record.status = status
            record.finished_at = text("CURRENT_TIMESTAMP")
            record.last_error = last_error
