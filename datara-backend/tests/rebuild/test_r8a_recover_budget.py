"""START_FAILURE_TASKS resets retry state for the failed downstream chain."""

from datetime import datetime
from types import SimpleNamespace

from common.models import TaskInstance, WorkflowInstance
from master import scheduler, state


def test_start_failure_tasks_resets_retry_budget_and_clears_stale_task_data(db_session, monkeypatch):
    finished_at = datetime(2026, 10, 18, 12, 30)
    retry_at = datetime(2026, 10, 18, 12, 31)
    instance = WorkflowInstance(
        instance_id="recover-budget-run",
        wf_code=1,
        state=state.FAILURE,
        end_time=finished_at,
    )
    tasks = [
        TaskInstance(
            instance_id=instance.instance_id,
            node_id="failed",
            node_type="sql",
            name="failed",
            state=state.FAILURE,
            attempt=4,
            end_time=finished_at,
            delay_until=retry_at,
            outputs={"stale": "failed output"},
        ),
        TaskInstance(
            instance_id=instance.instance_id,
            node_id="retrying",
            node_type="sql",
            name="retrying",
            state=state.RETRY,
            attempt=3,
            end_time=finished_at,
            delay_until=retry_at,
            outputs={"stale": "retry output"},
        ),
        TaskInstance(
            instance_id=instance.instance_id,
            node_id="running",
            node_type="sql",
            name="running",
            state=state.RUNNING,
            attempt=2,
            end_time=finished_at,
            delay_until=retry_at,
            outputs={"stale": "running output"},
        ),
        TaskInstance(
            instance_id=instance.instance_id,
            node_id="succeeded",
            node_type="sql",
            name="succeeded",
            state=state.SUCCESS,
            attempt=2,
            end_time=finished_at,
            delay_until=retry_at,
            outputs={"kept": "successful output"},
        ),
        TaskInstance(
            instance_id=instance.instance_id,
            node_id="unrelated",
            node_type="sql",
            name="unrelated",
            state=state.KILL,
            attempt=5,
            end_time=finished_at,
            delay_until=retry_at,
            outputs={"kept": "unrelated output"},
        ),
    ]
    db_session.add_all([instance, *tasks])
    db_session.commit()

    graph = SimpleNamespace(
        nodes={node_id: {"type": "sql"} for node_id in ("failed", "retrying", "running", "succeeded", "unrelated")},
        succs={
            "failed": [{"target": "retrying"}, {"target": "succeeded"}],
            "retrying": [{"target": "running"}],
            "running": [],
            "succeeded": [],
            "unrelated": [],
        },
    )
    monkeypatch.setattr(scheduler, "new_session", lambda: db_session)
    monkeypatch.setattr(scheduler, "_load_graph", lambda _session, _wf_code: (None, graph))
    monkeypatch.setattr(scheduler, "_spawn_runnable", lambda _instance_id, _graph: None)
    command = SimpleNamespace(id=1, command_type="START_FAILURE_TASKS")

    scheduler._cmd_failure_tasks(command, {"instanceId": instance.instance_id})

    refreshed = {
        task.node_id: task
        for task in db_session.query(TaskInstance).filter_by(instance_id=instance.instance_id).all()
    }
    for node_id in ("failed", "retrying", "running"):
        task = refreshed[node_id]
        assert task.state == state.SUBMITTED
        assert task.attempt == 1
        assert task.end_time is None
        assert task.delay_until is None
        assert task.outputs is None

    assert refreshed["succeeded"].state == state.SUCCESS
    assert refreshed["succeeded"].attempt == 2
    assert refreshed["succeeded"].outputs == {"kept": "successful output"}
    assert refreshed["unrelated"].state == state.KILL
    assert refreshed["unrelated"].attempt == 5
    assert refreshed["unrelated"].outputs == {"kept": "unrelated output"}
    refreshed_instance = db_session.query(WorkflowInstance).filter_by(instance_id=instance.instance_id).one()
    assert refreshed_instance.state == state.RUNNING
    assert refreshed_instance.end_time is None
