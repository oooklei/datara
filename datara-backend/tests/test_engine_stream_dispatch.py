"""G1 流节点分派接线单测（实施计划 20260926 Task C1）。

背景：master 批引擎分派表此前缺 stream_input/stream_fuse/stream_output，含流节点的
画布走批启动时落 executor_not_implemented 内部错误（P0 缺口 G1）。修复语义（I8 裁定②
「master 只注册/透传，不持有引擎」）：_exec_stream 状态占位——同工作流有活跃流任务
（t_stream_job starting/running/reconnecting）→ 节点 SUCCESS 指向承载任务；无 → FAILURE
引导先启动流任务，数据面仍由 worker 常驻流引擎承载。

覆盖：
1. 分派表含三个流类型（源码断言，防再回退——与 CI 路由检查同手法）；
2. _exec_stream 两分支（活跃→SUCCESS / stopped·缺失→FAILURE）；
3. 实例缺失/wf_code=0 → FAILURE 不炸线程。

DB：sqlite 内存库（conftest compiles 补丁），WfRunnable.__new__ 跳过重量级初始化，
状态推进方法打桩捕获。
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import master.engine as engine_mod  # noqa: E402
from common.models import StreamJob, WorkflowInstance  # noqa: E402
from master.engine import WorkflowExecuteRunnable  # noqa: E402


def _make_runnable(instance_id: str) -> WorkflowExecuteRunnable:
    """跳过 __init__（线程/DB 装载），仅注入 _exec_stream 触碰的属性。"""
    r = WorkflowExecuteRunnable.__new__(WorkflowExecuteRunnable)
    r.instance_id = instance_id
    return r


def test_dispatch_table_contains_stream_types():
    """回归守卫：分派表必须接线三个流类型（源码断言，防再次回退为缺口）。"""
    src = (BACKEND / "master" / "engine.py").read_text(encoding="utf-8")
    for t in ("stream_input", "stream_fuse", "stream_output"):
        assert '"%s": self._exec_stream' % t in src, t


def _seed(db_session, wf_code: int, job_status: str = None):
    db_session.add(WorkflowInstance(instance_id="i-stream", wf_code=wf_code, state="running"))
    if job_status is not None:
        db_session.add(StreamJob(doc_id="wf_x", wf_code=wf_code, status=job_status))
    db_session.commit()


def _run_exec_stream(db_session, monkeypatch) -> dict:
    r = _make_runnable("i-stream")
    captured = {}

    def fake_set_state(key, st, outputs=None, log_lines=None):
        captured["key"] = key
        captured["state"] = st
        captured["outputs"] = outputs
        captured["logs"] = log_lines

    r._set_state = fake_set_state
    r._advance_downstream = lambda nid, li: captured.setdefault("advanced", (nid, li))
    r._node_name = lambda nid: "流源"
    monkeypatch.setattr(engine_mod, "new_session", lambda: db_session)
    r._exec_stream(("n1", 0), {})
    return captured


def test_stream_node_success_with_active_job(db_session, monkeypatch):
    _seed(db_session, 83640, "running")
    captured = _run_exec_stream(db_session, monkeypatch)
    assert captured["state"] == "success"
    assert captured["outputs"]["streamJobId"] >= 1
    assert captured["outputs"]["streamStatus"] == "running"
    assert captured["advanced"] == ("n1", 0)


def test_stream_node_success_with_starting_job(db_session, monkeypatch):
    """starting/reconnecting 亦视为承载中（与 STREAM_ACTIVE_STATES 同口径）。"""
    _seed(db_session, 83640, "starting")
    assert _run_exec_stream(db_session, monkeypatch)["state"] == "success"


def test_stream_node_fails_when_job_stopped(db_session, monkeypatch):
    _seed(db_session, 83640, "stopped")
    captured = _run_exec_stream(db_session, monkeypatch)
    assert captured["state"] == "failure"
    assert captured["outputs"]["error"] == "stream_job_not_started"
    assert "stream-jobs/start" in captured["logs"][0]


def test_stream_node_fails_when_no_job(db_session, monkeypatch):
    _seed(db_session, 83640, None)
    captured = _run_exec_stream(db_session, monkeypatch)
    assert captured["state"] == "failure"
    assert captured["outputs"]["error"] == "stream_job_not_started"


def test_stream_node_survives_missing_instance(db_session, monkeypatch):
    """实例行缺失（脏数据）→ FAILURE 而非异常炸实例线程。"""
    captured = _run_exec_stream(db_session, monkeypatch)
    assert captured["state"] == "failure"
    assert captured["outputs"]["error"] == "stream_job_not_started"


# ---------------- G-14 流子图提取 + 桥接 ----------------


def _stream_doc():
    """构造含流子图的画布：start → sql → stream_input → stream_fuse → stream_output → page_board → end。"""
    return {
        "nodes": [
            {"id": "start", "type": "start", "data": {}},
            {"id": "sql1", "type": "sql", "data": {"name": "查询"}},
            {"id": "si", "type": "stream_input", "data": {"srcType": "kafka", "dsRef": "kafka_main", "topic": "t1"}},
            {"id": "sf", "type": "stream_fuse", "data": {"fuseType": "filter"}},
            {"id": "so", "type": "stream_output", "data": {"outTable": "sink"}},
            {"id": "pb", "type": "page_board", "data": {}},
            {"id": "end", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start", "target": "sql1"},
            {"source": "sql1", "target": "si"},
            {"source": "si", "target": "sf"},
            {"source": "sf", "target": "so"},
            {"source": "so", "target": "pb"},
            {"source": "pb", "target": "end"},
        ],
    }


def _stream_only_doc():
    """纯流子图（无批组件混编）：stream_input → stream_fuse → stream_output。"""
    return {
        "nodes": [
            {"id": "si", "type": "stream_input", "data": {"srcType": "kafka", "dsRef": "kafka_main", "topic": "t1"}},
            {"id": "sf", "type": "stream_fuse", "data": {"fuseType": "filter"}},
            {"id": "so", "type": "stream_output", "data": {"outTable": "sink"}},
        ],
        "edges": [
            {"source": "si", "target": "sf"},
            {"source": "sf", "target": "so"},
        ],
    }


def test_extract_stream_subgraph_removes_stream_nodes():
    """G-14：流子图从批运行图中提取，流节点不再出现在 Graph 中。"""
    from master.dag import extract_stream_subgraph

    doc = _stream_doc()
    bridged, spec = extract_stream_subgraph(doc)
    assert spec is not None, "应成功提取流子图"
    # 流节点已从桥接图中移除
    types_after = {n["type"] for n in bridged["nodes"]}
    assert "stream_input" not in types_after
    assert "stream_fuse" not in types_after
    assert "stream_output" not in types_after
    # 批节点保留
    assert "start" in types_after
    assert "sql" in types_after
    assert "end" in types_after


def test_extract_stream_subgraph_bridges_batch_nodes():
    """G-14：批前驱 → 流 的边桥接为 批前驱 → 批后继，保持 DAG 连通。"""
    from master.dag import extract_stream_subgraph

    doc = _stream_doc()
    bridged, _spec = extract_stream_subgraph(doc)
    edges_by_pair = {(e["source"], e["target"]) for e in bridged["edges"]}
    # 桥接边：sql1 → page_board（绕过流子图）
    assert any(s == "sql1" and t == "pb" for s, t in edges_by_pair), f"缺少桥接边 sql1→pb，实际边: {edges_by_pair}"
    # 流内部边被移除
    assert ("si", "sf") not in edges_by_pair
    assert ("sf", "so") not in edges_by_pair


def test_parse_graph_returns_stream_spec():
    """G-14：parse_graph 返回 (Graph, stream_spec) 元组。"""
    from master.dag import parse_graph

    # 使用含 start/end 的合法 DAG（parse_graph 要求恰有一个 start）
    doc = {
        "nodes": [
            {"id": "start", "type": "start", "data": {}},
            {"id": "si", "type": "stream_input", "data": {"srcType": "kafka", "dsRef": "kafka_main", "topic": "t1"}},
            {"id": "sf", "type": "stream_fuse", "data": {"fuseType": "filter"}},
            {"id": "so", "type": "stream_output", "data": {"outTable": "sink"}},
            {"id": "end", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start", "target": "si"},
            {"source": "si", "target": "sf"},
            {"source": "sf", "target": "so"},
            {"source": "so", "target": "end"},
        ],
    }
    graph, spec = parse_graph(doc)
    # 流节点不在 Graph 中
    types_in_graph = {n["type"] for n in graph.nodes.values()}
    assert "stream_input" not in types_in_graph
    assert "stream_fuse" not in types_in_graph
    assert "stream_output" not in types_in_graph
    # spec 非空，含 3 个流节点
    assert spec is not None
    assert len(spec["nodes"]) == 3  # stream_input + stream_fuse + stream_output


def test_parse_graph_no_stream_returns_none_spec():
    """G-14：纯批处理画布 → spec 为 None。"""
    from master.dag import parse_graph

    doc = {
        "nodes": [
            {"id": "start", "type": "start", "data": {}},
            {"id": "sql1", "type": "sql", "data": {}},
            {"id": "end", "type": "end", "data": {}},
        ],
        "edges": [
            {"source": "start", "target": "sql1"},
            {"source": "sql1", "target": "end"},
        ],
    }
    graph, spec = parse_graph(doc)
    assert spec is None
    assert "sql" in {n["type"] for n in graph.nodes.values()}


def test_extract_stream_subgraph_isolates_from_batch_mix():
    """G-14：流子图提取仅校验隔离出的流子图，批组件不触发 stray 拒绝。

    提取后批组件（sql1）保留在桥接图中，流节点被移除。
    """
    from master.dag import extract_stream_subgraph

    doc = {
        "nodes": [
            {"id": "si", "type": "stream_input", "data": {"srcType": "kafka", "dsRef": "k1", "topic": "t1"}},
            {"id": "sf", "type": "stream_fuse", "data": {"fuseType": "filter"}},
            {"id": "so", "type": "stream_output", "data": {"outTable": "sink"}},
            {"id": "sql1", "type": "sql", "data": {}},  # 批组件混编
        ],
        "edges": [
            {"source": "si", "target": "sf"},
            {"source": "sf", "target": "so"},
            {"source": "so", "target": "sql1"},
        ],
    }
    bridged, spec = extract_stream_subgraph(doc)
    # 隔离出的流子图结构合规 → 提取成功
    assert spec is not None
    # 流节点从桥接图移除，批节点保留
    types_after = {n["type"] for n in bridged["nodes"]}
    assert "stream_input" not in types_after
    assert "sql" in types_after


def test_extract_stream_subgraph_fallback_on_missing_sink():
    """G-14：流子图缺 stream_output（汇）→ 结构不合规，提取降级返回 None。"""
    from master.dag import extract_stream_subgraph

    doc = {
        "nodes": [
            {"id": "si", "type": "stream_input", "data": {"srcType": "kafka", "dsRef": "k1", "topic": "t1"}},
            {"id": "sf", "type": "stream_fuse", "data": {"fuseType": "filter"}},
            # 缺 stream_output
        ],
        "edges": [
            {"source": "si", "target": "sf"},
        ],
    }
    _bridged, spec = extract_stream_subgraph(doc)
    assert spec is None, "缺汇的流子图应降级"
