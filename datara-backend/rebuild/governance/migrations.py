from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Callable

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from rebuild.governance.contracts import is_sha256_digest
from rebuild.governance.models import SchemaMigrationRecord
from rebuild.governance.revisions import v0001_governance_catalog


MigrationUpgrade = Callable[[Engine], None]
_LOCAL_MIGRATION_LOCK = RLock()
_MYSQL_LOCK_NAME = "datara_rebuild_schema_migrations"


@dataclass(frozen=True)
class GovernanceMigration:
    revision: str
    checksum: str
    upgrade: MigrationUpgrade


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
        if any(not migration.revision or not is_sha256_digest(migration.checksum) for migration in self.migrations):
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
                skipped.append(migration.revision)
                continue
            try:
                migration.upgrade(self.engine)
            except Exception as error:  # Persist only the exception class; driver text can contain connection details.
                self._finish_revision(migration.revision, status="failed", last_error=type(error).__name__)
                raise MigrationApplyError(f"migration {migration.revision} failed ({type(error).__name__})") from None
            self._finish_revision(migration.revision, status="completed", last_error="")
            applied.append(migration.revision)
        return MigrationResult(applied=tuple(applied), skipped=tuple(skipped))

    def _prepare_revision(self, migration: GovernanceMigration) -> bool:
        with Session(self.engine) as session, session.begin():
            record = self.get_revision(session, migration.revision)
            if record is not None and record.checksum != migration.checksum:
                raise MigrationChecksumConflict(f"migration checksum changed for {migration.revision}")
            if record is not None and record.status == "completed":
                return True
            if record is None:
                record = SchemaMigrationRecord(
                    revision=migration.revision,
                    checksum=migration.checksum,
                    status="running",
                    attempt_count=1,
                )
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


R3_GOVERNANCE_MIGRATIONS = (
    GovernanceMigration(
        revision=v0001_governance_catalog.revision,
        checksum=v0001_governance_catalog.checksum,
        upgrade=v0001_governance_catalog.upgrade,
    ),
)
