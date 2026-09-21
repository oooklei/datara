"""血缘查询路由（I5 设计文档 §6，F25/F27）。

- GET /lineage/tables：表级边列表（前端 TableLineage 契约 {from,to,task,wf} + 追溯附加字段）
- GET /lineage/fields：字段级映射（前端 FieldLineage 契约 {[target]: [{from,transform}]}）
- GET /lineage/stats：统计浮窗（边数/字段映射数/覆盖表数/覆盖工作流数/最近采集时间）
- GET /lineage/trace：实例/节点维度追溯（不去重，保留实例级血缘快照）

多实例去重口径：整体重跑产生新实例号 → 同 (wf_code,node_id,stmt_no,from,to) 多行，
列表/字段/统计按该维度保留最新实例（Python 端 O(n) 单遍，当前规模数百行）；
trace 接口按 instance_id 过滤呈现实例快照原貌。

表名输出剥 db 前缀（对齐前端 MetaTable.name 裸表名契约与 tables.yaml 对账口径；
临时表注册名 raw_txt 本无前缀不受影响）。
"""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.auth import get_current_user
from common.db import get_db
from common.log import get_logger
from common.models import LineageEdge, LineageField, User
from common.resp import fmt_dt, ok

logger = get_logger("api.lineage")

router = APIRouter(prefix="/lineage", tags=["lineage"])


def _bare(name: str) -> str:
    """db.table → table（临时注册名无前缀原样）。"""
    return name.rsplit(".", 1)[-1] if name else name


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
