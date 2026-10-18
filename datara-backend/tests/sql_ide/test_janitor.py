from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from rebuild.sql_ide.janitor import cleanup_sweep, register_cleanup_sweep
from rebuild.sql_ide.result_store import PersistentExportJobStore, PersistentResultPageStore
from rebuild.sql_ide.snapshots import SqlIdeEventStore
from rebuild.sql_ide.status_store import SqlIdeStatusStore
from rebuild.common.db import Base


class CleanupStore:
    def __init__(self, result: int) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    def cleanup_expired(self, **kwargs: object) -> int:
        self.calls.append(kwargs)
        return self.result


@pytest.fixture
def stores() -> dict[str, CleanupStore]:
    return {
        "snapshots": CleanupStore(1),
        "events": CleanupStore(2),
        "exports": CleanupStore(3),
        "statuses": CleanupStore(4),
    }


def test_cleanup_sweep_delegates_to_existing_stores_with_one_clock(stores):
    now = datetime(2026, 10, 19, 1, 2, 3, tzinfo=timezone.utc)

    cleaned = cleanup_sweep(
        snapshot_store=stores["snapshots"],
        event_store=stores["events"],
        export_store=stores["exports"],
        status_store=stores["statuses"],
        now=now,
    )

    assert cleaned == {"snapshots": 1, "events": 2, "exports": 3, "statuses": 4}
    assert stores["snapshots"].calls == [{"now": now}]
    assert stores["events"].calls == [{"now": now}]
    assert stores["exports"].calls == [{"before": "2026-10-19T01:02:03Z"}]
    assert stores["statuses"].calls == [{"now": now}]


def test_register_cleanup_sweep_adds_periodic_job(stores):
    class Scheduler:
        def __init__(self) -> None:
            self.jobs = []

        def add_job(self, func, **kwargs) -> None:
            self.jobs.append((func, kwargs))

    scheduler = Scheduler()
    job = register_cleanup_sweep(
        scheduler,
        snapshot_store=stores["snapshots"],
        event_store=stores["events"],
        export_store=stores["exports"],
        status_store=stores["statuses"],
        interval_seconds=900,
    )

    assert len(scheduler.jobs) == 1
    callback, options = scheduler.jobs[0]
    assert callback is job
    assert options == {
        "trigger": "interval",
        "seconds": 900,
        "id": "sql_ide_cleanup_sweep",
        "replace_existing": True,
    }
    assert callback() == {"snapshots": 1, "events": 2, "exports": 3, "statuses": 4}


@pytest.mark.parametrize("interval_seconds", [0, -1, 1.5, True])
def test_register_cleanup_sweep_rejects_invalid_interval(stores, interval_seconds):
    class Scheduler:
        def add_job(self, func, **kwargs) -> None:
            pytest.fail("invalid schedule must not be registered")

    with pytest.raises(ValueError):
        register_cleanup_sweep(
            Scheduler(),
            snapshot_store=stores["snapshots"],
            event_store=stores["events"],
            export_store=stores["exports"],
            status_store=stores["statuses"],
            interval_seconds=interval_seconds,
        )


def test_cleanup_sweep_propagates_store_failure(stores):
    class BrokenStore:
        def cleanup_expired(self, **kwargs: object) -> int:
            raise RuntimeError("storage unavailable")

    with pytest.raises(RuntimeError, match="storage unavailable"):
        cleanup_sweep(
            snapshot_store=stores["snapshots"],
            event_store=BrokenStore(),
            export_store=stores["exports"],
            status_store=stores["statuses"],
            now=datetime(2026, 10, 19, tzinfo=timezone.utc),
        )


def test_cleanup_sweep_applies_store_retention_boundaries():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    snapshots = PersistentResultPageStore(session_factory=sessions)
    exports = PersistentExportJobStore(session_factory=sessions)
    events = SqlIdeEventStore(session_factory=sessions)
    statuses = SqlIdeStatusStore(session_factory=sessions)
    origin = datetime(2026, 10, 19, tzinfo=timezone.utc)

    snapshots.save_snapshot(
        project_id=1,
        user_id=2,
        history_id="janitor-retention",
        stmt_index=0,
        columns=["value"],
        rows=[[1]],
        now=origin,
    )
    exports.create_job(
        project_id=1,
        user_id=2,
        task_id="janitor-export",
        format="csv",
        row_count=1,
        byte_count=1,
        now=origin,
    )
    events.append(event_type="janitor-retention", payload={}, now=origin)
    statuses.start_execution(
        task_id="janitor-status",
        project_id=1,
        user_id=2,
        status="running",
        now=origin,
    )

    at_59m = datetime(2026, 10, 19, 0, 59, tzinfo=timezone.utc)
    assert cleanup_sweep(
        snapshot_store=snapshots,
        event_store=events,
        export_store=exports,
        status_store=statuses,
        now=at_59m,
    ) == {"snapshots": 0, "events": 0, "exports": 0, "statuses": 0}

    at_1h = datetime(2026, 10, 19, 1, tzinfo=timezone.utc)
    assert cleanup_sweep(
        snapshot_store=snapshots,
        event_store=events,
        export_store=exports,
        status_store=statuses,
        now=at_1h,
    ) == {"snapshots": 0, "events": 0, "exports": 1, "statuses": 0}

    at_24h = datetime(2026, 10, 20, tzinfo=timezone.utc)
    assert cleanup_sweep(
        snapshot_store=snapshots,
        event_store=events,
        export_store=exports,
        status_store=statuses,
        now=at_24h,
    ) == {"snapshots": 1, "events": 0, "exports": 0, "statuses": 0}

    at_7d = datetime(2026, 10, 26, tzinfo=timezone.utc)
    assert cleanup_sweep(
        snapshot_store=snapshots,
        event_store=events,
        export_store=exports,
        status_store=statuses,
        now=at_7d,
    ) == {"snapshots": 0, "events": 1, "exports": 0, "statuses": 0}

    at_365d = datetime(2027, 10, 19, tzinfo=timezone.utc)
    assert cleanup_sweep(
        snapshot_store=snapshots,
        event_store=events,
        export_store=exports,
        status_store=statuses,
        now=at_365d,
    ) == {"snapshots": 0, "events": 0, "exports": 0, "statuses": 1}

