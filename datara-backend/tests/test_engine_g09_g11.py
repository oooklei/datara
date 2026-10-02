"""G-09 循环批次切片 + G-11 notify 触发时机驱动 单测。

G-09：_loop_batch_info 按 batchSize 切片 collection，返回 batchItems/batchIndex/batchTotal。
G-11：_notify_trigger_matches 按 trigger 参数（on_success/on_failure/always）判定是否匹配上游状态。
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from master.engine import WorkflowExecuteRunnable  # noqa: E402


def _make_runnable(node_data=None):
    """跳过 __init__，仅注入方法触碰的属性。"""
    r = WorkflowExecuteRunnable.__new__(WorkflowExecuteRunnable)
    r.instance_id = "i-test"

    class _FakeResolver:
        levels = {}  # _expr_scope 需要

        def resolve_text(self, text, scope, loop_iter, extra):
            return text  # 原样返回（测试用逗号分隔清单）

        def run_vars_snapshot(self):
            return {}

        def runtime_scope(self, loop_iter):
            return {}
    r.resolver = _FakeResolver()
    _nd = node_data if node_data is not None else {}
    r._node_data = lambda nid: _nd
    return r


# ---------------- G-09 循环批次切片 ----------------

def test_loop_batch_info_slices_by_batch_size():
    """collection=a,b,c,d,e batchSize=2 → 3 批（2,2,1）。"""
    r = _make_runnable({"collection": "a,b,c,d,e", "batchSize": 2})
    info1 = r._loop_batch_info("nd1", 1)
    assert info1["batchItems"] == "a,b"
    assert info1["batchIndex"] == 0
    assert info1["batchTotal"] == 3
    info2 = r._loop_batch_info("nd1", 2)
    assert info2["batchItems"] == "c,d"
    assert info2["batchIndex"] == 1
    info3 = r._loop_batch_info("nd1", 3)
    assert info3["batchItems"] == "e"
    assert info3["batchIndex"] == 2


def test_loop_batch_info_no_collection_returns_empty():
    """无 collection 配置 → 返回空 dict（不影响既有单轮语义）。"""
    r = _make_runnable({})
    assert r._loop_batch_info("nd1", 1) == {}


def test_loop_batch_info_default_batch_size():
    """batchSize 缺省 → 按 1 处理（每批 1 项）。"""
    r = _make_runnable({"collection": "x,y,z"})
    info = r._loop_batch_info("nd1", 2)
    assert info["batchItems"] == "y"
    assert info["batchTotal"] == 3


# ---------------- G-11 notify 触发时机 ----------------

def _make_runnable_with_graph(pred_states=None, node_data=None):
    """创建带图结构的 runnable（mock preds 上游状态）。"""
    r = _make_runnable(node_data)
    r._states = pred_states or []
    r.graph = type("G", (), {"preds": {"nd_notify": [{"source": "nd_src"}]}})()
    r._row = lambda nid, li: {"state": r._states[0]} if r._states else None
    return r


def test_notify_trigger_always_matches():
    """trigger=always → 恒匹配。"""
    r = _make_runnable_with_graph(["failure"], {"trigger": "always"})
    assert r._notify_trigger_matches("nd_notify", 0) is True


def test_notify_trigger_on_success_matches_when_success():
    """trigger=on_success + 上游 success → 匹配。"""
    r = _make_runnable_with_graph(["success"], {"trigger": "on_success"})
    assert r._notify_trigger_matches("nd_notify", 0) is True


def test_notify_trigger_on_success_no_match_when_failure():
    """trigger=on_success + 上游 failure → 不匹配（跳过通知）。"""
    r = _make_runnable_with_graph(["failure"], {"trigger": "on_success"})
    assert r._notify_trigger_matches("nd_notify", 0) is False


def test_notify_trigger_on_failure_matches_when_failure():
    """trigger=on_failure + 上游 failure → 匹配。"""
    r = _make_runnable_with_graph(["failure"], {"trigger": "on_failure"})
    assert r._notify_trigger_matches("nd_notify", 0) is True


def test_notify_trigger_default_is_on_success():
    """trigger 缺省 → 等同 on_success。"""
    r = _make_runnable_with_graph(["success"], {})
    assert r._notify_trigger_matches("nd_notify", 0) is True


def test_notify_trigger_no_preds_fallback_match():
    """无上游（孤立节点）→ 兜底匹配（避免通知永远发不出）。"""
    r = _make_runnable_with_graph([], {"trigger": "on_success"})
    r.graph = type("G", (), {"preds": {"nd_notify": []}})()
    assert r._notify_trigger_matches("nd_notify", 0) is True
