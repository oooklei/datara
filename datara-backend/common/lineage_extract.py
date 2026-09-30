"""设计态血缘解析器（Task 2）：工作流定义 graph_json 节点/边 → 表级/字段级血缘推导。

- 纯函数：不触库、不发 IO、不抛出（单节点异常记 opaques.reason，不影响其余节点）
- 产出对齐 common/models.py LineageEdge/LineageField 构造参数；src_type="design"、
  instance_id=0（设计态标识）、tmp_flag=0（临时表映射是运行态概念，设计态不判）
- 表级边 stmt_no：sql 节点取语句序号（1 起，pre→sql→post 全语句顺序拆分序，与运行态
  collect_sql_lineage 口径一致）；其余组件 0
- 表名形态（与运行态 worker/lineage.py 的 db.table 口径对齐）：显式 schema 已知 →
  `{schema}.{table}`；否则 `{ds}.{table}`（运行态 db_name 存于 t_data_source，设计态
  纯函数不可查库，以数据源名代库名——sql 未限定名由 parse_sql_lineage(default_db) 补齐，
  同理）；文件源边 from_table = `file:{path}`（运行态 file_sync 执行器无血缘采集，
  采用任务裁定形态）

config key 契约（均已核实源码，勿凭猜测改动）：
┌──────────────────┬──────────────────────────────────────────────────────────────┐
│ 组件             │ 真实 key（依据）                                             │
├──────────────────┼──────────────────────────────────────────────────────────────┤
│ 节点/边结构      │ nodes=[{id,type,data}] edges=[{source,target,sourceHandle,   │
│                  │ label}]（master/dag.py parse_graph；兼容 nodeId/config 别名）│
│ sql              │ datasource（数据源名）/pre/sql/post（分号多语句）            │
│                  │ （worker/executors/sql.py + dag_catalog.json C11）           │
│ endpoint_select  │ baseMode(src_base/tgt_base/file_sync)/srcDs/srcTable(纯表名  │
│                  │ 或 {schema,table}，writeAs=schemaTable)/probeResult(文本     │
│                  │ "schema.table,…"或 [{schema,table}])/tgtDs/tgtTable/filePath │
│                  │ （master/engine.py _apply_detail_config + endpoint_select.md）│
│ sync（运行态键） │ readerDs/readerTable/readerPath/readerFile.path/writerDs/    │
│                  │ writerTable/fieldMap（worker/executors/sync.py）             │
│ file_sync        │ filePath/stagedPath/targetDs/targetSchema/targetTable        │
│                  │ （worker/executors/file_sync.py；运行态无血缘采集）          │
│ field_map(union) │ data.inputs=["<节点id>:sourceRef"|":targetRef"|"id"(旧格式)] │
│                  │ + fieldMap=[{from,to}|{key,value}]；方向：field_map          │
│                  │ fmSrcIndex=0/fmTgtIndex=1，field_map_union 反向(1/0)         │
│                  │ （types.ts ResourcePick + dag.ts:675/696 + field_map*.md；   │
│                  │ 端口语义优先，无端口按索引定向）                             │
│ condition_set    │ 仅 filterExpr/incrementalColumn/incrementalExpr，无源/目标表 │
│                  │ 语义 → 跳过组（condition_set.md 已核实）                     │
└──────────────────┴──────────────────────────────────────────────────────────────┘

分派矩阵：
- sql                          → parse_sql_lineage 逐语句转 table_edges + field_edges
- endpoint_select/sync/        → config 直读每对 src→tgt 组合 → table_edges；
  file_sync/file_sync_orch       fieldMap 非空 → field_edges（transform 留空，D2 留空只表级）
- field_map/field_map_union    → 输入表沿拓扑回溯前驱（控制流穿透）取端点两侧；
                                  fieldMap 经索引方向定向 → table_edges + field_edges
- 逻辑控制/模板（无残留配置）  → 跳过（不产边不记 opaque）
- python/shell/流处理/未知类型 → opaques（决策 D3）
"""

from collections import deque

from common.sqlparser import parse_sql_lineage

# 跳过组：逻辑控制 + 直通无表配置 + 模板类型（components/catalog.py 口径 + condition_set 已核实无表语义；
# page_board 虽为 passthrough，按任务裁定 D3 归 opaque 展示组件）
SKIP_TYPES = frozenset({
    "start", "end", "conditions", "switch", "fork", "join", "merge", "delay",
    "dependent", "loop", "variable", "assert",
    "condition_set",
    "demo_pipeline", "src_base_orch", "tgt_base_orch",
})

# 端点族：持有源/目标表语义的节点（设计态 endpoint_select + 运行态 sync/file_sync 兜底）
ENDPOINT_TYPES = frozenset({"endpoint_select", "sync", "file_sync"})

_SQL_KEYS = ("pre", "sql", "post")  # 执行顺序（sql.py：前置 → 主 → 后置）


# ---------------- 基础工具 ----------------

def _node_id(node: dict) -> str:
    """节点 id（真实结构 id；兼容任务口径 nodeId 别名）。"""
    return str(node.get("id") or node.get("nodeId") or "").strip()


def _node_data(node: dict) -> dict:
    """节点配置（真实结构 data；兼容任务口径 config 别名；非 dict 容错为空）。"""
    for key in ("data", "config"):
        val = node.get(key)
        if isinstance(val, dict):
            return val
    return {}


def _safe_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _split_table(v) -> tuple:
    """表取值拆分：str（"tbl" 或 "schema.tbl"）或 {schema, table} 对象 → (schema, table)。"""
    if isinstance(v, dict):
        return (str(v.get("schema") or "").strip().strip("`"),
                str(v.get("table") or "").strip().strip("`"))
    text = str(v or "").strip().strip("`")
    if "." in text:
        schema, name = text.split(".", 1)
        return schema.strip(), name.strip()
    return "", text


def _qualify(ds, table) -> str:
    """表名限定：显式 schema → {schema}.{table}；否则 {ds}.{table}（形态依据见模块 docstring）。"""
    schema, name = _split_table(table)
    if not name:
        return ""
    if schema:
        return "%s.%s" % (schema, name)
    ds_name = str(ds or "").strip()
    return "%s.%s" % (ds_name, name) if ds_name else name


def _field_map_pairs(data: dict) -> list:
    """fieldMap（真实 key；columnMap 别名兜底）→ [(src_field, tgt_field)]。

    条目双兼容（对齐 sync._column_pairs 口径）：执行器契约 {from, to} / 前端 kv 形态 {key, value}。
    """
    raw = data.get("fieldMap") or data.get("columnMap") or []
    if not isinstance(raw, list):
        return []
    pairs = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        src = str(item.get("from") or item.get("key") or "").strip()
        dst = str(item.get("to") or item.get("value") or "").strip()
        if src and dst:
            pairs.append((src, dst))
    return pairs


def _probe_tables(raw) -> list:
    """probeResult 双形态 → 限定表名清单（去重保序；对齐 engine._probe_schemas_text 口径）。"""
    out, seen = [], set()
    items = []
    if isinstance(raw, str):
        items = [p.strip() for p in raw.replace("，", ",").split(",") if p.strip()]
    elif isinstance(raw, list):
        items = raw
    for item in items:
        schema, name = _split_table(item)
        if not name:
            continue
        qualified = "%s.%s" % (schema, name) if schema else name
        if qualified not in seen:
            seen.add(qualified)
            out.append(qualified)
    return out


def _t_edge(wf_code: int, node_id: str, from_table: str, to_table: str,
            stmt_no: int = 0) -> dict:
    return {"wf_code": wf_code, "instance_id": 0, "node_id": node_id,
            "stmt_no": stmt_no, "from_table": from_table, "to_table": to_table,
            "tmp_flag": 0, "src_type": "design"}


def _f_edge(to_table: str, to_field: str, from_table: str, from_field: str,
            transform: str = "") -> dict:
    return {"to_table": to_table, "to_field": to_field, "from_table": from_table,
            "from_field": from_field, "transform": transform, "src_type": "design"}


def _fkey(edge: dict) -> tuple:
    """字段边去重键（对齐 t_lineage_field uk：edge 关联由 Task 3 落库时建立）。"""
    return (edge["to_table"], edge["to_field"], edge["from_table"], edge["from_field"])


def _dedup(items: list, key) -> list:
    """保序去重（同节点内重复边防御，落库去重由 Task 3 按 uk 处理）。"""
    seen = set()
    out = []
    for item in items:
        k = key(item)
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out


# ---------------- 端点族：源/目标侧解析 ----------------

def _endpoint_tgt_table(data: dict, node_type: str) -> str:
    """端点节点目标侧限定表名（无目标 → 空串）。"""
    if node_type == "sync":
        return _qualify(data.get("writerDs"), data.get("writerTable"))
    if node_type == "file_sync":
        schema, name = _split_table(data.get("targetTable"))
        schema = schema or str(data.get("targetSchema") or "").strip()
        if not name:
            return ""
        return "%s.%s" % (schema, name) if schema else _qualify(data.get("targetDs"), name)
    return _qualify(data.get("tgtDs"), data.get("tgtTable"))


def _endpoint_src_tables(data: dict, node_type: str) -> list:
    """端点节点源侧限定表名清单（多源探测逐表；文件源/无源 → 空清单）。"""
    if node_type == "sync":
        table = _qualify(data.get("readerDs"), data.get("readerTable"))
        return [table] if table else []
    if node_type == "file_sync":
        return []
    mode = str(data.get("baseMode") or "src_base").strip()
    if mode == "file_sync":
        return []
    if mode == "tgt_base":
        probe = _probe_tables(data.get("probeResult"))
        if probe:
            return probe
        # 探测结果为空回落运行态口径：exact 同名探测基准表 = 目标表名（engine._probe_reader_table）
        ds = str(data.get("srcDs") or "").strip()
        name = _split_table(data.get("tgtTable"))[1]
        return ["%s.%s" % (ds, name)] if ds and name else []
    table = _qualify(data.get("srcDs"), data.get("srcTable"))
    return [table] if table else []


def _file_src_path(data: dict) -> str:
    """文件源路径（endpoint_select.filePath / file_sync.filePath|stagedPath / sync readerFile|readerPath）。"""
    path = str(data.get("filePath") or "").strip()
    if not path:
        path = str(data.get("stagedPath") or "").strip()
    if not path and isinstance(data.get("readerFile"), dict):
        path = str(data["readerFile"].get("path") or "").strip()
    if not path:
        path = str(data.get("readerPath") or "").strip()
    return path.rstrip("/").strip()


def _sync_family_edges(node_id: str, data: dict, node_type: str, wf_code: int) -> tuple:
    """同步编排族：每对 src→tgt 组合 → table_edges；fieldMap 非空 → field_edges（D2 留空只表级）。"""
    tgt = _endpoint_tgt_table(data, node_type)
    if not tgt:
        return [], []
    src_tables = _endpoint_src_tables(data, node_type)
    file_path = "" if src_tables else _file_src_path(data)  # 连接型优先；无表才惰性取文件路径
    if file_path:
        table_edges = [_t_edge(wf_code, node_id, "file:%s" % file_path, tgt)]
    else:
        table_edges = [_t_edge(wf_code, node_id, src, tgt) for src in src_tables]
    field_edges = [
        _f_edge(edge["to_table"], dst, edge["from_table"], src)
        for edge in table_edges
        for src, dst in _field_map_pairs(data)
    ]
    return _dedup(table_edges, lambda e: (e["stmt_no"], e["from_table"], e["to_table"])), field_edges


# ---------------- field_map / field_map_union：前驱回溯 ----------------

def _ref_node(ref, by_id: dict):
    """inputs 引用（"<节点id>[:port]"）→ 节点 dict；引用缺失/未知节点 → None。"""
    text = str(ref or "").strip()
    if not text:
        return None
    return by_id.get(text.split(":", 1)[0])


def _walk_up_endpoints(node_id: str, by_id: dict, preds: dict) -> list:
    """沿入边向上回溯端点节点；跳过组（控制流/直通无表/模板）继续上溯，其余终止该分支。"""
    out, seen = [], {node_id}
    queue = deque(preds.get(node_id, []))
    while queue:
        pid = queue.popleft()  # BFS 保边序
        if pid in seen:
            continue
        seen.add(pid)
        pred = by_id.get(pid)
        if pred is None:
            continue
        ptype = str(pred.get("type") or "").strip()
        if ptype in ENDPOINT_TYPES:
            out.append(pred)
        elif ptype in SKIP_TYPES:
            queue.extend(preds.get(pid, []))
    return out


def _field_map_edges(node_id: str, data: dict, node_type: str, wf_code: int,
                     by_id: dict, preds: dict) -> tuple:
    """field_map/field_map_union：端点两侧解析（inputs 端口语义 > 索引定向 > 前驱回溯）→ 表级+字段边。

    - 索引方向契约（dag.ts 已核实）：field_map fmSrcIndex=0/fmTgtIndex=1；field_map_union 反向(1/0)
    - 端口语义（":sourceRef"/":targetRef" 后缀）优先于索引（FieldRenderer.vue fmRefNode 同口径）
    """
    inputs = data.get("inputs") if isinstance(data.get("inputs"), list) else []
    src_idx, tgt_idx = (1, 0) if node_type == "field_map_union" else (0, 1)
    src_node = tgt_node = None
    for ref in inputs:  # 端口语义优先
        text = str(ref or "")
        if text.endswith(":sourceRef") and src_node is None:
            src_node = _ref_node(text, by_id)
        elif text.endswith(":targetRef") and tgt_node is None:
            tgt_node = _ref_node(text, by_id)
    if src_node is None and len(inputs) > src_idx:  # 旧格式无端口引用按索引定向
        src_node = _ref_node(inputs[src_idx], by_id)
    if tgt_node is None and len(inputs) > tgt_idx:
        tgt_node = _ref_node(inputs[tgt_idx], by_id)

    src_tables = _endpoint_src_tables(_node_data(src_node), _node_type(src_node)) if src_node else []
    tgt_table = _endpoint_tgt_table(_node_data(tgt_node), _node_type(tgt_node)) if tgt_node else ""
    if not src_tables or not tgt_table:  # 兜底：前驱回溯（穿过控制流）
        for endpoint in _walk_up_endpoints(node_id, by_id, preds):
            edata, etype = _node_data(endpoint), _node_type(endpoint)
            if not src_tables:
                src_tables = _endpoint_src_tables(edata, etype)
            if not tgt_table:
                tgt_table = _endpoint_tgt_table(edata, etype)
            if src_tables and tgt_table:
                break
    if not src_tables or not tgt_table:  # 端点不可解析 → 容错产空
        return [], []

    table_edges = _dedup(
        [_t_edge(wf_code, node_id, src, tgt_table) for src in src_tables],
        lambda e: (e["stmt_no"], e["from_table"], e["to_table"]))
    field_edges = [
        _f_edge(tgt_table, dst, src, src_field)
        for src_field, dst in _field_map_pairs(data)
        for src in (e["from_table"] for e in table_edges)
    ]
    return table_edges, _dedup(field_edges, _fkey)


def _node_type(node) -> str:
    if not isinstance(node, dict):
        return ""
    return str(node.get("type") or "").strip()


# ---------------- sql 节点 ----------------

def _sql_edges(node_id: str, data: dict, wf_code: int) -> tuple:
    """sql 节点：pre+sql+post 按执行序合并解析（stmt_no=全语句顺序拆分序，对齐运行态）。

    纯 SELECT 无 to_tables → 不落（与 worker.lineage._collect 口径一致）；
    SELECT * fields 为空 → 只落表级（sqlparser 对 Star 不产字段级）。
    """
    parts = []
    for key in _SQL_KEYS:
        for seg in str(data.get(key) or "").split(";"):
            seg = seg.strip()
            if seg:
                parts.append(seg)
    if not parts:
        return [], []
    default_db = str(data.get("datasource") or data.get("datasource_id") or "").strip()
    table_edges, field_edges = [], []
    for parsed in parse_sql_lineage(";\n".join(parts), default_db):
        if not parsed.to_tables:
            continue
        for to_table in parsed.to_tables:
            for from_table in (parsed.from_tables or [""]):
                table_edges.append(
                    _t_edge(wf_code, node_id, from_table, to_table, parsed.stmt_no))
            for fm in parsed.fields:
                if fm.to_table == to_table:
                    field_edges.append(_f_edge(
                        fm.to_table, fm.to_field, fm.from_table, fm.from_field, fm.transform))
    return table_edges, field_edges


# ---------------- 主入口 ----------------

def extract_wf_lineage(nodes, edges, wf_code) -> dict:
    """工作流定义节点/边 → 设计态血缘（纯函数，容错不抛出）。

    - nodes: [{id, type, data}]（master/dag.py 口径；兼容 nodeId/config 别名）
    - edges: [{source, target, ...}]（仅取拓扑关系）
    - wf_code: 工作流编码（不可转 int 时兜底 0）
    - 返回 {"table_edges": [...], "field_edges": [...], "opaques": [...]}
    """
    wf = _safe_int(wf_code)
    node_list = [n for n in (nodes or []) if isinstance(n, dict)]
    by_id: dict = {}
    for node in node_list:
        try:
            nid = _node_id(node)
        except Exception:  # noqa: BLE001 信封层异常：不进索引，主循环统一记 opaque
            continue
        if nid:
            by_id.setdefault(nid, node)
    preds: dict = {}
    for edge in (edges or []):
        if not isinstance(edge, dict):
            continue
        src, tgt = edge.get("source"), edge.get("target")
        if src and tgt:
            preds.setdefault(str(tgt), []).append(str(src))

    table_edges: list = []
    field_edges: list = []
    opaques: list = []
    for node in node_list:
        nid = ntype = ""
        try:  # try 上移：信封层（_node_id/type/data）异常同样隔离，不破「纯函数不抛出」契约
            nid = _node_id(node)
            ntype = str(node.get("type") or "").strip()
            data = _node_data(node)
            if not nid or not ntype or ntype in SKIP_TYPES:
                continue  # 逻辑控制/模板/缺 id：不产边不记 opaque
            if ntype == "sql":
                te, fe = _sql_edges(nid, data, wf)
            elif ntype in ENDPOINT_TYPES or ntype == "file_sync_orch":
                te, fe = _sync_family_edges(nid, data, ntype, wf)
            elif ntype in ("field_map", "field_map_union"):
                te, fe = _field_map_edges(nid, data, ntype, wf, by_id, preds)
            else:
                opaques.append({"wf_code": wf, "node_id": nid, "type": ntype})
                continue
            table_edges.extend(te)
            field_edges.extend(fe)
        except Exception as exc:  # noqa: BLE001 单节点异常隔离（任务裁定，附 reason）
            opaques.append({"wf_code": wf, "node_id": nid, "type": ntype,
                            "reason": "%s: %s" % (type(exc).__name__, exc)})
    return {"table_edges": table_edges, "field_edges": field_edges, "opaques": opaques}
