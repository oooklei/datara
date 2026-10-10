"""E1 实例状态 SSE 流（GET /instances/{id}/stream）单测。

- 连接即推基线快照（task_state_changed 全量、幂等 patch 口径）；
- DB 状态变更后下一轮 diff 推增量；实例转终态推 instance_finished 后服务端关流；
- 已终态实例：基线 + instance_finished 立即关流；
- 空闲心跳注释行；新增任务行（循环扩行）视为变更推送；404/权限闸门。

测试策略（关键教训，两处）：
- starlette TestClient 对响应体整体缓冲——有限流（终态即关流）可用 client 正常测；
  无限流（运行中实例）会永久挂死 → 运行中场景直调端点函数取 body_iterator 逐帧拉取；
- body_iterator 是 async generator（iterate_in_threadpool），asyncio.run 每次重建事件
  循环时 shutdown_asyncgens 会关掉它 → 整个交互必须跑在**单个**事件循环里（SSESession）；
- gen 每轮 session.close() 会 expunge 身份映射（生产语义：读者会话自清理）→ 测试若与流
  共用一个 session 做写入，改完 commit 实际不落库（对象已 detach）。**流开后的状态变更必须
  走独立 writer session**（对应生产中 master 进程独立写库的真实拓扑）。

夹具复用 conftest（sqlite 内存库 + dependency_overrides）：
- _stream_session 打桩返回共享 db_session（生产为每轮独立短会话）；
- SSE_POLL_SEC 调速 0.01s，测试秒级完成。
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

import api.instance as instance_mod
from common.models import TRunEvent, TaskInstance, WorkflowInstance

IID = "20260927-stream-0001"
USER = SimpleNamespace(id=1, user_name="tester", user_role="dev")


def set_role(app, role: str) -> None:
    """切换注入用户角色（与 conftest.set_role 同实现；conftest 不可直接 import）。"""
    from api.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, user_name="tester", user_role=role)


@pytest.fixture(autouse=True)
def fast_sse(db_session, monkeypatch):
    """SSE 全局调速：流内会话指向共享 sqlite 会话 + 轮询 0.01s（生产 1s/独立短会话）。"""
    monkeypatch.setattr(instance_mod, "_stream_session", lambda: db_session)
    monkeypatch.setattr(instance_mod, "SSE_POLL_SEC", 0.01)


def _mk_instance(db, state="running", end_time=None):
    db.add(WorkflowInstance(instance_id=IID, wf_code=1, state=state, end_time=end_time))
    db.commit()


def _mk_task(db, node_id, state, attempt=1):
    t = TaskInstance(instance_id=IID, node_id=node_id, node_type="sql", name=f"节点{node_id}",
                     state=state, attempt=attempt)
    db.add(t)
    db.commit()
    return t


def _mk_run_event(db, event_id, event_type="node_executed", payload='{"state": "success"}'):
    row = TRunEvent(
        id=event_id,
        run_id=IID,
        node_id="n1",
        event_type=event_type,
        payload_json=payload,
    )
    db.add(row)
    db.commit()
    return row


class SSESession:
    """单事件循环内驱动 SSE 流：拉取事件帧 / 断言关流（教训见模块 docstring）。"""

    def __init__(self, body_iterator):
        self.it = body_iterator

    async def events(self, n: int, timeout: float = 5.0):
        """拉取直到解析出 n 个事件帧（心跳/空帧跳过；流提前结束则断言失败）。"""
        events: list[tuple[str, dict]] = []
        pending = None
        while len(events) < n:
            try:
                chunk = await asyncio.wait_for(self.it.__anext__(), timeout)
            except StopAsyncIteration:
                raise AssertionError(f"流提前关闭，仅得 {len(events)}/{n} 事件: {events}")
            for line in chunk.split("\n"):
                if line.startswith("event: "):
                    pending = line[len("event: "):]
                elif line.startswith("data: ") and pending:
                    events.append((pending, json.loads(line[len("data: "):])))
                    pending = None
        return events

    async def heartbeat(self, timeout: float = 5.0) -> str:
        """拉一个原始 chunk（心跳用例断言注释行）。"""
        return await asyncio.wait_for(self.it.__anext__(), timeout)

    async def assert_closed(self):
        try:
            chunk = await asyncio.wait_for(self.it.__anext__(), 2.0)
        except StopAsyncIteration:
            return
        raise AssertionError(f"流未按预期关闭，仍产出: {chunk!r}")


def _open_stream(db) -> SSESession:
    """直调端点取 body_iterator（绕开 TestClient 整体缓冲；无限流场景专用）。"""
    resp = instance_mod.stream_instance(IID, user=USER, db=db)
    return SSESession(resp.body_iterator)


def _writer(db):
    """独立写会话（同引擎同连接）：流内 gen 的 close() 会 expunge 共享 session 的对象，
    之后再用它 commit 是空写（教训见模块 docstring）；生产中状态变更是 master 独立写库。"""
    from sqlalchemy.orm import sessionmaker
    return sessionmaker(bind=db.get_bind(), expire_on_commit=False)()


def test_stream_404_unknown_instance(client):
    assert client.get(f"/api/v1/instances/{IID}/stream").status_code == 404


def test_stream_requires_view_all(client, db_session):
    """权限闸门与详情接口同口径（view_all）：未知角色权限空集 → 403。"""
    set_role(client.app, "dev")
    _mk_instance(db_session, state="success")  # 终态 → 有限流，TestClient 可整体缓冲
    resp = client.get(f"/api/v1/instances/{IID}/stream")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert "instance_finished" in resp.text
    set_role(client.app, "guest")  # ROLE_PERMS 无 guest → 权限空集
    assert client.get(f"/api/v1/instances/{IID}/stream").status_code == 403


def test_stream_terminal_instance_snapshot_then_close(db_session):
    """已终态实例：基线快照 + instance_finished 后服务端关流（直调拉取口径）。"""
    _mk_instance(db_session, state="success")
    _mk_task(db_session, "n1", "success")
    _mk_task(db_session, "n2", "skip")

    async def main():
        s = _open_stream(db_session)
        events = await s.events(3)
        assert [e[0] for e in events] == ["task_state_changed", "task_state_changed", "instance_finished"]
        n1 = events[0][1]
        assert n1["nodeId"] == "n1" and n1["state"] == "success" and n1["taskId"] > 0
        fin = events[2][1]
        assert fin["instanceId"] == IID and fin["state"] == "success"
        await s.assert_closed()

    asyncio.run(main())


def test_list_run_events_paginates_and_supports_resume_cursor(client, db_session):
    _mk_instance(db_session, state="running")
    _mk_run_event(db_session, 1, "node_executing")
    _mk_run_event(db_session, 2, "node_executed")
    _mk_run_event(db_session, 3, "execution_success")

    latest = client.get(f"/api/v1/instances/{IID}/events?page_size=2")
    assert latest.status_code == 200
    body = latest.json()["data"]
    assert body["total"] == 3
    assert [item["id"] for item in body["list"]] == [3, 2]
    assert body["list"][1]["payload"] == {"state": "success"}

    resumed = client.get(f"/api/v1/instances/{IID}/events?after_id=1")
    assert [item["id"] for item in resumed.json()["data"]["list"]] == [2, 3]


def test_stream_replays_run_events_and_honors_last_event_id(db_session):
    _mk_instance(db_session, state="running")
    _mk_run_event(db_session, 1, "node_executing")
    _mk_run_event(db_session, 2, "node_executed")

    async def main():
        s = SSESession(instance_mod.stream_instance(
            IID, last_event_id="1", user=USER, db=db_session,
        ).body_iterator)
        events = await s.events(1)
        assert events[0][0] == "node_event"
        payload = events[0][1]
        assert payload["id"] == 2 and payload["type"] == "node_executed"
        assert payload["payload"] == {"state": "success"} and payload["ts"]

    asyncio.run(main())


def test_terminal_stream_replays_every_durable_event_before_closing(db_session):
    _mk_instance(db_session, state="success")
    db_session.add_all([
        TRunEvent(
            id=event_id,
            run_id=IID,
            node_id="n1",
            event_type="progress",
            payload_json=json.dumps({"value": event_id}),
        )
        for event_id in range(1, 202)
    ])
    db_session.commit()

    async def main():
        s = _open_stream(db_session)
        events = await s.events(202)
        node_events = [payload for name, payload in events if name == "node_event"]
        assert [item["id"] for item in node_events] == list(range(1, 202))
        assert events[-1][0] == "instance_finished"
        await s.assert_closed()

    asyncio.run(main())


def test_stream_running_diff_then_finish(db_session):
    """运行中实例：基线 → 无变更不重推 → DB 变更推增量（含 attempt）→ 终态 finished 关流。"""
    _mk_instance(db_session)
    t1 = _mk_task(db_session, "n1", "running")
    _mk_task(db_session, "n2", "success")

    async def main():
        s = _open_stream(db_session)
        baseline = await s.events(2)
        assert [e[1]["nodeId"] for e in baseline] == ["n1", "n2"]
        # ① 任务状态变更（独立 writer，模拟 master 落库）→ 下一轮 diff 单帧推送
        writer = _writer(db_session)
        writer.get(TaskInstance, t1.id).state = "success"
        writer.get(TaskInstance, t1.id).attempt = 2
        writer.commit()
        diff = await s.events(1)
        assert diff[0][0] == "task_state_changed"
        assert diff[0][1]["nodeId"] == "n1" and diff[0][1]["state"] == "success"
        assert diff[0][1]["attempt"] == 2
        # ② 实例转终态 → instance_finished 后关流
        inst = writer.query(WorkflowInstance).filter_by(instance_id=IID).first()
        inst.state = "success"
        writer.commit()
        fin = await s.events(1)
        assert fin[0][0] == "instance_finished" and fin[0][1]["state"] == "success"
        await s.assert_closed()

    asyncio.run(main())


def test_stream_heartbeat_when_idle(db_session, monkeypatch):
    """空闲无事件按 HEARTBEAT_SEC 推注释行心跳（防代理断连）。"""
    monkeypatch.setattr(instance_mod, "SSE_HEARTBEAT_SEC", 0.05)
    _mk_instance(db_session)
    _mk_task(db_session, "n1", "running")

    async def main():
        s = _open_stream(db_session)
        await s.events(1)  # 基线
        chunk = await s.heartbeat()
        assert chunk.startswith(": heartbeat"), chunk

    asyncio.run(main())


def test_stream_new_task_row_appended(db_session):
    """流中途新增任务行（循环迭代扩行）：基线外的 id 视为变更推增量。"""
    _mk_instance(db_session)
    _mk_task(db_session, "n1", "success")

    async def main():
        s = _open_stream(db_session)
        await s.events(1)  # 基线 n1
        _mk_task(db_session, "n1", "running")  # 循环第 2 轮新行
        diff = await s.events(1)
        assert diff[0][1]["nodeId"] == "n1" and diff[0][1]["state"] == "running"

    asyncio.run(main())
