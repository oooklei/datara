"""R6-H05b fault-injection matrix for duplicate delivery and recovery."""

from datetime import timedelta
from types import SimpleNamespace

from common import queue
from common.models import TaskInstance, WorkflowInstance
from master import failover
from master import engine as engine_module
from master import state
from master.engine import WorkflowExecuteRunnable
from tests.rebuild.r6_fakes import FakeClock


class _Graph:
    def node(self, node_id):
        return {
            "type": "python",
            "data": {"name": node_id, "constraints": {"retryTimes": 2, "retryInterval": 60}},
        }


def test_resume_retry_uses_original_persisted_deadline_after_config_change(monkeypatch):
    """A restart must honor the retry deadline saved before configuration changed."""
    clock = FakeClock()
    monkeypatch.setattr(engine_module, "now", clock.now)
    original_deadline = clock.now() + timedelta(seconds=45)
    runnable = WorkflowExecuteRunnable.__new__(WorkflowExecuteRunnable)
    runnable.instance_id = "retry-config-change"
    runnable.graph = _Graph()
    runnable.rows = {
        ("task-a", 0): {
            "id": 1,
            "state": state.RETRY,
            "attempt": 2,
            "start_time": None,
            "delay_until": original_deadline,
        }
    }
    runnable.by_task_id = {1: ("task-a", 0)}
    runnable.fail_defaults = {"retryTimes": 2, "retryIntervalSec": 3600}
    runnable.timers_retry = {}

    runnable._resume_sweep()

    assert runnable.timers_retry[("task-a", 0)] == original_deadline


def test_duplicate_worker_failure_message_is_absorbed(monkeypatch):
    runnable = WorkflowExecuteRunnable.__new__(WorkflowExecuteRunnable)
    runnable.instance_id = "duplicate-worker-message"
    runnable.rows = {
        ("task-a", 0): {
            "id": 1,
            "state": state.RUNNING,
            "attempt": 1,
            "end_time": None,
        }
    }
    runnable.by_task_id = {1: ("task-a", 0)}
    saved_rows = []
    downstream_advances = []
    runnable._save_row = lambda key, **kwargs: saved_rows.append((key, kwargs))
    runnable._schedule_retry = lambda *_args: False
    runnable._advance_downstream = lambda *args: downstream_advances.append(args)
    runnable._event = lambda *_args, **_kwargs: None
    persisted_task = SimpleNamespace(end_time=None, outputs=None, log_path=None, host=None)

    class _Session:
        def get(self, _model, _task_id):
            return persisted_task

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(engine_module, "new_session", _Session)
    message = {
        "taskId": 1,
        "attempt": 1,
        "state": state.FAILURE,
        "outputs": {"error": "worker reported failure"},
    }

    runnable._apply_worker_state(message)
    runnable._apply_worker_state(message)

    assert runnable.rows[("task-a", 0)]["state"] == state.FAILURE
    assert len(saved_rows) == 1
    assert downstream_advances == [("task-a", 0)]


def test_failover_redispatches_running_task_after_worker_becomes_unreachable(
    db_session, monkeypatch
):
    instance = WorkflowInstance(
        instance_id="worker-unreachable-run",
        wf_code=0,
        state=state.RUNNING,
        recovery=0,
    )
    task = TaskInstance(
        instance_id=instance.instance_id,
        node_id="worker-task",
        node_type="python",
        name="worker-task",
        state=state.RUNNING,
        attempt=3,
        host="worker-that-went-away",
    )
    db_session.add_all([instance, task])
    db_session.commit()
    dispatches = []
    monkeypatch.setattr(failover, "new_session", lambda: db_session)
    monkeypatch.setattr(queue, "add_task", lambda payload, priority=3: dispatches.append((payload, priority)))

    assert failover.recover_running_instances() == 1

    recovered = db_session.query(TaskInstance).filter_by(instance_id=instance.instance_id).one()
    assert recovered.state == state.SUBMITTED
    assert recovered.attempt == 3
    assert len(dispatches) == 1
    assert dispatches[0][0]["taskId"] == task.id
    assert dispatches[0][0]["instanceId"] == instance.instance_id
