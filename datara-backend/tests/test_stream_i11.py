"""I11 流处理组件单测：Simulate/Redis Stream/MQTT 三新源 + WindowAggOp 新聚合函数。

覆盖（对齐 stream-realtime-demos 三 use_case 的事件 schema）：
1. SimulateSource：三数据集事件 schema 与比例字段、simEvents 过滤分路、eps 速率摊派、越界钳制；
2. RedisStreamSource：XREADGROUP 解析、消息两种形态解码（data=JSON 串 / 整 fields）、
   BUSYGROUP 续跑容错、缺配置报错；
3. MqttSource：回调线程 → 队列桥接、poll 出队、队满背压丢新包、缺配置报错；
4. build_source 七源工厂分发与未知分型报错；
5. WindowAggOp：count_distinct 任意类型去重（排除 None）、rms、混合多字段聚合、
   未知聚合函数报错、窗口到期定时触发端到端。

kafka 依赖的单测见 test_stream_sources.py（I9），本文件自举模式与其一致：
stub common.* 轻量模块 + importlib 独立加载（simpleeval 以最小桩注入，仅满足 import，
WindowAggOp 不调用表达式求值）。
"""

import importlib.util
import logging
import math
import pathlib
import sys
import time
import types
from collections import Counter

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _stub(mod_name, **attrs):
    mod = types.ModuleType(mod_name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[mod_name] = mod
    return mod


def _load(mod_name, rel_path, stubs):
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    for name, attrs in stubs.items():
        _stub(name, **attrs)
    spec = importlib.util.spec_from_file_location(mod_name, ROOT / rel_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[mod_name] = mod
    return mod


def _load_sources():
    return _load("datara_test_stream_i11_sources", "worker/stream/sources.py", {
        "common": {},
        "common.dsconn": {"resolve_file_path": lambda p: p},
        "common.db": {"new_session": lambda: None},
        "common.log": {"get_logger": logging.getLogger},
        "common.models": {"DataSource": type("DataSource", (), {})},
    })


def _load_ops():
    return _load("datara_test_stream_i11_ops", "worker/stream/ops.py", {
        "common.log": {"get_logger": logging.getLogger},
        "simpleeval": {"simple_eval": lambda expr, names=None: eval(expr, {"__builtins__": {}}, dict(names or {}))},
    })


_sources = _load_sources()
_ops = _load_ops()
SimulateSource = _sources.SimulateSource
RedisStreamSource = _sources.RedisStreamSource
MqttSource = _sources.MqttSource
build_source = _sources.build_source
SourceError = _sources.SourceError
WindowAggOp = _ops.WindowAggOp
OpError = _ops.OpError


# ---------- build_source 七源工厂 ----------

def test_build_source_dispatch():
    assert isinstance(build_source("n1", {"srcType": "simulate"}), SimulateSource)
    assert isinstance(build_source("n1", {"srcType": "redis"}), RedisStreamSource)
    assert isinstance(build_source("n1", {"srcType": "mqtt"}), MqttSource)


def test_build_source_unknown_type():
    with pytest.raises(SourceError, match="未知流输入分型"):
        build_source("n1", {"srcType": "nope"})


# ---------- SimulateSource ----------

ECOM_FIELDSETS = {
    "order_pay": {"order_id", "user_id", "goods_id", "amount", "ts"},
    "user_click": {"user_id", "goods_id", "ts"},
    "cart_event": {"user_id", "goods_id", "action", "ts"},
}
IOT_FIELDSETS = {
    "temp": {"device", "value", "ts"},
    "press": {"device", "value", "ts"},
    "vib": {"device", "value", "ts"},
    "alert": {"device", "type", "ts"},
}
VISIT_FIELDSETS = {
    "order": {"order_id", "user_id", "amount", "ts"},
    "visit": {"user_id", "page", "ts"},
}


def _drain(src, rounds=80):
    """连续 poll 收集样本（eps=5 → 每轮配额 1 条）。"""
    rows = []
    for _ in range(rounds):
        rows.extend(src.poll(100))
    return rows


@pytest.mark.parametrize("dataset,fieldsets", [
    ("ecommerce", ECOM_FIELDSETS),
    ("iot", IOT_FIELDSETS),
    ("visit", VISIT_FIELDSETS),
])
def test_simulate_event_schema(dataset, fieldsets):
    # 400 条：iot alert 概率 0.02 期望 ~8 条（P(零)=0.0003），visit order 0.2 期望 ~80 条
    rows = _drain(SimulateSource("n1", {"simDataset": dataset}), rounds=400)
    for r in rows:
        name = r["data"]["event"]
        assert name in fieldsets, f"未预期事件 {name}"
        assert fieldsets[name] <= set(r["data"]), f"{name} 缺字段: {r['data']}"
        assert r["source"] == "n1:simulate"
        assert isinstance(r["ts"], float)
    seen = {r["data"]["event"] for r in rows}
    assert seen == set(fieldsets), f"事件覆盖不全: {seen} vs {set(fieldsets)}"


def test_simulate_ecommerce_ratio():
    """ecommerce 三事件近 demo 比例（0.2/0.6/0.2，宽松断言防 flaky）。"""
    rows = _drain(SimulateSource("n1", {"simDataset": "ecommerce"}), rounds=400)
    cnt = Counter(r["data"]["event"] for r in rows)
    assert cnt["user_click"] > cnt["order_pay"] * 1.8
    assert cnt["user_click"] > cnt["cart_event"] * 1.8


def test_simulate_events_filter():
    """simEvents 过滤分路：本源只产生指定事件（多源分路场景）。"""
    src = SimulateSource("n1", {"simDataset": "iot", "simEvents": "temp,press"})
    src.open(None)
    rows = _drain(src, rounds=120)
    assert rows, "过滤后无产出"
    assert {r["data"]["event"] for r in rows} <= {"temp", "press"}


def test_simulate_rate_quota():
    """eps=5 → 每 200ms 轮配额恰好 1 条；offset 暴露剩余配额。"""
    src = SimulateSource("n1", {"simDataset": "visit", "simEps": 5})
    src.open(None)
    assert len(src.poll(100)) == 1
    assert len(src.poll(100)) == 1
    assert src.offset == {"quota": 0.0}


def test_simulate_eps_clamp():
    assert SimulateSource("n1", {"simEps": 1000}).eps == 200.0
    assert SimulateSource("n1", {"simEps": "abc"}).eps == 5.0
    assert SimulateSource("n1", {}).eps == 5.0


# ---------- RedisStreamSource ----------

class FakeRedis:
    instances: list["FakeRedis"] = []
    busygroup_keys: set = set()  # 类属性（测试注入）：这些 (stream, group) 已存在 → raise BUSYGROUP

    def __init__(self, **kw):
        self.kw = kw
        self.groups: list = []
        self.xread_calls: list = []
        self.xread_responses: list = []
        # busygroup_keys 为类属性（测试注入），实例不覆盖
        FakeRedis.instances.append(self)

    @classmethod
    def from_url(cls, url, **kw):
        return cls(url=url, **kw)

    def ping(self):
        return True

    def xgroup_create(self, stream, group, id="$", mkstream=False):
        if (stream, group) in self.busygroup_keys:
            raise RuntimeError("BUSYGROUP Consumer Group name already exists")
        self.groups.append((stream, group, id))

    def xreadgroup(self, group, consumer, streams=None, count=None, block=None):
        self.xread_calls.append((group, consumer, dict(streams or {}), count, block))
        return self.xread_responses.pop(0) if self.xread_responses else []

    def close(self):
        pass


@pytest.fixture()
def fake_redis(monkeypatch):
    FakeRedis.instances = []
    fake_asyncio = types.ModuleType("redis.asyncio")
    fake_pkg = types.SimpleNamespace(Redis=FakeRedis, asyncio=fake_asyncio)
    monkeypatch.setitem(sys.modules, "redis", fake_pkg)
    monkeypatch.setitem(sys.modules, "redis.asyncio", fake_asyncio)
    return FakeRedis


def test_redis_open_requires_config():
    src = RedisStreamSource("n1", {"streamsText": "s1"})
    with pytest.raises(SourceError, match="Redis URL"):
        src.open(None)
    src2 = RedisStreamSource("n1", {"redisUrl": "redis://x:6379/0"})
    with pytest.raises(SourceError, match="Stream"):
        src2.open(None)


def test_redis_open_and_group(fake_redis):
    src = RedisStreamSource("n1", {
        "redisUrl": "redis://redis:6379/0", "streamsText": "s1,s2", "redisGroup": "g1",
    })
    src.open({"streams": ["s1"], "group": "g1"})  # 注入旧位点：open 不做核对仅装配
    r = fake_redis.instances[0]
    assert r.kw["url"] == "redis://redis:6379/0"
    assert r.groups == [("s1", "g1", "$"), ("s2", "g1", "$")]


def test_redis_open_busygroup_tolerated(fake_redis):
    """BUSYGROUP = 组已存在（重启续跑），open 不报错。"""
    fake_redis.busygroup_keys = {("s1", "g1")}
    src = RedisStreamSource("n1", {"redisUrl": "redis://x/0", "streamsText": "s1", "redisGroup": "g1"})
    src.open(None)  # 不抛
    assert fake_redis.instances[0].groups == []


def test_redis_poll_decode_shapes(fake_redis):
    """消息两种形态：data=JSON 串（灌数形态）/ 整 fields 即数据；ts 从 data 提取。"""
    src = RedisStreamSource("n1", {"redisUrl": "redis://x/0", "streamsText": "orders"})
    src.open(None)
    r = fake_redis.instances[0]
    r.xread_responses = [[
        ("orders", [
            ("1-1", {"data": '{"order_id":"o1","amount":9.9,"ts":1000.5}'}),
            ("1-2", {"user_id": "u1", "page": "/home"}),
            ("1-3", {"data": "not-json"}),
            ("1-4", {"data": "[1,2]"}),  # 非 dict JSON → {"value": [...]}
        ]),
    ]]
    rows = src.poll(10)
    assert len(rows) == 3  # 坏 JSON 跳过
    assert rows[0] == {"source": "n1:redis:orders", "ts": 1000.5, "data": {"order_id": "o1", "amount": 9.9}}
    assert rows[1]["data"] == {"user_id": "u1", "page": "/home"}
    assert rows[2]["data"] == {"value": [1, 2]}
    # 消费参数：count=max_rows，block=400ms，'>' 只取未投递消息
    g, c, streams, count, block = r.xread_calls[0]
    assert (g, c, streams, count, block) == ("datara-flink", "c1", {"orders": ">"}, 10, 400)
    src.close()


def test_redis_offset_contract(fake_redis):
    src = RedisStreamSource("n1", {"redisUrl": "redis://x/0", "streamsText": "a,b", "redisGroup": "g9"})
    src.open(None)
    assert src.offset == {"streams": ["a", "b"], "group": "g9"}


# ---------- MqttSource ----------

class FakeMqttClient:
    def __init__(self, api_version):
        self.api_version = api_version
        self.on_message = None
        self.connected = None
        self.subscribed: list = []
        self.loop_started = False

    def connect(self, host, port, keepalive=60):
        self.connected = (host, port)

    def subscribe(self, topic, qos=0):
        self.subscribed.append((topic, qos))

    def loop_start(self):
        self.loop_started = True

    def loop_stop(self):
        pass

    def disconnect(self):
        pass


@pytest.fixture()
def fake_paho(monkeypatch):
    created: list[FakeMqttClient] = []

    def factory(api_version):
        c = FakeMqttClient(api_version)
        created.append(c)
        return c

    client_mod = types.ModuleType("paho.mqtt.client")
    client_mod.Client = factory
    client_mod.CallbackAPIVersion = types.SimpleNamespace(VERSION2=2)
    monkeypatch.setitem(sys.modules, "paho", types.ModuleType("paho"))
    monkeypatch.setitem(sys.modules, "paho.mqtt", types.ModuleType("paho.mqtt"))
    monkeypatch.setitem(sys.modules, "paho.mqtt.client", client_mod)
    return created


def _msg(topic: str, payload: bytes):
    return types.SimpleNamespace(topic=topic, payload=payload)


def test_mqtt_open_requires_config():
    src = MqttSource("n1", {"mqttTopics": "t1"})
    with pytest.raises(SourceError, match="MQTT"):
        src.open(None)
    src2 = MqttSource("n1", {"mqttHost": "h"})
    with pytest.raises(SourceError, match="MQTT"):
        src2.open(None)


def test_mqtt_open_subscribe(fake_paho):
    src = MqttSource("n1", {"mqttHost": "datara-emqx", "mqttPort": 1883, "mqttTopics": "iot/temp,iot/press"})
    src.open(None)
    c = fake_paho[0]
    assert c.api_version == 2  # CallbackAPIVersion.VERSION2（paho 2.x 契约）
    assert c.connected == ("datara-emqx", 1883)
    assert c.subscribed == [("iot/temp", 0), ("iot/press", 0)]
    assert c.loop_started
    src.close()


def test_mqtt_poll_queue_bridge(fake_paho):
    """回调入队 → poll 出队；坏 payload 降级 {"value": 文本}；ts 提取。"""
    src = MqttSource("n1", {"mqttHost": "h", "mqttTopics": "iot/temp"})
    src.open(None)
    c = fake_paho[0]
    c.on_message(None, None, _msg("iot/temp", b'{"device":"d1","value":45.5,"ts":2000.0}'))
    c.on_message(None, None, _msg("iot/temp", b'raw-text'))
    rows = src.poll(10)
    assert len(rows) == 2
    assert rows[0] == {"source": "n1:mqtt:iot/temp", "ts": 2000.0, "data": {"device": "d1", "value": 45.5}}
    assert rows[1]["data"] == {"value": "raw-text"}
    assert src.offset == {"topics": ["iot/temp"]}


def test_mqtt_queue_full_backpressure(fake_paho):
    """队满丢新包（QoS0 背压语义），不抛异常。"""
    src = MqttSource("n1", {"mqttHost": "h", "mqttTopics": "t"})
    src.open(None)
    import queue as pyqueue
    src._queue = pyqueue.Queue(maxsize=1)
    src._queue.put(("t", {"old": 1}))  # 占满
    c = fake_paho[0]
    c.on_message(None, None, _msg("t", b'{"new":2}'))  # 被丢弃，不抛
    rows = src.poll(10)
    assert rows == [{"source": "n1:mqtt:t", "ts": rows[0]["ts"], "data": {"old": 1}}]


# ---------- WindowAggOp 新聚合函数 ----------

def _mk_op(aggs, group_keys=""):
    return WindowAggOp({"groupKeys": group_keys, "aggs": aggs, "windowType": "tumbling",
                        "windowSizeSec": 5, "watermarkSec": 0})


def test_window_unknown_func_raises():
    with pytest.raises(OpError, match="未知聚合函数"):
        _mk_op([{"key": "v", "value": "median:x"}])


def test_window_count_distinct_any_type():
    """count_distinct 对任意类型去重（字符串/数值混合），None 不计入。"""
    op = _mk_op([{"key": "user_id", "value": "count_distinct:uv"}])
    bucket = {"start": 100, "end": 105, "rows": [
        {"user_id": "u1"}, {"user_id": "u2"}, {"user_id": "u1"}, {}, {"user_id": None},
    ]}
    out = op._result(bucket)["data"]
    assert out["uv"] == 2


def test_window_rms():
    op = _mk_op([{"key": "vib", "value": "rms:vib_rms"}])
    bucket = {"start": 0, "end": 5, "rows": [{"vib": 3}, {"vib": 4}, {"other": 1}]}
    out = op._result(bucket)["data"]
    assert math.isclose(out["vib_rms"], math.sqrt((9 + 16) / 2))


def test_window_mixed_aggs_iot_shape():
    """IoT 场景混合聚合：avg/max/rms/count_distinct 同窗口并行 + 分组键回填。"""
    op = _mk_op([
        {"key": "temp", "value": "avg:temp_avg"},
        {"key": "press", "value": "max:press_max"},
        {"key": "vib", "value": "rms:vib_rms"},
        {"key": "user", "value": "count_distinct:uv"},
    ], group_keys="device")
    bucket = {"start": 10, "end": 15, "rows": [
        {"device": "d1", "temp": 40, "press": 3.0, "vib": 3, "user": "u1"},
        {"device": "d1", "temp": 50, "press": 4.0, "vib": 4, "user": "u2"},
        {"device": "d1", "temp": 45, "vib": 0, "user": "u1"},  # 无 press
    ]}
    out = op._result(bucket)["data"]
    assert out["device"] == "d1"
    assert out["temp_avg"] == 45.0
    assert out["press_max"] == 4.0  # 缺失行被数值过滤
    assert math.isclose(out["vib_rms"], math.sqrt(25 / 3))
    assert out["uv"] == 2
    assert (out["win_start"], out["win_end"]) == (10, 15)


def test_window_count_len_rows():
    op = _mk_op([{"key": "x", "value": "count:n"}])
    out = op._result({"start": 0, "end": 5, "rows": [{"a": 1}, {"b": 2}]})["data"]
    assert out["n"] == 2


def test_window_fire_end_to_end():
    """到期窗口由定时线程触发投递（水位线 0，行 ts 已过窗口 end）。"""
    op = WindowAggOp({"windowType": "tumbling", "windowSizeSec": 2, "watermarkSec": 0,
                      "aggs": [{"key": "v", "value": "sum:s"}]})
    outs: list = []
    op.bind_emit(outs.append)
    op.open()
    try:
        ts = time.time() - 5  # 落在已到期桶
        ws = int(ts // 2) * 2
        noop = lambda _r: None  # noqa: E731 原始行透传不关心
        op.process({"source": "n1", "ts": ts, "data": {"v": 7}}, noop)
        op.process({"source": "n1", "ts": ts, "data": {"v": 8}}, noop)
        deadline = time.time() + 5
        while not outs and time.time() < deadline:
            time.sleep(0.1)
        assert outs, "窗口未触发"
        out = outs[0]["data"]
        assert out["s"] == 15
        assert out["win_start"] == ws
        assert outs[0]["source"] == "window"
    finally:
        op.close()
