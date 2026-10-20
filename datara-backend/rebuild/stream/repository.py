"""R8-STREAM repository — job state machine, checkpoints, snapshots, failures.

Contract source: design §8 (observation chain) + §13.7 (runtime tables, eight
states). The state machine is a closed transition table: every state change
must go through ``transition`` and a legal (state, action) pair; anything else
raises :class:`StreamDomainError` (4002 illegal transition).

Observation aggregation (``observe``) returns the §8 metric set: rates,
input/output/success/failure/skipped/duplicate counts, backlog, offset and
window result come from the latest snapshot in the window verbatim; the error
sample count is aggregated from stream_failure_event rows in the window.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rebuild.stream.models import (
    StreamCheckpointRecord,
    StreamFailureEventRecord,
    StreamJobAttemptRecord,
    StreamJobRecord,
    StreamMetricSnapshotRecord,
    StreamRecoveryEventRecord,
)
from rebuild.stream.producer_schema import validate_runtime_config

STREAM_STATES = ("CREATED", "STARTING", "RUNNING", "PAUSED", "STOPPING", "STOPPED", "FAILED", "RECOVERING")

# (current_state, action) -> next_state. Restarting from STOPPED/FAILED opens a
# new attempt (attempt_no increments); only STARTING→RUNNING confirms liveness.
STREAM_TRANSITIONS: dict[tuple[str, str], str] = {
    ("CREATED", "start"): "STARTING",
    ("STARTING", "activate"): "RUNNING",
    ("STARTING", "stop"): "STOPPING",
    ("STARTING", "fail"): "FAILED",
    ("RUNNING", "pause"): "PAUSED",
    ("RUNNING", "recover"): "RECOVERING",
    ("RUNNING", "stop"): "STOPPING",
    ("RUNNING", "fail"): "FAILED",
    ("PAUSED", "resume"): "RUNNING",
    ("PAUSED", "recover"): "RECOVERING",
    ("PAUSED", "stop"): "STOPPING",
    ("PAUSED", "fail"): "FAILED",
    ("RECOVERING", "activate"): "RUNNING",
    ("RECOVERING", "stop"): "STOPPING",
    ("RECOVERING", "fail"): "FAILED",
    ("STOPPING", "complete_stop"): "STOPPED",
    ("STOPPING", "fail"): "FAILED",
    ("STOPPED", "start"): "STARTING",
    ("FAILED", "start"): "STARTING",
    ("FAILED", "recover"): "RECOVERING",
}


class StreamDomainError(ValueError):
    def __init__(self, code: int, msg: str) -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg


def _runtime_config_json(runtime_config: dict[str, Any] | str | None) -> str:
    if runtime_config is None:
        return "{}"
    if isinstance(runtime_config, str):
        json.loads(runtime_config)  # reject malformed JSON storage early
        return runtime_config
    return json.dumps(runtime_config, ensure_ascii=False)


def _optional_json(payload: str | None) -> dict[str, Any]:
    return json.loads(payload) if payload else {}


def _window_bound(bound: str) -> datetime:
    """Parse an ISO-8601 window bound into a datetime.

    String bounds must not be compared raw against DateTime columns: storage
    renders with a space separator while ISO uses 'T', so same-day windows
    would silently miss every row. Accept date-only (midnight) and datetime.
    """
    if not isinstance(bound, str) or not bound:
        raise StreamDomainError(4001, "window bounds must be ISO-8601 strings")
    try:
        return datetime.fromisoformat(bound)
    except ValueError:
        raise StreamDomainError(4001, f"invalid ISO-8601 window bound: {bound}")


class StreamRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # -- job lifecycle -------------------------------------------------------

    def register(
        self,
        name: str,
        workflow_id: int,
        mq_topic: str,
        runtime_config: dict[str, Any] | str | None = None,
        legacy_job_id: int | None = None,
    ) -> StreamJobRecord:
        if not name or not isinstance(name, str):
            raise StreamDomainError(4001, "name is required")
        if isinstance(workflow_id, bool) or not isinstance(workflow_id, int) or workflow_id <= 0:
            raise StreamDomainError(4001, "workflow_id must be a positive integer")
        if not mq_topic or not isinstance(mq_topic, str):
            raise StreamDomainError(4001, "mq_topic is required")
        if legacy_job_id is not None and (isinstance(legacy_job_id, bool) or not isinstance(legacy_job_id, int) or legacy_job_id <= 0):
            raise StreamDomainError(4001, "legacy_job_id must be a positive integer")
        if legacy_job_id is not None and self._session.scalar(
            select(StreamJobRecord.id).where(StreamJobRecord.legacy_job_id == legacy_job_id)
        ) is not None:
            raise StreamDomainError(4001, "legacy_job_id is already linked to another stream job")
        raw_config = runtime_config or {}
        if isinstance(raw_config, str):
            try:
                raw_config = json.loads(raw_config)
            except json.JSONDecodeError as exc:
                raise StreamDomainError(4001, "runtime_config must be valid JSON") from exc
        try:
            normalized_config = validate_runtime_config(raw_config)
        except (TypeError, ValueError) as exc:
            raise StreamDomainError(4001, f"invalid runtime_config: {exc}") from exc
        record = StreamJobRecord(
            name=name,
            workflow_id=workflow_id,
            legacy_job_id=legacy_job_id,
            mq_topic=mq_topic,
            runtime_config=_runtime_config_json(normalized_config),
            state="CREATED",
        )
        self._session.add(record)
        self._session.flush()
        return record

    def get_job(self, job_id: int) -> StreamJobRecord:
        record = self._session.get(StreamJobRecord, job_id)
        if record is None:
            raise StreamDomainError(4041, f"stream job {job_id} not found")
        return record

    def list_jobs(self) -> list[dict[str, Any]]:
        rows = self._session.scalars(select(StreamJobRecord).order_by(StreamJobRecord.id))
        return [self.job_payload(row) for row in rows]

    def transition(self, job_id: int, action: str, *, event_time: datetime | None = None) -> StreamJobRecord:
        record = self.get_job(job_id)
        source = record.state
        target = STREAM_TRANSITIONS.get((source, action))
        if target is None:
            raise StreamDomainError(4002, f"illegal transition {source} --{action}--> ?")
        now = event_time or datetime.now()
        updates: dict[str, Any] = {"state": target}
        if action == "start":
            updates.update(attempt_no=record.attempt_no + 1, started_at=now, finished_at=None)
        elif action in {"complete_stop", "fail"}:
            updates["finished_at"] = now
        # Compare-and-set on the previous state so racing transitions cannot
        # both succeed after reading the same state.
        result = self._session.query(StreamJobRecord).filter(
            StreamJobRecord.id == job_id, StreamJobRecord.state == source
        ).update(updates, synchronize_session=False)
        if result != 1:
            raise StreamDomainError(4002, "concurrent state transition; reload and retry")
        self._session.refresh(record)
        if action == "start":
            # DEP-05: persist the new attempt slice in the independent table;
            # stream_job.attempt_no stays the current-attempt pointer.
            self._session.add(StreamJobAttemptRecord(
                job_id=job_id,
                attempt_no=record.attempt_no,
                status="STARTING",
                started_at=now,
            ))
        elif record.attempt_no > 0:
            self._session.query(StreamJobAttemptRecord).filter(
                StreamJobAttemptRecord.job_id == job_id,
                StreamJobAttemptRecord.attempt_no == record.attempt_no,
            ).update(
                {"status": target, "finished_at": now if action in {"complete_stop", "fail"} else None},
                synchronize_session=False,
            )
        if target == "RECOVERING" or (source == "RECOVERING" and target == "RUNNING"):
            self._session.add(StreamRecoveryEventRecord(
                job_id=job_id,
                kind="recovery-started" if target == "RECOVERING" else "recovery-completed",
                detail=f"{source} --{action}--> {target}",
                event_time=now,
            ))
        self._session.flush()
        if source == "RECOVERING" and target == "RUNNING":
            from rebuild.stream.alert import evaluate_failure_alert
            evaluate_failure_alert(self._session, job_id, now=now)
        return record

    @staticmethod
    def job_payload(record: StreamJobRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "name": record.name,
            "workflow_id": record.workflow_id,
            "legacy_job_id": record.legacy_job_id,
            "mq_topic": record.mq_topic,
            "runtime_config": _optional_json(record.runtime_config),
            "state": record.state,
            "attempt_no": record.attempt_no,
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "finished_at": record.finished_at.isoformat() if record.finished_at else None,
        }

    # -- checkpoints ----------------------------------------------------------

    def write_checkpoint(
        self,
        job_id: int,
        partition_id: str,
        offset_value: int,
        payload: dict[str, Any] | str | None,
        event_time: datetime,
    ) -> StreamCheckpointRecord:
        self.get_job(job_id)
        if not partition_id or not isinstance(partition_id, str):
            raise StreamDomainError(4001, "partition_id is required")
        if isinstance(offset_value, bool) or not isinstance(offset_value, int) or offset_value < 0:
            raise StreamDomainError(4001, "offset_value must be a non-negative integer")
        if isinstance(payload, str):
            json.loads(payload)
            stored = payload
        else:
            stored = json.dumps(payload or {}, ensure_ascii=False)
        record = StreamCheckpointRecord(
            job_id=job_id,
            partition_id=partition_id,
            offset_value=offset_value,
            payload=stored,
            event_time=event_time,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def latest_checkpoint(self, job_id: int, partition_id: str) -> dict[str, Any] | None:
        """Recovery read: newest checkpoint row for one partition."""
        self.get_job(job_id)
        record = self._session.scalar(
            select(StreamCheckpointRecord)
            .where(StreamCheckpointRecord.job_id == job_id, StreamCheckpointRecord.partition_id == partition_id)
            .order_by(StreamCheckpointRecord.event_time.desc(), StreamCheckpointRecord.id.desc())
            .limit(1)
        )
        return self._checkpoint_payload(record) if record is not None else None

    def latest_checkpoints(self, job_id: int) -> list[dict[str, Any]]:
        """Recovery read: newest checkpoint row per partition (all partitions)."""
        self.get_job(job_id)
        rows = self._session.scalars(
            select(StreamCheckpointRecord)
            .where(StreamCheckpointRecord.job_id == job_id)
            .order_by(StreamCheckpointRecord.partition_id, StreamCheckpointRecord.event_time, StreamCheckpointRecord.id)
        )
        newest: dict[str, StreamCheckpointRecord] = {}
        for row in rows:
            newest[row.partition_id] = row
        return [self._checkpoint_payload(newest[key]) for key in sorted(newest)]

    def list_attempts(self, job_id: int) -> list[dict[str, Any]]:
        """Read attempt slices from the independent stream_job_attempt table.

        DEP-05 (user ruling 方案 A): attempt history lives in its own table,
        oldest attempt first; the folded stream_job.attempt_no counter is no
        longer the read source.
        """
        self.get_job(job_id)
        rows = self._session.scalars(
            select(StreamJobAttemptRecord)
            .where(StreamJobAttemptRecord.job_id == job_id)
            .order_by(StreamJobAttemptRecord.attempt_no)
        ).all()
        return [
            {
                "job_id": row.job_id,
                "attempt_id": row.attempt_no,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "ended_at": row.finished_at.isoformat() if row.finished_at else None,
                "exit_reason": row.status if row.status in {"STOPPED", "FAILED"} else None,
            }
            for row in rows
        ]

    def list_metric_points(self, job_id: int, window_from: str, window_to: str, limit: int = 100) -> list[dict[str, Any]]:
        self.get_job(job_id)
        start, end = _window_bound(window_from), _window_bound(window_to)
        rows = self._session.scalars(
            select(StreamMetricSnapshotRecord)
            .where(StreamMetricSnapshotRecord.job_id == job_id,
                   StreamMetricSnapshotRecord.captured_at >= start,
                   StreamMetricSnapshotRecord.captured_at <= end)
            .order_by(StreamMetricSnapshotRecord.captured_at, StreamMetricSnapshotRecord.id)
            .offset(0).limit(max(0, min(limit, 500)))
        )
        fields = ("produce_rate", "consume_rate", "process_rate", "input_count", "output_count",
                  "success_count", "failure_count", "skipped_count", "duplicate_count", "backlog", "offset_value")
        return [{"job_id": row.job_id, "metric": field, "value": getattr(row, field),
                 "captured_at": row.captured_at.isoformat()}
                for row in rows for field in fields]

    def list_recovery_events(self, job_id: int, window_from: str, window_to: str, limit: int = 100) -> list[dict[str, Any]]:
        self.get_job(job_id)
        start, end = _window_bound(window_from), _window_bound(window_to)
        rows = self._session.scalars(
            select(StreamRecoveryEventRecord)
            .where(StreamRecoveryEventRecord.job_id == job_id,
                   StreamRecoveryEventRecord.event_time >= start,
                   StreamRecoveryEventRecord.event_time <= end)
            .order_by(StreamRecoveryEventRecord.event_time, StreamRecoveryEventRecord.id)
            .limit(max(0, min(limit, 500)))
        )
        return [{"event_id": str(row.id), "job_id": row.job_id, "kind": row.kind,
                 "detail": row.detail, "occurred_at": row.event_time.isoformat()} for row in rows]

    @staticmethod
    def _checkpoint_payload(record: StreamCheckpointRecord) -> dict[str, Any]:
        return {
            "job_id": record.job_id,
            "partition_id": record.partition_id,
            "offset_value": record.offset_value,
            "payload": _optional_json(record.payload),
            "event_time": record.event_time.isoformat(),
        }

    # -- metric snapshots ------------------------------------------------------

    def append_metric_snapshot(self, job_id: int, metrics: dict[str, Any], captured_at: datetime) -> dict[str, Any]:
        job = self.get_job(job_id)
        window_result = metrics.get("window_result", {})
        snapshot = StreamMetricSnapshotRecord(
            job_id=job.id,
            attempt_no=int(metrics.get("attempt_no", job.attempt_no)),
            produce_rate=int(metrics.get("produce_rate", 0)),
            consume_rate=int(metrics.get("consume_rate", 0)),
            process_rate=int(metrics.get("process_rate", 0)),
            input_count=int(metrics.get("input_count", 0)),
            output_count=int(metrics.get("output_count", 0)),
            success_count=int(metrics.get("success_count", 0)),
            failure_count=int(metrics.get("failure_count", 0)),
            skipped_count=int(metrics.get("skipped_count", 0)),
            duplicate_count=int(metrics.get("duplicate_count", 0)),
            backlog=int(metrics.get("backlog", 0)),
            offset_value=int(metrics.get("offset_value", 0)),
            window_result=json.dumps(window_result, ensure_ascii=False),
            captured_at=captured_at,
        )
        self._session.add(snapshot)
        self._session.flush()
        return {
            "job_id": snapshot.job_id,
            "attempt_no": snapshot.attempt_no,
            "produce_rate": snapshot.produce_rate,
            "consume_rate": snapshot.consume_rate,
            "process_rate": snapshot.process_rate,
            "input_count": snapshot.input_count,
            "output_count": snapshot.output_count,
            "success_count": snapshot.success_count,
            "failure_count": snapshot.failure_count,
            "skipped_count": snapshot.skipped_count,
            "duplicate_count": snapshot.duplicate_count,
            "backlog": snapshot.backlog,
            "offset_value": snapshot.offset_value,
            "window_result": _optional_json(snapshot.window_result),
            "captured_at": snapshot.captured_at.isoformat(),
        }

    # -- failure events --------------------------------------------------------

    def record_failure(
        self,
        job_id: int,
        attempt_no: int,
        error_type: str,
        sample_data: dict[str, Any] | str,
        event_time: datetime,
    ) -> dict[str, Any]:
        self.get_job(job_id)
        if not error_type or not isinstance(error_type, str):
            raise StreamDomainError(4001, "error_type is required")
        if isinstance(sample_data, str):
            json.loads(sample_data)
            stored = sample_data
        else:
            stored = json.dumps(sample_data, ensure_ascii=False)
        record = StreamFailureEventRecord(
            job_id=job_id,
            attempt_no=int(attempt_no),
            error_type=error_type,
            sample_data=stored,
            event_time=event_time,
        )
        self._session.add(record)
        self._session.flush()
        # Keep threshold alerting on the write path: the evaluator only logs
        # locally and never performs an external notification request.
        from rebuild.stream.alert import evaluate_failure_alert
        evaluate_failure_alert(self._session, job_id, now=event_time)
        return {
            "job_id": record.job_id,
            "attempt_no": record.attempt_no,
            "error_type": record.error_type,
            "sample_data": _optional_json(record.sample_data),
            "event_time": record.event_time.isoformat(),
        }

    def list_failures(
        self, job_id: int, window_from: str, window_to: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Failure sample query: job rows in the window, oldest first."""
        self.get_job(job_id)
        bound_from, bound_to = _window_bound(window_from), _window_bound(window_to)
        rows = self._session.scalars(
            select(StreamFailureEventRecord)
            .where(
                StreamFailureEventRecord.job_id == job_id,
                StreamFailureEventRecord.event_time >= bound_from,
                StreamFailureEventRecord.event_time <= bound_to,
            )
            .order_by(StreamFailureEventRecord.event_time, StreamFailureEventRecord.id)
            .limit(limit)
        )
        return [
            {
                "job_id": row.job_id,
                "attempt_no": row.attempt_no,
                "error_type": row.error_type,
                "sample_data": _optional_json(row.sample_data),
                "event_time": row.event_time.isoformat(),
            }
            for row in rows
        ]

    # -- observation aggregation (design §8 metric set) ------------------------

    def observe(self, job_id: int, window_from: str, window_to: str) -> dict[str, Any]:
        """Aggregate the §8 observation metrics for one job over a window.

        Gauges/counters/window_result come from the latest snapshot verbatim;
        ``error_sample_count`` aggregates stream_failure_event rows in the
        window. No other derivation happens on either side.
        """
        job = self.get_job(job_id)
        bound_from, bound_to = _window_bound(window_from), _window_bound(window_to)
        latest = self._session.scalar(
            select(StreamMetricSnapshotRecord)
            .where(
                StreamMetricSnapshotRecord.job_id == job_id,
                StreamMetricSnapshotRecord.captured_at >= bound_from,
                StreamMetricSnapshotRecord.captured_at <= bound_to,
            )
            .order_by(StreamMetricSnapshotRecord.captured_at.desc(), StreamMetricSnapshotRecord.id.desc())
            .limit(1)
        )
        snapshot_count = self._session.scalar(
            select(func.count())
            .select_from(StreamMetricSnapshotRecord)
            .where(
                StreamMetricSnapshotRecord.job_id == job_id,
                StreamMetricSnapshotRecord.captured_at >= bound_from,
                StreamMetricSnapshotRecord.captured_at <= bound_to,
            )
        )
        error_sample_count = self._session.scalar(
            select(func.count())
            .select_from(StreamFailureEventRecord)
            .where(
                StreamFailureEventRecord.job_id == job_id,
                StreamFailureEventRecord.event_time >= bound_from,
                StreamFailureEventRecord.event_time <= bound_to,
            )
        )
        error_samples = self.list_failures(job_id, window_from, window_to, limit=20)
        payload: dict[str, Any] = {
            "job_id": job.id,
            "name": job.name,
            "state": job.state,
            "attempt_no": job.attempt_no,
            "snapshot_count": int(snapshot_count or 0),
            "error_sample_count": int(error_sample_count or 0),
            "error_samples": error_samples,
        }
        if latest is not None:
            payload.update(
                {
                    "produce_rate": latest.produce_rate,
                    "consume_rate": latest.consume_rate,
                    "process_rate": latest.process_rate,
                    "input_count": latest.input_count,
                    "output_count": latest.output_count,
                    "success_count": latest.success_count,
                    "failure_count": latest.failure_count,
                    "skipped_count": latest.skipped_count,
                    "duplicate_count": latest.duplicate_count,
                    "backlog": latest.backlog,
                    "offset_value": latest.offset_value,
                    "window_result": _optional_json(latest.window_result),
                    "captured_at": latest.captured_at.isoformat(),
                }
            )
        else:
            payload.update(
                {
                    "produce_rate": 0,
                    "consume_rate": 0,
                    "process_rate": 0,
                    "input_count": 0,
                    "output_count": 0,
                    "success_count": 0,
                    "failure_count": 0,
                    "skipped_count": 0,
                    "duplicate_count": 0,
                    "backlog": 0,
                    "offset_value": 0,
                    "window_result": {},
                    "captured_at": None,
                }
            )
        return payload
