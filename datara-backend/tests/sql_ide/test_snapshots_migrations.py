from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect


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
