"""I18 建模应用服务（A6-3 新建模型：编码正则 + 唯一 + 分层命名规范校验）。

迁移源实锚（逐项照抄，业务逻辑不重构）：
- `datara-backend/api/model.py:165-182`（`create_model` 路由体）
- `datara-backend/api/model.py:40`（`CODE_RE`）
- `datara-backend/api/model.py:76-85`（`_check_code`）
- 旧侧 `DwModel` 列默认值实锚 `common/models.py:782-808`

校验次序（旧侧原样，**注意 4002 先于 8003/8002/8004**）：
分层存在 → 引擎存在 → 编码正则 → 编码唯一 → 分层命名规范。

**A6-17 物理化**（`physicalize`，实锚 `api/model.py:503-546`）：script 分支纯出文本不落库；
exec 分支白名单仅 `CREATE`（`sqlglot` 拆语句防注释内分号误拆）+ 逐条执行 + 失败附已执行条数。
exec 的连接面由随票下沉的 `rebuild/model/dsconn.py` 提供（pymysql 原生短连接，不进池），
并经 `connector` 注入缝使契约测试可用 fake 连接（不触真实网络）。

**A6-18 逆向扫描库表**（`reverse_scan`，实锚 `api/model.py:598-626`）：information_schema
内省表清单（表名/注释/行数估算/列数）；`rows` 为估算值。

**A6-19 逆向导入建模**（`reverse_import`，实锚 `api/model.py:642-684`）：逐表建草稿；
已存在/校验不过计入 `skipped`，成功者落库。随票下沉两个纯助手 `_col_to_field`
（`:562-577`，COLUMNS 行 → 契约字段 dict）与 `_reverse_create`（`:580-590`，建草稿 + 字段），
二者均为纯函数/无外部依赖，可差分锁定。

**A6-20 DDL 文件导入**（`reverse_import_ddl`，实锚 `api/model.py:687-735`）：`.sql` ≤5MB
→ `parse_create_tables`（随票下沉 `rebuild/model/ddlparser.py`，纯函数可差分）→ ODS 草稿；
解码兜底 `decode_ddl`（utf-8 → gbk）与 5MB 上限在 API 层（旧侧同在路由内）。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

import sqlglot
from sqlglot import exp
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from rebuild.model.ddlgen import dialect_notes, gen_ddl
from rebuild.model.ddlparser import parse_create_tables
from rebuild.model.dsconn import open_connection
from rebuild.model.errors import (
    DS_NOT_FOUND,
    MODEL_CODE_DUP,
    MODEL_CODE_INVALID,
    MODEL_DDL_INVALID,
    MODEL_FIELDS_LOCKED,
    MODEL_NAMING_RULE,
    MODEL_NOT_FOUND,
    MODEL_IN_USE,
    MODEL_PHYS_FAIL,
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
    DataSourceRecord,
    EngineTypeRecord,
    LineageEdgeRecord,
    _now,
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

# 审计留痕（旧侧 `api/model.py:38` `audit = get_logger("audit.model")`）。
# rebuild 无 `common/log.py`，按域内既有口径用 stdlib `logging`（同 `rebuild/model/dicts.py:19`
# 的 `logging.getLogger("rebuild.model")`）；命名挂 `rebuild.model` 之下，与旧侧
# `audit.model` 的「建模域审计」语义一一对应。**仅落日志，无 DB 审计表**
# （旧侧同：`common/audit.py` 不存在，`audit` 只是 logger）。
audit = logging.getLogger("rebuild.model.audit")

# 逆向导入 engine 映射：ds.type → EngineType 主键（`_require_conn_ds` 已限定仅这两种类型）。
# 迁移源实锚 `datara-backend/api/model.py:44`（`_REV_ENGINE_MAP`）。
# 注意：此映射**不查 EngineType 表**——旧侧逆向路径即直写字面量（见 `_reverse_create` 注记）。
_REV_ENGINE_MAP = {"mysql": "MySQL", "greatdb": "GreatDB"}


def _col_to_field(c: tuple) -> dict:
    """information_schema.COLUMNS 行（10 列）→ API 契约字段 dict。

    迁移源实锚 `datara-backend/api/model.py:562-577`（`_col_to_field` 逐项照抄）。
    入参序：`name, data_type, column_type, is_nullable, default, comment, key,
    char_len, num_p, num_s`；**`column_type` 解包后不使用**（`_column_type`），
    与旧侧同（仅 `DATA_TYPE` 决定类型族）。
    """
    (name, data_type, _column_type, is_nullable, default, cmt, key,
     char_len, num_p, num_s) = c
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


def decode_ddl(raw: bytes) -> str:
    """DDL 字节流解码：`utf-8` 优先，失败退 `gbk(errors="replace")`。

    迁移源实锚 `datara-backend/api/model.py:706-709`（逐行照抄）。
    纯函数（无 IO）→ 契约测试可直接断言编码兜底行为。
    """
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("gbk", errors="replace")


def _reverse_create(session: Session, code: str, layer: str, name: str, domain: str,
                    engine: str, owner: str, fields: list[dict], remark: str = "") -> int:
    """逆向建草稿模型 + 字段（调用方已做 code 查重/规范校验）。

    迁移源实锚 `datara-backend/api/model.py:580-590`（`_reverse_create` 逐行照抄）。
    三处「照抄而非优化」的刻意为之：
    ① **不做**分层/引擎存在闸——旧侧 `create_model`（`:171-174`）有此二闸，但逆向路径
       刻意没有；`engine` 直接取 `_REV_ENGINE_MAP[ds.type]` 字面量（`"MySQL"`/`"GreatDB"`），
       不校验该名字是否存在于 `t_engine_type`。
    ② `flush()` 而非 `commit()`：整批循环结束由调用方统一提交（旧侧 `:682`）。
    ③ `name=name or code`：空名回落为编码（旧侧同）。
    """
    m = DwModelRecord(
        code=code, name=name or code, layer=layer, type="明细表",
        biz_domain=domain, engine=engine, status="draft", version=1,
        security_level="内部", owner=owner, remark=remark,
    )
    session.add(m)
    session.flush()
    for i, f in enumerate(fields, 1):
        session.add(DwModelFieldRecord(model_id=m.id, seq=i, **_field_kwargs(f)))
    return m.id


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


@dataclass(frozen=True)
class ReverseImportTable:
    """A6-19 逆向导入单表入参（旧侧 `ReverseImportTable` 照抄，`:629-633`）。

    `tb` 为必填；`layer` 缺省 `"ODS"`；`name` 缺省 `None`（服务侧 `t.name or ""`）。
    """

    tb: str
    layer: str = "ODS"
    biz_domain: str = ""
    name: Optional[str] = None


class ModelService:
    """建模主表写操作（本票仅 `create`；后续票按同形追加）。"""

    def __init__(
        self,
        session: Session,
        owner: str,
        *,
        connector: Optional[Callable[..., Any]] = None,
    ) -> None:
        """`connector` = 物理化 exec 分支的连接工厂（A6-17 注入缝）。

        缺省 `rebuild.model.dsconn.open_connection`（照抄旧侧 `common/dsconn.py:38-62`）；
        契约测试注入 fake 连接，**避免测试触真实网络**（域规范：本机只做代码/静态/类型/
        逻辑稽核，真库联调归 192.168.1.9）。
        """
        self.session = session
        self.owner = owner
        self.repository = ModelRepository(session)
        self._connector = connector or open_connection

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

    def physicalize(
        self,
        model_id: int,
        engine: str,
        ds_id: Optional[int] = None,
        db_name: Optional[str] = None,
        mode: str = "script",
        ddl: Optional[str] = None,
    ) -> dict[str, Any]:
        """物理化（script/exec 双模式；旧侧 `api/model.py:503-546` 逐行照抄）。

        ① 模型不存在 → 8001/404（**先于** mode 闸，与旧侧同序）
        ② `mode` 闸：非 `exec`/`script` → 4002/400「mode 仅支持 exec/script」
        ③ 引擎白名单闸：非 `mysql`/`greatdb`/`doris` → 4002/400「不支持的引擎方言: …」
           （**注意 doris 可生成脚本但不可 exec** —— exec 分支的数据源类型闸在 ⑤）
        ④ `ddl` 入参缺省则由 `gen_ddl` 生成；`ValueError` → 8003/400，msg 用异常原文
        ⑤ **script 分支到此直接返回** `{script, notes}`，**不落库、不改状态**
        ⑥ exec：数据源行缺失或 `type` 非 mysql/greatdb → 4001/400
        ⑦ exec：`sqlglot.parse(sql, read="mysql")` 拆语句（**防注释内分号误拆**）；
           解析异常 → 8009/400「DDL 解析失败: …」
        ⑧ exec：白名单**仅放行 `exp.Create`**（排除法会漏 `Command` 兜底节点如 `GRANT`）；
           含非 CREATE 或语句列表为空 → 8009/400「物理化仅允许 CREATE TABLE 语句」
        ⑨ exec：逐条执行 + `conn.commit()`；失败 → 8009/400，
           `data={"executed": N, "error": str(exc)}`，**状态不变**（I18 §8）
        ⑩ exec 成功：`status="built"` + `last_ddl` + `built_at` + `built_by`，审计留痕，
           返回 `{status: "built", executed: N}`

        **不判状态闸**：旧侧对 `draft`/`published`/`built`/`produced` 一律放行物理化，
        回草稿由 A6-15 负责 —— 照抄，不额外加闸。
        """
        record = self.session.get(DwModelRecord, model_id)
        if record is None:
            raise ModelDomainError(MODEL_NOT_FOUND, status=404)
        if mode not in ("exec", "script"):
            raise ModelDomainError(PARAM_INVALID, "mode 仅支持 exec/script", status=400)
        fields = [
            _field_row(f)
            for f in (
                self.session.query(DwModelFieldRecord)
                .filter(DwModelFieldRecord.model_id == model_id)
                .order_by(DwModelFieldRecord.seq)
                .all()
            )
        ]
        if engine not in ("mysql", "greatdb", "doris"):
            raise ModelDomainError(PARAM_INVALID, f"不支持的引擎方言: {engine}", status=400)
        try:
            sql = ddl or gen_ddl(record.code, record.name, fields, engine)
        except ValueError as exc:  # ddlgen 约定：非法标识符/类型/空字段 → 400
            raise ModelDomainError(MODEL_CODE_INVALID, str(exc), status=400) from None
        if mode == "script":
            return {"script": sql, "notes": dialect_notes(fields, engine)}

        ds = self.session.get(DataSourceRecord, ds_id) if ds_id else None
        if ds is None or ds.type not in ("mysql", "greatdb"):
            raise ModelDomainError(
                DS_NOT_FOUND, "物理化需选择 mysql/greatdb 连接型数据源", status=400
            )
        try:
            stmts = [s for s in (sqlglot.parse(sql, read="mysql") or []) if s is not None]
        except sqlglot.errors.ParseError as exc:  # 畸形 DDL 一并 400 而非 500
            raise ModelDomainError(MODEL_PHYS_FAIL, f"DDL 解析失败: {exc}", status=400) from None
        bad = next((s for s in stmts if not isinstance(s, exp.Create)), None)
        if bad is not None or not stmts:  # 白名单仅 CREATE；空语句列表同样拒绝
            raise ModelDomainError(
                MODEL_PHYS_FAIL, "物理化仅允许 CREATE TABLE 语句", status=400
            )
        executed = 0
        try:
            conn = self._connector(ds, db=db_name or None)
            try:
                with conn.cursor() as cur:
                    for s in stmts:
                        cur.execute(s.sql(dialect="mysql"))
                        executed += 1
                    conn.commit()
            finally:
                conn.close()
        except Exception as exc:  # noqa: BLE001 执行失败：状态不变 + 审计 + 已执行条数
            audit.error(
                "model.physicalize user=%s code=%s FAIL executed=%d err=%s",
                self.owner, record.code, executed, exc,
            )
            raise ModelDomainError(
                MODEL_PHYS_FAIL,
                f"DDL 执行失败（已执行 {executed} 条）：{exc}",
                status=400,
                data={"executed": executed, "error": str(exc)},
            ) from None
        record.status = "built"
        record.last_ddl = sql
        record.built_at = _now()
        record.built_by = self.owner
        self.session.commit()
        audit.info(
            "model.physicalize user=%s code=%s version=%s", self.owner, record.code, record.version
        )
        return {"status": "built", "executed": executed}

    def _require_conn_ds(self, ds_id: int) -> DataSourceRecord:
        """连接型数据源闸（逆向 scan/import/import-ddl 共用；旧侧 `api/model.py:552-558`）。

        ① 行缺失 → 4001/400，**msg 用内置文案**（旧侧 `ApiError(DS_NOT_FOUND, status=400)` 无 msg）
        ② `type` 非 mysql/greatdb → 4002/400「逆向导入仅支持连接型数据源（mysql/greatdb）」
           （旧侧此处用 PARAM_INVALID 而非 DS_NOT_FOUND —— 照抄该「类型不符报 4002」口径）
        """
        ds = self.session.get(DataSourceRecord, ds_id)
        if ds is None:
            raise ModelDomainError(DS_NOT_FOUND, status=400)
        if ds.type not in ("mysql", "greatdb"):
            raise ModelDomainError(
                PARAM_INVALID, "逆向导入仅支持连接型数据源（mysql/greatdb）", status=400
            )
        return ds

    def reverse_scan(self, ds_id: int, db_name: str = "") -> dict[str, Any]:
        """逆向内省表清单（表名/注释/行数估算/列数；旧侧 `api/model.py:572-594`）。

        ① 数据源闸（`_require_conn_ds`）：4001 / 4002
        ② `target_db = body.dbName or ds.db_name or ""` —— **falsy 链**照抄（空串库名合法）
        ③ **连接用 `open_connection(ds)`，不传 `db`** —— 连接落在 `ds.db_name`，
           `target_db` 只进 SQL 的 `TABLE_SCHEMA = %s`（information_schema 跨库可查）；照抄
        ④ 两条 `information_schema` 查询（TABLES + COLUMNS 计数），`cur.close()`/`conn.close()`
           双层 `finally` 保证释放（**游标非上下文管理器**，旧侧同）
        ⑤ 行数/列数为 **int 兜底**（`int(r[2] or 0)`、`int(r[1] or 0)`）；`comment` `None → ""`；
           `cols` 查不到计 0（`col_counts.get(r[0], 0)`）
        ⑥ 出参 `{db: target_db, tables: [{tb, comment, rows, cols}]}`；表序 = SQL `ORDER BY TABLE_NAME`
           （**不在 Python 侧重排**，照抄）
        """
        ds = self._require_conn_ds(ds_id)
        target_db = db_name or ds.db_name or ""
        conn = self._connector(ds)
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
        tables = [
            {"tb": r[0], "comment": r[1] or "", "rows": int(r[2] or 0), "cols": col_counts.get(r[0], 0)}
            for r in rows
        ]
        return {"db": target_db, "tables": tables}

    def reverse_import(self, ds_id: int, db_name: str,
                       tables: list["ReverseImportTable"]) -> dict[str, Any]:
        """逆向导入建模（逐表建草稿；已存在/校验不过计入 skipped，成功者落库）。

        迁移源实锚 `datara-backend/api/model.py:642-684`（`reverse_import` 逐行照抄）。
        逐表次序：① `code = tb.strip()` ② 同名模型 → skipped「同名模型已存在」
        ③ `_check_code` 不过 → skipped（`reason` 取异常文案，缺省「校验未通过」）
        ④ 内省 COLUMNS；空 → skipped「未找到列（表不存在？）」⑤ `_reverse_create`。
        **无整批事务**：逐表 `flush` 后循环结束统一 `commit`（旧侧 `:682`）。
        """
        ds = self._require_conn_ds(ds_id)
        target_db = db_name or ds.db_name or ""
        imported, skipped = 0, []
        conn = self._connector(ds)
        try:
            for t in tables:
                code = t.tb.strip()
                if self.repository.find_by_code(code) is not None:
                    skipped.append({"tb": code, "reason": "同名模型已存在"})
                    continue
                try:
                    self._check_code(code, self.session.get(DwLayerRecord, t.layer))
                except ModelDomainError as exc:
                    skipped.append({"tb": code, "reason": exc.message or "校验未通过"})
                    continue
                cur = conn.cursor()
                try:
                    cur.execute(
                        "SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, "
                        "COLUMN_COMMENT, COLUMN_KEY, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, "
                        "NUMERIC_SCALE FROM information_schema.COLUMNS "
                        "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
                        (target_db, code),
                    )
                    cols = cur.fetchall()
                finally:
                    cur.close()
                if not cols:  # 目标表不存在/无列信息 → 跳过，不建 0 字段草稿模型
                    skipped.append({"tb": code, "reason": "未找到列（表不存在？）"})
                    continue
                _reverse_create(
                    self.session, code, t.layer, t.name or "", t.biz_domain,
                    _REV_ENGINE_MAP[ds.type], self.owner, [_col_to_field(c) for c in cols],
                )
                imported += 1
        finally:
            conn.close()
        self.session.commit()
        audit.info(
            "model.reverse_import user=%s imported=%d skipped=%d",
            self.owner, imported, len(skipped),
        )
        return {"imported": imported, "skipped": skipped}

    def reverse_import_ddl(self, raw: bytes) -> dict[str, Any]:
        """DDL 文件导入（`.sql`，≤5MB）：sqlglot 解析 CREATE TABLE → ODS 草稿。

        迁移源实锚 `datara-backend/api/model.py:687-735`（`reverse_import_ddl`）。
        **分层读取 + 分块上限由 API 层负责**（旧侧同在路由内）；本方法只接已读入的字节：
        ① `decode_ddl` 解码（utf-8 → gbk 兜底）② `parse_create_tables` 解析
        ③ 逐表：空名跳过 → 同名模型 skipped → `_check_code(code, "ODS")` 不过 skipped
        → `_reverse_create`（engine 恒 `"MySQL"`、remark = 表注释或「DDL 导入」）
        ④ 末尾统一 `commit`。
        """
        sql = decode_ddl(raw)
        try:
            parsed = parse_create_tables(sql)
        except Exception as exc:  # noqa: BLE001 sqlglot ParseError → 8010/400 附行号
            line = getattr(exc, "line", None)
            raise ModelDomainError(
                MODEL_DDL_INVALID,
                f"DDL 解析失败：{exc}" + (f"（第 {line} 行）" if line else ""),
                status=400,
            ) from None
        imported, skipped = 0, []
        for t in parsed:
            code = (t["name"] or "").strip()
            if not code:
                continue
            if self.repository.find_by_code(code) is not None:
                skipped.append({"tb": code, "reason": "同名模型已存在"})
                continue
            try:
                self._check_code(code, self.session.get(DwLayerRecord, "ODS"))
            except ModelDomainError as exc:
                skipped.append({"tb": code, "reason": exc.message or "校验未通过"})
                continue
            _reverse_create(
                self.session, code, "ODS", "", "", "MySQL", self.owner,
                t["fields"], remark=t["comment"] or "DDL 导入",
            )
            imported += 1
        self.session.commit()
        audit.info(
            "model.reverse_import user=%s ddl imported=%d skipped=%d",
            self.owner, imported, len(skipped),
        )
        return {"imported": imported, "skipped": skipped}

    def lineage(self, model_id: int) -> dict[str, Any]:
        """血缘合并图（R4）：`declared` = `t_dw_model_relation` 双向展开；
        `runtime` = `t_lineage_edge` 按 code 匹配（边端点归一化）。

        迁移源实锚 `datara-backend/api/model.py:741-792`（`model_lineage` 逐行照抄）。
        """
        record = self.session.get(DwModelRecord, model_id)
        if record is None:
            raise ModelDomainError(MODEL_NOT_FOUND, status=404)
        nodes = [{"id": record.code, "kind": "model", "label": f"{record.code} {record.name}"}]
        edges: list[dict] = []

        rels = (
            self.session.query(DwModelRelationRecord)
            .filter(or_(DwModelRelationRecord.src_model_id == model_id,
                        DwModelRelationRecord.tgt_model_id == model_id))
            .all()
        )
        rel_ids = {r.src_model_id for r in rels} | {r.tgt_model_id for r in rels}
        name_by_id = {
            x.id: x
            for x in self.session.query(DwModelRecord)
            .filter(DwModelRecord.id.in_(rel_ids)).all()
        }
        for r in rels:
            s = name_by_id.get(r.src_model_id)
            t = name_by_id.get(r.tgt_model_id)
            if not s or not t:
                continue
            if s.id != model_id:
                nodes.append({"id": s.code, "kind": "model", "label": f"{s.code} {s.name}"})
            if t.id != model_id:
                nodes.append({"id": t.code, "kind": "model", "label": f"{t.code} {t.name}"})
            edges.append({"from": s.code, "to": t.code, "kind": "declared", "relType": r.rel_type or ""})

        like = f"%.{record.code}"
        run = (
            self.session.query(LineageEdgeRecord)
            .filter(or_(LineageEdgeRecord.from_table.like(like),
                        LineageEdgeRecord.to_table.like(like)))
            .limit(200).all()
        )
        for e in run:
            if e.from_table and not e.from_table.endswith(f".{record.code}"):
                nodes.append({"id": e.from_table, "kind": "ext", "label": e.from_table})
            if e.to_table and not e.to_table.endswith(f".{record.code}"):
                nodes.append({"id": e.to_table, "kind": "ext", "label": e.to_table})
            # 边端点归一化：模型侧表名（db.code）映射为模型节点裸 code，保证边引用的 id 均在 nodes 中
            edges.append({
                "from": record.code if (e.from_table or "").endswith(f".{record.code}") else e.from_table,
                "to": record.code if (e.to_table or "").endswith(f".{record.code}") else e.to_table,
                "kind": "runtime",
            })

        seen: set[str] = set()
        uniq_nodes = []
        for n in nodes:
            if n["id"] in seen:
                continue
            seen.add(n["id"])
            uniq_nodes.append(n)
        return {
            "nodes": uniq_nodes,
            "edges": edges,
            "sources": {
                "declared": sum(1 for e in edges if e["kind"] == "declared"),
                "runtime": sum(1 for e in edges if e["kind"] == "runtime"),
            },
        }

    def impact(self, model_id: int) -> dict[str, Any]:
        """下游递归清单（声明血缘 DFS，环防护）。

        迁移源实锚 `datara-backend/api/model.py:795-821`（`model_impact` 逐行照抄）。
        **递归实现**（旧侧同）—— 深链可能触及 Python 递归上限，见候核。
        """
        record = self.session.get(DwModelRecord, model_id)
        if record is None:
            raise ModelDomainError(MODEL_NOT_FOUND, status=404)
        nxt: dict[int, list[int]] = {}
        for r in self.session.query(DwModelRelationRecord).all():
            nxt.setdefault(r.src_model_id, []).append(r.tgt_model_id)
        out: list[dict] = []
        path = [record]
        seen = {record.id}

        def dfs(cur: DwModelRecord) -> None:
            for t in nxt.get(cur.id, []):
                if t in seen:
                    continue
                seen.add(t)
                tm = self.session.get(DwModelRecord, t)
                if tm is None:
                    continue
                path.append(tm)
                out.append({
                    "modelId": tm.id, "code": tm.code, "name": tm.name,
                    "path": " → ".join(x.code for x in path),
                })
                dfs(tm)
                path.pop()

        dfs(record)
        return {"list": out}

    def _check_code(self, code: str, layer: Optional[DwLayerRecord]) -> None:
        """编码正则 + 唯一 + 分层命名规范（创建/逆向共用；迁移源实锚 `api/model.py:76-85`）。

        `layer` 可为 `None`：旧侧 `_check_code` 为 `l = db.get(DwLayer, layer)` 后判
        `if l and l.rule`，**分层不存在时静默跳过命名规范**（逆向路径依赖此语义，
        `create` 则在调用前另有存在闸 → 传得进非 `None`）。
        """
        if not CODE_RE.match(code):
            raise ModelDomainError(MODEL_CODE_INVALID, status=400)
        if self.repository.find_by_code(code) is not None:
            raise ModelDomainError(MODEL_CODE_DUP, status=409)
        if layer is not None and layer.rule:
            prefix = layer.rule.split("，")[0].split("_")[0].strip()
            if prefix and not code.startswith(prefix + "_"):
                raise ModelDomainError(
                    MODEL_NAMING_RULE, f"编码需符合分层命名规范：{layer.rule}", status=400
                )
