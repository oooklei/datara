from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from rebuild.common.db import Base


@pytest.fixture
def history_store():
    from rebuild.sql_ide.history_store import SqlIdeHistoryStore

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    yield SqlIdeHistoryStore(session_factory=sessions)
    engine.dispose()


def test_history_is_project_and_user_scoped_and_soft_deleted(history_store):
    from rebuild.sql_ide.history_store import SqlIdeHistoryRecord

    history_id = history_store.create_history(
        project_id=7, user_id=11, datasource_id=3, db="analytics", sql_text="select 1",
        status="succeeded", stmt_count=1, elapsed_ms=12,
    )
    assert history_store.list_history(project_id=7, user_id=11, datasource_id=3)[0]["history_id"] == history_id
    assert history_store.list_history(project_id=7, user_id=12, datasource_id=3) == []
    assert history_store.list_history(project_id=8, user_id=11, datasource_id=3) == []

    assert history_store.delete_history(project_id=7, user_id=11, history_id=history_id) is True
    assert history_store.list_history(project_id=7, user_id=11, datasource_id=3) == []
    # Deletion preserves the durable row for audit/reference integrity.
    record = history_store.get_history_record(history_id=history_id)
    assert isinstance(record, SqlIdeHistoryRecord)
    assert record.deleted_at is not None
    assert history_store.delete_history(project_id=7, user_id=11, history_id=history_id) is False


def test_scripts_are_project_shared_with_revision_compare_and_swap(history_store):
    script = history_store.save_script(project_id=7, user_id=11, name="daily", sql_text="select 1")
    assert script["revision"] == 1
    assert history_store.list_scripts(project_id=7, user_id=12) == [script]
    assert history_store.list_scripts(project_id=8, user_id=11) == []

    updated = history_store.save_script(
        project_id=7, user_id=12, script_id=script["script_id"], expected_revision=1,
        name="daily", sql_text="select 2",
    )
    assert updated["revision"] == 2
    assert updated["sql_text"] == "select 2"
    with pytest.raises(ValueError, match="revision"):
        history_store.save_script(
            project_id=7, user_id=11, script_id=script["script_id"], expected_revision=1,
            name="stale", sql_text="select 3",
        )


def test_scripts_soft_delete_and_audit_are_append_only(history_store):
    from rebuild.sql_ide.history_store import SqlIdeHistoryAuditRecord

    script = history_store.save_script(project_id=7, user_id=11, name="draft", sql_text="select 1")
    assert history_store.delete_script(
        project_id=7, user_id=11, script_id=script["script_id"], expected_revision=1
    ) is True
    assert history_store.list_scripts(project_id=7, user_id=12) == []
    assert history_store.delete_script(
        project_id=7, user_id=11, script_id=script["script_id"], expected_revision=1
    ) is False

    audit = history_store.list_audit(project_id=7)
    assert [item["action"] for item in audit] == ["script.created", "script.deleted"]
    assert all("sql_text" not in item and "sql_digest" in item for item in audit)
    assert len(history_store.get_audit_records(project_id=7)) == 2


def test_deleted_script_can_be_restored_within_retention_window(history_store):
    from rebuild.sql_ide.history_store import SCRIPT_TOMBSTONE_TTL

    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    script = history_store.save_script(
        project_id=3, user_id=4, name="recoverable", sql_text="select 1", now=created
    )
    deleted = created + timedelta(days=1)
    assert history_store.delete_script(
        project_id=3, user_id=4, script_id=script["script_id"], expected_revision=1, now=deleted
    )

    restored = history_store.save_script(
        project_id=3,
        user_id=4,
        script_id=script["script_id"],
        expected_revision=2,
        name="recovered",
        sql_text="select 2",
        now=deleted + SCRIPT_TOMBSTONE_TTL - timedelta(days=1),
    )

    assert restored["revision"] == 3
    assert restored["name"] == "recovered"
    assert restored["sql_text"] == "select 2"
    assert history_store.list_scripts(project_id=3) == [restored]
    assert history_store.get_script_record(script_id=script["script_id"]).expires_at is None
    assert [item["action"] for item in history_store.list_audit(project_id=3)] == [
        "script.created", "script.deleted", "script.updated"
    ]


def test_history_retention_prunes_expired_rows_but_keeps_audit(history_store):
    from rebuild.sql_ide.history_store import AUDIT_MIN_TTL, HISTORY_TOMBSTONE_TTL, HISTORY_TTL

    now = datetime(2026, 10, 19, tzinfo=timezone.utc)
    history_id = history_store.create_history(
        project_id=7, user_id=11, datasource_id=3, db=None, sql_text="select secret_value",
        status="failed", stmt_count=1, elapsed_ms=8, now=now,
    )
    assert history_store.get_history_record(history_id=history_id).expires_at == (now + HISTORY_TTL).replace(
        tzinfo=None
    )
    deleted_at = now + timedelta(days=10)
    assert history_store.delete_history(
        project_id=7, user_id=11, history_id=history_id, now=deleted_at
    )
    assert history_store.get_history_record(history_id=history_id).expires_at == (
        deleted_at + HISTORY_TOMBSTONE_TTL
    ).replace(tzinfo=None)
    assert history_store.cleanup_expired(now=deleted_at + HISTORY_TOMBSTONE_TTL) == 1
    assert history_store.get_history_record(history_id=history_id) is None
    events = history_store.get_audit_records(project_id=7)
    assert events and all("secret_value" not in (event.sql_digest or "") for event in events)
    assert len(events) == 2
    assert HISTORY_TTL.total_seconds() > 0
    assert all(event.retain_until >= event.created_at + AUDIT_MIN_TTL for event in events)


def test_history_tombstone_uses_creation_expiry_when_earlier(history_store):
    from rebuild.sql_ide.history_store import HISTORY_TOMBSTONE_TTL, HISTORY_TTL

    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    history_id = history_store.create_history(
        project_id=1, user_id=2, datasource_id=3, db=None, sql_text="select 1",
        status="timed_out", stmt_count=1, elapsed_ms=0, now=created,
    )
    deleted = created + HISTORY_TTL - timedelta(days=5)
    history_store.delete_history(project_id=1, user_id=2, history_id=history_id, now=deleted)
    record = history_store.get_history_record(history_id=history_id)
    assert record.expires_at == (created + HISTORY_TTL).replace(tzinfo=None)
    assert record.expires_at < (deleted + HISTORY_TOMBSTONE_TTL).replace(tzinfo=None)


def test_scripts_live_until_delete_then_cleanup_after_30_days_and_audit_is_retained(history_store):
    from rebuild.sql_ide.history_store import AUDIT_MIN_TTL, SCRIPT_TOMBSTONE_TTL

    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    script = history_store.save_script(
        project_id=3, user_id=4, name="long-lived", sql_text="select 1", now=created
    )
    assert history_store.get_script_record(script_id=script["script_id"]).expires_at is None
    assert history_store.cleanup_expired(now=created + timedelta(days=500)) == 0
    assert history_store.get_script_record(script_id=script["script_id"]) is not None

    deleted = created + timedelta(days=500)
    assert history_store.delete_script(
        project_id=3, user_id=4, script_id=script["script_id"], expected_revision=1, now=deleted
    )
    tombstone = history_store.get_script_record(script_id=script["script_id"])
    assert tombstone.expires_at == (deleted + SCRIPT_TOMBSTONE_TTL).replace(tzinfo=None)
    assert history_store.cleanup_expired(now=deleted + SCRIPT_TOMBSTONE_TTL) == 1
    assert history_store.get_script_record(script_id=script["script_id"]) is None

    audit = history_store.get_audit_records(project_id=3)
    assert len(audit) == 2
    assert all(item.retain_until >= item.created_at + AUDIT_MIN_TTL for item in audit)
    assert history_store.cleanup_expired(now=deleted + timedelta(days=400)) == 0
    assert len(history_store.get_audit_records(project_id=3)) == 2


def test_history_accepts_only_a5_terminal_statuses(history_store):
    for status in ("succeeded", "failed", "partial_failure", "canceled", "timed_out"):
        history_store.create_history(
            project_id=1, user_id=2, datasource_id=3, db=None, sql_text="select 1",
            status=status, stmt_count=1, elapsed_ms=1,
        )
    with pytest.raises(ValueError, match="status"):
        history_store.create_history(
            project_id=1, user_id=2, datasource_id=3, db=None, sql_text="select 1",
            status="success", stmt_count=1, elapsed_ms=1,
        )


def test_history_script_migration_is_revisioned_and_idempotent():
    from rebuild.sql_ide.migrations import SQL_IDE_ALL_MIGRATIONS, SqlIdeMigrationRunner

    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        runner = SqlIdeMigrationRunner(engine, SQL_IDE_ALL_MIGRATIONS)
        first = runner.apply()
        second = runner.apply()

        assert first.applied[-1:] == ("sql_ide_0003_history_scripts",)
        assert second.skipped[-1:] == ("sql_ide_0003_history_scripts",)
        schema = inspect(engine)
        assert schema.has_table("sql_ide_history")
        assert schema.has_table("sql_ide_scripts")
        assert schema.has_table("sql_ide_history_audit")
    finally:
        engine.dispose()
