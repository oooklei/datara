"""graph_json → 执行图（F42，设计文档 §5.1）。

- GraphDocument：{id, name, version, meta, nodes: [{id, type, data}], edges: [{source, target, sourceHandle, label}]}
- 邻接表 + 入度表；回环边（target 为 loop 节点，C10）不计入常规入度与无环校验
- 非法图（无开始节点 / 非回环有环 / 空节点）抛 ValueError，命令置 fail + 原因写命令参数
- sourceHandle 语义：conditions/switch 分支边 handle=branch.id（或 label=branch.name，前端 portsOf 口径）
"""

from typing import Optional

# G-19 单一真源：由 components.catalog 统一定义，消除 4 处字面量副本
# 注：scripts/check_dag_route_completeness.py 依赖本 frozenset 做键集解析 — 改 import 不改结构
from components.catalog import STREAM_TYPES


def eliminate_reroutes(graph_json: dict) -> dict:
    """Remove editing-only reroute nodes and bridge every predecessor to successor."""
    if not isinstance(graph_json, dict):
        return graph_json
    raw_nodes = graph_json.get("nodes")
    raw_edges = graph_json.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        return graph_json

    nodes = [dict(node) for node in raw_nodes if isinstance(node, dict)]
    edges = [dict(edge) for edge in raw_edges if isinstance(edge, dict)]
    reroute_ids = [str(node.get("id")) for node in nodes
                   if node.get("id") and node.get("type") == "reroute"]
    for reroute_id in reroute_ids:
        incoming = [edge for edge in edges if str(edge.get("target") or "") == reroute_id]
        outgoing = [edge for edge in edges if str(edge.get("source") or "") == reroute_id]
        edges = [edge for edge in edges
                 if str(edge.get("source") or "") != reroute_id
                 and str(edge.get("target") or "") != reroute_id]
        existing = {
            (
                str(edge.get("source") or ""),
                str(edge.get("target") or ""),
                str(edge.get("sourceHandle") or ""),
                str(edge.get("targetHandle") or ""),
            )
            for edge in edges
        }
        for before in incoming:
            for after in outgoing:
                source = str(before.get("source") or "")
                target = str(after.get("target") or "")
                bridged = {"source": source, "target": target}
                for key in ("sourceHandle", "kind"):
                    if before.get(key) is not None:
                        bridged[key] = before[key]
                for key in ("targetHandle", "label", "partial"):
                    if after.get(key) is not None:
                        bridged[key] = after[key]
                identity = (
                    source,
                    target,
                    str(bridged.get("sourceHandle") or ""),
                    str(bridged.get("targetHandle") or ""),
                )
                if not source or not target or source == target or identity in existing:
                    continue
                edges.append(bridged)
                existing.add(identity)

    out = dict(graph_json)
    out["nodes"] = [node for node in nodes if str(node.get("id") or "") not in reroute_ids]
    out["edges"] = edges
    return out


class Graph:
    """执行图：节点/边/邻接/入度（回环边单独归档）。"""

    def __init__(self, nodes: dict, edges: list):
        self.nodes = nodes  # {node_id: {"id","type","data"}}
        self.edges = edges  # [{"source","target","sourceHandle","label"}]
        self.preds: dict = {}  # {node_id: [edge, ...]}（不含回环边）
        self.succs: dict = {}  # {node_id: [edge, ...]}（不含回环边）
        self.back_edges: list = []  # 回环边（target 为 loop）
        self.indegree: dict = {}  # 常规入度（不含回环边）
        for node_id in nodes:
            self.preds[node_id] = []
            self.succs[node_id] = []
            self.indegree[node_id] = 0
        for edge in edges:
            if edge["target"] not in nodes or edge["source"] not in nodes:
                raise ValueError("边引用不存在节点: %s → %s" % (edge["source"], edge["target"]))
            if nodes[edge["target"]]["type"] == "loop":
                self.back_edges.append(edge)
            else:
                self.preds[edge["target"]].append(edge)
                self.succs[edge["source"]].append(edge)
                self.indegree[edge["target"]] += 1

    def node(self, node_id: str) -> dict:
        return self.nodes[node_id]

    def start_nodes(self) -> list:
        """入度=0 节点；图校验保证恰有一个 start。"""
        return [nid for nid, deg in self.indegree.items() if deg == 0]

    def branch_match(self, edge: dict, branch: Optional[dict]) -> bool:
        """分支边匹配：sourceHandle ∈ {branch.id, branch.name, branch.expr} 或 label=branch.name。"""
        if branch is None:
            return not edge.get("sourceHandle")
        handle = edge.get("sourceHandle") or ""
        return handle in (branch.get("id"), branch.get("name"), branch.get("expr")) or \
            edge.get("label") == branch.get("name")


def extract_stream_subgraph(graph_json: dict) -> tuple[dict, Optional[dict]]:
    """G-14 完整方案：流子图从批运行图中提取 + 桥接（I8 裁定②「常驻作业」类别）。

    流节点（stream_input/fuse/output）是常驻流作业算子，**不应进入 Master 的任务状态机**。
    本函数在 parse_graph 前执行：
    1. 识别流子图节点 + 校验结构（有 stream_input 源 / stream_output 汇 / 无游离 / join 入边）；
    2. 移除流节点及其内部边；
    3. 桥接：批处理前驱 → 流输入 的边 改写为 批处理前驱 → 批处理后继（保持 DAG 连通）；
    4. 返回 (桥接后的 graph_json, 流子图 spec)——后者供实例启动时注册 stream_job。

    无流节点时 spec 为 None（纯批处理画布，绝大多数场景）；不合规（混编批组件/缺源汇/游离）
    亦返回 None，由下游 _exec_stream 兜底 FAILURE（避免解析阶段因流图瑕疵拒绝整个工作流）。

    spec 格式对齐 api.streamjob.extract_stream_spec 的产出：
        {"name": <画布名>, "nodes": [{id,type,params}], "edges": [{source,target}]}
    """
    if not isinstance(graph_json, dict):
        return graph_json, None
    raw_nodes = graph_json.get("nodes")
    raw_edges = graph_json.get("edges")
    if not isinstance(raw_nodes, list) or not isinstance(raw_edges, list):
        return graph_json, None

    stream_ids = {str(n["id"]) for n in raw_nodes
                  if isinstance(n, dict) and n.get("type") in STREAM_TYPES}
    if not stream_ids:
        return graph_json, None

    # ---- 结构校验（与 api.streamjob.extract_stream_spec 同口径）----
    # 关键：仅对**隔离出的流子图**校验（不含批组件），避免批组件触发 stray 拒绝。
    # 延迟导入：api.streamjob 依赖 FastAPI，仅在含流节点时加载。
    try:
        from api.streamjob import extract_stream_spec
        from common.models import WfDefinition
        # 构造仅含流节点 + page_board 的子图文档（extract_stream_spec 允许 page_board）。
        stream_nodes = [dict(n) for n in raw_nodes
                        if isinstance(n, dict) and str(n.get("id") or "") in stream_ids]
        # page_board 节点保留在子图中（display 类型，extract_stream_spec 允许）
        display_nodes = [dict(n) for n in raw_nodes
                         if isinstance(n, dict)
                         and str(n.get("id") or "") not in stream_ids
                         and str(n.get("type") or "") == "page_board"]
        sub_ids = {str(n["id"]) for n in stream_nodes + display_nodes}
        sub_edges = [dict(e) for e in raw_edges
                     if isinstance(e, dict)
                     and str(e.get("source") or "") in sub_ids
                     and str(e.get("target") or "") in sub_ids]
        sub_doc = {"nodes": stream_nodes + display_nodes, "edges": sub_edges}
        _defn = WfDefinition(id="_batch_extract", name=str(graph_json.get("name") or ""))
        spec = extract_stream_spec(_defn, sub_doc)
    except Exception as exc:  # noqa: BLE001 —— 流图不合规，降级：不提取，由 _exec_stream 兜底
        # 延迟导入避免模块级循环（dag ← engine ← scheduler → api）
        from common.log import get_logger
        get_logger("master.dag").warning("流子图提取降级（结构不合规: %s），留给 _exec_stream 兜底", exc)
        return graph_json, None

    # ---- 移除流节点 + 内部边 ----
    remaining_nodes = [dict(n) for n in raw_nodes
                       if isinstance(n, dict) and str(n.get("id") or "") not in stream_ids]
    internal_edges = [dict(e) for e in raw_edges
                      if isinstance(e, dict)
                      and str(e.get("source") or "") not in stream_ids
                      and str(e.get("target") or "") not in stream_ids]

    # ---- 桥接：批前驱 → 流 的边 → 批前驱 → 批后继 ----
    # 收集：哪些批节点有边进入流子图（preds），哪些批节点有边从子图引出（succs）。
    preds_of_stream: set = set()   # 有出边指向流节点的批节点
    succs_of_stream: set = set()   # 有入边从流节点引出的批节点
    for e in raw_edges:
        if not isinstance(e, dict):
            continue
        src, tgt = str(e.get("source") or ""), str(e.get("target") or "")
        if tgt in stream_ids and src not in stream_ids:
            preds_of_stream.add(src)
        elif src in stream_ids and tgt not in stream_ids:
            succs_of_stream.add(tgt)

    bridge_edges = list(internal_edges)
    seen_edges: set = set()
    for e in internal_edges:
        if isinstance(e, dict):
            seen_edges.add((str(e.get("source")), str(e.get("target"))))

    for pred in preds_of_stream:
        for succ in succs_of_stream:
            if pred == succ:
                continue  # 自环跳过（批节点经流回到自身——语义荒谬，不桥）
            key = (pred, succ)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            bridge_edges.append({
                "source": pred, "target": succ,
                "sourceHandle": None, "label": "stream_bridge",
            })

    out = dict(graph_json)
    out["nodes"] = remaining_nodes
    out["edges"] = bridge_edges
    return out, spec


def parse_graph(graph_json: dict, comp_versions: Optional[dict] = None) -> tuple[Graph, Optional[dict]]:
    """GraphDocument dict → (Graph, stream_spec)；非法抛 ValueError（原因回写命令参数）。

    返回元组：
    - Graph：批运行图（流节点已提取移除，批前驱→批后继已桥接）。
    - stream_spec | None：提取的流子图 spec（含 nodes/edges），供 scheduler 在实例启动时
      注册 stream_job；无流节点时为 None。

    comp_versions（Task D2 §9.6）：物化器按源组件（endpoint_select）published 版本
    注入 sys_exec 节点 componentRef；None 时兜底 v1（ref 仅治理留痕，R6 豁免不校验）。
    """
    # 设计态 → 运行态物化（同步编排端点合一 §3.2）：assert 入边处物化 sys_exec 执行节点。
    # 函数体在 engine.py；延迟导入避免循环依赖（engine 顶层依赖本模块的 Graph/loop_bodies）。
    from master.engine import materialize_sync_exec

    # Reroute is an editing-graph affordance only.  Eliminate it before stream
    # extraction/materialization so every execution path sees the same graph.
    graph_json = eliminate_reroutes(graph_json)

    # G-14 完整方案：先提取流子图（流节点不进入 Master 任务状态机）。
    # 函数体在本模块；延迟调用避免模块级循环（extract_stream_subgraph 内含 api 延迟导入）。
    graph_json, stream_spec = extract_stream_subgraph(graph_json)

    graph_json = materialize_sync_exec(graph_json, comp_versions=comp_versions)
    if not isinstance(graph_json, dict):
        raise ValueError("graph_json 非法（非 JSON 对象）")
    raw_nodes = graph_json.get("nodes")
    raw_edges = graph_json.get("edges")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError("画布无节点")
    nodes = {}
    for n in raw_nodes:
        if not isinstance(n, dict) or not n.get("id") or not n.get("type"):
            raise ValueError("节点缺少 id/type: %r" % (n,))
        nodes[str(n["id"])] = {"id": str(n["id"]), "type": str(n["type"]), "data": n.get("data") or {}}
    edges = []
    for idx, e in enumerate(raw_edges if isinstance(raw_edges, list) else []):
        if isinstance(e, dict) and e.get("source") and e.get("target"):
            edges.append({
                "_idx": idx,  # 全局边序号（引擎边状态键，两侧列表共享）
                "source": str(e["source"]),
                "target": str(e["target"]),
                "sourceHandle": e.get("sourceHandle"),
                "label": e.get("label"),
                # I7：GEdge.partial 部分依赖声明透传（EdgePartialDep：table/fields/filter/scope），
                # 引擎派发时消费（_collect_partial_inputs 注入下游输入）
                "partial": e.get("partial") if isinstance(e.get("partial"), dict) else None,
            })
    graph = Graph(nodes, edges)
    starts = [nid for nid, n in nodes.items() if n["type"] == "start"]
    if len(starts) != 1:
        raise ValueError("开始节点（C1）必须恰有一个，实际 %d 个" % len(starts))
    _check_cycle(graph)
    return graph, stream_spec


def _check_cycle(graph: Graph) -> None:
    """非回环子图无环校验（Kahn）；有环抛 ValueError。"""
    indegree = dict(graph.indegree)
    queue = [nid for nid, deg in indegree.items() if deg == 0]
    seen = 0
    while queue:
        nid = queue.pop()
        seen += 1
        for edge in graph.succs[nid]:
            indegree[edge["target"]] -= 1
            if indegree[edge["target"]] == 0:
                queue.append(edge["target"])
    if seen != len(graph.nodes):
        raise ValueError("DAG 存在环（非回环边），拒绝启动")


def loop_bodies(graph: Graph) -> dict:
    """C10 循环体划分（§6.8）：{loop节点: 体节点集}。

    体 = 从 Loop 沿非回环边可达、且能（沿非回环边）到达任一回边源节点的节点，
    含回边源节点本身；Loop 的非环下游（出口链）不在体内。
    无回环边的 Loop 体为空集（引擎按透传处理）。
    """
    bodies: dict = {}
    for loop_id, node in graph.nodes.items():
        if node["type"] != "loop":
            continue
        targets = {e["source"] for e in graph.back_edges if e["target"] == loop_id}
        if not targets:
            bodies[loop_id] = set()
            continue
        forward = set()
        stack = [loop_id]
        while stack:
            cur = stack.pop()
            for edge in graph.succs[cur]:
                if edge["target"] not in forward:
                    forward.add(edge["target"])
                    stack.append(edge["target"])
        body = set(targets)
        stack = list(targets)
        while stack:
            cur = stack.pop()
            for edge in graph.preds[cur]:
                if edge["source"] not in body and edge["source"] in forward:
                    body.add(edge["source"])
                    stack.append(edge["source"])
        bodies[loop_id] = body
    return bodies
