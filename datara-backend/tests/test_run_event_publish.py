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
