"""In-memory execution session lifecycle state for SQL IDE tabs.

The store keeps only session identity and task status/cursor references. It does
not retain SQL, variables, event payloads, or result rows. A production adapter
must provide durable task/event records separately; reconnecting never starts a
second execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Any


_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "canceled", "timed_out"})


@dataclass
class _Session:
    project_id: int
    user_id: int
    datasource_id: int
    session_id: str
    connected: bool = True
    active_task_id: str | None = None
    last_task_id: str | None = None
    execution_count: int = 0


@dataclass
class _Task:
    project_id: int
    user_id: int
    datasource_id: int
    session_id: str
    task_id: str
    status: str = "running"
    last_event_id: int = 0


class InMemoryExecutionSessionStore:
    """Track per-tab serial execution and reconnectable task references."""

    def __init__(self) -> None:
        self._sessions: dict[str, _Session] = {}
        self._tasks: dict[str, _Task] = {}
        self._lock = RLock()

    def connect(
        self,
        *,
        project_id: int,
        user_id: int,
        datasource_id: int,
        session_id: str,
    ) -> dict[str, Any]:
        """Create a session or reattach to its existing identity and task."""
        if not session_id or project_id < 0 or user_id < 0 or datasource_id < 0:
            raise ValueError("session identity is invalid")
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = _Session(project_id, user_id, datasource_id, session_id)
                self._sessions[session_id] = session
            elif (session.project_id, session.user_id, session.datasource_id) != (
                project_id,
                user_id,
                datasource_id,
            ):
                raise PermissionError("session identity is already bound")
            session.connected = True
            return self._session_view(session)

    def disconnect(self, *, session_id: str) -> bool:
        """Detach the client without canceling any active execution."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or not session.connected:
                return False
            session.connected = False
            return True

    def start_task(self, *, session_id: str, task_id: str) -> dict[str, Any]:
        """Associate one new execution with a connected, currently idle tab."""
        if not task_id:
            raise ValueError("task_id is required")
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None or not session.connected:
                raise ValueError("session must be connected")
            if session.active_task_id is not None:
                raise ValueError("session already has an active task")
            if task_id in self._tasks:
                raise ValueError("task_id is already registered")
            task = _Task(
                project_id=session.project_id,
                user_id=session.user_id,
                datasource_id=session.datasource_id,
                session_id=session.session_id,
                task_id=task_id,
            )
            self._tasks[task_id] = task
            session.active_task_id = task_id
            session.last_task_id = task_id
            session.execution_count += 1
            return self._task_view(task)

    def record_event(self, *, task_id: str, event_id: int) -> None:
        """Advance a task's persisted event cursor without storing its payload."""
        if event_id <= 0:
            raise ValueError("event_id must be a positive integer")
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError("task_id was not found")
            if task.status != "running":
                raise ValueError("cannot record an event for a terminal task")
            if event_id <= task.last_event_id:
                raise ValueError("event_id must increase monotonically")
            task.last_event_id = event_id

    def finish_task(self, *, task_id: str, status: str) -> None:
        """Record the authoritative terminal status and release the tab slot."""
        if status not in _TERMINAL_STATUSES:
            raise ValueError("terminal status is required")
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError("task_id was not found")
            if task.status != "running":
                if task.status == status:
                    return
                raise ValueError("task is already terminal")
            task.status = status
            session = self._sessions[task.session_id]
            if session.active_task_id == task_id:
                session.active_task_id = None

    def _session_view(self, session: _Session) -> dict[str, Any]:
        task_id = session.active_task_id or session.last_task_id
        task = self._tasks.get(task_id) if task_id else None
        return {
            "session_id": session.session_id,
            "project_id": session.project_id,
            "user_id": session.user_id,
            "datasource_id": session.datasource_id,
            "connected": session.connected,
            "active_task_id": session.active_task_id,
            "last_task_id": session.last_task_id,
            "task_status": task.status if task else None,
            "last_event_id": task.last_event_id if task else 0,
            "execution_count": session.execution_count,
        }

    @staticmethod
    def _task_view(task: _Task) -> dict[str, Any]:
        return {
            "task_id": task.task_id,
            "session_id": task.session_id,
            "project_id": task.project_id,
            "user_id": task.user_id,
            "datasource_id": task.datasource_id,
            "status": task.status,
            "last_event_id": task.last_event_id,
        }
