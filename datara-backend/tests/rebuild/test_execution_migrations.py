"""Execution DDL registry: checksum, idempotency, recovery and downgrade."""

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from rebuild.execution.migrations import EXECUTION_MIGRATIONS, apply_execution_migrations
from rebuild.execution.models import EXECUTION_TABLES
from rebuild.governance.migrations import (
    GovernanceMigration,
    MigrationApplyError,
    MigrationChecksumConflict,
    MigrationRunner,
)
from rebuild.governance.models import SchemaMigrationRecord
from rebuild.execution.revisions.v0001_execution_tables import downgrade


def test_execution_migration_is_checksummed_idempotent_and_downgradeable():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    first = apply_execution_migrations(engine)
    second = apply_execution_migrations(engine)

    assert first.applied == ("r9_0001_execution_tables",)
    assert second.skipped == first.applied
    assert {table.name for table in EXECUTION_TABLES} <= set(inspect(engine).get_table_names())
    with Session(engine) as session:
        record = session.scalar(
            select(SchemaMigrationRecord).where(
                SchemaMigrationRecord.revision == "r9_0001_execution_tables"
            )
        )
        assert record is not None and record.status == "completed"
        assert len(record.checksum) == 64

    downgrade(engine)
    assert not ({table.name for table in EXECUTION_TABLES} & set(inspect(engine).get_table_names()))


def test_execution_migration_checksum_drift_fails_closed():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    apply_execution_migrations(engine)
    changed = EXECUTION_MIGRATIONS[0]
    migration = type(changed)(
        revision=changed.revision,
        checksum="0" * 64,
        upgrade=lambda _engine: pytest.fail("must reject checksum drift before DDL"),
        tables=changed.tables,
    )
    with pytest.raises(MigrationChecksumConflict):
        MigrationRunner(engine, [migration]).apply()


def test_execution_migration_failed_state_is_persisted_for_retry():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    def fail(_engine):
        raise RuntimeError("private driver details")

    migration = GovernanceMigration("r9_test_failed", "b" * 64, fail)
    with pytest.raises(MigrationApplyError, match="RuntimeError") as raised:
        MigrationRunner(engine, [migration]).apply()
    assert "private driver details" not in str(raised.value)
    with Session(engine) as session:
        record = session.scalar(
            select(SchemaMigrationRecord).where(SchemaMigrationRecord.revision == "r9_test_failed")
        )
        assert record is not None and record.status == "failed"
        assert record.last_error == "RuntimeError"


def test_mysql_migration_lock_conflict_blocks_execution():
    class FakeConnection:
        def __init__(self):
            self.sql = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def scalar(self, statement, _params):
            self.sql.append(str(statement))
            return 0

    class FakeMySQLEngine:
        dialect = type("Dialect", (), {"name": "mysql"})()

        def __init__(self):
            self.connection = FakeConnection()

        def connect(self):
            return self.connection

    engine = FakeMySQLEngine()
    migration = EXECUTION_MIGRATIONS[0]
    with pytest.raises(MigrationApplyError, match="could not acquire schema migration lock"):
        MigrationRunner(engine, [migration]).apply()
    assert any("GET_LOCK" in statement for statement in engine.connection.sql)
