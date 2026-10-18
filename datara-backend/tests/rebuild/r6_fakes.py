"""Small deterministic fixtures shared by R6 retry and failover tests.

These fakes provide controllable time, persistence observations, dispatch counts,
and explicit failure injection. They do not implement R6 scheduling semantics;
tests must exercise the production object under test and assert its effects here.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from threading import Lock
from typing import Any


class FakeClock:
    def __init__(self, current: datetime | None = None):
        self.current = current or datetime(2026, 1, 1, 0, 0, 0)

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> datetime:
        self.current += delta
        return self.current


class FakeR6Store:
    """Observable workflow/task/retry records with atomic per-attempt claims."""

    def __init__(self):
        self.workflows: dict[str, dict[str, Any]] = {}
        self.tasks: dict[tuple[str, str], dict[str, Any]] = {}
        self.retries: dict[tuple[str, str], dict[str, Any]] = {}
        self._claims: set[tuple[str, str, int]] = set()
        self._lock = Lock()

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(
            {
                "workflows": self.workflows,
                "tasks": self.tasks,
                "retries": self.retries,
                "claims": self._claims,
            }
        )

    def get(self, kind: str, key: Any) -> dict[str, Any] | None:
        collection = self._collection(kind)
        record = collection.get(key)
        return deepcopy(record) if record is not None else None

    def list_nonterminal(self) -> list[dict[str, Any]]:
        terminal = {"SUCCESS", "FAILED", "KILLED", "SKIP", "CANCELED"}
        return [deepcopy(row) for row in self.tasks.values() if row.get("state") not in terminal]

    def list_due_retry(self, now: datetime) -> list[dict[str, Any]]:
        return [
            deepcopy(row)
            for row in self.retries.values()
            if row.get("deadline") is not None and row["deadline"] <= now
        ]

    def upsert(self, kind: str, key: Any, record: dict[str, Any]) -> dict[str, Any]:
        collection = self._collection(kind)
        collection[key] = deepcopy(record)
        return deepcopy(collection[key])

    def atomic_claim(self, run_id: str, task_id: str, attempt: int) -> bool:
        claim = (run_id, task_id, attempt)
        with self._lock:
            if claim in self._claims:
                return False
            self._claims.add(claim)
            return True

    def _collection(self, kind: str) -> dict[Any, dict[str, Any]]:
        try:
            return {
                "workflow": self.workflows,
                "task": self.tasks,
                "retry": self.retries,
            }[kind]
        except KeyError as exc:
            raise ValueError(f"unknown R6 record kind: {kind}") from exc


class FakeDispatcher:
    """Records dispatch attempts and can model success-before-state-persist."""

    def __init__(self, *, already_executed: set[Any] | None = None):
        self.calls: list[Any] = []
        self.already_executed = already_executed if already_executed is not None else set()
        self.fail_next: Exception | None = None

    def dispatch(self, task_key: Any) -> bool:
        self.calls.append(task_key)
        if self.fail_next is not None:
            error, self.fail_next = self.fail_next, None
            raise error
        # True means an execution may have happened even though its status was
        # not persisted; callers must rely on the per-attempt claim for replay.
        self.already_executed.add(task_key)
        return True


class FakeFailpoint:
    """One-shot exceptions addressable by the recovery/retry operation name."""

    def __init__(self):
        self._armed: dict[str, Exception] = {}

    def arm(self, operation: str, error: Exception | None = None) -> None:
        self._armed[operation] = error or RuntimeError(f"injected {operation} failure")

    def hit(self, operation: str) -> None:
        error = self._armed.pop(operation, None)
        if error is not None:
            raise error


class FakeComplementBatchStore:
    """Append-only observer for persisted backfill batches and run links."""

    def __init__(self, snapshot: dict[str, Any] | None = None):
        state = deepcopy(snapshot or {})
        self.batches: dict[str, dict[str, Any]] = state.get("batches", {})
        self.runs: dict[str, dict[str, Any]] = state.get("runs", {})

    def snapshot(self) -> dict[str, Any]:
        return deepcopy({"batches": self.batches, "runs": self.runs})

    def record_batch(self, batch_id: str, batch: dict[str, Any]) -> None:
        self.batches[batch_id] = deepcopy(batch)

    def record_run(self, run_id: str, batch_id: str, run_date: str) -> None:
        self.runs[run_id] = {"batch_id": batch_id, "run_date": run_date}
