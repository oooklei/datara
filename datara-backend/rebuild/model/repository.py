"""I18 数仓建模字典仓储（A6-1 建模字典三表查询）。

查询口径逐项照抄旧侧 `datara-backend/api/model.py:101-108`：
- `layers`  按 `seq` 升序，字段 `{code, name, rule, color, seq}`
- `domains` 按 `id` 升序，字段 `{name, remark}`
- `engines` 按 `name` 升序，字段 `{name, ddl, xc}`（`xc` 归一为 `bool`）
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from rebuild.model.models import (
    BizDomainRecord,
    DwLayerRecord,
    DwModelFieldRecord,
    DwModelRecord,
    DwModelRelationRecord,
    DwModelVersionRecord,
    EngineTypeRecord,
)


def fmt_dt(value: Optional[datetime]) -> Optional[str]:
    """datetime → 'YYYY-MM-DD HH:mm:ss'（本地时区写库，原样序列化）。

    迁移源实锚：`datara-backend/common/resp.py:113-118`。
    """
    if value is None:
        return None
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _xc_map(session: Session) -> dict[str, bool]:
    """引擎名 → 信创徽标（迁移源实锚 `api/model.py:57-58`）。"""
    return {row.name: bool(row.xc) for row in session.query(EngineTypeRecord).all()}


def _model_row(m: DwModelRecord, xcs: dict[str, bool]) -> dict[str, Any]:
    """模型列表行（迁移源实锚 `api/model.py:61-70`，逐字段照抄）。"""
    return {
        "id": m.id, "code": m.code, "name": m.name, "layer": m.layer, "type": m.type,
        "bizDomain": m.biz_domain or "", "engine": m.engine or "",
        "engineXc": xcs.get(m.engine or "", False),
        "dsId": m.ds_id, "dbName": m.db_name, "securityLevel": m.security_level or "内部",
        "status": m.status, "version": m.version, "owner": m.owner or "",
        "builtAt": fmt_dt(m.built_at), "updatedAt": fmt_dt(m.update_time),
        "remark": m.remark or "",
    }


def _field_row(f: DwModelFieldRecord) -> dict[str, Any]:
    """模型字段行（迁移源实锚 `api/model.py:72-79`，逐字段照抄）。"""
    return {
        "name": f.name, "dataType": f.data_type, "length": f.length or "",
        "precision": f.precision or "", "nullable": bool(f.nullable),
        "defaultValue": f.default_value or "", "comment": f.comment or "",
        "isPk": bool(f.is_pk), "isPartition": bool(f.is_partition), "dictRef": f.dict_ref or "",
    }


def _field_kwargs(f: dict[str, Any]) -> dict[str, Any]:
    """API 契约字段 dict → ORM 列 kwargs（与 `_field_row` 互逆；字段保存/逆向导入共用）。

    迁移源实锚：`datara-backend/api/model.py:267-283`（`_field_kwargs` 逐项照抄）。
    注意：`seq` 不入此映射（由保存方按提交顺序 `enumerate(..., 1)` 重排）。
    """
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


def _version_row(v: DwModelVersionRecord) -> dict[str, Any]:
    """版本列表行（迁移源实锚 `api/model.py:360-361`，逐字段照抄）。"""
    return {
        "id": v.id, "version": v.version, "changeNote": v.change_note,
        "createdBy": v.created_by, "createdAt": fmt_dt(v.create_time),
    }


class ModelDictRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def dicts(self) -> dict[str, list[dict[str, Any]]]:
        """分层/业务域/引擎字典一次取齐（列表与设计器共用）。"""
        layers = [
            {"code": row.code, "name": row.name, "rule": row.rule, "color": row.color, "seq": row.seq}
            for row in self._session.query(DwLayerRecord).order_by(DwLayerRecord.seq).all()
        ]
        domains = [
            {"name": row.name, "remark": row.remark}
            for row in self._session.query(BizDomainRecord).order_by(BizDomainRecord.id).all()
        ]
        engines = [
            {"name": row.name, "ddl": row.ddl, "xc": bool(row.xc)}
            for row in self._session.query(EngineTypeRecord).order_by(EngineTypeRecord.name).all()
        ]
        return {"layers": layers, "domains": domains, "engines": engines}


class ModelRepository:
    """I18 模型主表仓储（A6-2 列表 + 双维交叉统计）。

    查询口径逐项照抄旧侧 `datara-backend/api/model.py:114-155`：
    - `_base`：status 精确过滤；keyword 剥离后按 code/name/owner 三字段 LIKE
    - 主查询：叠 layer（精确）与 domain（精确），`update_time desc` 排序 + 分页
    - 双维统计：分层计数**叠 domain**、域计数**叠 layer**（交叉过滤，I18 §4.1）
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_code(self, code: str) -> Optional[DwModelRecord]:
        """按物理表名取模型（A6-3 唯一性校验；迁移源实锚 `api/model.py:79`）。"""
        return self._session.query(DwModelRecord).filter(DwModelRecord.code == code).first()

    def list_versions(self, model_id: int) -> list[DwModelVersionRecord]:
        """版本快照列表（A6-12；`version` 降序 + `id` 降序，迁移源实锚 `api/model.py:359`）。"""
        return (
            self._session.query(DwModelVersionRecord)
            .filter(DwModelVersionRecord.model_id == model_id)
            .order_by(DwModelVersionRecord.version.desc(), DwModelVersionRecord.id.desc())
            .all()
        )

    def find_version(self, model_id: int, version_id: int) -> Optional[DwModelVersionRecord]:
        """按 (model_id, id) 取版本快照（A6-14 diff / A6-15 回滚共用；实锚 `api/model.py:368-369`）。"""
        return (
            self._session.query(DwModelVersionRecord)
            .filter(
                DwModelVersionRecord.id == version_id,
                DwModelVersionRecord.model_id == model_id,
            )
            .first()
        )

    def _base(self, query, status: str, keyword: str):
        """status 精确 + keyword 三字段 LIKE（迁移源实锚 `api/model.py:122-129`）。"""
        if status:
            query = query.filter(DwModelRecord.status == status)
        if keyword:
            like = f"%{keyword}%"
            query = query.filter(or_(
                DwModelRecord.code.like(like),
                DwModelRecord.name.like(like),
                DwModelRecord.owner.like(like),
            ))
        return query

    def list_models(
        self,
        *,
        layer: str = "",
        status: str = "",
        domain: str = "",
        keyword: str = "",
        page: int = 1,
        size: int = 50,
    ) -> dict[str, Any]:
        kw = keyword.strip()

        query = self._base(self._session.query(DwModelRecord), status, kw)
        if layer:
            query = query.filter(DwModelRecord.layer == layer)
        if domain:
            query = query.filter(DwModelRecord.biz_domain == domain)
        total = query.count()
        rows = (
            query.order_by(DwModelRecord.update_time.desc())
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )
        xcs = _xc_map(self._session)

        layer_stats = []
        for row in self._session.query(DwLayerRecord).order_by(DwLayerRecord.seq).all():
            count_query = self._base(
                self._session.query(func.count(DwModelRecord.id)), status, kw
            ).filter(DwModelRecord.layer == row.code)
            if domain:
                count_query = count_query.filter(DwModelRecord.biz_domain == domain)
            layer_stats.append({"code": row.code, "count": count_query.scalar()})

        domain_stats = []
        for row in self._session.query(BizDomainRecord).order_by(BizDomainRecord.id).all():
            count_query = self._base(
                self._session.query(func.count(DwModelRecord.id)), status, kw
            ).filter(DwModelRecord.biz_domain == row.name)
            if layer:
                count_query = count_query.filter(DwModelRecord.layer == layer)
            domain_stats.append({"name": row.name, "count": count_query.scalar()})

        return {
            "list": [_model_row(m, xcs) for m in rows],
            "total": total,
            "layers": layer_stats,
            "domains": domain_stats,
        }


class ErRepository:
    """ER 图读写仓储（A6-4 读取 / A6-5 保存，迁移源实锚 `api/model.py:421-431`）。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def graph(self, *, layer: str = "", domain: str = "") -> dict[str, Any]:
        """ER 图 nodes + edges（照抄旧侧 `get_er`：双边均须在过滤后集合内）。"""
        query = self._session.query(DwModelRecord)
        if layer:
            query = query.filter(DwModelRecord.layer == layer)
        if domain:
            query = query.filter(DwModelRecord.biz_domain == domain)
        models = query.order_by(DwModelRecord.id).all()
        ids = {m.id for m in models}
        xcs = _xc_map(self._session)
        nodes = [
            {"id": str(m.id), "model": _model_row(m, xcs), "erPos": m.er_pos or {}}
            for m in models
        ]
        # 旧侧：ids 为空时不查关系（避免 `IN ()` 空集）
        rels = (
            self._session.query(DwModelRelationRecord)
            .filter(
                DwModelRelationRecord.src_model_id.in_(ids),
                DwModelRelationRecord.tgt_model_id.in_(ids),
            )
            .all()
            if ids
            else []
        )
        edges = [
            {
                "id": r.id,
                "source": str(r.src_model_id),
                "target": str(r.tgt_model_id),
                "relType": r.rel_type,
                "srcFields": r.src_fields,
                "tgtFields": r.tgt_fields,
                "joinDesc": r.join_desc,
            }
            for r in rels
        ]
        return {"nodes": nodes, "edges": edges}
