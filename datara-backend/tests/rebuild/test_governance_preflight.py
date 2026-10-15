from sqlalchemy import create_engine, inspect, text

from rebuild.governance.migration_preflight import inspect_governance_schema
from rebuild.governance.migrations import R3_GOVERNANCE_MIGRATIONS, MigrationRunner
from rebuild.governance.models import GOVERNANCE_I19_I20_TABLES, GOVERNANCE_TABLES, LEGACY_CARRY_FORWARD_TABLES
from rebuild.project.models import ProjectRecord
from rebuild.identity.models import UserRecord


def isolated_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ProjectRecord.__table__.create(engine)
    UserRecord.__table__.create(engine)
    return engine


def test_preflight_is_read_only_and_reports_all_registered_additive_tables():
    engine = isolated_engine()
    before = set(inspect(engine).get_table_names())

    report = inspect_governance_schema(engine)

    after = set(inspect(engine).get_table_names())
    assert report.ready
    expected = {table.name for table in (*GOVERNANCE_TABLES, *LEGACY_CARRY_FORWARD_TABLES, *GOVERNANCE_I19_I20_TABLES)}
    assert set(report.missing_tables) == expected
    assert report.conflicts == ()
    assert not report.revision_table_present
    assert report.revision_status == "absent"
    assert before == after


def test_preflight_fails_closed_on_incompatible_existing_governance_table():
    engine = isolated_engine()
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE rebuild_governance_asset (id VARCHAR(20) PRIMARY KEY)"))

    report = inspect_governance_schema(engine)

    assert not report.ready
    assert any("rebuild_governance_asset" in conflict for conflict in report.conflicts)
    assert "rebuild_governance_asset" not in report.missing_tables


def test_preflight_detects_a_completed_revision_with_missing_tables():
    engine = isolated_engine()
    from rebuild.governance.migrations import MigrationRunner, R3_GOVERNANCE_MIGRATIONS

    MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS).apply()
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE rebuild_governance_asset"))

    report = inspect_governance_schema(engine)

    assert not report.ready
    assert report.revision_status == "completed"
    assert any("completed revision" in conflict for conflict in report.conflicts)


def test_preflight_accepts_schema_created_by_the_registered_revision():
    engine = isolated_engine()
    from rebuild.governance.migrations import MigrationRunner, R3_GOVERNANCE_MIGRATIONS

    MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS).apply()

    report = inspect_governance_schema(engine)

    assert report.ready
    assert report.missing_tables == ()
    assert report.conflicts == ()
    assert report.revision_status == "completed"


def test_preflight_allows_v1_complete_while_v2_is_pending():
    engine = isolated_engine()
    MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS[:1]).apply()

    report = inspect_governance_schema(engine)

    assert report.ready
    assert report.revision_status == "absent"
    assert set(report.missing_tables) == {
        table.name for table in (*LEGACY_CARRY_FORWARD_TABLES, *GOVERNANCE_I19_I20_TABLES)
    }


def test_preflight_allows_v2_complete_while_v3_is_pending():
    engine = isolated_engine()
    MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS[:2]).apply()

    report = inspect_governance_schema(engine)

    assert report.ready
    assert report.revision_status == "absent"
    assert set(report.missing_tables) == {table.name for table in GOVERNANCE_I19_I20_TABLES}


def test_migration_cli_refuses_non_mysql_target_before_connecting(monkeypatch, capsys):
    import sys

    from rebuild.governance import migration_apply

    monkeypatch.setenv("REBUILD_DB_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setattr(sys, "argv", ["migration_apply", "--apply"])

    assert migration_apply.main() == 4
    assert "not the isolated R3 schema" in capsys.readouterr().err


def test_mysql_tinyint_one_reflects_boolean_but_other_tinyint_sizes_do_not():
    from sqlalchemy import Boolean
    from sqlalchemy.dialects.mysql import TINYINT

    from rebuild.governance.migration_preflight import _types_compatible

    assert _types_compatible(TINYINT(display_width=1), Boolean())
    assert not _types_compatible(TINYINT(display_width=4), Boolean())


def test_preflight_compares_mysql_generated_identifiers_by_schema_shape():
    from rebuild.governance.migration_preflight import _compare_table

    engine = isolated_engine()
    MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS).apply()
    delegate = inspect(engine)

    class MySQLLikeInspector:
        def __getattr__(self, name):
            return getattr(delegate, name)

        def get_indexes(self, table_name):
            # MySQL shortens long generated identifiers; their physical
            # contract is still the ordered columns and uniqueness.
            return [
                {**index, "name": "mysql_shortened_identifier"}
                for index in delegate.get_indexes(table_name)
            ]

        def get_unique_constraints(self, table_name):
            table = next(table for table in LEGACY_CARRY_FORWARD_TABLES if table.name == table_name)
            unnamed = {
                tuple(column.name for column in constraint.columns)
                for constraint in table.constraints
                if constraint.__class__.__name__ == "UniqueConstraint" and constraint.name is None
            }
            return [
                {
                    **constraint,
                    "name": "mysql_generated_name"
                    if tuple(constraint.get("column_names") or ()) in unnamed
                    else constraint.get("name"),
                }
                for constraint in delegate.get_unique_constraints(table_name)
            ]

    table = next(
        table for table in LEGACY_CARRY_FORWARD_TABLES if table.name == "rebuild_governance_asset_metadata_extension"
    )
    assert _compare_table(MySQLLikeInspector(), table) == []


def test_preflight_detects_foreign_key_delete_action_drift():
    from rebuild.governance.migration_preflight import _compare_table

    engine = isolated_engine()
    MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS).apply()
    delegate = inspect(engine)
    table = next(
        table
        for table in LEGACY_CARRY_FORWARD_TABLES
        if table.name == "rebuild_governance_warehouse_model_field"
    )

    class DriftedInspector:
        def __getattr__(self, name):
            return getattr(delegate, name)

        def get_foreign_keys(self, table_name):
            keys = delegate.get_foreign_keys(table_name)
            if table_name != table.name:
                return keys
            return [
                {**key, "options": {**key.get("options", {}), "ondelete": "CASCADE"}}
                if key.get("constrained_columns") == ["model_id"]
                else key
                for key in keys
            ]

    assert any("foreign key" in conflict for conflict in _compare_table(DriftedInspector(), table))


def test_preflight_detects_missing_check_constraint():
    from rebuild.governance.migration_preflight import _compare_table

    engine = isolated_engine()
    MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS).apply()
    delegate = inspect(engine)
    table = next(
        table
        for table in LEGACY_CARRY_FORWARD_TABLES
        if table.name == "rebuild_governance_warehouse_model_field"
    )

    class MissingCheckInspector:
        def __getattr__(self, name):
            return getattr(delegate, name)

        def get_check_constraints(self, table_name):
            checks = delegate.get_check_constraints(table_name)
            return checks[:-1] if table_name == table.name else checks

    assert any("check constraint" in conflict for conflict in _compare_table(MissingCheckInspector(), table))


def test_preflight_accepts_unique_index_as_unique_constraint_equivalent():
    from rebuild.governance.migration_preflight import _compare_table

    engine = isolated_engine()
    MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS).apply()
    delegate = inspect(engine)
    table = next(
        table
        for table in LEGACY_CARRY_FORWARD_TABLES
        if table.name == "rebuild_governance_domain"
    )
    expected = next(
        constraint
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
        and tuple(column.name for column in constraint.columns) == ("project_id", "name")
    )

    class IndexBackedUniqueInspector:
        def __getattr__(self, name):
            return getattr(delegate, name)

        def get_unique_constraints(self, table_name):
            constraints = delegate.get_unique_constraints(table_name)
            return [
                item for item in constraints
                if not (table_name == table.name and tuple(item.get("column_names") or ()) == ("project_id", "name"))
            ]

        def get_indexes(self, table_name):
            indexes = delegate.get_indexes(table_name)
            if table_name == table.name:
                indexes.append({"name": expected.name, "column_names": ["project_id", "name"], "unique": True})
            return indexes

    assert _compare_table(IndexBackedUniqueInspector(), table) == []



def test_preflight_does_not_treat_partial_unique_index_as_constraint_equivalent():
    from rebuild.governance.migration_preflight import _compare_table

    engine = isolated_engine()
    MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS).apply()
    delegate = inspect(engine)
    table = next(
        table for table in LEGACY_CARRY_FORWARD_TABLES if table.name == "rebuild_governance_domain"
    )

    class PartialUniqueInspector:
        def __getattr__(self, name):
            return getattr(delegate, name)

        def get_unique_constraints(self, table_name):
            constraints = delegate.get_unique_constraints(table_name)
            if table_name != table.name:
                return constraints
            return [
                item for item in constraints
                if tuple(item.get("column_names") or ()) != ("project_id", "name")
            ]

        def get_indexes(self, table_name):
            indexes = delegate.get_indexes(table_name)
            if table_name == table.name:
                indexes.append(
                    {
                        "name": "partial_uq_project_name",
                        "column_names": ["project_id", "name"],
                        "unique": True,
                        "dialect_options": {"sqlite_where": "name <> ''"},
                    }
                )
            return indexes

    conflicts = _compare_table(PartialUniqueInspector(), table)

    assert any("missing or incompatible unique constraint" in conflict for conflict in conflicts)


def test_preflight_detects_unexpected_unique_index():
    from rebuild.governance.migration_preflight import _compare_table

    engine = isolated_engine()
    MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS).apply()
    delegate = inspect(engine)
    table = next(
        table for table in LEGACY_CARRY_FORWARD_TABLES if table.name == "rebuild_governance_domain"
    )

    class ExtraUniqueInspector:
        def __getattr__(self, name):
            return getattr(delegate, name)

        def get_indexes(self, table_name):
            indexes = delegate.get_indexes(table_name)
            if table_name == table.name:
                indexes.append({"name": "unexpected_uq", "column_names": ["description"], "unique": True})
            return indexes

    assert any("unexpected unique" in conflict for conflict in _compare_table(ExtraUniqueInspector(), table))
