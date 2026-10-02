import json

from common import monitor


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.hashes = {}

    def set(self, key, value, ex): self.values[key] = (value, ex)
    def get(self, key): return self.values.get(key, (None,))[0]
    def hset(self, key, field, value): self.hashes.setdefault(key, {})[field] = value
    def hgetall(self, key): return self.hashes.get(key, {})
    def expire(self, key, ttl): self.values[f"ttl:{key}"] = ttl


def test_reported_metrics_include_time_and_known_node(monkeypatch) -> None:
    client = FakeRedis()
    monkeypatch.setattr(monitor, "collect_metrics", lambda: {"cpu": 12.5})
    monkeypatch.setattr(monitor.redis_queue, "get_client", lambda: client)
    monkeypatch.setattr(monitor.time, "time", lambda: 1000.0)
    monitor.report_metrics("worker", "node-a")
    raw, ttl = client.values[monitor.metrics_key("worker", "node-a")]
    assert json.loads(raw) == {"cpu": 12.5, "reportedAt": 1000.0}
    assert ttl == monitor.METRICS_TTL_SEC
    assert monitor.read_known_nodes("worker") == {"node-a": 1000.0}


def test_known_node_survives_missing_metric_value(monkeypatch) -> None:
    client = FakeRedis()
    client.hashes[monitor.known_nodes_key("master")] = {"node-old": "900.5"}
    monkeypatch.setattr(monitor.redis_queue, "get_client", lambda: client)
    assert monitor.read_metrics("master", "node-old") is None
    assert monitor.read_known_nodes("master") == {"node-old": 900.5}
