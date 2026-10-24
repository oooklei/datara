from types import SimpleNamespace

from common.models import TaskInstance, WorkflowInstance
from master import scheduler, state


def test_repeat_running_creates_new_instance_and_copies_variable_snapshot(db_session, monkeypatch):
    origin = WorkflowInstance(
        instance_id="origin-rerun",
        wf_code=88001,
        wf_version=7,
        state=state.FAILURE,
        variables={"tenant": "t1", "secret": "masked"},
        run_mode="manual",
    )
    db_session.add(origin)
    db_session.commit()

    graph = SimpleNamespace(
        nodes={
            "sql-1": {"type": "SQL", "data": {"name": "load"}},
            "py-1": {"type": "PYTHON", "data": {"name": "transform"}},
        }
    )
    monkeypatch.setattr(scheduler, "new_session", lambda: db_session)
    monkeypatch.setattr(scheduler, "_load_graph", lambda _session, _wf_code: (SimpleNamespace(version=7), graph, None))
    monkeypatch.setattr(scheduler, "loop_bodies", lambda _graph: {})
    monkeypatch.setattr(scheduler, "generate_instance_id", lambda _wf_code: "rerun-new")

    command = SimpleNamespace(id=901, command_type="REPEAT_RUNNING")
    scheduler._cmd_repeat_running(command, {"instanceId": "origin-rerun"})

    rerun = db_session.query(WorkflowInstance).filter_by(instance_id="rerun-new").one()
    assert rerun.id != origin.id
    assert rerun.wf_code == origin.wf_code
    assert rerun.wf_version == origin.wf_version
    assert rerun.state == state.SUBMITTED
    assert rerun.variables == origin.variables
    assert rerun.variables is not origin.variables
    tasks = db_session.query(TaskInstance).filter_by(instance_id="rerun-new").all()
    assert {task.node_id for task in tasks} == {"sql-1", "py-1"}
    assert all(task.state == state.SUBMITTED and task.attempt == 1 for task in tasks)


def test_repeat_running_does_not_mutate_origin_when_snapshot_is_changed(db_session, monkeypatch):
    origin = WorkflowInstance(
        instance_id="origin-immutable",
        wf_code=88002,
        wf_version=3,
        state=state.SUCCESS,
        variables={"run": {"date": "2026-01-01"}},
    )
    db_session.add(origin)
    db_session.commit()
    graph = SimpleNamespace(nodes={"node": {"type": "SHELL", "data": {}}})
    monkeypatch.setattr(scheduler, "new_session", lambda: db_session)
    monkeypatch.setattr(scheduler, "_load_graph", lambda _session, _wf_code: (SimpleNamespace(version=3), graph, None))
    monkeypatch.setattr(scheduler, "loop_bodies", lambda _graph: {})
    monkeypatch.setattr(scheduler, "generate_instance_id", lambda _wf_code: "rerun-immutable")

    scheduler._cmd_repeat_running(SimpleNamespace(id=902, command_type="REPEAT_RUNNING"), {"instanceId": origin.instance_id})
    rerun = db_session.query(WorkflowInstance).filter_by(instance_id="rerun-immutable").one()
    rerun.variables["run"]["date"] = "2026-01-02"
    db_session.flush()
    persisted_origin = db_session.query(WorkflowInstance).filter_by(instance_id=origin.instance_id).one()
    assert persisted_origin.variables == {"run": {"date": "2026-01-01"}}
