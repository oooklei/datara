"""Component catalog DDL registry guards."""

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from rebuild.component_spec.migrations import (
    COMPONENT_SPEC_MIGRATIONS,
    apply_component_spec_migrations,
)
from rebuild.governance.migrations import (
    MigrationApplyError,
    MigrationChecksumConflict,
    MigrationRunner,
)
from rebuild.governance.models import SchemaMigrationRecord


def test_component_spec_migration_is_checksummed_and_idempotent() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    first = apply_component_spec_migrations(engine)
    second = apply_component_spec_migrations(engine)

    assert first.applied == ("i4_0001_component_catalog",)
    assert second.skipped == first.applied
    assert {"t_component", "t_component_version", "t_component_log"} <= set(
        inspect(engine).get_table_names()
    )
    inspector = inspect(engine)
    assert "idx_comp_profile_state" in {
        item["name"] for item in inspector.get_indexes("t_component")
    }
    assert "idx_compver_comp" in {
        item["name"] for item in inspector.get_indexes("t_component_version")
    }
    assert "idx_complog_comp" in {
        item["name"] for item in inspector.get_indexes("t_component_log")
    }
    assert {tuple(item["column_names"]) for item in inspector.get_unique_constraints("t_component")} >= {
        ("type",)
    }
    assert {
        tuple(item["column_names"])
        for item in inspector.get_unique_constraints("t_component_version")
    } >= {("type", "version")}
    with Session(engine) as session:
        record = session.scalar(
            select(SchemaMigrationRecord).where(
                SchemaMigrationRecord.revision == "i4_0001_component_catalog"
            )
        )
        assert record is not None
        assert record.checksum == COMPONENT_SPEC_MIGRATIONS[0].checksum
        assert record.status == "completed"


def test_component_spec_migration_checksum_drift_fails_closed() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    apply_component_spec_migrations(engine)
    registered = COMPONENT_SPEC_MIGRATIONS[0]
    upgrade_called = False

    def unexpected_upgrade(_engine) -> None:
        nonlocal upgrade_called
        upgrade_called = True

    changed = type(registered)(
        revision=registered.revision,
        checksum="0" * 64,
        upgrade=unexpected_upgrade,
        tables=registered.tables,
    )

    with pytest.raises(MigrationChecksumConflict, match="checksum changed"):
        MigrationRunner(engine, (changed,)).apply()
    assert upgrade_called is False


def test_component_spec_migration_rejects_partial_existing_schema_without_creating_more_tables() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE t_component (id BIGINT PRIMARY KEY)"))

    with pytest.raises(MigrationApplyError, match="RuntimeError"):
        apply_component_spec_migrations(engine)

    table_names = set(inspect(engine).get_table_names())
    assert "t_component_version" not in table_names
    assert "t_component_log" not in table_names
    with Session(engine) as session:
        record = session.scalar(
            select(SchemaMigrationRecord).where(
                SchemaMigrationRecord.revision == "i4_0001_component_catalog"
            )
        )
        assert record is not None
        assert record.status == "failed"
        assert record.last_error == "RuntimeError"


def test_component_spec_migration_rejects_structurally_valid_partial_schema() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    COMPONENT_SPEC_MIGRATIONS[0].tables[0].create(bind=engine)

    with pytest.raises(MigrationApplyError, match="RuntimeError"):
        apply_component_spec_migrations(engine)

    assert set(inspect(engine).get_table_names()).isdisjoint(
        {"t_component_version", "t_component_log"}
    )


def test_component_spec_migration_rejects_existing_table_missing_required_index() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    for table in COMPONENT_SPEC_MIGRATIONS[0].tables:
        table.create(bind=engine, checkfirst=True)
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX idx_comp_profile_state"))

    with pytest.raises(MigrationApplyError, match="RuntimeError"):
        apply_component_spec_migrations(engine)


def test_component_spec_migration_revalidates_schema_after_completed_revision() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    apply_component_spec_migrations(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE t_component_log"))

    with pytest.raises(MigrationApplyError, match="schema validation failed"):
        apply_component_spec_migrations(engine)

    assert "t_component_log" not in inspect(engine).get_table_names()
