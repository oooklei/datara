"""Durable backfill batch state and date expansion.

The service owns scheduling semantics while the supplied store owns persistence.
Runs are linked to their batch before being returned to a caller, so a snapshot
reloaded into a new service retains both progress and run-to-batch identity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Protocol
from uuid import uuid4


class BackfillValidationError(ValueError):
    """Raised when a backfill request cannot be scheduled safely."""


class ComplementBatchStore(Protocol):
    def record_batch(self, batch_id: str, batch: dict[str, Any]) -> None: ...

    def record_run(self, run_id: str, batch_id: str, run_date: str) -> None: ...


@dataclass
class BackfillBatch:
    batch_id: str
    workflow_code: int
    date_from: date
    date_to: date
    mode: str
    dates: list[date]
    execution_groups: list[list[date]]
    max_parallelism: int
    timezone: str = "Asia/Shanghai"
    completed_dates: set[date] = field(default_factory=set)
    pending_dates: list[date] = field(default_factory=list)
    failed_dates: set[date] = field(default_factory=set)
    active_dates: set[date] = field(default_factory=set)


@dataclass(frozen=True)
class BackfillRun:
    run_id: str
    batch_id: str
    run_date: date


class BackfillBatchService:
    """Create and advance serial or bounded-parallel date batches."""

    def __init__(self, store: ComplementBatchStore):
        self._store = store
        self._batches: dict[str, BackfillBatch] = {}
        self._runs: dict[str, tuple[str, date]] = {}

    def create(
        self,
        *,
        workflow_code: int,
        date_from: date,
        date_to: date,
        mode: str = "serial",
        parallelism: int = 1,
        timezone: str = "Asia/Shanghai",
    ) -> BackfillBatch:
        if date_to < date_from:
            raise BackfillValidationError("date_to must be on or after date_from")
        normalized_mode = mode.lower()
        if normalized_mode not in {"serial", "parallel"}:
            raise BackfillValidationError("mode must be serial or parallel")
        if normalized_mode == "parallel" and parallelism < 1:
            raise BackfillValidationError("parallelism must be at least 1")

        dates: list[date] = []
        current = date_from
        while current <= date_to:
            dates.append(current)
            current += timedelta(days=1)

        width = parallelism if normalized_mode == "parallel" else 1
        groups = [dates[index:index + width] for index in range(0, len(dates), width)]
        batch_id = str(uuid4())
        batch = BackfillBatch(
            batch_id=batch_id,
            workflow_code=workflow_code,
            date_from=date_from,
            date_to=date_to,
            mode=normalized_mode,
            dates=dates,
            execution_groups=groups,
            max_parallelism=width,
            timezone=timezone,
            pending_dates=list(dates),
        )
        self._batches[batch_id] = batch
        self._persist(batch)
        return batch

    def get(self, batch_id: str) -> BackfillBatch | None:
        if batch_id in self._batches:
            return self._batches[batch_id]
        persisted = self._store.get("batch", batch_id)  # type: ignore[attr-defined]
        if persisted is None:
            return None
        batch = self._restore(persisted)
        self._batches[batch_id] = batch
        return batch

    def start_next(self, batch_id: str) -> BackfillRun | None:
        batch = self.get(batch_id)
        if batch is None or batch.failed_dates or not batch.pending_dates:
            return None
        if len(batch.active_dates) >= batch.max_parallelism:
            return None
        run_date = batch.pending_dates.pop(0)
        batch.active_dates.add(run_date)
        run = BackfillRun(str(uuid4()), batch_id, run_date)
        self._runs[run.run_id] = (batch_id, run_date)
        self._store.record_run(run.run_id, batch_id, run_date.isoformat())
        self._persist(batch)
        return run

    def complete_run(self, run_id: str, *, outcome: str) -> BackfillRun | None:
        run_info = self._runs.get(run_id)
        if run_info is None:
            persisted = self._store.get("run", run_id)  # type: ignore[attr-defined]
            if persisted is None:
                return None
            run_info = (persisted["batch_id"], date.fromisoformat(persisted["run_date"]))
            self._runs[run_id] = run_info
        batch_id, run_date = run_info
        batch = self.get(batch_id)
        if batch is None:
            return None
        normalized_outcome = outcome.lower()
        batch.active_dates.discard(run_date)
        if normalized_outcome == "success":
            batch.completed_dates.add(run_date)
        elif normalized_outcome in {"failure", "failed"}:
            batch.failed_dates.add(run_date)
            batch.pending_dates.clear()
        else:
            raise BackfillValidationError("outcome must be success or failure")
        self._persist(batch)
        if normalized_outcome == "success" and batch.mode == "serial":
            return self.start_next(batch_id)
        return None

    def run_batch(self, run_id: str) -> tuple[str, date] | None:
        info = self._runs.get(run_id)
        if info is not None:
            return info
        persisted = self._store.get("run", run_id)  # type: ignore[attr-defined]
        if persisted is None:
            return None
        info = (persisted["batch_id"], date.fromisoformat(persisted["run_date"]))
        self._runs[run_id] = info
        return info

    def _persist(self, batch: BackfillBatch) -> None:
        self._store.record_batch(batch.batch_id, {
            "batch_id": batch.batch_id,
            "workflow_code": batch.workflow_code,
            "date_from": batch.date_from.isoformat(),
            "date_to": batch.date_to.isoformat(),
            "mode": batch.mode,
            "timezone": batch.timezone,
            "dates": [item.isoformat() for item in batch.dates],
            "execution_groups": [[item.isoformat() for item in group] for group in batch.execution_groups],
            "max_parallelism": batch.max_parallelism,
            "completed_dates": [item.isoformat() for item in batch.completed_dates],
            "pending_dates": [item.isoformat() for item in batch.pending_dates],
            "failed_dates": [item.isoformat() for item in batch.failed_dates],
            "active_dates": [item.isoformat() for item in batch.active_dates],
        })

    @staticmethod
    def _restore(value: dict[str, Any]) -> BackfillBatch:
        return BackfillBatch(
            batch_id=value["batch_id"],
            workflow_code=value["workflow_code"],
            date_from=date.fromisoformat(value["date_from"]),
            date_to=date.fromisoformat(value["date_to"]),
            mode=value["mode"],
            dates=[date.fromisoformat(item) for item in value["dates"]],
            execution_groups=[[date.fromisoformat(item) for item in group] for group in value["execution_groups"]],
            max_parallelism=value["max_parallelism"],
            timezone=value.get("timezone", "Asia/Shanghai"),
            completed_dates={date.fromisoformat(item) for item in value["completed_dates"]},
            pending_dates=[date.fromisoformat(item) for item in value["pending_dates"]],
            failed_dates={date.fromisoformat(item) for item in value["failed_dates"]},
            active_dates={date.fromisoformat(item) for item in value.get("active_dates", [])},
        )
