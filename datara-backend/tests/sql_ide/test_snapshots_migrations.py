from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable


SQL_IDE_REQUIRED_TABLES = {
    "sql_ide_result_sets",
    "sql_ide_export_job_handles",
    "sql_ide_export_jobs",
    "sql_ide_export_audit",
    "sql_ide_events",
    "sql_ide_history",
    "sql_ide_scripts",
    "sql_ide_history_audit",
    "sql_ide_execution_status",
    "sql_ide_execution_events",
}


def test_sql_ide_history_tables_compile_for_mysql():
    from rebuild.sql_ide.history_store import (
        SqlIdeHistoryAuditRecord,
        SqlIdeHistoryRecord,
        SqlIdeScriptRecord,
    )

    for model in (SqlIdeHistoryRecord, SqlIdeScriptRecord, SqlIdeHistoryAuditRecord):
        assert str(CreateTable(model.__table__).compile(dialect=mysql.dialect()))


def test_sql_ide_snapshot_migration_is_revisioned_and_idempotent():
    from rebuild.sql_ide.migrations import (
        SQL_IDE_MIGRATIONS,
        SqlIdeMigrationRunner,
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        runner = SqlIdeMigrationRunner(engine, SQL_IDE_MIGRATIONS)
        first = runner.apply()
        second = runner.apply()

        assert first.applied == ("sql_ide_0001_snapshots_and_exports",)
        assert second.skipped == ("sql_ide_0001_snapshots_and_exports",)
        assert inspect(engine).has_table("sql_ide_result_sets")
        assert inspect(engine).has_table("sql_ide_export_job_handles")
        assert inspect(engine).has_table("sql_ide_export_jobs")
        assert inspect(engine).has_table("sql_ide_export_audit")
        assert inspect(engine).has_table("sql_ide_schema_migrations")
    finally:
        engine.dispose()


def test_sql_ide_completed_migration_repairs_a_missing_required_table():
    from rebuild.sql_ide.migrations import SQL_IDE_ALL_MIGRATIONS, SqlIdeMigrationRunner

    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        runner = SqlIdeMigrationRunner(engine, SQL_IDE_ALL_MIGRATIONS)
        runner.apply()
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE sql_ide_history_audit"))

        repaired = runner.apply()

        assert repaired.applied == ("sql_ide_0003_history_scripts",)
        assert "sql_ide_history_audit" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_app_lifespan_applies_every_sql_ide_migration():
    from rebuild.api.app import create_app

    app = create_app("sqlite+pysqlite:///:memory:", token_secret="sql-ide-schema-test-secret")
    with TestClient(app):
        engine = app.state.session_factory.kw["bind"]
        assert SQL_IDE_REQUIRED_TABLES <= set(inspect(engine).get_table_names())


def test_export_job_store_enforces_configured_limits_and_expiry():
    from datetime import datetime, timezone

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from rebuild.common.db import Base
    from rebuild.sql_ide.result_store import (
        DEFAULT_EXPORT_MAX_BYTES,
        DEFAULT_EXPORT_MAX_ROWS,
        PersistentExportJobStore,
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    store = PersistentExportJobStore(session_factory=sessionmaker(bind=engine))
    now = datetime(2026, 10, 19, tzinfo=timezone.utc)
    try:
        job = store.create_job(
            project_id=7,
            user_id=11,
            task_id="task-1",
            format="csv",
            row_count=DEFAULT_EXPORT_MAX_ROWS,
            byte_count=DEFAULT_EXPORT_MAX_BYTES,
            now=now,
        )
        assert job["status"] == "queued"
        assert job["expires_at"] == "2026-10-19T01:00:00Z"
        assert store.get_job(export_id=job["export_id"], now=now)["row_count"] == DEFAULT_EXPORT_MAX_ROWS

        with pytest.raises(ValueError, match="export limit exceeded"):
            store.create_job(
                project_id=7,
                user_id=11,
                task_id="task-too-many-rows",
                format="csv",
                row_count=DEFAULT_EXPORT_MAX_ROWS + 1,
                byte_count=1,
                now=now,
            )
        with pytest.raises(ValueError, match="export limit exceeded"):
            store.create_job(
                project_id=7,
                user_id=11,
                task_id="task-too-large",
                format="csv",
                row_count=1,
                byte_count=DEFAULT_EXPORT_MAX_BYTES + 1,
                now=now,
            )

        assert store.cleanup_expired(before="2026-10-19T01:00:00Z") == 1
    finally:
        engine.dispose()
