"""FV-07 R5-A 会话与执行生命周期终验。

验收标准（草案）：
- executeSql 幂等键+摘要、accepted→终态状态机
- 取消幂等
- sessionId 断线恢复（A5 §4.7）
- SSE Last-Event-ID 顺序重放/reset-required
- getExecutionStatus 恢复面
- 终态命名 succeeded/failed 与契约一致

测试策略：全部 mock/内存，禁真实写库。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from rebuild.sql_ide.cancel import CancellationResult, request_cancellation
from rebuild.sql_ide.session_store import InMemoryExecutionSessionStore


class TestSessionLifecycle:
    """会话生命周期：connect → start_task → record_event → finish_task。"""

    def test_connect_creates_session(self):
        store = InMemoryExecutionSessionStore()
        view = store.connect(project_id=1, user_id=2, datasource_id=3, session_id="s1")
        assert view["session_id"] == "s1"
        assert view["connected"] is True
        assert view["active_task_id"] is None
        assert view["execution_count"] == 0

    def test_connect_invalid_session_id(self):
        store = InMemoryExecutionSessionStore()
        with pytest.raises(ValueError):
            store.connect(project_id=1, user_id=2, datasource_id=3, session_id="")

    def test_connect_negative_ids_rejected(self):
        store = InMemoryExecutionSessionStore()
        with pytest.raises(ValueError):
            store.connect(project_id=-1, user_id=2, datasource_id=3, session_id="s1")

    def test_reconnect_restores_identity(self):
        """断线重连恢复同一 session 身份。"""
        store = InMemoryExecutionSessionStore()
        store.connect(project_id=1, user_id=2, datasource_id=3, session_id="s1")
        store.disconnect(session_id="s1")
        view = store.connect(project_id=1, user_id=2, datasource_id=3, session_id="s1")
        assert view["connected"] is True

    def test_reconnect_conflict_rejected(self):
        """不同 project/user/datasource 复用同一 session_id → 拒绝。"""
        store = InMemoryExecutionSessionStore()
        store.connect(project_id=1, user_id=2, datasource_id=3, session_id="s1")
        with pytest.raises(PermissionError):
            store.connect(project_id=99, user_id=2, datasource_id=3, session_id="s1")

    def test_disconnect(self):
        store = InMemoryExecutionSessionStore()
        store.connect(project_id=1, user_id=2, datasource_id=3, session_id="s1")
        assert store.disconnect(session_id="s1") is True
        view = store.connect(project_id=1, user_id=2, datasource_id=3, session_id="s1")
        assert view["connected"] is True

    def test_disconnect_unknown_session(self):
        store = InMemoryExecutionSessionStore()
        assert store.disconnect(session_id="nonexistent") is False

    def test_disconnect_already_disconnected(self):
        store = InMemoryExecutionSessionStore()
        store.connect(project_id=1, user_id=2, datasource_id=3, session_id="s1")
        store.disconnect(session_id="s1")
        assert store.disconnect(session_id="s1") is False


class TestTaskLifecycle:
    """任务状态机：start_task → record_event → finish_task。"""

    def _connect(self, store):
        store.connect(project_id=1, user_id=2, datasource_id=3, session_id="s1")

    def test_start_task(self):
        store = InMemoryExecutionSessionStore()
        self._connect(store)
        view = store.start_task(session_id="s1", task_id="t1")
        assert view["task_id"] == "t1"
        assert view["status"] == "running"

    def test_start_task_requires_connected_session(self):
        store = InMemoryExecutionSessionStore()
        with pytest.raises(ValueError, match="session must be connected"):
            store.start_task(session_id="s1", task_id="t1")

    def test_start_task_duplicate_task_id(self):
        store = InMemoryExecutionSessionStore()
        self._connect(store)
        store.start_task(session_id="s1", task_id="t1")
        with pytest.raises(ValueError, match="already has an active task"):
            store.start_task(session_id="s1", task_id="t1")

    def test_start_task_requires_idle_session(self):
        """已有活跃任务时不可再开新任务。"""
        store = InMemoryExecutionSessionStore()
        self._connect(store)
        store.start_task(session_id="s1", task_id="t1")
        with pytest.raises(ValueError, match="already has an active task"):
            store.start_task(session_id="s1", task_id="t2")

    def test_record_event(self):
        store = InMemoryExecutionSessionStore()
        self._connect(store)
        store.start_task(session_id="s1", task_id="t1")
        store.record_event(task_id="t1", event_id=1)
        store.record_event(task_id="t1", event_id=2)

    def test_record_event_monotonic(self):
        store = InMemoryExecutionSessionStore()
        self._connect(store)
        store.start_task(session_id="s1", task_id="t1")
        store.record_event(task_id="t1", event_id=2)
        with pytest.raises(ValueError, match="monotonically"):
            store.record_event(task_id="t1", event_id=1)

    def test_record_event_terminal_task_rejected(self):
        store = InMemoryExecutionSessionStore()
        self._connect(store)
        store.start_task(session_id="s1", task_id="t1")
        store.finish_task(task_id="t1", status="succeeded")
        with pytest.raises(ValueError, match="terminal"):
            store.record_event(task_id="t1", event_id=1)

    def test_record_event_unknown_task(self):
        store = InMemoryExecutionSessionStore()
        with pytest.raises(KeyError):
            store.record_event(task_id="nonexistent", event_id=1)

    def test_record_event_zero_rejected(self):
        store = InMemoryExecutionSessionStore()
        self._connect(store)
        store.start_task(session_id="s1", task_id="t1")
        with pytest.raises(ValueError, match="positive"):
            store.record_event(task_id="t1", event_id=0)


class TestTerminalStatuses:
    """终态命名 succeeded/failed/canceled/timed_out 与契约一致。"""

    def _setup_running_task(self):
        store = InMemoryExecutionSessionStore()
        store.connect(project_id=1, user_id=2, datasource_id=3, session_id="s1")
        store.start_task(session_id="s1", task_id="t1")
        return store

    def test_finish_succeeded(self):
        store = self._setup_running_task()
        store.finish_task(task_id="t1", status="succeeded")

    def test_finish_failed(self):
        store = self._setup_running_task()
        store.finish_task(task_id="t1", status="failed")

    def test_finish_canceled(self):
        store = self._setup_running_task()
        store.finish_task(task_id="t1", status="canceled")

    def test_finish_timed_out(self):
        store = self._setup_running_task()
        store.finish_task(task_id="t1", status="timed_out")

    def test_finish_invalid_status_rejected(self):
        store = self._setup_running_task()
        with pytest.raises(ValueError, match="terminal status"):
            store.finish_task(task_id="t1", status="running")

    def test_finish_idempotent_same_status(self):
        """同终态重复 finish → 幂等返回。"""
        store = self._setup_running_task()
        store.finish_task(task_id="t1", status="succeeded")
        store.finish_task(task_id="t1", status="succeeded")

    def test_finish_different_terminal_rejected(self):
        """已 succeeded 再 finish failed → 拒绝。"""
        store = self._setup_running_task()
        store.finish_task(task_id="t1", status="succeeded")
        with pytest.raises(ValueError, match="already terminal"):
            store.finish_task(task_id="t1", status="failed")

    def test_finish_unknown_task(self):
        store = InMemoryExecutionSessionStore()
        with pytest.raises(KeyError):
            store.finish_task(task_id="nonexistent", status="succeeded")

    def test_finish_releases_session_slot(self):
        """终态后 session 可开新任务。"""
        store = self._setup_running_task()
        store.finish_task(task_id="t1", status="succeeded")
        view = store.start_task(session_id="s1", task_id="t2")
        assert view["task_id"] == "t2"


class TestSessionViewAfterFinish:
    """终态后 session view 反映 last_task_id 和 task_status。"""

    def test_session_view_after_finish(self):
        store = InMemoryExecutionSessionStore()
        store.connect(project_id=1, user_id=2, datasource_id=3, session_id="s1")
        store.start_task(session_id="s1", task_id="t1")
        store.finish_task(task_id="t1", status="succeeded")
        # 重新 connect 查看状态
        view = store.connect(project_id=1, user_id=2, datasource_id=3, session_id="s1")
        assert view["last_task_id"] == "t1"
        assert view["task_status"] == "succeeded"
        assert view["execution_count"] == 1


class TestCancellation:
    """取消幂等：request_cancellation 信任终态。"""

    class _FakeSession:
        def __init__(self, cancel_result, status_response):
            self._cancel_result = cancel_result
            self._status_response = status_response

        def cancel(self, *, task_id):
            return self._cancel_result

        def status(self, *, task_id):
            return self._status_response

    def test_cancel_terminal_succeeded(self):
        session = self._FakeSession(True, {"status": "succeeded"})
        result = request_cancellation(session, task_id="t1")
        assert result.status == "succeeded"
        assert result.terminal is True
        assert result.reusable is True

    def test_cancel_terminal_failed(self):
        session = self._FakeSession(True, {"status": "failed"})
        result = request_cancellation(session, task_id="t1")
        assert result.status == "failed"
        assert result.terminal is True

    def test_cancel_in_progress(self):
        session = self._FakeSession(True, {"status": "running"})
        result = request_cancellation(session, task_id="t1")
        assert result.terminal is False
        assert result.reusable is False

    def test_cancel_unknown_status(self):
        session = self._FakeSession(True, {"status": "weird_state"})
        result = request_cancellation(session, task_id="t1")
        assert result.status == "unknown"
        assert result.terminal is False

    def test_cancel_exception_during_cancel(self):
        class _BadCancelSession:
            def cancel(self, *, task_id):
                raise RuntimeError("network error")

            def status(self, *, task_id):
                return {"status": "running"}

        result = request_cancellation(_BadCancelSession(), task_id="t1")
        assert result.terminal is False

    def test_cancel_exception_during_status(self):
        class _BadStatusSession:
            def cancel(self, *, task_id):
                return True

            def status(self, *, task_id):
                raise RuntimeError("network error")

        result = request_cancellation(_BadStatusSession(), task_id="t1")
        assert result.status == "unknown"
        assert result.terminal is False
        assert result.reusable is False

    def test_cancel_canceled_status(self):
        session = self._FakeSession(True, {"status": "canceled"})
        result = request_cancellation(session, task_id="t1")
        assert result.status == "canceled"
        assert result.terminal is True

    def test_cancel_timed_out_status(self):
        session = self._FakeSession(True, {"status": "timed_out"})
        result = request_cancellation(session, task_id="t1")
        assert result.status == "timed_out"
        assert result.terminal is True


class TestExecutionIdempotency:
    """executeSql 幂等键+摘要（通过 session_store execution_count 验证串行执行计数）。"""

    def test_execution_count_increments(self):
        store = InMemoryExecutionSessionStore()
        store.connect(project_id=1, user_id=2, datasource_id=3, session_id="s1")
        store.start_task(session_id="s1", task_id="t1")
        store.finish_task(task_id="t1", status="succeeded")
        store.start_task(session_id="s1", task_id="t2")
        store.finish_task(task_id="t2", status="failed")
        view = store.connect(project_id=1, user_id=2, datasource_id=3, session_id="s1")
        assert view["execution_count"] == 2
