from sqlalchemy import create_engine, inspect


def test_event_snapshot_migration_is_revisioned_and_idempotent():
    from rebuild.sql_ide.migrations import SQL_IDE_EVENT_MIGRATIONS, SqlIdeMigrationRunner

    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        runner = SqlIdeMigrationRunner(engine, SQL_IDE_EVENT_MIGRATIONS)
        first = runner.apply()
        second = runner.apply()

        assert first.applied[-1:] == ("sql_ide_0002_events",)
        assert second.skipped[-1:] == ("sql_ide_0002_events",)
        assert inspect(engine).has_table("sql_ide_events")
    finally:
        engine.dispose()
