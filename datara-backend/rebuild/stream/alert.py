"""Threshold-based stream failure alert policy (logging only, no external calls)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from rebuild.stream.repository import StreamRepository

logger = logging.getLogger("rebuild.stream.alert")


def evaluate_failure_alert(session: Session, job_id: int, *, now: datetime | None = None) -> dict[str, Any]:
    """Log an alert after three failures in five minutes; recovery clears it."""
    now = now or datetime.now()
    start = now - timedelta(minutes=5)
    repo = StreamRepository(session)
    failures = repo.list_failures(job_id, start.isoformat(), now.isoformat(), limit=500)
    events = repo.list_recovery_events(job_id, start.isoformat(), now.isoformat(), limit=500)
    last_failure = max((row["event_time"] for row in failures), default="")
    last_recovery = max(
        (event["occurred_at"] for event in events if event["kind"] == "recovery-completed"),
        default="",
    )
    recovered = bool(last_recovery and last_recovery > last_failure)
    active = len(failures) >= 3 and not recovered
    result = {"job_id": job_id, "failure_count": len(failures), "active": active, "cleared_by_recovery": recovered}
    if active:
        logger.error("stream failure threshold reached: job=%s failures=%s window=5m", job_id, len(failures))
    elif recovered:
        logger.info("stream failure alert cleared after recovery: job=%s", job_id)
    return result
