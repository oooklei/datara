"""I18 建模应用服务（A6-3 新建模型：编码正则 + 唯一 + 分层命名规范校验）。

迁移源实锚（逐项照抄，业务逻辑不重构）：
- `datara-backend/api/model.py:165-182`（`create_model` 路由体）
- `datara-backend/api/model.py:40`（`CODE_RE`）
- `datara-backend/api/model.py:76-85`（`_check_code`）
- 旧侧 `DwModel` 列默认值实锚 `common/models.py:782-808`

校验次序（旧侧原样，**注意 4002 先于 8003/8002/8004**）：
分层存在 → 引擎存在 → 编码正则 → 编码唯一 → 分层命名规范。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from rebuild.model.ddlgen import dialect_notes, gen_ddl
from rebuild.model.errors import (
    MODEL_CODE_DUP,
    MODEL_CODE_INVALID,
    MODEL_FIELDS_LOCKED,
    MODEL_NAMING_RULE,
    MODEL_NOT_FOUND,
    MODEL_IN_USE,
    MODEL_REV_CONFLICT,
    MODEL_STATE_CONFLICT,
    PARAM_INVALID,
    ModelDomainError,
)
from rebuild.model.models import (
    DwLayerRecord,
    DwModelFieldRecord,
    DwModelRecord,
    DwModelRelationRecord,
    DwModelVersionRecord,
    EngineTypeRecord,
)
from rebuild.model.repository import (
    ModelRepository,
    _field_kwargs,
    _field_row,
    _model_row,
    _version_row,
    _xc_map,
)

CODE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class ModelCreateInput:
    """A6-3 入参（旧侧 `ModelCreateBody` 六字段）。"""

    name: str
    code: str
    layer: str
    engine: str
    type: str = "明细表"
    biz_domain: str = ""


@dataclass(frozen=True)
class ModelUpdateInput:
    """A6-7 模型更新入参（旧侧 `ModelUpdateBody` 六**可选**字段，`None` = 不修改）。"""

    name: Optional[str] = None
    remark: Optional[str] = None
    owner: Optional[str] = None
    security_level: Optional[str] = None
    ds_id: Optional[int] = None
    db_name: Optional[str] = None


class ModelService:
    """建模主表写操作（本票仅 `create`；后续票按同形追加）。"""

    def __init__(self, session: Session, owner: str) -> None:
        self.session = session
        self.owner = owner
        self.repository = ModelRepository(session)

    def create(self, value: ModelCreateInput) -> DwModelRecord:
        code = value.code.strip()
        # ① 分层存在（旧侧 `db.get(DwLayer, body.layer)`，DwLayer 主键=code）
        layer = self.session.get(DwLayerRecord, value.layer)
        if layer is None:
            raise ModelDomainError(PARAM_INVALID, f"分层不存在: {value.layer}", status=400)
        # ② 引擎存在（旧侧 `db.get(EngineType, body.engine)`，EngineType 主键=name）
        if self.session.get(EngineTypeRecord, value.engine) is None:
            raise ModelDomainError(PARAM_INVALID, f"引擎不存在: {value.engine}", status=400)
        # ③ 编码正则 + 唯一 + 分层命名规范（`_check_code` 照抄）
        self._check_code(code, layer)
        record = DwModelRecord(
            code=code,
            name=value.name.strip(),
            layer=value.layer,
            type=value.type,
            biz_domain=value.biz_domain,
            engine=value.engine,
            status="draft",
            version=1,
            security_level="内部",
            owner=self.owner,
        )
        try:
            self.session.add(record)
            self.session.commit()
        except IntegrityError:
            # 并发插入撞 `t_dw_model.code` UNIQUE：归一为旧侧 8002/409。
            self.session.rollback()
            raise ModelDomainError(MODEL_CODE_DUP, status=409) from None
        self.session.refresh(record)
        return record

    def delete(self, model_id: int) -> bool:
        """模型删除（已物理化拒删 + 下游血缘引用防护 + 字段/关系级联）。

        迁移源实锚：`datara-backend/api/model.py:239-258`（`delete_model` 逐行照抄）。
        """
        record = self.session.get(DwModelRecord, model_id)
        if record is None:
            raise ModelDomainError(MODEL_NOT_FOUND, status=404)
        if record.status in ("built", "produced"):
            raise ModelDomainError(MODEL_STATE_CONFLICT, "已物理化模型不可删除", status=409)
        # 血缘引用防护：仅查**本模型为上游**（src）的边，下游模型存在则计入 refs
        refs = []
        for relation in (
            self.session.query(DwModelRelationRecord)
            .filter(DwModelRelationRecord.src_model_id == model_id)
            .all()
        ):
            target = self.session.get(DwModelRecord, relation.tgt_model_id)
            if target:
                refs.append({"id": target.id, "code": target.code, "name": target.name})
        if refs:
            raise ModelDomainError(MODEL_IN_USE, status=409, data={"refs": refs})
        self.session.query(DwModelFieldRecord).filter(
            DwModelFieldRecord.model_id == model_id
        ).delete()
        self.session.query(DwModelRelationRecord).filter(
            or_(
                DwModelRelationRecord.src_model_id == model_id,
                DwModelRelationRecord.tgt_model_id == model_id,
            )
        ).delete(synchronize_session=False)
        self.session.delete(record)
        self.session.commit()
        return True

    def update(self, model_id: int, change: "ModelUpdateInput") -> dict[str, Any]:
        """模型更新（六可选字段；已发布仅可改备注/负责人/密级/目标数据源）。

        迁移源实锚：`datara-backend/api/model.py:216-233`（`update_model` 逐行照抄）。
        """
        record = self.session.get(DwModelRecord, model_id)
        if record is None:
            raise ModelDomainError(MODEL_NOT_FOUND, status=404)
        # 旧侧次序：状态冲突判定**先于**任何字段写入；且仅当 name 被改为**不同**值才冲突
        if record.status != "draft" and change.name is not None and change.name != record.name:
            raise ModelDomainError(
                MODEL_STATE_CONFLICT, "已发布模型仅可修改备注/负责人/密级/目标数据源", status=409
            )
        if change.name is not None:
            record.name = change.name.strip()
        if change.remark is not None:
            record.remark = change.remark
        if change.owner is not None:
            record.owner = change.owner
        if change.security_level is not None:
            record.security_level = change.security_level
        if change.ds_id is not None:
            record.ds_id = change.ds_id
        if change.db_name is not None:
            record.db_name = change.db_name
        self.session.commit()
        return _model_row(record, _xc_map(self.session))

    def detail(self, model_id: int) -> dict[str, Any]:
        """模型详情 = ModelRow + `fields`（按 `seq` 升序）。

        迁移源实锚：`datara-backend/api/model.py:198-206`（`get_model`）+ `:72-79`（`_field_row`）。
        """
        record = self.session.get(DwModelRecord, model_id)
        if record is None:
            raise ModelDomainError(MODEL_NOT_FOUND, status=404)
        fields = (
            self.session.query(DwModelFieldRecord)
            .filter(DwModelFieldRecord.model_id == model_id)
            .order_by(DwModelFieldRecord.seq)
            .all()
        )
        row = _model_row(record, _xc_map(self.session))
        row["fields"] = [_field_row(f) for f in fields]
        return row

    def save_er(self, positions: dict, relations: dict) -> bool:
        """ER 图保存：positions 全量覆盖 + relations 增量 diff。

        迁移源实锚：`datara-backend/api/model.py:435-453`（`put_er` 逐行照抄）。
        """
        for raw_id, pos in positions.items():
            record = self.session.get(DwModelRecord, int(raw_id))
            if record is None:
                raise ModelDomainError(MODEL_NOT_FOUND, status=404)
            record.er_pos = {"x": float(pos.get("x", 0)), "y": float(pos.get("y", 0))}
        for raw in relations.get("removed", []):
            relation = self.session.get(
                DwModelRelationRecord, int(raw.get("id", raw) if isinstance(raw, dict) else raw)
            )
            if relation:
                self.session.delete(relation)
        for item in relations.get("added", []) + relations.get("updated", []):
            raw_id = item.get("id")
            relation = self.session.get(DwModelRelationRecord, int(raw_id)) if raw_id else None
            if relation is None:
                relation = DwModelRelationRecord(
                    src_model_id=int(item["source"]),
                    tgt_model_id=int(item["target"]),
                    created_by=self.owner,
                )
                self.session.add(relation)
            relation.rel_type = item.get("relType", relation.rel_type)
            relation.src_fields = item.get("srcFields", relation.src_fields)
            relation.tgt_fields = item.get("tgtFields", relation.tgt_fields)
            relation.join_desc = item.get("joinDesc", relation.join_desc)
        self.session.commit()
        return True

    def save_fields(self, model_id: int, rev: int, fields: list[dict]) -> int:
        """字段全量保存（乐观锁：`rev` 须等于当前 `version`，成功即递增；仅 draft 可保存）。

        迁移源实锚：`datara-backend/api/model.py:288-305`（`save_fields` 逐行照抄）。

        ① 模型不存在 → 8001/404
        ② `status != "draft"` → 8007/409（**先于**乐观锁判定，与旧侧同序）
        ③ 条件更新 `UPDATE ... WHERE version == rev`：rowcount 为 0 即 `rev` 已被他人推进，
           `refresh` 回读真实 `version` 后 → 8006/422 `data={"currentRev": ...}`
        ④ 成功后 `version = rev + 1`（ORM 对象的 version 已被 ③ 的批量 UPDATE 绕过，须显式置值），
           再按提交顺序**全量替换**字段（先删后插，`seq` 自 1 重排）
        """
        record = self.session.get(DwModelRecord, model_id)
        if record is None:
            raise ModelDomainError(MODEL_NOT_FOUND, status=404)
        if record.status != "draft":
            raise ModelDomainError(MODEL_FIELDS_LOCKED, status=409)
        rows = (
            self.session.query(DwModelRecord)
            .filter(DwModelRecord.id == model_id, DwModelRecord.version == rev)
            .update({"version": DwModelRecord.version + 1})
        )
        if rows == 0:
            self.session.refresh(record)
            raise ModelDomainError(MODEL_REV_CONFLICT, status=422, data={"currentRev": record.version})
        record.version = rev + 1
        self.session.query(DwModelFieldRecord).filter(
            DwModelFieldRecord.model_id == model_id
        ).delete()
        for seq, field in enumerate(fields, 1):
            self.session.add(DwModelFieldRecord(model_id=model_id, seq=seq, **_field_kwargs(field)))
        self.session.commit()
        return record.version

    def publish(self, model_id: int) -> dict[str, Any]:
        """模型发布（draft → published；直接发布无审批流，R5）。

        迁移源实锚：`datara-backend/api/model.py:311-321`（`publish_model` 逐行照抄）。
        非 draft 一律 8005/409「仅草稿可发布」（**不含** built/produced 的细分文案）。
        """
        record = self.session.get(DwModelRecord, model_id)
        if record is None:
            raise ModelDomainError(MODEL_NOT_FOUND, status=404)
        if record.status != "draft":
            raise ModelDomainError(MODEL_STATE_CONFLICT, "仅草稿可发布", status=409)
        record.status = "published"
        self.session.commit()
        return {"status": "published"}

    def redraft(self, model_id: int) -> dict[str, Any]:
        """模型回草稿（published/built/produced → draft，`version` 递增）。

        迁移源实锚：`datara-backend/api/model.py:342-352`（`redraft_model` 逐行照抄）。
        **注意状态闸方向与 `publish` 相反**：此处 `status == "draft"` 才冲突（8005/409「当前已是草稿」）。
        返回 `ModelRow`（非 `{status: ...}`），与 A6-10 出参形状不同。
        """
        record = self.session.get(DwModelRecord, model_id)
        if record is None:
            raise ModelDomainError(MODEL_NOT_FOUND, status=404)
        if record.status == "draft":
            raise ModelDomainError(MODEL_STATE_CONFLICT, "当前已是草稿", status=409)
        record.status = "draft"
        record.version += 1
        self.session.commit()
        return _model_row(record, _xc_map(self.session))

    def versions(self, model_id: int) -> list[dict[str, Any]]:
        """版本列表（`version` 降序 + `id` 降序；旧侧 `api/model.py:355-361`）。

        8001 判定对象是**模型**而非版本（旧侧先 `_get_model(db, model_id)`）：
        模型不存在 → 8001/404；模型存在但无快照 → 空列表（**不**是 404）。
        """
        record = self.session.get(DwModelRecord, model_id)
        if record is None:
            raise ModelDomainError(MODEL_NOT_FOUND, status=404)
        return [_version_row(v) for v in self.repository.list_versions(model_id)]

    def save_version(self, model_id: int, change_note: str, created_by: str) -> dict[str, Any]:
        """版本快照创建（主数据 + fields + relations 全量 JSON）。

        迁移源实锚：`datara-backend/api/model.py:362-374`（`save_model_version`）+
        `:325-335`（`_model_snapshot`）+ `:460-463`（`_fields_of`，按 `seq` 升序）。

        `snapshot_json` 用 `json.dumps(..., ensure_ascii=False)` **保中文原样**
        （旧侧同参数；若用默认 `ensure_ascii=True` 会写成 `\\uXXXX` 转义，A6-14 diff
        与 A6-15 回滚虽仍能解析，但快照文本与旧侧不再逐字一致）。
        """
        record = self.session.get(DwModelRecord, model_id)
        if record is None:
            raise ModelDomainError(MODEL_NOT_FOUND, status=404)
        snapshot = self._snapshot(record)
        row = DwModelVersionRecord(
            model_id=record.id,
            version=record.version,
            snapshot_json=json.dumps(snapshot, ensure_ascii=False),
            change_note=change_note.strip(),
            created_by=created_by,
        )
        self.session.add(row)
        self.session.commit()
        return {"id": row.id, "version": row.version, "changeNote": row.change_note}

    def _snapshot(self, record: DwModelRecord) -> dict[str, Any]:
        """版本快照载体：`{model: ModelRow, fields: [...], relations: [...]}`（全量）。

        迁移源实锚：`datara-backend/api/model.py:325-335`（`_model_snapshot` 逐行照抄）。
        关系取**双向**（`or_(src, tgt)`），与 A6-5 ER 保存的增量口径无关。
        """
        fields = [
            _field_row(f)
            for f in (
                self.session.query(DwModelFieldRecord)
                .filter(DwModelFieldRecord.model_id == record.id)
                .order_by(DwModelFieldRecord.seq)
                .all()
            )
        ]
        relations = [
            {
                "id": r.id, "srcModelId": r.src_model_id, "tgtModelId": r.tgt_model_id,
                "relType": r.rel_type, "srcFields": r.src_fields, "tgtFields": r.tgt_fields,
                "joinDesc": r.join_desc,
            }
            for r in (
                self.session.query(DwModelRelationRecord)
                .filter(or_(
                    DwModelRelationRecord.src_model_id == record.id,
                    DwModelRelationRecord.tgt_model_id == record.id,
                ))
                .all()
            )
        ]
        return {
            "model": _model_row(record, _xc_map(self.session)),
            "fields": fields,
            "relations": relations,
        }

    def diff_version(
        self, model_id: int, version_id: int, base: Optional[int] = None
    ) -> dict[str, Any]:
        """版本 diff（**仅比较 fields**；`base` 为可选基准版本 **id**）。

        迁移源实锚：`datara-backend/api/model.py:377-394`（`diff_model_version` 逐行照抄）。

        - 两次 8001 判定对象不同：模型缺失 → 内置 msg；版本行缺失 → 显式 msg「版本不存在」。
        - `base` 缺省或**指向不存在的版本 id** 时，基准静默取空快照
          （`{"fields": [], "model": {}, "relations": []}`），**不**报错（旧侧 `if base` + `.first()` 语义）。
        - `added`/`removed`/`changed` 以**字段名**为键做集合运算（旧侧 `dict.keys()` 差集/交集，
          顺序为 set 迭代序，非插入序 —— 照抄，不做排序「优化」）。
        - `relationsChanged` 为**全量关系列表**的相等性布尔（非关系列表 diff）。
        """
        record = self.session.get(DwModelRecord, model_id)
        if record is None:
            raise ModelDomainError(MODEL_NOT_FOUND, status=404)
        cur = self.repository.find_version(model_id, version_id)
        if cur is None:
            raise ModelDomainError(MODEL_NOT_FOUND, "版本不存在", status=404)
        prev = self.repository.find_version(model_id, base) if base else None
        a = json.loads(prev.snapshot_json) if prev else {"fields": [], "model": {}, "relations": []}
        b = json.loads(cur.snapshot_json)
        af = {x["name"]: x for x in a.get("fields", [])}
        bf = {x["name"]: x for x in b.get("fields", [])}
        added = [bf[k] for k in bf.keys() - af.keys()]
        removed = [af[k] for k in af.keys() - bf.keys()]
        changed = [
            {"name": k, "before": af[k], "after": bf[k]}
            for k in bf.keys() & af.keys()
            if af[k] != bf[k]
        ]
        return {
            "added": added,
            "removed": removed,
            "changed": changed,
            "relationsChanged": a.get("relations", []) != b.get("relations", []),
        }

    def rollback_version(self, model_id: int, version_id: int, created_by: str) -> dict[str, Any]:
        """版本回滚（字段还原 + 回 draft + version 递增 + 存新快照）。

        迁移源实锚：`datara-backend/api/model.py:396-415`（`rollback_model_version` 逐行照抄）。

        **不判状态闸**：旧侧无条件 `m.status = "draft"`，即便模型**已是 draft** 也照做
        （不报 8005）。回滚的幂等性由调用方（FE）保证，后端不拦 —— 照抄。

        返回 `sourceVersion` 取快照行的 **`version` 值**（非入参 `version_id`）。
        """
        record = self.session.get(DwModelRecord, model_id)
        if record is None:
            raise ModelDomainError(MODEL_NOT_FOUND, status=404)
        source = self.repository.find_version(model_id, version_id)
        if source is None:
            raise ModelDomainError(MODEL_NOT_FOUND, "版本不存在", status=404)
        snapshot = json.loads(source.snapshot_json)
        record.status = "draft"
        record.version += 1
        fields = snapshot.get("fields", [])
        self.session.query(DwModelFieldRecord).filter(
            DwModelFieldRecord.model_id == record.id
        ).delete()
        for seq, field in enumerate(fields, 1):
            self.session.add(
                DwModelFieldRecord(model_id=record.id, seq=seq, **_field_kwargs(field))
            )
        self.session.commit()
        saved = DwModelVersionRecord(
            model_id=record.id,
            version=record.version,
            snapshot_json=json.dumps(self._snapshot(record), ensure_ascii=False),
            change_note=f"rollback from {source.version}",
            created_by=created_by,
        )
        self.session.add(saved)
        self.session.commit()
        return {
            "status": "draft",
            "version": record.version,
            "sourceVersion": source.version,
        }

    def preview_ddl(self, model_id: int, engine: str = "") -> dict[str, Any]:
        """DDL 方言预览（**不落库**，供前端可编辑框；旧侧 `api/model.py:466-481`）。

        ① 模型不存在 → 8001/404（与 A6-12/14/15 同：判定对象是**模型**）
        ② `engine` 缺省（空串）→ 按模型 `engine` 查 `t_engine_type` 取 `ddl` 列，
           查不到或 `ddl` 为空则回退 `"mysql"`（旧侧 `row.ddl if row and row.ddl else "mysql"`）
        ③ `gen_ddl` 的 `ValueError`（非法标识符/类型/空字段/不支持引擎）→ 8003/400，
           **msg 用异常原文**（旧侧 `ApiError(MODEL_CODE_INVALID, str(exc), status=400)`）
        ④ `dialect_notes` 在 `try` **之外**调用：`engine` 非法时先被 ③ 拦下，不会到达
        ⑤ 出参 `{engine: ddl_id, ddl, notes}`；**不写任何表**（`last_ddl`/`status`/`version` 均不变）
        """
        record = self.session.get(DwModelRecord, model_id)
        if record is None:
            raise ModelDomainError(MODEL_NOT_FOUND, status=404)
        if not engine:
            row = self.session.get(EngineTypeRecord, record.engine) if record.engine else None
            ddl_id = row.ddl if row and row.ddl else "mysql"
        else:
            ddl_id = engine
        fields = [
            _field_row(f)
            for f in (
                self.session.query(DwModelFieldRecord)
                .filter(DwModelFieldRecord.model_id == model_id)
                .order_by(DwModelFieldRecord.seq)
                .all()
            )
        ]
        try:
            ddl = gen_ddl(record.code, record.name, fields, ddl_id)
        except ValueError as exc:  # ddlgen 约定：非法标识符/类型/空字段 → 400
            raise ModelDomainError(MODEL_CODE_INVALID, str(exc), status=400) from None
        return {"engine": ddl_id, "ddl": ddl, "notes": dialect_notes(fields, ddl_id)}

    def _check_code(self, code: str, layer: DwLayerRecord) -> None:
        """编码正则 + 唯一 + 分层命名规范（创建/逆向共用；迁移源实锚 `api/model.py:76-85`）。"""
        if not CODE_RE.match(code):
            raise ModelDomainError(MODEL_CODE_INVALID, status=400)
        if self.repository.find_by_code(code) is not None:
            raise ModelDomainError(MODEL_CODE_DUP, status=409)
        if layer.rule:
            prefix = layer.rule.split("，")[0].split("_")[0].strip()
            if prefix and not code.startswith(prefix + "_"):
                raise ModelDomainError(
                    MODEL_NAMING_RULE, f"编码需符合分层命名规范：{layer.rule}", status=400
                )
