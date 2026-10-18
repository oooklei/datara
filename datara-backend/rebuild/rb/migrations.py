"""R5-B 迁移管理器（revision/checksum/upgrade 约定）。

依 governance/migrations.py 模式：
- 每个迁移有 revision（唯一标识）、checksum（SHA-256）、upgrade(engine) 回调
- MigrationRunner 处理 MySQL 锁、revision 跟踪、checksum 验证
- 表定义在 rb/ledger/ledger_repository.py
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from threading import RLock
from typing import Callable, Optional

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.rb.ledger.ledger_repository import RB_TABLES

MigrationUpgrade = Callable[[Engine], None]
_LOCAL_MIGRATION_LOCK = RLock()
_MYSQL_LOCK_NAME = "datara_rb_schema_migrations"


@dataclass(frozen=True)
class RbMigration:
    revision: str
    checksum: str
    upgrade: MigrationUpgrade
    tables: tuple = ()


@dataclass(frozen=True)
class RbMigrationResult:
    applied: tuple[str, ...]
    skipped: tuple[str, ...]


class RbMigrationApplyError(RuntimeError):
    pass


class RbMigrationChecksumConflict(RuntimeError):
    pass


class RbMigrationRunner:
    def __init__(self, engine: Engine, migrations: tuple[RbMigration, ...] | list[RbMigration]):
        self.engine = engine
        self.migrations = tuple(migrations)
        revisions = [migration.revision for migration in self.migrations]
        if len(revisions) != len(set(revisions)):
            raise ValueError("migration revisions must be unique")
        if any(not migration.revision or not self._is_sha256_digest(migration.checksum) for migration in self.migrations):
            raise ValueError("migration revision and lowercase SHA-256 checksum are required")

    def apply(self) -> RbMigrationResult:
        with _LOCAL_MIGRATION_LOCK:
            if self.engine.dialect.name == "mysql":
                return self._apply_with_mysql_lock()
            return self._apply_revisions()

    def get_revision(self, session: Session, revision: str):
        return session.scalar(select(RbMigrationRecord).where(RbMigrationRecord.revision == revision))

    def _ensure_revision_table(self) -> None:
        RbMigrationRecord.__table__.create(bind=self.engine, checkfirst=True)

    def _apply_with_mysql_lock(self) -> RbMigrationResult:
        with self.engine.connect() as connection:
            acquired = connection.scalar(text("SELECT GET_LOCK(:lock_name, 30)"), {"lock_name": _MYSQL_LOCK_NAME})
            if acquired != 1:
                raise RbMigrationApplyError("could not acquire schema migration lock")
            try:
                return self._apply_revisions()
            finally:
                connection.execute(text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": _MYSQL_LOCK_NAME})

    def _apply_revisions(self) -> RbMigrationResult:
        self._ensure_revision_table()
        applied: list[str] = []
        skipped: list[str] = []
        for migration in self.migrations:
            if self._prepare_revision(migration):
                skipped.append(migration.revision)
                continue
            try:
                migration.upgrade(self.engine)
            except Exception as error:
                self._finish_revision(migration.revision, status="failed", last_error=type(error).__name__)
                raise RbMigrationApplyError(f"migration {migration.revision} failed ({type(error).__name__})") from None
            self._finish_revision(migration.revision, status="completed", last_error="")
            applied.append(migration.revision)
        return RbMigrationResult(applied=tuple(applied), skipped=tuple(skipped))

    def _prepare_revision(self, migration: RbMigration) -> bool:
        with Session(self.engine) as session, session.begin():
            record = self.get_revision(session, migration.revision)
            if record is not None and record.checksum != migration.checksum:
                raise RbMigrationChecksumConflict(f"migration checksum changed for {migration.revision}")
            if record is not None and record.status == "completed":
                return True
            if record is None:
                record = RbMigrationRecord(
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

    @staticmethod
    def _is_sha256_digest(value: str) -> bool:
        return len(value) == 64 and all(c in "0123456789abcdef" for c in value)


from sqlalchemy import Integer, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class RbMigrationRecord(Base):
    """rb_schema_migrations 表。"""
    __tablename__ = "rb_schema_migrations"

    revision: Mapped[str] = mapped_column(String(64), primary_key=True)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, server_default=func.current_timestamp())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(String(256), nullable=False, default="")


def _v0001_upgrade(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine, tables=list(RB_TABLES), checkfirst=True)


_DDL_MANIFEST = (
    "rb_0001_r5_b_tables v1: rb_policy_snapshots,rb_impact_snapshots,rb_execution_records; "
    "ENGINE=InnoDB CHARSET=utf8mb4; all indexes"
)
_v0001_checksum = hashlib.sha256(_DDL_MANIFEST.encode("utf-8")).hexdigest()

RB_MIGRATIONS = (
    RbMigration(
        revision="rb_0001_r5_b_tables",
        checksum=_v0001_checksum,
        upgrade=_v0001_upgrade,
        tables=RB_TABLES,
    ),
)
