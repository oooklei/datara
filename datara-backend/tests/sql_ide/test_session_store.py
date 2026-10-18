from __future__ import annotations

import pytest


@pytest.fixture
def session_store():
    from rebuild.sql_ide.session_store import InMemoryExecutionSessionStore

    return InMemoryExecutionSessionStore()


def test_reconnect_preserves_session_and_active_task_without_reexecuting(session_store):
    session_store.connect(
        project_id=7, user_id=11, datasource_id=3, session_id="tab-1"
    )
    session_store.start_task(session_id="tab-1", task_id="task-1")
    session_store.record_event(task_id="task-1", event_id=4)

    session_store.disconnect(session_id="tab-1")
    resumed = session_store.connect(
        project_id=7, user_id=11, datasource_id=3, session_id="tab-1"
    )

    assert resumed["session_id"] == "tab-1"
    assert resumed["connected"] is True
    assert resumed["active_task_id"] == "task-1"
    assert resumed["last_event_id"] == 4
    assert resumed["task_status"] == "running"
    assert resumed["execution_count"] == 1


def test_one_session_serializes_tasks_but_another_session_can_run(session_store):
    for session_id in ("tab-1", "tab-2"):
        session_store.connect(
            project_id=7, user_id=11, datasource_id=3, session_id=session_id
        )
    session_store.start_task(session_id="tab-1", task_id="task-1")

    with pytest.raises(ValueError, match="active task"):
        session_store.start_task(session_id="tab-1", task_id="task-2")

    assert session_store.start_task(session_id="tab-2", task_id="task-2")["task_id"] == "task-2"


def test_terminal_status_and_event_cursor_are_available_after_disconnect(session_store):
    session_store.connect(
        project_id=7, user_id=11, datasource_id=3, session_id="tab-1"
    )
    session_store.start_task(session_id="tab-1", task_id="task-1")
    session_store.record_event(task_id="task-1", event_id=9)
    session_store.finish_task(task_id="task-1", status="succeeded")
    session_store.disconnect(session_id="tab-1")

    resumed = session_store.connect(
        project_id=7, user_id=11, datasource_id=3, session_id="tab-1"
    )
    assert resumed["active_task_id"] is None
    assert resumed["last_task_id"] == "task-1"
    assert resumed["task_status"] == "succeeded"
    assert resumed["last_event_id"] == 9
    assert resumed["execution_count"] == 1


def test_session_identity_cannot_be_rebound_to_another_project_or_user(session_store):
    session_store.connect(
        project_id=7, user_id=11, datasource_id=3, session_id="tab-1"
    )

    with pytest.raises(PermissionError, match="session identity"):
        session_store.connect(
            project_id=8, user_id=11, datasource_id=3, session_id="tab-1"
        )

    with pytest.raises(PermissionError, match="session identity"):
        session_store.connect(
            project_id=7, user_id=12, datasource_id=3, session_id="tab-1"
        )


def test_store_rejects_invalid_event_ids_and_terminal_status(session_store):
    session_store.connect(
        project_id=7, user_id=11, datasource_id=3, session_id="tab-1"
    )
    session_store.start_task(session_id="tab-1", task_id="task-1")

    with pytest.raises(ValueError, match="event_id"):
        session_store.record_event(task_id="task-1", event_id=-1)
    with pytest.raises(ValueError, match="terminal status"):
        session_store.finish_task(task_id="task-1", status="running")

