"""graph_json → 执行图（F42，设计文档 §5.1）。

- GraphDocument：{id, name, version, meta, nodes: [{id, type, data}], edges: [{source, target, sourceHandle, label}]}
- 邻接表 + 入度表；回环边（target 为 loop 节点，C10）不计入常规入度与无环校验
- 非法图（无开始节点 / 非回环有环 / 空节点）抛 ValueError，命令置 fail + 原因写命令参数
- sourceHandle 语义：conditions/switch 分支边 handle=branch.id（或 label=branch.name，前端 portsOf 口径）
"""

from typing import Optional

# 逻辑节点类型（master 内联执行，不派 worker；设计文档 §6）
LOGICAL_TYPES = frozenset({
    "start", "end", "conditions", "switch", "fork", "join", "merge", "delay", "dependent", "loop",
})
# 本期可派发 worker 的数据节点（i3-3 执行器注册后生效；I6 +sync）
WORKER_TYPES = frozenset({"sql", "shell", "python", "ssh", "smoke", "sync"})


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


def parse_graph(graph_json: dict) -> Graph:
    """GraphDocument dict → Graph；非法抛 ValueError（原因回写命令参数）。"""
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
    return graph


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
