"""I18 数仓建模 API（P0 批）：模型 CRUD / 字典 / 字段 / 发布 / 物理化 / 逆向 / 血缘声明。

- 权限：写操作 require_perm("model:write")（admin/dev）；读操作登录即可
- 审计：get_logger("audit.model")，格式 model.{op} user=.. code=.. version=..（I18 §7）
- 错误码：8xxx 数仓建模段（common/resp.py）
"""

import re
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from api.auth import ApiError, get_current_user, require_perm
from common.db import get_db
from common.log import get_logger
from common.models import (
    BizDomain, DataSource, DwLayer, DwModel, DwModelField, DwModelRelation,
    EngineType, LineageEdge, User, now,
)
from common.resp import (
    DS_NOT_FOUND, MODEL_CODE_DUP, MODEL_CODE_INVALID, MODEL_IN_USE,
    MODEL_NAMING_RULE, MODEL_NOT_FOUND, MODEL_STATE_CONFLICT, PARAM_INVALID,
    fmt_dt, ok,
)

logger = get_logger("api.model")
audit = get_logger("audit.model")

router = APIRouter(tags=["model"])

CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


# ---------- 共用 ----------


def _get_model(db: Session, model_id: int) -> DwModel:
    m = db.get(DwModel, model_id)
    if m is None:
        raise ApiError(MODEL_NOT_FOUND, status=404)
    return m


def _xc_map(db: Session) -> dict:
    return {e.name: bool(e.xc) for e in db.query(EngineType).all()}


def _model_row(m: DwModel, xcs: dict) -> dict:
    return {
        "id": m.id, "code": m.code, "name": m.name, "layer": m.layer, "type": m.type,
        "bizDomain": m.biz_domain or "", "engine": m.engine or "",
        "engineXc": xcs.get(m.engine or "", False),
        "dsId": m.ds_id, "dbName": m.db_name, "securityLevel": m.security_level or "内部",
        "status": m.status, "version": m.version, "owner": m.owner or "",
        "builtAt": fmt_dt(m.built_at), "updatedAt": fmt_dt(m.update_time),
        "remark": m.remark or "",
    }


def _field_row(f: DwModelField) -> dict:
    return {
        "name": f.name, "dataType": f.data_type, "length": f.length or "",
        "precision": f.precision or "", "nullable": bool(f.nullable),
        "defaultValue": f.default_value or "", "comment": f.comment or "",
        "isPk": bool(f.is_pk), "isPartition": bool(f.is_partition), "dictRef": f.dict_ref or "",
    }


def _check_code(db: Session, code: str, layer: str) -> None:
    """编码正则 + 唯一 + 分层命名规范（创建/逆向共用）。"""
    if not CODE_RE.match(code):
        raise ApiError(MODEL_CODE_INVALID, status=400)
    if db.query(DwModel).filter(DwModel.code == code).first():
        raise ApiError(MODEL_CODE_DUP, status=409)
    l = db.get(DwLayer, layer)
    if l and l.rule:
        prefix = l.rule.split("，")[0].split("_")[0].strip()
        if prefix and not code.startswith(prefix + "_"):
            raise ApiError(MODEL_NAMING_RULE, f"编码需符合分层命名规范：{l.rule}", status=400)


# ---------- 字典 ----------


@router.get("/model-dicts")
def model_dicts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """分层/业务域/引擎字典一次取齐（列表与设计器共用）。"""
    return ok({
        "layers": [{"code": l.code, "name": l.name, "rule": l.rule, "color": l.color, "seq": l.seq}
                   for l in db.query(DwLayer).order_by(DwLayer.seq).all()],
        "domains": [{"name": d.name, "remark": d.remark}
                    for d in db.query(BizDomain).order_by(BizDomain.id).all()],
        "engines": [{"name": e.name, "ddl": e.ddl, "xc": bool(e.xc)}
                    for e in db.query(EngineType).order_by(EngineType.name).all()],
    })


# ---------- 模型 CRUD ----------


@router.get("/models")
def list_models(
    layer: str = "", status: str = "", domain: str = "", keyword: str = "",
    page: int = Query(default=1, ge=1), size: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    """列表 + 双维统计（交叉过滤，I18 §4.1）：分层计数叠 domain，域计数叠 layer。"""
    kw = keyword.strip()

    def _base(q):
        if status:
            q = q.filter(DwModel.status == status)
        if kw:
            like = f"%{kw}%"
            q = q.filter(or_(DwModel.code.like(like), DwModel.name.like(like), DwModel.owner.like(like)))
        return q

    q = _base(db.query(DwModel))
    if layer:
        q = q.filter(DwModel.layer == layer)
    if domain:
        q = q.filter(DwModel.biz_domain == domain)
    total = q.count()
    rows = q.order_by(DwModel.update_time.desc()).offset((page - 1) * size).limit(size).all()
    xcs = _xc_map(db)

    layer_stats = []
    for l in db.query(DwLayer).order_by(DwLayer.seq).all():
        c = _base(db.query(func.count(DwModel.id))).filter(DwModel.layer == l.code)
        if domain:
            c = c.filter(DwModel.biz_domain == domain)
        layer_stats.append({"code": l.code, "count": c.scalar()})

    domain_stats = []
    for d in db.query(BizDomain).order_by(BizDomain.id).all():
        c = _base(db.query(func.count(DwModel.id))).filter(DwModel.biz_domain == d.name)
        if layer:
            c = c.filter(DwModel.layer == layer)
        domain_stats.append({"name": d.name, "count": c.scalar()})

    return ok({"list": [_model_row(m, xcs) for m in rows], "total": total,
               "layers": layer_stats, "domains": domain_stats})


class ModelCreateBody(BaseModel):
    name: str
    code: str
    layer: str
    engine: str
    type: str = "明细表"
    bizDomain: str = ""


@router.post("/models")
def create_model(body: ModelCreateBody, user: User = Depends(require_perm("model:write")),
                 db: Session = Depends(get_db)):
    code = body.code.strip()
    if db.get(DwLayer, body.layer) is None:
        raise ApiError(PARAM_INVALID, f"分层不存在: {body.layer}", status=400)
    if db.get(EngineType, body.engine) is None:
        raise ApiError(PARAM_INVALID, f"引擎不存在: {body.engine}", status=400)
    _check_code(db, code, body.layer)
    m = DwModel(code=code, name=body.name.strip(), layer=body.layer, type=body.type,
                biz_domain=body.bizDomain, engine=body.engine, status="draft", version=1,
                security_level="内部", owner=user.user_name)
    db.add(m)
    db.commit()
    audit.info("model.create user=%s code=%s version=%s", user.user_name, m.code, m.version)
    return ok({"id": m.id})


@router.get("/models/{model_id}")
def get_model(model_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = _get_model(db, model_id)
    fields = (db.query(DwModelField).filter(DwModelField.model_id == model_id)
              .order_by(DwModelField.seq).all())
    d = _model_row(m, _xc_map(db))
    d["fields"] = [_field_row(f) for f in fields]
    return ok(d)


class ModelUpdateBody(BaseModel):
    name: Optional[str] = None
    remark: Optional[str] = None
    owner: Optional[str] = None
    securityLevel: Optional[str] = None
    dsId: Optional[int] = None
    dbName: Optional[str] = None


@router.put("/models/{model_id}")
def update_model(model_id: int, body: ModelUpdateBody,
                 user: User = Depends(require_perm("model:write")), db: Session = Depends(get_db)):
    m = _get_model(db, model_id)
    if m.status != "draft" and body.name is not None and body.name != m.name:
        raise ApiError(MODEL_STATE_CONFLICT, "已发布模型仅可修改备注/负责人/密级/目标数据源", status=409)
    if body.name is not None:
        m.name = body.name.strip()
    if body.remark is not None:
        m.remark = body.remark
    if body.owner is not None:
        m.owner = body.owner
    if body.securityLevel is not None:
        m.security_level = body.securityLevel
    if body.dsId is not None:
        m.ds_id = body.dsId
    if body.dbName is not None:
        m.db_name = body.dbName
    db.commit()
    audit.info("model.update user=%s code=%s version=%s", user.user_name, m.code, m.version)
    return ok(_model_row(m, _xc_map(db)))


@router.delete("/models/{model_id}")
def delete_model(model_id: int, user: User = Depends(require_perm("model:write")),
                 db: Session = Depends(get_db)):
    m = _get_model(db, model_id)
    if m.status in ("built", "produced"):
        raise ApiError(MODEL_STATE_CONFLICT, "已物理化模型不可删除", status=409)
    refs = []
    for r in db.query(DwModelRelation).filter(DwModelRelation.src_model_id == model_id).all():
        t = db.get(DwModel, r.tgt_model_id)
        if t:
            refs.append({"id": t.id, "code": t.code, "name": t.name})
    if refs:
        raise ApiError(MODEL_IN_USE, status=409, data={"refs": refs})
    db.query(DwModelField).filter(DwModelField.model_id == model_id).delete()
    db.query(DwModelRelation).filter(
        or_(DwModelRelation.src_model_id == model_id, DwModelRelation.tgt_model_id == model_id)
    ).delete(synchronize_session=False)
    db.delete(m)
    db.commit()
    audit.info("model.delete user=%s code=%s", user.user_name, m.code)
    return ok(True)
