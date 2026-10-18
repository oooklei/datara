from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


def test_event_store_appends_events_and_expires_after_seven_days():
    from rebuild.common.db import Base
    from rebuild.sql_ide.snapshots import EVENT_TTL, SqlIdeEventRecord, SqlIdeEventStore

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    store = SqlIdeEventStore(session_factory=sessions)
    now = datetime(2026, 10, 19, tzinfo=timezone.utc)
    try:
        event_id = store.append(event_type="query.completed", payload={"task_id": "q-1"}, now=now)
        with sessions() as session:
            event = session.get(SqlIdeEventRecord, event_id)
            assert event.created_at == now.replace(tzinfo=None)
            assert event.expires_at == (now + timedelta(days=7)).replace(tzinfo=None)
            assert event.payload == {"task_id": "q-1"}
            assert len(session.scalars(select(SqlIdeEventRecord)).all()) == 1
        assert EVENT_TTL == timedelta(days=7)
        assert store.cleanup_expired(now=now + timedelta(days=8)) == 1
    finally:
        engine.dispose()


def test_result_and_export_store_public_names_are_available():
    from rebuild.sql_ide.snapshots import ExportJobStore, ResultPageStore

    assert ResultPageStore is not None
    assert ExportJobStore is not None
