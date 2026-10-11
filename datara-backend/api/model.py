"""I18 数仓建模 API（P0 批）：模型 CRUD / 字典 / 字段 / 发布 / 物理化 / 逆向 / 血缘声明。

- 权限：写操作 require_perm("model:write")（admin/dev）；读操作登录即可
- 审计：get_logger("audit.model")，格式 model.{op} user=.. code=.. version=..（I18 §7）
- 错误码：8xxx 数仓建模段（common/resp.py）
"""

import re
from typing import Optional

import sqlglot
from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from sqlglot import exp

from api.auth import ApiError, get_current_user, require_perm
from common.db import get_db
from common.ddlgen import dialect_notes, gen_ddl
from common.dsconn import open_connection
from common.log import get_logger
from common.models import (
    BizDomain, DataSource, DwLayer, DwModel, DwModelField, DwModelRelation,
    EngineType, LineageEdge, User, now,
)
from common.resp import (
    DS_NOT_FOUND, MODEL_CODE_DUP, MODEL_CODE_INVALID, MODEL_DDL_INVALID, MODEL_FIELDS_LOCKED,
    MODEL_IN_USE, MODEL_NAMING_RULE, MODEL_NOT_FOUND, MODEL_PHYS_FAIL, MODEL_REV_CONFLICT,
    MODEL_STATE_CONFLICT, PARAM_INVALID,
    fmt_dt, ok,
)
from common.sqlparser import parse_create_tables

logger = get_logger("api.model")
audit = get_logger("audit.model")

router = APIRouter(tags=["model"])

CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# 逆向导入 engine 映射：ds.type → EngineType 主键（_conn_ds 已限定仅这两种类型）
_REV_ENGINE_MAP = {"mysql": "MySQL", "greatdb": "GreatDB"}


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


# ---------- 字段与发布 ----------


def _field_kwargs(f: dict) -> dict:
    """API 契约字段 dict → ORM 列 kwargs（字段保存/逆向导入共用）。"""
    return {
        "name": str(f.get("name") or "").strip(),
        "data_type": str(f.get("dataType") or "VARCHAR").upper(),
        "length": str(f.get("length") or ""),
        "precision": str(f.get("precision") or ""),
        "nullable": bool(f.get("nullable", True)),
        "default_value": str(f.get("defaultValue") or ""),
        "comment": str(f.get("comment") or ""),
        "is_pk": bool(f.get("isPk", False)),
        "is_partition": bool(f.get("isPartition", False)),
        "dict_ref": str(f.get("dictRef") or ""),
    }


class FieldsBody(BaseModel):
    rev: int
    fields: list[dict] = []


@router.put("/models/{model_id}/fields")
def save_fields(model_id: int, body: FieldsBody,
                user: User = Depends(require_perm("model:write")), db: Session = Depends(get_db)):
    """字段全量保存（乐观锁：rev 须等于当前 version，成功即递增；仅 draft 可保存）。"""
    m = _get_model(db, model_id)
    if m.status != "draft":
        raise ApiError(MODEL_FIELDS_LOCKED, status=409)
    rows = (db.query(DwModel)
            .filter(DwModel.id == model_id, DwModel.version == body.rev)
            .update({"version": DwModel.version + 1}))
    if rows == 0:
        db.refresh(m)
        raise ApiError(MODEL_REV_CONFLICT, status=422, data={"currentRev": m.version})
    m.version = body.rev + 1
    db.query(DwModelField).filter(DwModelField.model_id == model_id).delete()
    for i, f in enumerate(body.fields, 1):
        db.add(DwModelField(model_id=model_id, seq=i, **_field_kwargs(f)))
    db.commit()
    audit.info("model.fields user=%s code=%s version=%s n=%d", user.user_name, m.code, m.version, len(body.fields))
    return ok({"rev": m.version})


@router.post("/models/{model_id}/publish")
def publish_model(model_id: int, user: User = Depends(require_perm("model:write")),
                  db: Session = Depends(get_db)):
    """draft→published（直接发布 + 审计留痕，R5 无审批流）。"""
    m = _get_model(db, model_id)
    if m.status != "draft":
        raise ApiError(MODEL_STATE_CONFLICT, "仅草稿可发布", status=409)
    m.status = "published"
    db.commit()
    audit.info("model.publish user=%s code=%s version=%s", user.user_name, m.code, m.version)
    return ok({"status": "published"})


# ---------- DDL 与物理化 ----------


def _fields_of(db: Session, model_id: int) -> list[dict]:
    fs = (db.query(DwModelField).filter(DwModelField.model_id == model_id)
          .order_by(DwModelField.seq).all())
    return [_field_row(f) for f in fs]


@router.get("/models/{model_id}/ddl")
def preview_ddl(model_id: int, engine: str = "",
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """方言预览（不落库，供前端可编辑框）。engine 为方言标识，缺省按模型引擎映射。"""
    m = _get_model(db, model_id)
    if not engine:
        row = db.get(EngineType, m.engine) if m.engine else None
        ddl_id = row.ddl if row and row.ddl else "mysql"
    else:
        ddl_id = engine
    fields = _fields_of(db, model_id)
    try:
        ddl = gen_ddl(m.code, m.name, fields, ddl_id)
    except ValueError as exc:  # ddlgen 约定：非法标识符/类型/空字段 → 400
        raise ApiError(MODEL_CODE_INVALID, str(exc), status=400)
    return ok({"engine": ddl_id, "ddl": ddl, "notes": dialect_notes(fields, ddl_id)})


class PhysicalizeBody(BaseModel):
    engine: str
    dsId: Optional[int] = None
    dbName: Optional[str] = None
    mode: str = "script"  # exec | script
    ddl: Optional[str] = None


@router.post("/models/{model_id}/physicalize")
def physicalize(model_id: int, body: PhysicalizeBody,
                user: User = Depends(require_perm("model:write")), db: Session = Depends(get_db)):
    """物理化（R3 复用 dsconn 连接；60s 读超时对齐 meta_ops）。

    - script：仅返回校验后脚本文本，状态不变
    - exec：真实连接执行（sqlglot 拆语句防注释内分号误拆，白名单仅放行
      CREATE——排除法会漏 Command 兜底节点如 GRANT），成功→built，
      失败→状态不变并附已执行条数（I18 §8）
    """
    m = _get_model(db, model_id)
    if body.mode not in ("exec", "script"):
        raise ApiError(PARAM_INVALID, "mode 仅支持 exec/script", status=400)
    fields = _fields_of(db, model_id)
    if body.engine not in ("mysql", "greatdb", "doris"):
        raise ApiError(PARAM_INVALID, f"不支持的引擎方言: {body.engine}", status=400)
    try:
        sql = body.ddl or gen_ddl(m.code, m.name, fields, body.engine)
    except ValueError as exc:  # ddlgen 约定：非法标识符/类型/空字段 → 400
        raise ApiError(MODEL_CODE_INVALID, str(exc), status=400)
    if body.mode == "script":
        return ok({"script": sql, "notes": dialect_notes(fields, body.engine)})

    ds = db.get(DataSource, body.dsId) if body.dsId else None
    if ds is None or ds.type not in ("mysql", "greatdb"):
        raise ApiError(DS_NOT_FOUND, "物理化需选择 mysql/greatdb 连接型数据源", status=400)
    try:
        stmts = [s for s in (sqlglot.parse(sql, read="mysql") or []) if s is not None]
    except sqlglot.errors.ParseError as exc:  # 畸形 DDL 一并 400 而非 500
        raise ApiError(MODEL_PHYS_FAIL, f"DDL 解析失败: {exc}", status=400)
    bad = next((s for s in stmts if not isinstance(s, exp.Create)), None)
    if bad is not None or not stmts:  # 白名单仅 CREATE；空语句列表同样拒绝
        raise ApiError(MODEL_PHYS_FAIL, "物理化仅允许 CREATE TABLE 语句", status=400)
    executed = 0
    try:
        conn = open_connection(ds, db=body.dbName or None)
        try:
            with conn.cursor() as cur:
                for s in stmts:
                    cur.execute(s.sql(dialect="mysql"))
                    executed += 1
                conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 执行失败：状态不变 + 审计 + 已执行条数
        audit.error("model.physicalize user=%s code=%s FAIL executed=%d err=%s",
                    user.user_name, m.code, executed, exc)
        raise ApiError(MODEL_PHYS_FAIL, f"DDL 执行失败（已执行 {executed} 条）：{exc}",
                       status=400, data={"executed": executed, "error": str(exc)})
    m.status = "built"
    m.last_ddl = sql
    m.built_at = now()
    m.built_by = user.user_name
    db.commit()
    audit.info("model.physicalize user=%s code=%s version=%s", user.user_name, m.code, m.version)
    return ok({"status": "built", "executed": executed})


# ---------- 逆向工程 ----------


def _conn_ds(db: Session, ds_id: int) -> DataSource:
    ds = db.get(DataSource, ds_id)
    if ds is None:
        raise ApiError(DS_NOT_FOUND, status=400)
    if ds.type not in ("mysql", "greatdb"):
        raise ApiError(PARAM_INVALID, "逆向导入仅支持连接型数据源（mysql/greatdb）", status=400)
    return ds


def _col_to_field(c: tuple) -> dict:
    """information_schema.COLUMNS 行（10 列）→ API 契约字段 dict。"""
    (name, data_type, _column_type, is_nullable, default, cmt, key, char_len, num_p, num_s) = c
    dtype = str(data_type or "varchar").upper()
    length, precision = "", ""
    if dtype in ("VARCHAR", "CHAR"):
        length = str(char_len or "")
    elif dtype in ("DECIMAL", "NUMERIC"):
        length = str(num_p or "")
        precision = str(num_s or "")
    return {
        "name": name, "dataType": dtype, "length": length, "precision": precision,
        "nullable": is_nullable == "YES",
        "defaultValue": str(default) if default is not None else "",
        "comment": cmt or "", "isPk": key == "PRI", "isPartition": False, "dictRef": "",
    }


def _reverse_create(db: Session, code: str, layer: str, name: str, domain: str,
                    engine: str, owner: str, fields: list[dict], remark: str = "") -> int:
    """逆向建草稿模型 + 字段（调用方已做 code 查重/规范校验）。"""
    m = DwModel(code=code, name=name or code, layer=layer, type="明细表",
                biz_domain=domain, engine=engine, status="draft", version=1,
                security_level="内部", owner=owner, remark=remark)
    db.add(m)
    db.flush()
    for i, f in enumerate(fields, 1):
        db.add(DwModelField(model_id=m.id, seq=i, **_field_kwargs(f)))
    return m.id


class ReverseScanBody(BaseModel):
    dsId: int
    dbName: Optional[str] = None


@router.post("/models/reverse/scan")
def reverse_scan(body: ReverseScanBody, user: User = Depends(require_perm("model:write")),
                 db: Session = Depends(get_db)):
    """内省表清单（表名/注释/行数估算/列数）。"""
    ds = _conn_ds(db, body.dsId)
    target_db = body.dbName or ds.db_name or ""
    conn = open_connection(ds)
    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT TABLE_NAME, TABLE_COMMENT, TABLE_ROWS FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE' ORDER BY TABLE_NAME",
                (target_db,),
            )
            rows = cur.fetchall()
            cur.execute(
                "SELECT TABLE_NAME, COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s GROUP BY TABLE_NAME",
                (target_db,),
            )
            col_counts = {r[0]: int(r[1] or 0) for r in cur.fetchall()}
        finally:
            cur.close()
    finally:
        conn.close()
    tables = [{"tb": r[0], "comment": r[1] or "", "rows": int(r[2] or 0),
               "cols": col_counts.get(r[0], 0)} for r in rows]
    return ok({"db": target_db, "tables": tables})


class ReverseImportTable(BaseModel):
    tb: str
    layer: str = "ODS"
    bizDomain: str = ""
    name: Optional[str] = None


class ReverseImportBody(BaseModel):
    dsId: int
    dbName: Optional[str] = None
    tables: list[ReverseImportTable]


@router.post("/models/reverse/import")
def reverse_import(body: ReverseImportBody, user: User = Depends(require_perm("model:write")),
                   db: Session = Depends(get_db)):
    """逐表建草稿（字段内省直转；已存在/校验不过计入 skipped，成功者落库）。"""
    ds = _conn_ds(db, body.dsId)
    target_db = body.dbName or ds.db_name or ""
    imported, skipped = 0, []
    conn = open_connection(ds)
    try:
        for t in body.tables:
            code = t.tb.strip()
            if db.query(DwModel).filter(DwModel.code == code).first():
                skipped.append({"tb": code, "reason": "同名模型已存在"})
                continue
            try:
                _check_code(db, code, t.layer)
            except ApiError as e:
                skipped.append({"tb": code, "reason": e.msg or "校验未通过"})
                continue
            cur = conn.cursor()
            try:
                cur.execute(
                    "SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, "
                    "COLUMN_COMMENT, COLUMN_KEY, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE "
                    "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
                    "ORDER BY ORDINAL_POSITION",
                    (target_db, code),
                )
                cols = cur.fetchall()
            finally:
                cur.close()
            if not cols:  # 目标表不存在/无列信息 → 跳过，不建 0 字段草稿模型
                skipped.append({"tb": code, "reason": "未找到列（表不存在？）"})
                continue
            _reverse_create(db, code, t.layer, t.name or "", t.bizDomain,
                            _REV_ENGINE_MAP[ds.type], user.user_name,
                            [_col_to_field(c) for c in cols])
            imported += 1
    finally:
        conn.close()
    db.commit()
    audit.info("model.reverse_import user=%s imported=%d skipped=%d", user.user_name, imported, len(skipped))
    return ok({"imported": imported, "skipped": skipped})


@router.post("/models/reverse/import-ddl")
async def reverse_import_ddl(file: UploadFile = File(...),
                             user: User = Depends(require_perm("model:write")),
                             db: Session = Depends(get_db)):
    """DDL 文件导入（.sql，≤5MB）：sqlglot 解析 CREATE TABLE → ODS 草稿。"""
    limit = 5 * 1024 * 1024
    if file.size is not None and file.size > limit:  # size 已知时快速拒绝（size 可能为 None）
        raise ApiError(PARAM_INVALID, "DDL 文件超过 5MB 上限", status=400)
    chunks: list[bytes] = []
    total = 0
    while True:  # 分块读取兜底：超限立即中断，避免超大文件整体进内存
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise ApiError(PARAM_INVALID, "DDL 文件超过 5MB 上限", status=400)
        chunks.append(chunk)
    raw = b"".join(chunks)
    try:
        sql = raw.decode("utf-8")
    except UnicodeDecodeError:
        sql = raw.decode("gbk", errors="replace")
    try:
        parsed = parse_create_tables(sql)
    except Exception as exc:  # noqa: BLE001 sqlglot ParseError → 400 附行号
        line = getattr(exc, "line", None)
        raise ApiError(MODEL_DDL_INVALID, f"DDL 解析失败：{exc}" + (f"（第 {line} 行）" if line else ""),
                       status=400)  # noqa: B904
    imported, skipped = 0, []
    for t in parsed:
        code = (t["name"] or "").strip()
        if not code:
            continue
        if db.query(DwModel).filter(DwModel.code == code).first():
            skipped.append({"tb": code, "reason": "同名模型已存在"})
            continue
        try:
            _check_code(db, code, "ODS")
        except ApiError as e:
            skipped.append({"tb": code, "reason": e.msg or "校验未通过"})
            continue
        _reverse_create(db, code, "ODS", "", "", "MySQL", user.user_name,
                        t["fields"], remark=t["comment"] or "DDL 导入")
        imported += 1
    db.commit()
    audit.info("model.reverse_import user=%s ddl imported=%d skipped=%d",
               user.user_name, imported, len(skipped))
    return ok({"imported": imported, "skipped": skipped})
