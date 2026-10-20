"""Stream schema migration compatibility for fresh and pre-crosswalk databases."""

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from rebuild.governance.migrations import GovernanceMigration, MigrationRunner
from rebuild.stream.migrations import STREAM_MIGRATIONS, STREAM_TABLES, apply_stream_migrations
from rebuild.stream.revisions import v0001_legacy_job_mapping, v0002_stream_job_attempt

V0001 = "r8_0001_stream_legacy_job_mapping"
V0002 = "r8_0002_stream_job_attempt"


def _assert_crosswalk_schema(engine):
    inspector = inspect(engine)
    columns = {column["name"]: column for column in inspector.get_columns("stream_job")}
    assert "legacy_job_id" in columns
    assert columns["legacy_job_id"]["nullable"] is True

    indexes = inspector.get_indexes("stream_job")
    matching = [
        index for index in indexes if tuple(index.get("column_names") or ()) == ("legacy_job_id",)
    ]
    assert any(index.get("unique") for index in matching)
    assert any(index.get("name") == "ix_stream_job_legacy_job_id" for index in matching)


def _assert_attempt_table_schema(engine):
    inspector = inspect(engine)
    assert "stream_job_attempt" in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns("stream_job_attempt")}
    assert {"id", "job_id", "attempt_no", "status", "started_at", "finished_at"} <= columns
    # §13.13 timestamp contract
    assert {"created_at", "updated_at"} <= columns
    unique_constraints = [
        tuple(sorted(constraint["column_names"] or []))
        for constraint in inspector.get_unique_constraints("stream_job_attempt")
    ]
    assert any(constraint == ("attempt_no", "job_id") for constraint in unique_constraints)


def test_stream_migration_registry_contains_both_revisions_in_order():
    """DEP-05: the stream registry must own v0002 so the attempt table is applied."""
    assert [migration.revision for migration in STREAM_MIGRATIONS] == [V0001, V0002]
    assert {table.name for table in STREAM_TABLES} >= {
        "stream_job",
        "stream_job_attempt",
        "stream_checkpoint",
        "stream_metric_snapshot",
        "stream_failure_event",
    }


def test_stream_migration_creates_fresh_schema_and_is_idempotent():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        first = apply_stream_migrations(engine)
        second = apply_stream_migrations(engine)

        assert first.applied == (V0001, V0002)
        assert second.skipped == first.applied
        assert {table.name for table in STREAM_TABLES} <= set(inspect(engine).get_table_names())
        _assert_crosswalk_schema(engine)
        _assert_attempt_table_schema(engine)
    finally:
        engine.dispose()


def test_stream_migration_upgrades_existing_stream_job_and_enforces_unique_mapping():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(
                text("CREATE TABLE stream_job (id INTEGER PRIMARY KEY, state VARCHAR(32) NOT NULL)")
            )
            connection.execute(text("INSERT INTO stream_job (id, state) VALUES (1, 'RUNNING')"))

        first = apply_stream_migrations(engine)
        second = apply_stream_migrations(engine)

        assert first.applied == (V0001, V0002)
        assert second.skipped == first.applied
        _assert_crosswalk_schema(engine)
        _assert_attempt_table_schema(engine)
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO stream_job (id, state, legacy_job_id) VALUES (2, 'RUNNING', 20)")
            )
            connection.execute(
                text("INSERT INTO stream_job (id, state, legacy_job_id) VALUES (3, 'RUNNING', NULL)")
            )
            connection.execute(
                text("INSERT INTO stream_job (id, state, legacy_job_id) VALUES (4, 'RUNNING', NULL)")
            )

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text("INSERT INTO stream_job (id, state, legacy_job_id) VALUES (5, 'RUNNING', 20)")
                )
    finally:
        engine.dispose()


def test_stream_migration_v0002_adds_attempt_table_to_pre_v0002_schema():
    """A database that only received v0001 gains stream_job_attempt via v0002."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        # Simulate a pre-DEP-05 database: v0001 applied through the runner
        # (ledger records it as completed), v0002 never registered.
        MigrationRunner(
            engine,
            (
                GovernanceMigration(
                    revision=v0001_legacy_job_mapping.revision,
                    checksum=v0001_legacy_job_mapping.checksum,
                    upgrade=v0001_legacy_job_mapping.upgrade,
                    tables=v0001_legacy_job_mapping.STREAM_TABLES,
                ),
            ),
        ).apply()
        assert "stream_job_attempt" not in inspect(engine).get_table_names()

        result = apply_stream_migrations(engine)

        assert result.applied == (V0002,)
        assert "stream_job_attempt" in inspect(engine).get_table_names()
        _assert_attempt_table_schema(engine)
    finally:
        engine.dispose()


def test_stream_migration_v0002_downgrade_drops_only_the_attempt_table():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        applied = apply_stream_migrations(engine)
        assert applied.applied == (V0001, V0002)

        v0002_stream_job_attempt.downgrade(engine)

        remaining = set(inspect(engine).get_table_names())
        assert "stream_job_attempt" not in remaining
        # v0001-owned tables and the migration ledger survive the downgrade.
        assert {"stream_job", "stream_checkpoint", "stream_metric_snapshot", "stream_failure_event"} <= remaining

        # Roll the ledger back to "not applied" and re-apply: v0002 re-creates
        # the attempt table while v0001 stays completed.
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM rebuild_schema_migration WHERE revision = :revision"),
                {"revision": V0002},
            )
        restored = apply_stream_migrations(engine)
        assert restored.applied == (V0002,)
        assert "stream_job_attempt" in inspect(engine).get_table_names()
        _assert_attempt_table_schema(engine)
    finally:
        engine.dispose()
