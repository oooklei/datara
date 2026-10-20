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

import re
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from rebuild.model.errors import (
    MODEL_CODE_DUP,
    MODEL_CODE_INVALID,
    MODEL_NAMING_RULE,
    PARAM_INVALID,
    ModelDomainError,
)
from rebuild.model.models import DwLayerRecord, DwModelRecord, EngineTypeRecord
from rebuild.model.repository import ModelRepository

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
