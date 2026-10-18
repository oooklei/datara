"""Coordinate expiry cleanup across the SQL IDE stores.

Each store remains responsible for its retention rules and deletion logic. This
module only provides one sweep entry point and an adapter for interval schedulers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Protocol


class _NowCleanupStore(Protocol):
    def cleanup_expired(self, *, now: datetime | None = None) -> int: ...


class _BeforeCleanupStore(Protocol):
    def cleanup_expired(self, *, before: str) -> int: ...


class _IntervalScheduler(Protocol):
    def add_job(self, func: Callable[[], dict[str, int]], **kwargs: Any) -> Any: ...


def cleanup_sweep(
    *,
    snapshot_store: _NowCleanupStore,
    event_store: _NowCleanupStore,
    export_store: _BeforeCleanupStore,
    status_store: _NowCleanupStore,
    now: datetime | None = None,
) -> dict[str, int]:
    """Run the existing expiry cleanup methods and return deleted row counts.

    A shared timestamp makes the sweep deterministic at retention boundaries.
    Export jobs currently expose the established ``before`` ISO-8601 contract;
    the other stores accept ``now`` directly.
    """
    current = now or datetime.now(timezone.utc)
    return {
        "snapshots": snapshot_store.cleanup_expired(now=current),
        "events": event_store.cleanup_expired(now=current),
        "exports": export_store.cleanup_expired(before=_iso_utc(current)),
        "statuses": status_store.cleanup_expired(now=current),
    }


def register_cleanup_sweep(
    scheduler: _IntervalScheduler,
    *,
    snapshot_store: _NowCleanupStore,
    event_store: _NowCleanupStore,
    export_store: _BeforeCleanupStore,
    status_store: _NowCleanupStore,
    interval_seconds: int = 3600,
) -> Callable[[], dict[str, int]]:
    """Register and return a periodic SQL IDE cleanup callback.

    ``scheduler`` is an APScheduler-compatible object with ``add_job``; keeping
    it injected avoids coupling the janitor to a particular scheduler package.
    """
    if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, int) or interval_seconds <= 0:
        raise ValueError("interval_seconds must be a positive integer")

    def run() -> dict[str, int]:
        return cleanup_sweep(
            snapshot_store=snapshot_store,
            event_store=event_store,
            export_store=export_store,
            status_store=status_store,
        )

    scheduler.add_job(
        run,
        trigger="interval",
        seconds=interval_seconds,
        id="sql_ide_cleanup_sweep",
        replace_existing=True,
    )
    return run


def _iso_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")
