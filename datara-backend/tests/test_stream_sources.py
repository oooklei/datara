"""KafkaSource 位点恢复门控单测（I9 修复 I8 open() seek 时机 bug，I9 设计文档 §3.4/裁定项4）。

背景：I8 实现 open() 后立即 poll(timeout_ms=200)+seek，组 join/assignment 未就绪时
assignment() 为空 → seek 被跳过 → 重启按 auto_offset_reset=earliest 整题重放。
修复：open() 只暂存位点（_saved），poll() 门控——assignment 就绪先 seek 再消费；
未就绪仅推进组协调不消费（预取记录不入 _offsets，seek 后重取，不丢不重）。

测试以假 kafka 模块注入 sys.modules（kafka-python 非测试依赖），覆盖：
1. 续跑：分配就绪后按 saved 位点 seek，未保存分区不动（交给 auto_offset_reset）；
2. 首跑：无 saved 位点不做任何 seek（保持 auto_offset_reset 原语义）；
3. 预取不丢不重：分配在推进轮恰好完成且预取到 earliest 记录 → 丢弃不产出，
   seek 后从 saved 位点重新拉取；
4. 重连续跑：引擎重建 source 经 open 注入 rt.offsets，门控精确 seek 到注入位点（不重放）；
"""

import importlib.util
import logging
import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_sources():
    """以独立模块加载 worker/stream/sources.py（I9 单测自举）。

    绕开 worker/stream/__init__.py 的 engine/ops 依赖链（simpleeval 等运行时依赖单测环境
    不安装），并把 sources.py 直接依赖的 common.* 以轻量桩替换——本组用例只测 KafkaSource
    的位点门控逻辑，不触达 DB/日志实现。
    """
    name = "datara_test_stream_sources"
    if name in sys.modules:
        return sys.modules[name]

    def stub(mod_name, **attrs):
        mod = types.ModuleType(mod_name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        sys.modules[mod_name] = mod
        return mod

    if "common" not in sys.modules:
        stub("common")
    stub("common.dsconn", resolve_file_path=lambda p: p)
    stub("common.db", new_session=lambda: None)
    stub("common.log", get_logger=logging.getLogger)
    stub("common.models", DataSource=type("DataSource", (), {}))

    spec = importlib.util.spec_from_file_location(name, ROOT / "worker" / "stream" / "sources.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[name] = mod
    return mod


_sources = _load_sources()
KafkaSource = _sources.KafkaSource


class FakeTP:
    """模拟 kafka-python TopicPartition（namedtuple 语义：按 (topic, partition) 相等/可哈希）。"""

    def __init__(self, topic: str, partition: int):
        self.topic = topic
        self.partition = partition
        self.offset = None  # assign 模式下未用；保留字段便于断言

    def _key(self):
        return (self.topic, self.partition)

    def __eq__(self, other):
        return isinstance(other, FakeTP) and self._key() == other._key()

    def __hash__(self):
        return hash(self._key())

    def __repr__(self):
        return f"FakeTP({self.topic}:{self.partition})"


class FakeRecord:
    def __init__(self, offset: int, value: bytes, timestamp: int = 0):
        self.offset = offset
        self.value = value
        self.timestamp = timestamp


class FakeConsumer:
    """脚本化假消费者：responses 为每次 poll 的返回队列；on_poll(call_no) 可模拟分配完成。"""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._assignment: list = []
        self.seeks: list = []  # [(tp, offset)]
        self.poll_calls = 0
        self.responses: list = []
        self.on_poll = None
        self.closed = False

    def poll(self, timeout_ms=0, max_records=None):
        self.poll_calls += 1
        if self.on_poll:
            self.on_poll(self.poll_calls, self)
        return self.responses.pop(0) if self.responses else {}

    def assignment(self):
        return list(self._assignment)

    def seek(self, tp, offset):
        self.seeks.append((tp, int(offset)))

    def close(self):
        self.closed = True


@pytest.fixture()
def kafka_mod(monkeypatch):
    """注入假 kafka 模块（sources.open 内部 `from kafka import KafkaConsumer`）。"""
    created: list[FakeConsumer] = []

    def factory(*args, **kwargs):
        c = FakeConsumer(**kwargs)
        created.append(c)
        return c

    monkeypatch.setitem(sys.modules, "kafka", types.SimpleNamespace(KafkaConsumer=factory))
    return created


def make_source() -> KafkaSource:
    return KafkaSource("n1", {
        "brokers": "broker1:9092",
        "topic": "t1",
        "group": "g1",
        "startFrom": "earliest",
    })


def test_resume_seeks_saved_offsets(kafka_mod):
    """续跑：分配就绪后按 saved 位点 seek；未保存分区不 seek（保持 auto_reset）。"""
    src = make_source()
    src.open({"partitions": {"t1:0": 42}})
    consumer = kafka_mod[0]
    tp0, tp1 = FakeTP("t1", 0), FakeTP("t1", 1)
    # 调用#1（推进轮）内完成组分配；#2 为 seek 后数据轮
    consumer.on_poll = lambda no, c: setattr(c, "_assignment", [tp0, tp1])
    consumer.responses = [{}, {tp0: [FakeRecord(42, b'{"a":1}')]}]

    assert src.poll(100) == []  # 分配未就绪轮：仅推进，不消费
    rows = src.poll(100)  # 分配就绪：seek(42) 后消费
    assert consumer.seeks == [(tp0, 42)]  # t1:1 未保存不 seek
    assert len(rows) == 1 and rows[0]["data"] == {"a": 1}
    assert src.offset["partitions"] == {"t1:0": 43}


def test_first_run_no_seek(kafka_mod):
    """首跑（无 saved 位点）：门控旁路，直接按 auto_offset_reset 消费，零 seek。"""
    src = make_source()
    src.open(None)
    consumer = kafka_mod[0]
    tp0 = FakeTP("t1", 0)
    tp0.offset = 0  # auto_reset 后起始位点
    consumer._assignment = [tp0]
    consumer.responses = [{tp0: [FakeRecord(0, b'{"x":9}')]}]

    rows = src.poll(100)
    assert consumer.seeks == []  # 不做任何 seek
    assert len(rows) == 1 and src.offset["partitions"] == {"t1:0": 1}


def test_prefetched_records_discarded_before_seek(kafka_mod):
    """分配在推进轮恰好完成且预取 earliest 记录：丢弃不产出，seek 后重取（不丢不重）。"""
    src = make_source()
    src.open({"partitions": {"t1:0": 42}})
    consumer = kafka_mod[0]
    tp0 = FakeTP("t1", 0)
    prefetch = FakeRecord(0, b'{"stale":true}')  # auto_reset=earliest 预取（seek 前）

    def on_poll(no, c):
        if no == 1:  # 推进轮恰好完成分配并预取记录（竞态窗口）
            c._assignment = [tp0]
            c.responses.insert(0, {tp0: [prefetch]})

    consumer.on_poll = on_poll
    consumer.responses = [{tp0: [FakeRecord(42, b'{"ok":1}')]}]  # seek 后正常拉取

    assert src.poll(100) == []  # 预取记录被丢弃
    rows = src.poll(100)
    assert consumer.seeks == [(tp0, 42)]
    assert [r["data"] for r in rows] == [{"ok": 1}]  # 不含 stale，也不丢 42 位点记录
    assert src.offset["partitions"] == {"t1:0": 43}


def test_reconnect_resumes_from_engine_passed_offsets(kafka_mod):
    """重连续跑：引擎重连重建 source 并经 open 注入 rt.offsets（引擎侧同步的最新位点），
    门控精确 seek 到该位点，而非按 auto_offset_reset 整题重放（I8 bug 的实际故障路径）。"""
    # 首次运行：消费到 42 → _offsets 推进为 43
    src1 = make_source()
    src1.open({"partitions": {"t1:0": 42}})
    c1 = kafka_mod[0]
    tp = FakeTP("t1", 0)
    c1.on_poll = lambda no, c: setattr(c, "_assignment", [tp])
    c1.responses = [{}, {tp: [FakeRecord(42, b'{"a":1}')]}]
    src1.poll(100)
    src1.poll(100)
    assert src1.offset["partitions"] == {"t1:0": 43}

    # 引擎重连：重建 source（_offsets 全新为空），open 注入引擎侧位点 43
    src2 = make_source()
    src2.open({"partitions": {"t1:0": 43}})
    c2 = kafka_mod[1]
    c2.on_poll = lambda no, c: setattr(c, "_assignment", [tp])
    c2.responses = [{}, {tp: [FakeRecord(43, b'{"b":2}')]}]
    assert src2.poll(100) == []  # 分配未就绪轮：不消费
    rows2 = src2.poll(100)
    assert c2.seeks == [(tp, 43)]  # 从 43 续跑，不重放
    assert [r["data"] for r in rows2] == [{"b": 2}]
    assert src2.offset["partitions"] == {"t1:0": 44}
