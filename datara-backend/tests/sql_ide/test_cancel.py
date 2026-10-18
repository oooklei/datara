from __future__ import annotations

from dataclasses import dataclass

import pytest

from rebuild.sql_ide.cancel import CancellationResult, request_cancellation


@dataclass
class FakeSession:
    accepted: bool
    current_status: str
    cancel_calls: int = 0
    status_calls: int = 0

    def cancel(self, *, task_id: str) -> bool:
        assert task_id == "task-1"
        self.cancel_calls += 1
        return self.accepted

    def status(self, *, task_id: str) -> dict[str, str]:
        assert task_id == "task-1"
        self.status_calls += 1
        return {"status": self.current_status}


def test_accepted_request_is_not_reported_canceled_without_driver_confirmation() -> None:
    session = FakeSession(accepted=True, current_status="running")

    result = request_cancellation(session, task_id="task-1")

    assert result == CancellationResult(status="cancel_requested", terminal=False, reusable=False)
    assert (session.cancel_calls, session.status_calls) == (1, 1)


def test_driver_terminal_canceled_confirms_cancel_and_allows_reuse() -> None:
    session = FakeSession(accepted=True, current_status="canceled")

    result = request_cancellation(session, task_id="task-1")

    assert result == CancellationResult(status="canceled", terminal=True, reusable=True)


def test_unconfirmed_cancel_quarantines_connection() -> None:
    session = FakeSession(accepted=True, current_status="unknown")

    result = request_cancellation(session, task_id="task-1")

    assert result.status == "unknown"
    assert result.terminal is False
    assert result.reusable is False


def test_idempotent_cancel_reads_authoritative_terminal_state_even_if_not_accepted() -> None:
    session = FakeSession(accepted=False, current_status="canceled")

    result = request_cancellation(session, task_id="task-1")

    assert result == CancellationResult(status="canceled", terminal=True, reusable=True)


@pytest.mark.parametrize("terminal_status", ["succeeded", "failed", "partial_failure", "timed_out"])
def test_racing_terminal_status_is_preserved_and_connection_is_reusable(terminal_status: str) -> None:
    session = FakeSession(accepted=True, current_status=terminal_status)

    result = request_cancellation(session, task_id="task-1")

    assert result == CancellationResult(status=terminal_status, terminal=True, reusable=True)


def test_nonaccepted_request_that_is_still_running_is_not_claimed_canceled() -> None:
    session = FakeSession(accepted=False, current_status="running")

    result = request_cancellation(session, task_id="task-1")

    assert result == CancellationResult(status="running", terminal=False, reusable=False)
