"""血缘查询路由（I5 设计文档 §6，F25/F27）。

- GET /lineage/tables：表级边列表（前端 TableLineage 契约 {from,to,task,wf} + 追溯附加字段）
- GET /lineage/fields：字段级映射（前端 FieldLineage 契约 {[target]: [{from,transform}]}）
- GET /lineage/stats：统计浮窗（边数/字段映射数/覆盖表数/覆盖工作流数/最近采集时间）
- GET /lineage/trace：实例/节点维度追溯（不去重，保留实例级血缘快照）
- GET /lineage/graph：血缘图聚合（表/字段级聚边 + design/runtime 双源合并 + 中心表
  BFS 扩散，Task 4；替代原 baseline.py 的声明级 stub）
- POST /lineage/redesign/{wfCode}：按需重算单个工作流的设计态血缘
  （save/publish 成功后由 wf_definition 自动触发同一重算逻辑，本端点兜底手动重跑）

多实例去重口径：整体重跑产生新实例号 → 同 (wf_code,node_id,stmt_no,from,to) 多行，
列表/字段/统计按该维度保留最新实例（Python 端 O(n) 单遍，当前规模数百行）；
trace 接口按 instance_id 过滤呈现实例快照原貌。

表名输出剥 db 前缀（对齐前端 MetaTable.name 裸表名契约与 tables.yaml 对账口径；
临时表注册名 raw_txt 本无前缀不受影响）。graph 聚合键/节点 fq 同口径 _bare 归一
（1.9 实测：design 落数据源 ID 前缀、runtime 落数据源名前缀或裸名，原值聚合会裂边
致双源永不命中；归一后节点 ds 保留该端点首个出现形态，file:{path} 原样不剥）。
"""

import json
from collections import deque
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.auth import ApiError, get_current_user, require_perm
from common.db import get_db
from common.lineage_extract import FILE_NAME_PREFIX, SRC_TYPE_DESIGN, extract_wf_lineage
from common.log import get_logger
from common.models import LineageEdge, LineageField, User, WfDefinition
from common.resp import WF_NOT_FOUND, fmt_dt, ok

logger = get_logger("api.lineage")

router = APIRouter(prefix="/lineage", tags=["lineage"])


def _bare(name: str) -> str:
    """db.table → table（临时注册名无前缀原样；file:{path} 路径含点号，原样保留防误剥）。"""
    if not name:
        return name
    if name.startswith(FILE_NAME_PREFIX):
        return name
    return name.rsplit(".", 1)[-1]


def _field_node(table: str, field: str) -> str:
    """字段级图节点名："table.field"；无来源表（常量）返回空串（前端过滤）。"""
    if not table:
        return ""
    return "%s.%s" % (_bare(table), field or "")


def _latest_edges(edges: list) -> list:
    """按 (wf_code, node_id, stmt_no, from_table, to_table) 保留最新一条（多实例去重）。"""
    latest: dict = {}
    for e in edges:
        key = (e.wf_code, e.node_id, e.stmt_no, e.from_table, e.to_table)
        if key not in latest or e.id > latest[key].id:
            latest[key] = e
    return list(latest.values())


def _base_query(db: Session):
    return db.query(LineageEdge)


def _edge_item(e: LineageEdge) -> dict:
    """边输出行：前端契约四键 + 追溯/弹层附加字段。"""
    return {
        "from": _bare(e.from_table),
        "to": _bare(e.to_table),
        "task": e.node_name or "",
        "wf": e.wf_name or "",
        "instanceId": e.instance_id,
        "nodeId": e.node_id,
        "dsName": e.ds_name or "",
        "tmpFlag": 1 if e.tmp_flag else 0,
        "stmt": e.stmt or "",
        "stmtNo": e.stmt_no,
        "wfCode": e.wf_code,
        "createTime": fmt_dt(e.create_time),
    }


@router.get("/tables")
def list_tables(
    keyword: Optional[str] = None,
    wf_code: Optional[int] = None,
    instance_id: Optional[str] = None,
    table: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """表级边列表：keyword 模糊匹配 from/to 表名；table 以该表为中心（from 或 to 命中）。"""
    query = _base_query(db)
    if wf_code is not None:
        query = query.filter(LineageEdge.wf_code == wf_code)
    if instance_id:
        query = query.filter(LineageEdge.instance_id == instance_id)
    if keyword:
        like = "%%%s%%" % keyword
        query = query.filter(LineageEdge.from_table.like(like) | LineageEdge.to_table.like(like))
    edges = _latest_edges(query.all())
    if table:
        bare = _bare(table)
        edges = [e for e in edges
                 if _bare(e.from_table) == bare or _bare(e.to_table) == bare]
    items = [_edge_item(e) for e in sorted(edges, key=lambda x: x.id)]
    return ok(items)


@router.get("/fields")
def list_fields(
    table: Optional[str] = None,
    wf_code: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """字段级映射：目标表过滤 → FieldLineage 契约（target 键 = "table.field"）。"""
    query = _base_query(db)
    if wf_code is not None:
        query = query.filter(LineageEdge.wf_code == wf_code)
    edges = _latest_edges(query.all())
    if table:
        bare = _bare(table)
        edges = [e for e in edges if _bare(e.to_table) == bare]
    # 单目标语句字段级才落库（worker 侧保证）；字段按所属边（from 表）聚合
    out: dict = {}
    for e in sorted(edges, key=lambda x: x.id):
        rows = db.query(LineageField).filter(LineageField.edge_id == e.id).all()
        for f in rows:
            target = "%s.%s" % (_bare(e.to_table), f.to_field)
            src = _field_node(f.from_table, f.from_field)
            items = out.setdefault(target, [])
            if any(it["from"] == src for it in items):
                continue  # 多实例/同 key 去重
            items.append({"from": src, "transform": f.transform or ""})
    return ok(out)


@router.get("/stats")
def lineage_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """统计浮窗：去重呈现口径（边数/字段映射数/覆盖表数/覆盖工作流数/最近采集）。"""
    edges = _latest_edges(_base_query(db).all())
    edge_ids = [e.id for e in edges]
    fields_total = (
        db.query(LineageField).filter(LineageField.edge_id.in_(edge_ids)).count()
        if edge_ids else 0
    )
    tables = set()
    for e in edges:
        if e.from_table:
            tables.add(_bare(e.from_table))
        tables.add(_bare(e.to_table))
    last = max((e.create_time for e in edges), default=None)
    return ok({
        "edgeCount": len(edges),
        "fieldCount": fields_total,
        "tableCount": len(tables),
        "wfCount": len({e.wf_code for e in edges}),
        "lastTime": fmt_dt(last),
    })


@router.get("/trace")
def lineage_trace(
    instance_id: str,
    node_id: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """实例维度追溯（入口①③）：实例/节点过滤的边 + 字段（不去重，实例快照原貌）。"""
    query = _base_query(db).filter(LineageEdge.instance_id == instance_id)
    if node_id:
        query = query.filter(LineageEdge.node_id == node_id)
    edges = query.order_by(LineageEdge.stmt_no, LineageEdge.id).all()
    items = []
    for e in edges:
        item = _edge_item(e)
        item["fields"] = [
            {
                "toField": f.to_field,
                "from": _field_node(f.from_table, f.from_field),
                "fromTable": _bare(f.from_table) if f.from_table else "",
                "fromField": f.from_field or "",
                "transform": f.transform or "",
            }
            for f in db.query(LineageField).filter(LineageField.edge_id == e.id).all()
        ]
        items.append(item)
    return ok(items)


# ---------------- 血缘图聚合（GET /graph，Task 4） ----------------

GRAPH_DEFAULT_LIMIT = 200


def _split_fq(name: str) -> tuple:
    """fq → (ds, table)：file: 边 ds 置空保留原串（路径含点号不可按点拆）；db.table 按末段拆。"""
    if name.startswith(FILE_NAME_PREFIX):
        return "", name
    if "." in name:
        db_name, tbl = name.rsplit(".", 1)
        return db_name, tbl
    return "", name


def _field_fq(table: str, field: str) -> str:
    """字段级节点名 {table}.{field}（from/to 原值不改写）；无来源表（常量）退化为裸字段名。"""
    if not table:
        return field or ""
    return "%s.%s" % (table, field or "")


def _field_node_table(name: str) -> str:
    """字段级节点名 → 表部（"db.t.f"→"db.t"；裸字段/常量节点无表部返回空串）。"""
    head, sep, _tail = name.rpartition(".")
    return head if sep and head else ""


def _collect_opaques(db: Session, wf_codes) -> list:
    """opaque 节点重算（解析期不产边的组件，未落库故查询端从定义图重算）。

    wf_codes=None 取全部定义；给定集合时只解析相关工作流（扩散子图按需收窄，避免全量解析）。
    """
    query = db.query(WfDefinition)
    if wf_codes is not None:
        query = query.filter(WfDefinition.code.in_(wf_codes))
    out: list = []
    for definition in query.all():
        if not definition.graph_json:
            continue
        try:
            doc = json.loads(definition.graph_json)
        except (TypeError, ValueError):
            continue
        if not isinstance(doc, dict):
            continue
        parsed = extract_wf_lineage(
            doc.get("nodes") or [], doc.get("edges") or [], int(definition.code or 0))
        for op in parsed.get("opaques") or []:
            item = {"wfCode": op.get("wf_code"), "nodeId": op.get("node_id"),
                    "type": op.get("type")}
            if op.get("reason"):
                item["reason"] = op["reason"]
            out.append(item)
    out.sort(key=lambda o: (o["wfCode"] or 0, o["nodeId"]))
    return out


@router.get("/graph", summary="血缘图聚合（表/字段级聚边 + 中心表扩散）")
def lineage_graph(
    level: str = Query("table", pattern="^(table|field)$"),
    source: str = Query("all", pattern="^(all|design|runtime)$"),
    wf_code: Optional[int] = Query(None, alias="wfCode"),
    table: Optional[str] = None,
    direction: str = Query("both", pattern="^(upstream|downstream|both)$"),
    depth: int = Query(0, ge=0),
    limit: int = Query(GRAPH_DEFAULT_LIMIT, ge=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """聚合 t_lineage_edge / t_lineage_field 为图（标准响应包 data 内）：

    - 聚边：同 (from,to) 一条边（键 _bare 裸表名归一，field 级按字段行自身 from/to
      表对分组），sources=全量行 src_type 去重，refs=同 (wf,node,stmt) 多实例保留最新
      的明细；边端点/节点 fq 输出裸表名（ds 保留首见原形态），file:{path} 原样保留；
      节点 lastCollected=该节点全部聚合行 create_time max（design+runtime 合计，
      与 /stats lastTime 同口径；缺数据输出 null）；
    - 中心表扩散：_bare 归一化精确匹配优先、endsWith 兜底，BFS 沿 direction 方向
      （visited 防环），depth 截跳数，limit 截节点数（超出 truncated=true）。
    """
    table = (table or "").strip() or None

    # ---- 行集过滤（source/wfCode）----
    edge_query = _base_query(db)
    if wf_code is not None:
        edge_query = edge_query.filter(LineageEdge.wf_code == wf_code)
    if source != "all":
        edge_query = edge_query.filter(LineageEdge.src_type == source)

    node_acc: dict = {}  # fq -> {ds, table, tmp, sources:set, wfs:set, last:最大create_time}
    edges_out: list = []

    if level == "field":
        # field 级：字段行展开为边（挂靠明细取父边 wf/node/stmt；Task 3 已知限制：
        # 字段挂首边，聚合按字段行自身 from/to 表对分组，不复现 edge_id 挂靠）
        field_query = (
            db.query(LineageField, LineageEdge)
            .join(LineageEdge, LineageEdge.id == LineageField.edge_id)
        )
        if wf_code is not None:
            field_query = field_query.filter(LineageEdge.wf_code == wf_code)
        if source != "all":
            field_query = field_query.filter(LineageEdge.src_type == source)
        groups: dict = {}
        for f, e in field_query.all():
            # 分组键表部 _bare 归一（同表级口径：design ds-ID 前缀 / runtime ds 名前缀合一）
            groups.setdefault(
                (_bare(f.from_table), f.from_field, _bare(e.to_table), f.to_field), []).append((f, e))
        for (ft, ff, tt, tf), grp in groups.items():
            best: dict = {}  # 同 (wf,node,stmt) 多实例保留最新（edge.id 最大）
            fq_from, fq_to = _field_fq(ft, ff), _field_fq(tt, tf)  # 表部已归一的裸表名
            for f, e in grp:
                key = (e.wf_code, e.node_id, e.stmt_no)
                if key not in best or e.id > best[key].id:
                    best[key] = (f, e)
                # 节点 ds/表部取首个出现原形态（raw），键用归一 fq 与边端点一致
                for raw, fq in ((_field_fq(f.from_table, f.from_field), fq_from),
                                (_field_fq(e.to_table, f.to_field), fq_to)):
                    acc = node_acc.get(fq)
                    if acc is None:
                        ds, tbl = _split_fq(raw)
                        acc = node_acc[fq] = {"ds": ds, "table": tbl, "tmp": False,
                                              "sources": set(), "wfs": set(), "last": None}
                    acc["sources"].add(f.src_type)
                    acc["wfs"].add(e.wf_code)
                    acc["tmp"] = acc["tmp"] or bool(e.tmp_flag)
                    ct = e.create_time  # lastCollected：父边采集时间（与 /stats lastTime 同口径）
                    if ct is not None and (acc["last"] is None or ct > acc["last"]):
                        acc["last"] = ct
            edges_out.append({
                "from": fq_from, "to": fq_to, "level": "field",
                "sources": sorted({f.src_type for f, _e in grp}),
                "refs": [{"wfCode": e.wf_code, "nodeId": e.node_id, "stmtNo": e.stmt_no,
                          "transform": f.transform or ""}
                         for f, e in sorted(best.values(), key=lambda fe: fe[1].id)],
            })
    else:
        # table 级：同 (from,to) 聚一条边；聚合键 _bare 归一（1.9 实测：design 落数据源
        # ID 前缀 9.x、runtime 落数据源名前缀 ec.x 或裸名，同物理血缘原值聚合会裂边、
        # 双源 sources 永不命中）；sources 取全量行（多实例去重不丢 src_type）；
        # 节点 fq=裸表名（全局一致），ds 取该端点首个出现形态（ID/名前缀均可，不硬造）
        groups = {}
        for r in edge_query.all():
            groups.setdefault((_bare(r.from_table), _bare(r.to_table)), []).append(r)
        for (frm, to), grp in groups.items():
            best: dict = {}  # refs：组内裸端点恒定，同 (wf,node,stmt) 归一保留最新
            for r in grp:
                key = (r.wf_code, r.node_id, r.stmt_no)
                if key not in best or r.id > best[key].id:
                    best[key] = r
            edges_out.append({
                "from": frm, "to": to, "level": "table",
                "sources": sorted({r.src_type for r in grp}),
                "refs": [{"wfCode": r.wf_code, "nodeId": r.node_id, "stmtNo": r.stmt_no}
                         for r in sorted(best.values(), key=lambda x: x.id)],
            })
            for r in grp:
                for raw in (r.from_table, r.to_table):
                    if not raw:
                        continue  # 空来源（INSERT..VALUES 单边）不产 from 节点
                    fq = _bare(raw)  # 与聚合键同口径（file: 原样保留）
                    acc = node_acc.get(fq)
                    if acc is None:
                        ds, tbl = _split_fq(raw)
                        acc = node_acc[fq] = {"ds": ds, "table": tbl, "tmp": False,
                                              "sources": set(), "wfs": set(), "last": None}
                    acc["sources"].add(r.src_type)
                    acc["wfs"].add(r.wf_code)
                    acc["tmp"] = acc["tmp"] or bool(r.tmp_flag)
                    ct = r.create_time  # lastCollected：聚合行 create_time max（None 安全比较）
                    if ct is not None and (acc["last"] is None or ct > acc["last"]):
                        acc["last"] = ct
    edges_out.sort(key=lambda e: (e["from"], e["to"]))

    # ---- 中心表扩散 / 全图节点上限 ----
    truncated = False
    if table is not None:
        center_bare = _bare(table)

        def _node_table_name(fq: str) -> str:
            return fq if level == "table" else _field_node_table(fq)

        seeds = sorted(fq for fq in node_acc
                       if _bare(_node_table_name(fq)) == center_bare)
        if not seeds:  # 精确匹配不上 → endswith 兜底（容忍带前缀传入）
            seeds = sorted(fq for fq in node_acc
                           if _node_table_name(fq).endswith(table))
        if len(seeds) > limit:  # 多 seed 命中（field 级宽表逐字段）超上限 → 截 seed 并置位
            seeds = seeds[:limit]
            truncated = True
        adj_out: dict = {}
        adj_in: dict = {}
        for e in edges_out:
            adj_out.setdefault(e["from"], set()).add(e["to"])
            adj_in.setdefault(e["to"], set()).add(e["from"])
        visited = set(seeds)
        queue = deque((s, 0) for s in seeds)
        while queue:
            cur, hops = queue.popleft()
            if depth and hops >= depth:
                continue
            nxt_all = []
            if direction in ("downstream", "both"):
                nxt_all.extend(adj_out.get(cur, ()))
            if direction in ("upstream", "both"):
                nxt_all.extend(adj_in.get(cur, ()))
            for nxt in nxt_all:
                if nxt in visited:
                    continue
                if len(visited) >= limit:
                    truncated = True  # 邻居还有未收录节点 → 截断置位并停止扩散
                    queue.clear()
                    break
                visited.add(nxt)
                queue.append((nxt, hops + 1))
        kept = visited
        edges_out = [e for e in edges_out if e["from"] in kept and e["to"] in kept]
        if seeds:
            sub_wfs = {ref["wfCode"] for e in edges_out for ref in e["refs"]}
            opaques = _collect_opaques(db, sub_wfs)
        else:  # 中心表未命中任何节点 → 空图
            opaques = []
    else:
        ordered = sorted(node_acc)
        if len(ordered) > limit:
            truncated = True
            kept = set(ordered[:limit])
        else:
            kept = set(ordered)
        edges_out = [e for e in edges_out if e["from"] in kept and e["to"] in kept]
        opaques = _collect_opaques(db, {wf_code} if wf_code is not None else None)

    nodes = [{
        "fq": fq, "ds": node_acc[fq]["ds"], "table": node_acc[fq]["table"],
        "tmpFlag": 1 if node_acc[fq]["tmp"] else 0,
        "sources": sorted(node_acc[fq]["sources"]),
        "wfs": sorted(node_acc[fq]["wfs"]),
        "lastCollected": fmt_dt(node_acc[fq]["last"]),
    } for fq in sorted(kept)]
    return ok({"nodes": nodes, "edges": edges_out, "opaques": opaques,
               "truncated": truncated})


# ---------------- 设计态血缘重算落库（保存/发布/按需重算共用，Task 3） ----------------

def delete_design_lineage(db: Session, wf_code: int) -> int:
    """清理某工作流的 design 血缘行（先 field 后 edge：field 挂 edge_id）。

    供两处使用：重算的 delete-then-reinsert 前置清理；工作流删除的级联清理
    （与调度/版本快照同事务同等待遇，异常随删除主流程回滚，不做旁路）。
    """
    old_ids = [
        rid for (rid,) in db.query(LineageEdge.id).filter(
            LineageEdge.src_type == SRC_TYPE_DESIGN, LineageEdge.wf_code == wf_code).all()
    ]
    if not old_ids:
        return 0
    db.query(LineageField).filter(LineageField.edge_id.in_(old_ids)).delete(synchronize_session=False)
    db.query(LineageEdge).filter(LineageEdge.id.in_(old_ids)).delete(synchronize_session=False)
    return len(old_ids)


def rebuild_design_lineage(db: Session, definition: WfDefinition) -> dict:
    """重算工作流定义的设计态血缘（幂等 delete-then-reinsert，随调用方会话提交）。

    - 解析：common/lineage_extract.extract_wf_lineage（纯函数，不抛不触库）
    - 表级边批量 add → flush 取自增 id → 字段行按 (node_id,stmt_no,from,to) 精确挂靠
      同键表级边（同 wf 同表对多语句/多节点各归各边），未命中回落同表对兜底
    - 字段行找不到归属表级边（sql CTE/常量列等）跳过记日志，不炸
    - 批内按 uk 去重防御（design 行免逐行查旧，uk_lineage/uk_field 兜重复产出）
    - 返回 {tableEdges, fieldEdges, opaqueNodes}；异常向上抛，旁路由调用方定
      （保存/发布触发走 redesign_wf_lineage 兜底，redesign 端点如实暴露失败）
    """
    wf_code = int(definition.code or 0)
    doc = json.loads(definition.graph_json) if definition.graph_json else {}
    parsed = extract_wf_lineage(doc.get("nodes") or [], doc.get("edges") or [], wf_code)

    delete_design_lineage(db, wf_code)

    # 节点名展示冗余（best-effort：name 在节点顶层或 data 内，缺失留空）
    name_of: dict = {}
    for node in doc.get("nodes") or []:
        if isinstance(node, dict) and node.get("id"):
            data = node.get("data") if isinstance(node.get("data"), dict) else {}
            name_of[str(node["id"])] = str(node.get("name") or data.get("name") or "")

    edges: list = []
    seen_edge = set()
    for te in parsed["table_edges"]:
        key = (te["node_id"], te["stmt_no"], te["from_table"], te["to_table"])
        if key in seen_edge:
            continue
        seen_edge.add(key)
        edges.append(LineageEdge(
            wf_code=wf_code, wf_name=definition.name or "",
            instance_id=str(te.get("instance_id") or 0),  # 设计态 instance_id=0 标识
            node_id=te["node_id"], node_name=name_of.get(te["node_id"], ""),
            stmt_no=te["stmt_no"], from_table=te["from_table"], to_table=te["to_table"],
            tmp_flag=bool(te.get("tmp_flag")), src_type=SRC_TYPE_DESIGN,
        ))
    db.add_all(edges)
    db.flush()  # 取自增 edge.id 供字段行挂靠

    # 字段行挂靠索引：精确键 (node_id,stmt_no,from,to) 优先；同表对兜底覆盖解析器
    # 未携带精确归属或表对存在而 node/stmt 对不上的字段行（防孤儿跳过）
    edge_by_key: dict = {}
    edge_by_pair: dict = {}
    for edge in edges:
        edge_by_key.setdefault(
            (edge.node_id, edge.stmt_no, edge.from_table, edge.to_table), edge)
        edge_by_pair.setdefault((edge.from_table, edge.to_table), edge)
    fields: list = []
    seen_field = set()
    for fe in parsed["field_edges"]:
        edge = edge_by_key.get(
            (fe["node_id"], fe["stmt_no"], fe["from_table"], fe["to_table"]))
        if edge is None:
            edge = edge_by_pair.get((fe["from_table"], fe["to_table"]))
        if edge is None:
            logger.warning("设计态字段行无归属表级边，跳过: wf_code=%s %s.%s → %s.%s",
                           wf_code, fe["from_table"], fe["from_field"],
                           fe["to_table"], fe["to_field"])
            continue
        key = (edge.id, fe["to_field"], fe["from_table"], fe["from_field"])
        if key in seen_field:
            continue
        seen_field.add(key)
        fields.append(LineageField(
            edge_id=edge.id, to_field=fe["to_field"], from_table=fe["from_table"],
            from_field=fe["from_field"], transform=fe.get("transform") or "",
            src_type=SRC_TYPE_DESIGN,
        ))
    db.add_all(fields)
    db.commit()
    return {"tableEdges": len(edges), "fieldEdges": len(fields),
            "opaqueNodes": len(parsed["opaques"])}


def redesign_wf_lineage(db: Session, definition: WfDefinition) -> None:
    """设计态血缘重算旁路入口（保存/发布触发用）：任何异常仅记日志并回滚重算事务，
    绝不阻断工作流保存/发布主流程（与 worker/lineage.py 旁路口径一致）。"""
    try:
        stats = rebuild_design_lineage(db, definition)
        logger.info("设计态血缘重算: wf=%s code=%s → 表级边 %d / 字段行 %d / opaque 节点 %d",
                    definition.id, definition.code,
                    stats["tableEdges"], stats["fieldEdges"], stats["opaqueNodes"])
    except Exception as exc:  # noqa: BLE001 血缘旁路绝不阻断主流程
        db.rollback()
        logger.error("设计态血缘重算失败（不影响工作流主流程）: wf=%s code=%s %r",
                     definition.id, definition.code, exc)


@router.post("/redesign/{wf_code}")
def redesign_lineage(
    wf_code: int,
    user: User = Depends(require_perm("design_component")),
    db: Session = Depends(get_db),
):
    """按需重算单个工作流的设计态血缘（同 save/publish 触发的重算逻辑）。"""
    definition = db.query(WfDefinition).filter(WfDefinition.code == wf_code).first()
    if definition is None:
        raise ApiError(WF_NOT_FOUND, status=404)
    return ok(rebuild_design_lineage(db, definition))
