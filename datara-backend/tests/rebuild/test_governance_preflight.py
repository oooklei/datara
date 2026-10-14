from sqlalchemy import create_engine, inspect, text

from rebuild.governance.migration_preflight import inspect_governance_schema
from rebuild.governance.models import GOVERNANCE_TABLES
from rebuild.project.models import ProjectRecord


def isolated_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ProjectRecord.__table__.create(engine)
    return engine


def test_preflight_is_read_only_and_reports_only_planned_governance_tables():
    engine = isolated_engine()
    before = set(inspect(engine).get_table_names())

    report = inspect_governance_schema(engine)

    after = set(inspect(engine).get_table_names())
    assert report.ready
    assert set(report.missing_tables) == {table.name for table in GOVERNANCE_TABLES}
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
