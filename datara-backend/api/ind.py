"""I20 指标定义、版本与一致性规则 API。"""
import json
import re
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.auth import ApiError, get_current_user, require_perm
from common.db import get_db
from common.dsconn import open_connection, quote_ident
from common.models import DataSource, DwModel, Indicator, IndicatorVersion, User
from common.resp import ok

router = APIRouter(tags=["ind"])
AGGS = {"SUM", "COUNT", "AVG", "MAX", "MIN", "COUNT_DISTINCT"}
FILTER_RE = re.compile(r"^[A-Za-z0-9_ .<>=!'()]+(?:\s+AND\s+[A-Za-z0-9_ .<>=!'()]+)*$", re.I)


def _row(i: Indicator) -> dict:
    return {"id": i.id, "code": i.code, "name": i.name, "en": i.code, "type": i.type, "bizDef": i.biz_def,
            "techDef": i.tech_def, "srcKind": i.src_kind, "srcRef": i.src_ref, "srcTable": i.src_ref,
            "srcField": i.src_field, "outTable": i.out_table, "outTask": i.out_task, "period": i.period,
            "dims": i.dims, "unit": i.unit, "status": i.status, "v": i.version, "owner": i.owner,
            "domain": i.biz_domain, "baseMetricId": i.base_metric_id, "aggFn": i.agg_fn, "numField": i.num_field,
            "timeField": i.time_field, "dimField": i.dim_field, "filterCond": i.filter_cond}


class IndicatorBody(BaseModel):
    code: str
    name: str
    type: str = "原子"
    bizDomain: str = ""
    bizDef: str
    techDef: str = ""
    srcKind: str = "table"
    srcRef: str = ""
    srcField: str = ""
    outTable: str = ""
    outTask: str = ""
    period: str = "日"
    dims: str = ""
    unit: str = ""
    owner: str = ""
    baseMetricId: Optional[int] = None
    aggFn: Optional[str] = None
    numField: Optional[str] = None
    timeField: Optional[str] = None
    dimField: Optional[str] = None
    filterCond: Optional[str] = None


def _validate_config(body: IndicatorBody) -> None:
    if body.aggFn and body.aggFn not in AGGS: raise ApiError(4001, "聚合函数不在白名单", status=400)
    if body.filterCond and (";" in body.filterCond or "--" in body.filterCond or re.search(r"\bOR\b", body.filterCond, re.I) or not FILTER_RE.fullmatch(body.filterCond.strip())):
        raise ApiError(4001, "过滤条件仅支持 AND 条件且禁止注释/多语句", status=400)


def _table_source(i: Indicator, db: Session) -> tuple[DataSource, str, str]:
    ref = i.src_ref.strip()
    if i.src_kind == "model" and ref.isdigit():
        model = db.get(DwModel, int(ref))
        if model and model.ds_id and model.db_name:
            ref = f"{model.ds_id}/{model.db_name}/{model.code}"
    parts = ref.split("/", 2)
    if len(parts) != 3 or not parts[0].isdigit():
        raise ApiError(4001, "来源必须是 ds_id/db/table", status=400)
    ds = db.get(DataSource, int(parts[0]))
    if ds is None: raise ApiError(4001, "来源数据源不存在", status=400)
    return ds, parts[1], parts[2]


def _agg_expr(i: Indicator) -> str:
    if i.agg_fn not in AGGS or not i.num_field:
        raise ApiError(4001, "指标未配置合法聚合函数或取数字段", status=400)
    col = quote_ident(i.num_field)
    return "COUNT(DISTINCT %s)" % col if i.agg_fn == "COUNT_DISTINCT" else f"{i.agg_fn}({col})"


def _run_rows(i: Indicator, db: Session, sql: str):
    ds, db_name, _ = _table_source(i, db)
    conn = None
    try:
        conn = open_connection(ds, db=db_name, read_timeout=60)
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        raise ApiError(4002, f"指标取数失败: {exc}", status=400) from exc
    finally:
        if conn is not None: conn.close()


@router.get("/indicators/consistency")
def consistency(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Indicator).order_by(Indicator.id).all(); items = []
    by_name: dict[str, list[Indicator]] = {}; by_tech: dict[str, list[Indicator]] = {}
    for i in rows:
        by_name.setdefault(i.name, []).append(i)
        if i.tech_def.strip(): by_tech.setdefault(i.tech_def.strip(), []).append(i)
    for vals in by_name.values():
        if len(vals) > 1 and len({(x.biz_def, x.tech_def) for x in vals}) > 1:
            items.append({"metric": vals[0].name, "places": [x.code for x in vals], "result": "fail", "detail": "同名指标口径不一致"})
    for vals in by_tech.values():
        if len(vals) > 1 and len({x.name for x in vals}) > 1:
            items.append({"metric": vals[0].tech_def, "places": [x.code for x in vals], "result": "warn", "detail": "同技术口径不同名称，建议合并"})
    return ok({"checked": len(rows), "pass": len(rows) - sum(1 for x in items if x["result"] == "fail"), "fail": sum(1 for x in items if x["result"] == "fail"), "items": items})


@router.get("/indicators")
def list_indicators(type: str = "", domain: str = "", status: str = "", keyword: str = "", page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Indicator)
    if type: q = q.filter(Indicator.type == type)
    if domain: q = q.filter(Indicator.biz_domain == domain)
    if status: q = q.filter(Indicator.status == status)
    if keyword.strip(): q = q.filter(or_(Indicator.name.like(f"%{keyword.strip()}%"), Indicator.code.like(f"%{keyword.strip()}%")))
    total = q.count(); rows = q.order_by(Indicator.id.desc()).offset((page - 1) * size).limit(size).all()
    return ok({"list": [_row(i) for i in rows], "total": total, "page": page, "size": size})


@router.post("/indicators")
def create_indicator(body: IndicatorBody, user: User = Depends(require_perm("ind:write")), db: Session = Depends(get_db)):
    _validate_config(body)
    if db.query(Indicator).filter(or_(Indicator.code == body.code.strip(), Indicator.name == body.name.strip())).first():
        raise ApiError(8002, "指标编码或名称已存在，禁止同名不同义", status=409)
    i = Indicator(code=body.code.strip(), name=body.name.strip(), type=body.type, biz_domain=body.bizDomain, biz_def=body.bizDef.strip(), tech_def=body.techDef, src_kind=body.srcKind, src_ref=body.srcRef, src_field=body.srcField, out_table=body.outTable, out_task=body.outTask, period=body.period, dims=body.dims, unit=body.unit, owner=body.owner or user.user_name, base_metric_id=body.baseMetricId, agg_fn=body.aggFn, num_field=body.numField, time_field=body.timeField, dim_field=body.dimField, filter_cond=body.filterCond)
    db.add(i); db.commit(); return ok(_row(i))


@router.get("/indicators/{indicator_id}")
def get_indicator(indicator_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    i = db.get(Indicator, indicator_id)
    if i is None: raise ApiError(4041, "指标不存在", status=404)
    data = _row(i); data["versions"] = [{"id": v.id, "version": v.version, "changeNote": v.change_note, "createdBy": v.created_by} for v in db.query(IndicatorVersion).filter_by(indicator_id=i.id).order_by(IndicatorVersion.version.desc()).all()]
    return ok(data)


@router.post("/indicators/{indicator_id}/publish")
def publish_indicator(indicator_id: int, user: User = Depends(require_perm("ind:write")), db: Session = Depends(get_db)):
    i = db.get(Indicator, indicator_id)
    if i is None: raise ApiError(4041, "指标不存在", status=404)
    if i.status != "draft": raise ApiError(4001, "指标当前不可发布", status=409)
    i.status = "published"; db.commit(); return ok({"status": i.status, "version": i.version})


class ChangeBody(IndicatorBody):
    reason: str


@router.post("/indicators/{indicator_id}/change")
def change_indicator(indicator_id: int, body: ChangeBody, user: User = Depends(require_perm("ind:write")), db: Session = Depends(get_db)):
    if not body.reason.strip(): raise ApiError(4001, "口径变更原因必填", status=400)
    _validate_config(body); i = db.get(Indicator, indicator_id)
    if i is None: raise ApiError(4041, "指标不存在", status=404)
    i.biz_def, i.tech_def, i.version = body.bizDef, body.techDef, i.version + 1
    i.agg_fn, i.num_field, i.time_field, i.dim_field, i.filter_cond = body.aggFn, body.numField, body.timeField, body.dimField, body.filterCond
    snap = json.dumps(_row(i), ensure_ascii=False); db.add(IndicatorVersion(indicator_id=i.id, version=i.version, snapshot_json=snap, change_note=body.reason.strip(), created_by=user.user_name)); db.commit()
    return ok({"version": i.version, "recheck": True})


@router.get("/indicators/{indicator_id}/versions")
def indicator_versions(indicator_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ok([{"id": v.id, "version": v.version, "changeNote": v.change_note, "createdBy": v.created_by} for v in db.query(IndicatorVersion).filter_by(indicator_id=indicator_id).order_by(IndicatorVersion.version.desc()).all()])


@router.get("/indicators/{indicator_id}/trend")
def indicator_trend(indicator_id: int, days: int = Query(8, ge=1, le=31), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    i = db.get(Indicator, indicator_id)
    if i is None: raise ApiError(4041, "指标不存在", status=404)
    if not i.agg_fn or not i.time_field: raise ApiError(4001, "指标未配置取数或时间字段", status=400)
    ds, db_name, table = _table_source(i, db); _ = ds, db_name
    date_col = quote_ident(i.time_field); table_sql = quote_ident(table)
    filt = f" WHERE {i.filter_cond}" if i.filter_cond else ""
    sql = f"SELECT DATE({date_col}) AS d, {_agg_expr(i)} AS v FROM {table_sql}{filt} GROUP BY DATE({date_col}) ORDER BY d DESC LIMIT {days}"
    rows = list(reversed(_run_rows(i, db, sql)))
    series = [{"date": str(r[0]), "value": float(r[1] or 0)} for r in rows]
    vals = [x["value"] for x in series]; today = vals[-1] if vals else None; prev = vals[-2] if len(vals) > 1 else None
    avg = sum(vals) / len(vals) if vals else None; base = vals[0] if vals else None
    return ok({"series": series, "stats": {"today": today, "dod": (today - prev) if today is not None and prev is not None else None,
                                             "avg_n": avg, "vs_n": (today - base) if today is not None and base is not None else None}})


@router.get("/indicators/{indicator_id}/breakdown")
def indicator_breakdown(indicator_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    i = db.get(Indicator, indicator_id)
    if i is None: raise ApiError(4041, "指标不存在", status=404)
    if not i.agg_fn or not i.dim_field: raise ApiError(4001, "指标未配置取数或维度字段", status=400)
    _, _, table = _table_source(i, db); dim_col = quote_ident(i.dim_field)
    sql = f"SELECT {dim_col} AS d, {_agg_expr(i)} AS v FROM {quote_ident(table)} GROUP BY {dim_col} ORDER BY v DESC LIMIT 50"
    rows = _run_rows(i, db, sql); total = sum(float(r[1] or 0) for r in rows)
    return ok({"items": [{"name": str(r[0]), "value": float(r[1] or 0), "ratio": (float(r[1] or 0) / total if total else 0)} for r in rows], "total": total})
