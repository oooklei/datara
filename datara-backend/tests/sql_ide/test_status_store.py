from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import inspect

from rebuild.common.db import Base
from rebuild.sql_ide.migrations import SQL_IDE_ALL_MIGRATIONS, SQL_IDE_STATUS_MIGRATIONS, SqlIdeMigrationRunner
from rebuild.sql_ide.status_store import (
    EXECUTION_EVENT_TTL,
    EXECUTION_STATUS_TTL,
    SqlIdeExecutionEventRecord,
    SqlIdeExecutionRecord,
    SqlIdeStatusStore,
)


@pytest.fixture
def status_store():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[
        SqlIdeExecutionRecord.__table__, SqlIdeExecutionEventRecord.__table__
    ])
    factory = sessionmaker(engine, expire_on_commit=False)
    yield SqlIdeStatusStore(session_factory=factory)
    engine.dispose()


def test_status_and_events_are_scoped_to_project_and_user(status_store):
    task_id = status_store.start_execution(
        task_id="task-a", project_id=7, user_id=11, status="running",
        now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    status_store.append_event(
        task_id=task_id, project_id=7, user_id=11, event_type="statement.started",
        payload={"statement": 1}, now=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    owned = status_store.get_execution_status(task_id=task_id, project_id=7, user_id=11)
    assert owned["status"] == "running"
    assert status_store.list_execution_events(
        task_id=task_id, project_id=7, user_id=11
    )[0]["event_type"] == "statement.started"

    # A foreign project or user sees the same unavailable response as an unknown id.
    assert status_store.get_execution_status(
        task_id=task_id, project_id=8, user_id=11
    ) is None
    assert status_store.get_execution_status(
        task_id=task_id, project_id=7, user_id=12
    ) is None
    assert status_store.get_execution_status(
        task_id="missing", project_id=7, user_id=11
    ) is None
    assert status_store.list_execution_events(
        task_id=task_id, project_id=8, user_id=11
    ) == []
    assert status_store.list_execution_events(
        task_id=task_id, project_id=7, user_id=12
    ) == []


def test_execution_status_is_retained_for_365_days(status_store):
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    task_id = status_store.start_execution(
        task_id="task-expiry", project_id=1, user_id=2, status="queued", now=created,
    )
    assert EXECUTION_STATUS_TTL == timedelta(days=365)
    row = status_store.get_execution_record(task_id=task_id, project_id=1, user_id=2)
    assert row is not None
    assert row.expires_at == datetime(2027, 1, 1)

    assert status_store.get_execution_status(
        task_id=task_id, project_id=1, user_id=2,
        now=created + timedelta(days=365),
    ) is None
    assert status_store.cleanup_expired(now=created + timedelta(days=365)) == 1


def test_events_expire_seven_days_after_terminal_status_not_event_creation(status_store):
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    task_id = status_store.start_execution(
        task_id="task-terminal", project_id=3, user_id=4, status="running", now=created,
    )
    status_store.append_event(
        task_id=task_id, project_id=3, user_id=4, event_type="statement.started",
        payload={"statement": 1}, now=created,
    )
    event = status_store.list_execution_events(
        task_id=task_id, project_id=3, user_id=4, now=created + timedelta(days=30),
    )
    assert [row["event_type"] for row in event] == ["statement.started"]

    terminal = created + timedelta(days=30)
    assert status_store.update_status(
        task_id=task_id, project_id=3, user_id=4, status="succeeded", now=terminal,
    )
    assert EXECUTION_EVENT_TTL == timedelta(days=7)
    assert status_store.append_event(
        task_id=task_id, project_id=3, user_id=4, event_type="done",
        payload={"history_id": "history-a"}, now=terminal,
    )
    rows = status_store.get_execution_record(task_id=task_id, project_id=3, user_id=4)
    assert rows is not None
    assert rows.terminal_at == datetime(2026, 1, 31)
    assert status_store.update_status(
        task_id=task_id, project_id=3, user_id=4, status="failed", now=terminal + timedelta(seconds=1),
    ) is False
    assert status_store.get_execution_status(
        task_id=task_id, project_id=3, user_id=4,
    )["status"] == "succeeded"

    event_rows = status_store.list_execution_events(
        task_id=task_id, project_id=3, user_id=4, now=terminal + timedelta(days=6, hours=23),
    )
    assert len(event_rows) == 2
    assert status_store.list_execution_events(
        task_id=task_id, project_id=3, user_id=4, now=terminal + timedelta(days=7),
    ) == []
    # Event expiry must not shorten the independent 365-day status record.
    assert status_store.get_execution_status(
        task_id=task_id, project_id=3, user_id=4, now=terminal + timedelta(days=7),
    ) is not None


def test_event_query_is_ordered_and_paginated(status_store):
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    task_id = status_store.start_execution(
        task_id="task-page", project_id=1, user_id=2, status="running", now=now,
    )
    for index in range(3):
        status_store.append_event(
            task_id=task_id, project_id=1, user_id=2, event_type="step",
            payload={"index": index}, now=now + timedelta(seconds=index),
        )

    page = status_store.list_execution_events(
        task_id=task_id, project_id=1, user_id=2, limit=2, offset=1,
    )
    assert [event["payload"]["index"] for event in page] == [1, 2]

    with pytest.raises(ValueError):
        status_store.list_execution_events(task_id=task_id, project_id=1, user_id=2, limit=0)


def test_status_events_migration_is_0004_and_creates_both_tables():
    engine = create_engine("sqlite:///:memory:")
    result = SqlIdeMigrationRunner(engine, SQL_IDE_STATUS_MIGRATIONS).apply()

    assert SQL_IDE_STATUS_MIGRATIONS[0].revision == "sql_ide_0004_status_events"
    assert SQL_IDE_ALL_MIGRATIONS[-1].revision == "sql_ide_0004_status_events"
    assert result.applied == ("sql_ide_0004_status_events",)
    assert {"sql_ide_execution_status", "sql_ide_execution_events"}.issubset(
        set(inspect(engine).get_table_names())
    )
    status_columns = {column["name"]: column for column in inspect(engine).get_columns("sql_ide_execution_status")}
    event_columns = {column["name"]: column for column in inspect(engine).get_columns("sql_ide_execution_events")}
    assert "terminal_at" in status_columns
    assert event_columns["expires_at"]["nullable"] is True
    engine.dispose()
