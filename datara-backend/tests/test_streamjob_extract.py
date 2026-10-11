"""流任务 spec 提取的混编口径契约（统一工作流编排内核一致性）。

背景：任务中心统一 dagProfile 内核后，流分类画布的 palette 暴露 DAG 逻辑控制/
变量/通知/自检组件，且 dagProfile 校验要求「开始/结束」节点闭环。因此流任务启动
（extract_stream_spec）必须放行这些非管道组件，仅拦截真正的批处理组件
（数据计算/数据同步组），否则出现"前端要求加开始、后端拒绝开始"的口径冲突。
"""

from types import SimpleNamespace

import pytest

from api.auth import ApiError
from api.streamjob import NON_PIPELINE_TYPES, extract_stream_spec


def _def():
    return SimpleNamespace(name="t")


def _doc(*extra_nodes, extra_edges=()):
    nodes = [
        {"id": "si1", "type": "stream_input", "data": {"srcType": "simulate"}},
        {"id": "so1", "type": "stream_output", "data": {}},
    ]
    edges = [{"source": "si1", "target": "so1"}]
    for i, t in enumerate(extra_nodes):
        nodes.append({"id": f"x{i}", "type": t, "data": {}})
        edges.extend({"source": e[0], "target": e[1]} for e in extra_edges if e[0] == f"x{i}" or e[1] == f"x{i}")
    return {"nodes": nodes, "edges": edges}


def test_logic_and_display_nodes_are_allowed() -> None:
    """start/end/变量/通知/自检/看板 全部放行，spec 仅含流组件。"""
    spec = extract_stream_spec(_def(), _doc("start", "end", "variable", "notify", "smoke", "page_board"))
    assert sorted(n["type"] for n in spec["nodes"]) == ["stream_input", "stream_output"]
    assert spec["edges"] == [{"source": "si1", "target": "so1"}]


@pytest.mark.parametrize("ntype", sorted(NON_PIPELINE_TYPES))
def test_every_non_pipeline_type_is_allowed(ntype: str) -> None:
    """白名单内的组件逐一入画布均不被判混编（口径钉死，防回归收窄）。"""
    spec = extract_stream_spec(_def(), _doc(ntype))
    assert [n["type"] for n in spec["nodes"]] == ["stream_input", "stream_output"]


def test_logic_nodes_not_in_pipeline_graph() -> None:
    """start 连向 stream_input 的边不进流子图（逻辑节点不参与管道装配）。"""
    doc = _doc("start", extra_edges=(("x0", "si1"),))
    spec = extract_stream_spec(_def(), doc)
    assert spec["edges"] == [{"source": "si1", "target": "so1"}]


def test_batch_component_still_rejected() -> None:
    """批处理组件（数据计算组 sql）仍判混编拒绝。"""
    with pytest.raises(ApiError) as ei:
        extract_stream_spec(_def(), _doc("sql"))
    assert "混编批处理组件: sql" in str(ei.value.msg)


def test_sync_orchestration_component_still_rejected() -> None:
    """同步编排组件（数据同步组 src_base_orch）仍判混编拒绝。"""
    with pytest.raises(ApiError) as ei:
        extract_stream_spec(_def(), _doc("src_base_orch"))
    assert "混编批处理组件: src_base_orch" in str(ei.value.msg)


def test_no_stream_component_rejected() -> None:
    """纯逻辑节点画布（无流组件）仍要求流组件存在。"""
    doc = {"nodes": [{"id": "s1", "type": "start", "data": {}}], "edges": []}
    with pytest.raises(ApiError) as ei:
        extract_stream_spec(_def(), doc)
    assert "画布无流组件" in str(ei.value.msg)
