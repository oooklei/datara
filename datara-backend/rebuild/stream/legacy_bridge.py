"""Explicit mapping between the rebuild stream domain and legacy worker states."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from functools import lru_cache
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from rebuild.common.db import configure_engine
from rebuild.stream.models import StreamJobRecord
from rebuild.stream.repository import StreamDomainError, StreamRepository

logger = logging.getLogger("rebuild.stream.legacy_bridge")

STREAM_TO_LEGACY = {
    "CREATED": "stopped",
    "STARTING": "starting",
    "RUNNING": "running",
    "PAUSED": "stopped",
    "STOPPING": "stopped",
    "STOPPED": "stopped",
    "FAILED": "failed",
    "RECOVERING": "reconnecting",
}

LEGACY_TO_STREAM = {
    "starting": "STARTING",
    "running": "RUNNING",
    "reconnecting": "RECOVERING",
    "stopped": "STOPPED",
    "failed": "FAILED",
}

# Legacy WorkflowInstance states are a distinct enum; use one shared mapping
# for the engine's monitoring projection.
LEGACY_TO_WORKFLOW_INSTANCE = {
    "starting": "submitted",
    "running": "running",
    "reconnecting": "running",
    "stopped": "kill",
    "failed": "failure",
}


def to_legacy_state(state: str) -> str:
    try:
        return STREAM_TO_LEGACY[state.upper()]
    except (KeyError, AttributeError) as exc:
        raise ValueError(f"unknown stream state: {state}") from exc


def from_legacy_state(state: str) -> str:
    try:
        return LEGACY_TO_STREAM[state.lower()]
    except (KeyError, AttributeError) as exc:
        raise ValueError(f"unknown legacy stream state: {state}") from exc


@lru_cache(maxsize=2)
def _factory(url: str) -> sessionmaker:
    engine: Engine = configure_engine(url)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _session_factory() -> sessionmaker | None:
    url = os.environ.get("REBUILD_DB_URL", "").strip()
    return _factory(url) if url else None


def _mapped_job(session, legacy_job_id: int) -> StreamJobRecord | None:
    inspector = inspect(session.get_bind())
    if not inspector.has_table("stream_job"):
        return None
    columns = {item["name"] for item in inspector.get_columns("stream_job")}
    if "legacy_job_id" not in columns:
        return None
    return session.scalar(select(StreamJobRecord).where(StreamJobRecord.legacy_job_id == legacy_job_id))


def _move_to(repo: StreamRepository, job_id: int, target: str, event_time: datetime) -> None:
    job = repo.get_job(job_id)
    state = job.state
    if state == target:
        return
    if target == "STARTING":
        if state in {"CREATED", "STOPPED", "FAILED"}:
            repo.transition(job_id, "start", event_time=event_time)
        return
    if target == "RUNNING":
        if state in {"CREATED", "STOPPED", "FAILED"}:
            repo.transition(job_id, "start", event_time=event_time)
            state = "STARTING"
        if state in {"STARTING", "RECOVERING"}:
            repo.transition(job_id, "activate", event_time=event_time)
        elif state == "PAUSED":
            repo.transition(job_id, "resume", event_time=event_time)
        return
    if target == "RECOVERING":
        if state in {"FAILED"}:
            repo.transition(job_id, "recover", event_time=event_time)
        elif state in {"RUNNING", "PAUSED"}:
            repo.transition(job_id, "recover", event_time=event_time)
        return
    if target == "STOPPED":
        if state == "FAILED":
            repo.transition(job_id, "recover", event_time=event_time)
            state = "RECOVERING"
        if state == "CREATED":
            repo.transition(job_id, "start", event_time=event_time)
            state = "STARTING"
        if state in {"STARTING", "RUNNING", "PAUSED", "RECOVERING"}:
            repo.transition(job_id, "stop", event_time=event_time)
            state = "STOPPING"
        if state == "STOPPING":
            repo.transition(job_id, "complete_stop", event_time=event_time)
        return
    if target == "FAILED":
        if state in {"CREATED", "STOPPED"}:
            repo.transition(job_id, "start", event_time=event_time)
            state = "STARTING"
        if state in {"STARTING", "RUNNING", "PAUSED", "RECOVERING", "STOPPING"}:
            repo.transition(job_id, "fail", event_time=event_time)


def sync_legacy_state(legacy_job_id: int, legacy_state: str, *, event_time: datetime | None = None) -> bool:
    """Mirror status only when an explicit, persisted legacy ID crosswalk exists."""
    target = from_legacy_state(legacy_state)
    factory = _session_factory()
    if factory is None:
        return False
    with factory() as session:
        job = _mapped_job(session, legacy_job_id)
        if job is None:
            return False
        try:
            _move_to(StreamRepository(session), job.id, target, event_time or datetime.now())
            session.commit()
            return True
        except StreamDomainError as exc:
            session.rollback()
            logger.warning("legacy stream state mirror rejected: job=%s state=%s: %s", legacy_job_id, legacy_state, exc)
            return False


def sync_legacy_checkpoints(legacy_job_id: int, offsets: dict[str, dict], *, event_time: datetime | None = None) -> int:
    factory = _session_factory()
    if factory is None:
        return 0
    now = event_time or datetime.now()
    written = 0
    with factory() as session:
        job = _mapped_job(session, legacy_job_id)
        if job is None:
            return 0
        repo = StreamRepository(session)
        for source, payload in offsets.items():
            partitions = payload.get("partitions") if isinstance(payload, dict) else None
            entries = partitions.items() if isinstance(partitions, dict) else [(source, payload)]
            for partition, value in entries:
                numeric = value if isinstance(value, int) and not isinstance(value, bool) else None
                if isinstance(value, dict):
                    numeric = next((value[key] for key in ("offset", "pos", "log_pos", "cursor")
                                    if isinstance(value.get(key), int) and not isinstance(value.get(key), bool)), 0)
                repo.write_checkpoint(job.id, f"{source}:{partition}", max(0, numeric or 0),
                                      {"legacy_source": source, "offset": value}, now)
                written += 1
        session.commit()
    return written


def sync_legacy_metrics(legacy_job_id: int, metrics: dict[str, Any], *, captured_at: datetime | None = None) -> bool:
    factory = _session_factory()
    if factory is None:
        return False
    with factory() as session:
        job = _mapped_job(session, legacy_job_id)
        if job is None:
            return False
        payload = {key: metrics.get(key, 0) for key in (
            "produce_rate", "consume_rate", "process_rate", "input_count", "output_count",
            "success_count", "failure_count", "skipped_count", "duplicate_count", "backlog", "offset_value",
        )}
        payload.update(attempt_no=job.attempt_no, window_result=metrics.get("window_result", {}))
        StreamRepository(session).append_metric_snapshot(job.id, payload, captured_at or datetime.now())
        session.commit()
        return True


def sync_legacy_failure(legacy_job_id: int, error_type: str, sample: dict[str, Any], *, event_time: datetime | None = None) -> bool:
    factory = _session_factory()
    if factory is None:
        return False
    with factory() as session:
        job = _mapped_job(session, legacy_job_id)
        if job is None:
            return False
        StreamRepository(session).record_failure(job.id, job.attempt_no, error_type[:64] or "STREAM_ERROR", sample,
                                                 event_time or datetime.now())
        session.commit()
        return True
