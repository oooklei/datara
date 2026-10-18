"""R6 failover acceptance tests (P2-2 R5A FIVE-C T20)."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from common import queue
from common.models import TaskInstance, WorkflowInstance
from master import failover, scheduler, state
from tests.rebuild.r6_fakes import FakeClock, FakeDispatcher, FakeFailpoint, FakeR6Store


def _seed_instance(db_session, *, instance_id="run-1", task_state=state.RUNNING, attempt=4):
    instance = WorkflowInstance(instance_id=instance_id, wf_code=0, state=state.RUNNING, recovery=0)
    task = TaskInstance(
        instance_id=instance_id,
        node_id="task-1",
        node_type="smoke",
        name="smoke",
        state=task_state,
        attempt=attempt,
    )
    db_session.add_all([instance, task])
    db_session.commit()
    return instance, task


def _install_db(monkeypatch, db_session):
    monkeypatch.setattr(failover, "new_session", lambda: db_session)
    monkeypatch.setattr(scheduler, "new_session", lambda: db_session)


def _record_dispatch(monkeypatch, store, dispatcher):
    def add_task(payload, priority=3):
        run_id = payload["instanceId"]
        task_id = str(payload["taskId"])
        attempt = int(payload.get("attempt") or 1)
        key = (run_id, task_id, attempt)
        store.upsert("task", (run_id, task_id), {"run_id": run_id, "task_id": task_id, "attempt": attempt})
        dispatcher.dispatch(key)
        return "fake-message-id"

    monkeypatch.setattr(queue, "add_task", add_task)
    monkeypatch.setattr(
        queue,
        "add_task_fenced",
        lambda payload, priority=3, fence_token=1: add_task(payload, priority=priority),
    )


def _install_test_fence(monkeypatch):
    monkeypatch.setattr(queue, "claim_master_fence", lambda: 17)
    monkeypatch.setattr(queue, "set_master_fence", lambda _token: None)


def test_running_recovery_marks_fault_then_submitted_and_redispatches(db_session, monkeypatch):
    _seed_instance(db_session)
    committed_states = []
    original_commit = db_session.commit

    def record_commit():
        original_commit()
        task = db_session.query(TaskInstance).filter_by(instance_id="run-1").one()
        committed_states.append(task.state)

    monkeypatch.setattr(db_session, "commit", record_commit)
    store = FakeR6Store()
    dispatcher = FakeDispatcher()
    _record_dispatch(monkeypatch, store, dispatcher)
    _install_db(monkeypatch, db_session)

    assert failover.recover_running_instances() == 1

    task = db_session.query(TaskInstance).filter_by(instance_id="run-1").one()
    assert task.state == state.SUBMITTED
    assert task.attempt == 4
    assert committed_states == [state.FAULT_TOLERANCE, state.SUBMITTED]
    assert len(dispatcher.calls) == 1
    assert dispatcher.calls[0] == ("run-1", str(task.id), 4)
    assert store.get("task", ("run-1", str(task.id)))["attempt"] == 4


def test_duplicate_leader_same_attempt_dispatches_once(db_session, monkeypatch):
    _seed_instance(db_session, instance_id="duplicate-run")
    store = FakeR6Store()
    dispatcher = FakeDispatcher()
    _record_dispatch(monkeypatch, store, dispatcher)
    _install_db(monkeypatch, db_session)

    failover.recover_running_instances()
    failover.recover_running_instances()

    assert len(dispatcher.calls) == 1


def test_recovery_failure_is_rescanned_and_all_ten_instances_recovered(db_session, monkeypatch):
    for index in range(10):
        _seed_instance(db_session, instance_id=f"cohort-run-{index}", attempt=1)
    store = FakeR6Store()
    dispatcher = FakeDispatcher()
    failpoint = FakeFailpoint()
    failpoint.arm("recover:cohort-run-0")
    _record_dispatch(monkeypatch, store, dispatcher)
    _install_db(monkeypatch, db_session)
    _install_test_fence(monkeypatch)
    clock = FakeClock(datetime(2026, 1, 1, 0, 0, 0))
    monkeypatch.setattr(scheduler.time, "monotonic", lambda: clock.now().timestamp())
    original = failover._recover_one
    calls = {}

    def recover_one(instance_id, fence_token=None):
        calls[instance_id] = calls.get(instance_id, 0) + 1
        failpoint.hit(f"recover:{instance_id}")
        return original(instance_id, fence_token=fence_token)

    monkeypatch.setattr(failover, "_recover_one", recover_one)
    gate = scheduler.LeaderGate(SimpleNamespace(is_master=True))

    assert gate.check() is True
    assert len(dispatcher.calls) == 9
    assert gate.check() is True  # no hot loop before the configured rescan interval
    assert len(dispatcher.calls) == 9
    clock.advance(timedelta(seconds=10))
    assert gate.check() is True

    instances = db_session.query(WorkflowInstance).all()
    tasks = db_session.query(TaskInstance).all()
    assert len(instances) == len(tasks) == 10
    assert {task.state for task in tasks} == {state.SUBMITTED}
    assert calls["cohort-run-0"] == 2
    assert all(calls.get(f"cohort-run-{index}") == 1 for index in range(1, 10))
    assert len(dispatcher.calls) == 10


def test_manual_failure_recovery_resets_attempt_and_submits_failed_task(db_session, monkeypatch):
    instance = WorkflowInstance(instance_id="manual-run", wf_code=1, state=state.FAILURE, end_time=datetime.now())
    failed = TaskInstance(
        instance_id="manual-run", node_id="failed", node_type="smoke", state=state.FAILURE, attempt=3
    )
    db_session.add_all([instance, failed])
    db_session.commit()
    _install_db(monkeypatch, db_session)
    graph = SimpleNamespace(nodes={"failed": {"type": "smoke"}}, succs={"failed": []})
    monkeypatch.setattr(scheduler, "_load_graph", lambda _session, _wf_code: (None, graph))
    monkeypatch.setattr(scheduler, "_spawn_runnable", lambda _instance_id, _graph: None)
    command = SimpleNamespace(id=1, command_type="START_FAILURE_TASKS")

    scheduler._cmd_failure_tasks(command, {"instanceId": "manual-run"})

    refreshed = db_session.query(TaskInstance).filter_by(instance_id="manual-run").one()
    refreshed_instance = db_session.query(WorkflowInstance).filter_by(instance_id="manual-run").one()
    assert refreshed.state == state.SUBMITTED
    assert refreshed.attempt == 1
    assert refreshed_instance.state == state.RUNNING


def test_gate_throttles_whole_scan_error_then_retries_at_interval(monkeypatch):
    clock = FakeClock(datetime(2026, 1, 1, 0, 0, 0))
    monkeypatch.setattr(scheduler.time, "monotonic", lambda: clock.now().timestamp())
    calls = []

    def scan(fence_token=None):
        assert fence_token == 17
        calls.append(clock.now())
        if len(calls) == 1:
            raise RuntimeError("injected scan-wide database failure")
        return 1

    monkeypatch.setattr(scheduler, "recover_running_instances", scan)
    _install_test_fence(monkeypatch)
    gate = scheduler.LeaderGate(SimpleNamespace(is_master=True))

    assert gate.check() is True
    assert gate.check() is True
    clock.advance(timedelta(seconds=9))
    assert gate.check() is True
    assert len(calls) == 1
    clock.advance(timedelta(seconds=1))
    assert gate.check() is True
    assert len(calls) == 2
