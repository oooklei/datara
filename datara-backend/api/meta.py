"""I19 元数据目录扩展与标签 API。

目录先提供稳定的模型投影与扩展标注，连接型数据源内省沿用 datasource/meta_ops，
避免在本期复制连接器；标签与打标使用独立表作为唯一写入真源。
"""
import time
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.auth import ApiError, get_current_user, require_perm
from common.db import get_db
from common.dsconn import open_connection
from common.models import DataSource, DwModel, DwModelRelation, MetaTableExt, MetaTag, MetaTagging, User
from common.resp import ok

router = APIRouter(prefix="/meta", tags=["meta"])

_INTROSPECT_CACHE: dict[tuple[int, str], tuple[float, list[dict]]] = {}
_CACHE_TTL = 60.0


def _introspect_tables(db: Session, ds_id: int, db_name: str) -> list[dict]:
    key = (ds_id, db_name)
    cached = _INTROSPECT_CACHE.get(key)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    ds = db.get(DataSource, ds_id)
    if ds is None or ds.type not in ("mysql", "greatdb", "doris"):
        raise ApiError(4001, "仅支持连接型数据源内省", status=400)
    conn = None
    try:
        conn = open_connection(ds, db=db_name or ds.db_name or None)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT TABLE_NAME, TABLE_COMMENT, TABLE_ROWS FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME",
                (db_name or ds.db_name or "",),
            )
            rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001
        raise ApiError(4002, f"元数据内省失败: {exc}", status=400) from exc
    finally:
        if conn is not None:
            conn.close()
    out = [{"key": f"{ds_id}/{db_name or ds.db_name or ''}/{r[0]}", "type": "table", "id": ds_id,
            "code": r[0], "name": r[1] or r[0], "layer": _layer_of(r[0]), "domain": "",
            "status": "introspected", "rows": int(r[2] or 0)} for r in rows]
    _INTROSPECT_CACHE[key] = (time.monotonic() + _CACHE_TTL, out)
    return out


def _layer_of(code: str) -> str:
    lower = code.lower()
    for prefix, layer in (("ods_", "ODS"), ("dwd_", "DWD"), ("dws_", "DWS"), ("ads_", "ADS"), ("dim_", "DIM")):
        if lower.startswith(prefix):
            return layer
    return "未分层"


def _tag_row(row: MetaTag, count: int = 0) -> dict:
    return {"id": row.id, "name": row.name, "cat": row.cat, "color": row.color, "desc": row.desc, "cnt": count}


@router.get("/tags")
def list_tags(keyword: str = "", cat: str = "", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(MetaTag)
    if keyword.strip(): q = q.filter(MetaTag.name.like(f"%{keyword.strip()}%"))
    if cat: q = q.filter(MetaTag.cat == cat)
    rows = q.order_by(MetaTag.id.desc()).all()
    return ok([_tag_row(t, db.query(func.count(MetaTagging.id)).filter(MetaTagging.tag_id == t.id).scalar() or 0) for t in rows])


class TagBody(BaseModel):
    name: str
    cat: str = "用途"
    color: str = "#1677ff"
    desc: str = ""


@router.post("/tags")
def create_tag(body: TagBody, user: User = Depends(require_perm("meta:write")), db: Session = Depends(get_db)):
    if db.query(MetaTag).filter(MetaTag.name == body.name.strip()).first():
        raise ApiError(8002, "标签名称已存在", status=409)
    row = MetaTag(name=body.name.strip(), cat=body.cat, color=body.color, desc=body.desc)
    db.add(row); db.commit()
    return ok(_tag_row(row))


@router.put("/tags/{tag_id}")
def update_tag(tag_id: int, body: TagBody, user: User = Depends(require_perm("meta:write")), db: Session = Depends(get_db)):
    row = db.get(MetaTag, tag_id)
    if row is None: raise ApiError(4041, "标签不存在", status=404)
    row.name, row.cat, row.color, row.desc = body.name.strip(), body.cat, body.color, body.desc
    db.commit(); return ok(_tag_row(row))


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: int, user: User = Depends(require_perm("meta:write")), db: Session = Depends(get_db)):
    row = db.get(MetaTag, tag_id)
    if row is None: raise ApiError(4041, "标签不存在", status=404)
    db.query(MetaTagging).filter(MetaTagging.tag_id == tag_id).delete(synchronize_session=False)
    db.delete(row); db.commit(); return ok(True)


@router.get("/taggings")
def list_taggings(tag_id: Optional[int] = None, target_type: str = "", target_key: str = "",
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(MetaTagging)
    if tag_id: q = q.filter(MetaTagging.tag_id == tag_id)
    if target_type: q = q.filter(MetaTagging.target_type == target_type)
    if target_key: q = q.filter(MetaTagging.target_key == target_key)
    return ok([{"id": r.id, "tagId": r.tag_id, "targetType": r.target_type, "targetKey": r.target_key} for r in q.all()])


class TaggingBody(BaseModel):
    tagIds: list[int]
    targetType: str
    targetKey: str


@router.post("/taggings")
def set_taggings(body: TaggingBody, user: User = Depends(require_perm("meta:write")), db: Session = Depends(get_db)):
    if body.targetType not in ("table", "field", "model"): raise ApiError(4001, "targetType 不支持", status=400)
    if body.targetType == "model" and not body.targetKey.startswith("model/"): raise ApiError(4001, "模型 targetKey 无效", status=400)
    db.query(MetaTagging).filter(MetaTagging.target_type == body.targetType, MetaTagging.target_key == body.targetKey).delete(synchronize_session=False)
    for tid in sorted(set(body.tagIds)):
        if db.get(MetaTag, tid) is None: raise ApiError(4041, "标签不存在", status=404)
        db.add(MetaTagging(tag_id=tid, target_type=body.targetType, target_key=body.targetKey, created_by=user.user_name))
    db.commit(); return ok({"targetType": body.targetType, "targetKey": body.targetKey, "tagIds": sorted(set(body.tagIds))})


@router.get("/catalog/tables")
def catalog_tables(keyword: str = "", layer: str = "", domain: str = "", ds: Optional[int] = None,
                   db_name: str = Query("", alias="db"), page: int = Query(1, ge=1), size: int = Query(100, ge=1, le=500),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    remote = _introspect_tables(db, ds, db_name) if ds else []
    q = db.query(DwModel)
    if layer: q = q.filter(DwModel.layer == layer)
    if domain: q = q.filter(DwModel.biz_domain == domain)
    if keyword.strip(): q = q.filter(DwModel.code.like(f"%{keyword.strip()}%"))
    models = [{"key": f"model/{m.id}", "type": "model", "id": m.id, "code": m.code, "name": m.name,
               "layer": m.layer, "domain": m.biz_domain, "status": m.status, "modeled": True} for m in q.all()]
    model_codes = {m["code"] for m in models}
    for row in remote:
        row["modeled"] = row["code"] in model_codes
        ext = db.query(MetaTableExt).filter_by(ds_id=ds, db_name=db_name, table_name=row["code"]).first()
        if ext:
            row.update({"domain": ext.biz_domain, "securityLevel": ext.security_level, "owner": ext.owner, "remark": ext.remark})
    merged = remote + models
    if keyword.strip():
        kw = keyword.strip().lower(); merged = [r for r in merged if kw in str(r.get("code", "")).lower() or kw in str(r.get("name", "")).lower()]
    if layer: merged = [r for r in merged if r.get("layer") == layer]
    if domain: merged = [r for r in merged if r.get("domain") == domain]
    total = len(merged)
    return ok({"list": merged[(page - 1) * size: page * size], "total": total, "page": page, "size": size})


class ExtBody(BaseModel):
    bizDomain: str = ""
    securityLevel: str = "内部"
    owner: str = ""
    remark: str = ""


@router.put("/catalog/table/{key:path}/ext")
def put_ext(key: str, body: ExtBody, user: User = Depends(require_perm("meta:write")), db: Session = Depends(get_db)):
    parts = key.split("/", 2)
    if len(parts) != 3 or not parts[0].isdigit(): raise ApiError(4001, "仅支持 ds/db/table 标识", status=400)
    ds_id, db_name, table_name = int(parts[0]), parts[1], parts[2]
    row = db.query(MetaTableExt).filter_by(ds_id=ds_id, db_name=db_name, table_name=table_name).first()
    if row is None: row = MetaTableExt(ds_id=ds_id, db_name=db_name, table_name=table_name); db.add(row)
    row.biz_domain, row.security_level, row.owner, row.remark = body.bizDomain, body.securityLevel, body.owner, body.remark
    db.commit(); return ok({"key": key, "bizDomain": row.biz_domain, "securityLevel": row.security_level, "owner": row.owner, "remark": row.remark})


@router.get("/map")
def map_projection(view: str = "overview", layer: str = "", domain: str = "", limit: int = Query(200, ge=1, le=1000),
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(DwModel)
    if layer: q = q.filter(DwModel.layer == layer)
    if domain: q = q.filter(DwModel.biz_domain == domain)
    models = q.order_by(DwModel.id).limit(limit).all()
    ids = {m.id for m in models}
    nodes = [{"id": f"model/{m.id}", "type": "model", "label": m.name, "code": m.code,
              "layer": m.layer, "domain": m.biz_domain, "status": m.status} for m in models]
    rels = db.query(DwModelRelation).filter(DwModelRelation.src_model_id.in_(ids), DwModelRelation.tgt_model_id.in_(ids)).all() if ids else []
    edges = [{"source": f"model/{r.src_model_id}", "target": f"model/{r.tgt_model_id}", "kind": "declared", "relType": r.rel_type} for r in rels]
    return ok({"stats": {"dataSources": 0, "databases": 0, "tables": 0, "models": len(nodes), "tags": db.query(MetaTag).count()}, "nodes": nodes, "edges": edges, "view": view, "truncated": q.count() > limit})
