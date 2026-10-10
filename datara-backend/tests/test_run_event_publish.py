import json

from master import event_bus


class FakeRedis:
    def __init__(self):
        self.calls = []

    def publish(self, channel, message):
        self.calls.append((channel, json.loads(message)))


class FakeSession:
    def __init__(self):
        self.rows = []
        self.committed = False

    def add(self, row):
        self.rows.append(row)

    def commit(self):
        self.committed = True

    def close(self):
        pass


def test_publish_run_event_publishes_and_persists(monkeypatch):
    fake_db = FakeSession()
    monkeypatch.setattr(event_bus, "new_session", lambda: fake_db)
    fake_redis = FakeRedis()

    message = event_bus.publish_run_event(
        "run-1", "node-1", "node_executing", {"attempt": 1}, rds=fake_redis)

    assert fake_redis.calls == [("datara:run_events:run-1", message)]
    assert {"runId", "nodeId", "type", "ts", "payload"} <= set(message)
    assert message["type"] == "node_executing"
    assert fake_db.committed is True
    assert fake_db.rows[0].run_id == "run-1"
    assert fake_db.rows[0].event_type == "node_executing"


def test_publish_failure_is_non_fatal(monkeypatch):
    class BrokenRedis:
        def publish(self, *_args):
            raise RuntimeError("redis unavailable")

    class BrokenSession:
        def add(self, _row):
            raise RuntimeError("db unavailable")

        def close(self):
            pass

    monkeypatch.setattr(event_bus, "new_session", lambda: BrokenSession())
    message = event_bus.publish_run_event("run-2", "", "execution_start", rds=BrokenRedis())
    assert message["runId"] == "run-2"


# ---- progress 事件 200ms 合帧（方案 R6：窗口内多次只发最后一次；其余类型不节流）----
# 测试用 50ms 窗口等比加速，语义与生产 PROGRESS_FRAME_SEC=0.2 一致。


def test_progress_burst_coalesces_to_latest(monkeypatch):
    """同一 (run, node) 在合帧窗口内连发多次 → 到点只发最新一条（发布+落库各一条）。"""
    fake_db = FakeSession()
    monkeypatch.setattr(event_bus, "new_session", lambda: fake_db)
    framer = event_bus._ProgressFramer(window=0.05)
    fake_redis = FakeRedis()

    for value in range(5):  # 窗口内高频连发
        framer.submit("run-1", "n1", {"value": value, "max": 10}, rds=fake_redis)

    assert framer.wait_drained(timeout=2.0)
    assert len(fake_redis.calls) == 1, "窗口内多次 progress 只应发出最后一次"
    channel, message = fake_redis.calls[0]
    assert channel == "datara:run_events:run-1"
    assert message["type"] == "progress"
    assert message["payload"] == {"value": 4, "max": 10}
    assert len(fake_db.rows) == 1 and fake_db.rows[0].event_type == "progress"  # 落库同口径


def test_progress_coalesce_is_per_run_node(monkeypatch):
    """不同 run/node 的 progress 各自成帧，互不合并。"""
    monkeypatch.setattr(event_bus, "new_session", lambda: FakeSession())
    framer = event_bus._ProgressFramer(window=0.05)
    fake_redis = FakeRedis()

    framer.submit("run-1", "n1", {"value": 1}, rds=fake_redis)
    framer.submit("run-1", "n2", {"value": 2}, rds=fake_redis)
    framer.submit("run-2", "n1", {"value": 3}, rds=fake_redis)

    assert framer.wait_drained(timeout=2.0)
    assert len(fake_redis.calls) == 3


def test_progress_framed_via_publish_entrypoint(monkeypatch):
    """publish_run_event 对 progress 走合帧（窗口内不直发），其余事件类型即时直发。"""
    monkeypatch.setattr(event_bus, "new_session", lambda: FakeSession())
    framer = event_bus._ProgressFramer(window=0.05)
    monkeypatch.setattr(event_bus, "_framer", framer)
    fake_redis = FakeRedis()

    for value in range(3):
        message = event_bus.publish_run_event(
            "run-1", "n1", "progress", {"value": value}, rds=fake_redis)
        assert message["type"] == "progress"
    assert fake_redis.calls == [], "progress 在合帧窗口内不应直发"
    assert framer.wait_drained(timeout=2.0)
    assert [m["payload"]["value"] for _c, m in fake_redis.calls] == [2]  # 只发最新

    event_bus.publish_run_event("run-1", "n1", "node_executing", {"attempt": 1}, rds=fake_redis)
    assert fake_redis.calls[-1][1]["type"] == "node_executing"  # 非 progress 不节流
