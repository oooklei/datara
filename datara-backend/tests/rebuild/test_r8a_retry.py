"""R6-H01 automatic-retry contract tests against WorkflowExecuteRunnable."""

from __future__ import annotations

from datetime import timedelta
from threading import Barrier, Thread

import pytest

from common.models import TaskInstance, WorkflowInstance
from master import engine as engine_module
from master.engine import WorkflowExecuteRunnable
from master import state
from tests.rebuild.r6_fakes import FakeClock, FakeR6Store


RUN_ID = "r6-retry-run"
NODE_ID = "task-a"
TASK_ID = 811
KEY = (NODE_ID, 0)


class _Graph:
    def node(self, node_id):
        return {
            "type": "python",
            "data": {"name": node_id, "constraints": {"retryTimes": 2, "retryInterval": 1}},
        }


def _runnable(*, attempt=1, row_state=state.FAILURE, retry_times=2):
    runnable = WorkflowExecuteRunnable.__new__(WorkflowExecuteRunnable)
    runnable.instance_id = RUN_ID
    runnable.graph = _Graph()
    runnable.rows = {
        KEY: {"id": TASK_ID, "state": row_state, "attempt": attempt, "start_time": None, "delay_until": None}
    }
    runnable.by_task_id = {TASK_ID: KEY}
    runnable.fail_defaults = {"retryTimes": retry_times, "retryIntervalSec": 60}
    runnable.timers_retry = {}
    runnable.timers_delay = {}
    runnable.timers_dep = {}
    runnable.activated = set()
    runnable.events_seen = []
    runnable._event = lambda event_type, node_id="", payload=None: runnable.events_seen.append(
        (event_type, node_id, payload)
    )
    return runnable


def _seed(db_session, *, attempt=1, row_state=state.FAILURE, delay_until=None):
    db_session.add(WorkflowInstance(instance_id=RUN_ID, wf_code=90811, state=state.RUNNING))
    db_session.add(
        TaskInstance(
            id=TASK_ID,
            instance_id=RUN_ID,
            node_id=NODE_ID,
            node_type="python",
            name=NODE_ID,
            state=row_state,
            attempt=attempt,
            loop_iter=0,
            delay_until=delay_until,
        )
    )
    db_session.commit()


def _bind_store(db_session, monkeypatch, store):
    """Use real ORM persistence while mirroring task writes into the shared observer."""
    monkeypatch.setattr(engine_module, "new_session", lambda: db_session)
    monkeypatch.setattr(engine_module, "_append_task_log", lambda *_args: "r6-test.log")
    monkeypatch.setattr(engine_module, "_ensure_task_log_index", lambda *_args: None)
    original_save_row = WorkflowExecuteRunnable._save_row

    def save_and_observe(runnable, key, outputs=None, log_lines=None):
        original_save_row(runnable, key, outputs=outputs, log_lines=log_lines)
        row = runnable.rows[key]
        persisted = db_session.get(TaskInstance, row["id"])
        store.upsert(
            "task",
            (runnable.instance_id, str(key[0]), int(key[1])),
            {
                "run_id": runnable.instance_id,
                "task_id": str(key[0]),
                "task_row_id": row["id"],
                "state": persisted.state,
                "attempt": persisted.attempt,
                "deadline": persisted.delay_until,
            },
        )

    monkeypatch.setattr(WorkflowExecuteRunnable, "_save_row", save_and_observe)


def test_retry_budget_exhausted_stays_terminal_without_new_attempt(db_session, monkeypatch):
    _seed(db_session, attempt=3, row_state=state.FAILURE)
    store = FakeR6Store()
    _bind_store(db_session, monkeypatch, store)
    runnable = _runnable(attempt=3, row_state=state.FAILURE, retry_times=2)

    scheduled = runnable._schedule_retry(KEY, {"error": "connection reset"})

    task = db_session.get(TaskInstance, TASK_ID)
    assert scheduled is False
    assert (runnable.rows[KEY]["state"], runnable.rows[KEY]["attempt"]) == (state.FAILURE, 3)
    assert task.state == state.FAILURE and task.attempt == 3
    assert runnable.timers_retry == {}
    assert not [event for event in runnable.events_seen if event[0] == "node_retry"]


def test_retry_deadline_is_persisted_and_survives_restart_without_recalculation(db_session, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(engine_module, "now", clock.now)
    _seed(db_session, attempt=1, row_state=state.FAILURE)
    store = FakeR6Store()
    _bind_store(db_session, monkeypatch, store)
    runnable = _runnable(attempt=1, row_state=state.FAILURE)

    assert runnable._schedule_retry(KEY, {"error": "connection reset"}) is True
    persisted = db_session.get(TaskInstance, TASK_ID)
    original_deadline = clock.now() + timedelta(seconds=1)
    assert persisted.delay_until == original_deadline
    assert store.get("task", (RUN_ID, NODE_ID, 0))["deadline"] == original_deadline

    restarted = _runnable(attempt=2, row_state=state.RETRY)
    restarted.rows = {}
    restarted.by_task_id = {}
    restarted.fail_defaults = {"retryTimes": 2, "retryIntervalSec": 3600}
    restarted._load_rows()
    restarted._resume_sweep()

    assert restarted.rows[KEY]["delay_until"] == original_deadline
    assert restarted.timers_retry[KEY] == original_deadline
    assert restarted.timers_retry[KEY] != clock.now() + timedelta(seconds=3600)


def test_expired_retry_is_dispatched_immediately_during_resume_sweep(db_session, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(engine_module, "now", clock.now)
    expired = clock.now() - timedelta(seconds=1)
    _seed(db_session, attempt=2, row_state=state.RETRY, delay_until=expired)
    _bind_store(db_session, monkeypatch, FakeR6Store())
    runnable = _runnable(attempt=2, row_state=state.RETRY)
    runnable.fail_defaults = {"retryTimes": 2, "retryIntervalSec": 3600}
    runnable._execute_node = lambda key: runnable.events_seen.append(("dispatch", key, None))
    runnable._load_rows()

    runnable._resume_sweep()
    runnable._on_timer(clock.now())

    assert ("dispatch", KEY, None) in runnable.events_seen
    assert runnable.timers_retry == {}
    assert runnable.rows[KEY]["state"] == state.SUBMITTED


def test_deterministic_error_has_no_retry_event_timer_or_attempt(db_session, monkeypatch):
    _seed(db_session, attempt=1, row_state=state.FAILURE)
    store = FakeR6Store()
    _bind_store(db_session, monkeypatch, store)
    runnable = _runnable(attempt=1, row_state=state.FAILURE)

    assert runnable._schedule_retry(KEY, {"error": "SQL syntax error"}) is False

    assert runnable.rows[KEY]["attempt"] == 1
    assert runnable.rows[KEY]["state"] == state.FAILURE
    assert runnable.timers_retry == {}
    assert not [event for event in runnable.events_seen if event[0] == "node_retry"]
    assert store.get("task", (RUN_ID, NODE_ID, 0)) is None


def test_retry_strategy_persisted_matches_classifier(db_session, monkeypatch):
    from master.retry_classifier import classify_error, retry_decision

    _seed(db_session, attempt=1, row_state=state.FAILURE)
    _bind_store(db_session, monkeypatch, FakeR6Store())
    runnable = _runnable(attempt=1, row_state=state.FAILURE)

    kind = classify_error("ConnectionError", "connection reset", None)
    expected = retry_decision(kind, failed_attempt=1, fallback_seconds=60)
    assert runnable._schedule_retry(KEY, {"exceptionType": "ConnectionError", "error": "connection reset"}) is True

    persisted = db_session.get(TaskInstance, TASK_ID)
    assert persisted.retry_strategy == expected.strategy
    assert runnable.rows[KEY]["retry_strategy"] == expected.strategy


def test_resume_legacy_retry_row_without_deadline_falls_back_to_current_config(db_session, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(engine_module, "now", clock.now)
    warnings = []
    monkeypatch.setattr(engine_module.logger, "warning", lambda message, *args: warnings.append(message % args))
    _seed(db_session, attempt=2, row_state=state.RETRY)
    _bind_store(db_session, monkeypatch, FakeR6Store())
    runnable = _runnable(attempt=2, row_state=state.RETRY)
    runnable.fail_defaults = {"retryTimes": 2, "retryIntervalSec": 90}
    runnable._load_rows()

    runnable._resume_sweep()

    assert runnable.timers_retry[KEY] == clock.now() + timedelta(seconds=60)
    assert any("legacy retry row" in warning for warning in warnings)


def test_duplicate_concurrent_failure_only_advances_attempt_once(monkeypatch):
    runnable = _runnable(attempt=1, row_state=state.FAILURE)
    runnable._save_row = lambda *_args, **_kwargs: None
    barrier = Barrier(3)
    outcomes = []

    def deliver_failure():
        barrier.wait()
        outcomes.append(runnable._schedule_retry(KEY, {"error": "connection reset"}))

    workers = [Thread(target=deliver_failure) for _ in range(2)]
    for worker in workers:
        worker.start()
    barrier.wait()
    for worker in workers:
        worker.join(timeout=2)

    assert all(not worker.is_alive() for worker in workers)
    assert outcomes.count(True) == 1
    assert runnable.rows[KEY]["attempt"] == 2
    assert len([event for event in runnable.events_seen if event[0] == "node_retry"]) == 1


@pytest.mark.skip(reason="R6 v1.0 §3.1 leaves cancel-vs-retry precedence pending adjudication; keep RED.")
def test_cancel_race_pending_adjudication():
    """Pending only: do not infer whether cancellation or the retry timer wins."""
