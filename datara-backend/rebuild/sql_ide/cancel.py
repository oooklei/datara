"""Fail-closed cancellation confirmation for SQL execution sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol


class CancelSession(Protocol):
    def cancel(self, *, task_id: str) -> bool: ...

    def status(self, *, task_id: str) -> Mapping[str, Any]: ...


_TERMINAL_STATUSES = frozenset({"canceled", "succeeded", "failed", "partial_failure", "timed_out"})
_CANCELLABLE_STATUSES = frozenset({"queued", "running", "cancel_requested"})


@dataclass(frozen=True)
class CancellationResult:
    status: str
    terminal: bool
    reusable: bool


def request_cancellation(session: CancelSession, *, task_id: str) -> CancellationResult:
    """Request cancellation, then trust only an authoritative terminal status.

    The caller must keep the connection out of its reusable pool when
    ``reusable`` is false (including pending, running, and unknown outcomes).
    """
    try:
        accepted = bool(session.cancel(task_id=task_id))
    except Exception:
        # A transport/driver exception does not prove that cancellation failed;
        # query status and quarantine unless the driver confirms a terminal state.
        accepted = False

    try:
        observed = session.status(task_id=task_id)
    except Exception:
        return CancellationResult(status="unknown", terminal=False, reusable=False)

    raw_status = observed.get("status") if isinstance(observed, Mapping) else None
    if not isinstance(raw_status, str):
        return CancellationResult(status="unknown", terminal=False, reusable=False)

    status = raw_status.strip().lower()
    if status in _TERMINAL_STATUSES:
        return CancellationResult(status=status, terminal=True, reusable=True)
    if status in _CANCELLABLE_STATUSES:
        if accepted:
            return CancellationResult(status="cancel_requested", terminal=False, reusable=False)
        return CancellationResult(status=status, terminal=False, reusable=False)
    return CancellationResult(status="unknown", terminal=False, reusable=False)
