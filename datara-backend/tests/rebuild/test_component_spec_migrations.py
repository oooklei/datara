"""Component catalog DDL registry guards."""

import hashlib
import json

import pytest
from sqlalchemy import BigInteger, Boolean, Integer, MetaData, String, create_engine, inspect, select, text
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session

from common.models import Component, ComponentLog, ComponentVersion
from rebuild.component_spec.migrations import (
    COMPONENT_SPEC_MIGRATIONS,
    apply_component_spec_migrations,
)
from rebuild.component_spec.revisions import v0001_component_spec_tables as revision
from rebuild.governance.migrations import (
    MigrationApplyError,
    MigrationChecksumConflict,
    MigrationRunner,
)
from rebuild.governance.models import SchemaMigrationRecord


def test_revision_uses_frozen_tables_and_released_checksum() -> None:
    assert all(
        frozen is not evolving
        for frozen, evolving in zip(
            revision.COMPONENT_TABLES,
            (Component.__table__, ComponentVersion.__table__, ComponentLog.__table__),
            strict=True,
        )
    )
    encoded = json.dumps(
        revision.SCHEMA_MANIFEST,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    assert hashlib.sha256(encoded).hexdigest() == "959482177e46f8f5d6e50ea9e446cf5804dda51c1d4e161597eb6549cedb46c5"
    assert revision.checksum == "19ed75a37416a0e3e4b463ea357c78f79601f014f7c75160470d296000c81fcf"
    assert revision.SCHEMA_MANIFEST["tables"][0]["columns"][0]["autoincrement"] is True


def _create_schema_with_column_type(column_name: str, replacement_type) -> object:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    tables = [table.to_metadata(metadata) for table in revision.COMPONENT_TABLES]
    tables[0].columns[column_name].type = replacement_type
    metadata.create_all(engine)
    return engine


def test_component_spec_migration_rejects_sqlite_wrong_type_family() -> None:
    engine = _create_schema_with_column_type("name", mysql.INTEGER())

    with pytest.raises(MigrationApplyError, match="RuntimeError"):
        apply_component_spec_migrations(engine)


def test_component_spec_migration_rejects_sqlite_wrong_string_length() -> None:
    engine = _create_schema_with_column_type("name", String(127))

    with pytest.raises(MigrationApplyError, match="RuntimeError"):
        apply_component_spec_migrations(engine)


def test_mysql_type_contract_normalizes_display_width_but_preserves_length() -> None:
    dialect = mysql.dialect()

    assert revision._type_contract(mysql.INTEGER(display_width=11), dialect) == revision._type_contract(
        mysql.INTEGER(), dialect
    )
    assert revision._type_contract(mysql.VARCHAR(128), dialect) != revision._type_contract(mysql.VARCHAR(127), dialect)
    assert revision._type_contract(Boolean(), dialect) == revision._type_contract(
        mysql.TINYINT(display_width=1), dialect
    )
    assert revision._type_contract(BigInteger(), dialect) != revision._type_contract(Integer(), dialect)


def test_mysql_type_contract_preserves_text_capacity_class() -> None:
    dialect = mysql.dialect()
    expected = revision._type_contract(mysql.LONGTEXT(), dialect)

    assert expected != revision._type_contract(mysql.TEXT(), dialect)
    assert expected != revision._type_contract(mysql.MEDIUMTEXT(), dialect)
    assert expected != revision._type_contract(mysql.TINYTEXT(), dialect)


def test_mysql_existing_primary_key_without_auto_increment_is_rejected(monkeypatch) -> None:
    dialect = mysql.dialect()
    table = revision.COMPONENT_TABLES[0]
    columns = [
        {
            "name": column.name,
            "nullable": column.nullable,
            "type": column.type,
            "autoincrement": False if column.name == "id" else None,
        }
        for column in table.columns
    ]

    class FakeInspector:
        def get_pk_constraint(self, _table_name):
            return {"constrained_columns": ["id"]}

        def get_columns(self, _table_name):
            return columns

        def get_indexes(self, _table_name):
            return [
                {"name": index.name, "column_names": [column.name for column in index.columns]}
                for index in table.indexes
            ]

        def get_unique_constraints(self, _table_name):
            return [{"column_names": ["type"]}]

    class FakeEngine:
        pass

    engine = FakeEngine()
    engine.dialect = dialect
    monkeypatch.setattr(revision, "inspect", lambda _engine: FakeInspector())

    with pytest.raises(RuntimeError, match="incompatible column layout"):
        revision._validate_existing_table(engine, table)


def test_component_spec_migration_is_checksummed_and_idempotent() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    first = apply_component_spec_migrations(engine)
    second = apply_component_spec_migrations(engine)

    assert first.applied == tuple(migration.revision for migration in COMPONENT_SPEC_MIGRATIONS)
    assert second.skipped == first.applied
    assert {"t_component", "t_component_version", "t_component_log"} <= set(inspect(engine).get_table_names())
    inspector = inspect(engine)
    assert "idx_comp_profile_state" in {item["name"] for item in inspector.get_indexes("t_component")}
    assert "idx_compver_comp" in {item["name"] for item in inspector.get_indexes("t_component_version")}
    assert "idx_complog_comp" in {item["name"] for item in inspector.get_indexes("t_component_log")}
    assert {tuple(item["column_names"]) for item in inspector.get_unique_constraints("t_component")} >= {("type",)}
    assert {tuple(item["column_names"]) for item in inspector.get_unique_constraints("t_component_version")} >= {
        ("type", "version")
    }
    with Session(engine) as session:
        record = session.scalar(
            select(SchemaMigrationRecord).where(SchemaMigrationRecord.revision == "i4_0001_component_catalog")
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
            select(SchemaMigrationRecord).where(SchemaMigrationRecord.revision == "i4_0001_component_catalog")
        )
        assert record is not None
        assert record.status == "failed"
        assert record.last_error == "RuntimeError"


def test_component_spec_migration_rejects_structurally_valid_partial_schema() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    COMPONENT_SPEC_MIGRATIONS[0].tables[0].create(bind=engine)

    with pytest.raises(MigrationApplyError, match="RuntimeError"):
        apply_component_spec_migrations(engine)

    assert set(inspect(engine).get_table_names()).isdisjoint({"t_component_version", "t_component_log"})


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
