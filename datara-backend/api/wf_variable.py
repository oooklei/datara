"""工作流变量路由：GET / POST / PUT / DELETE，字段对齐前端 WfVariable。

WfVariable（src/services/types.ts）：{id, wf, name, value, type, encrypted, options, desc}
后端落库 t_wf_variable（wf_code 关联），API 层做 id(wf_xxx) ↔ code 映射。
"""

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import ApiError, get_current_user, require_perm
from common.db import get_db
from common.log import get_logger
from common.models import User, WfDefinition, WfVariable
from common.resp import WF_NOT_FOUND, fail, ok

logger = get_logger("api.wf_variable")

router = APIRouter(prefix="/workflow-variables", tags=["wf-variable"])


class VariableBody(BaseModel):
    wf: str
    name: str
    value: Optional[str] = ""
    type: str = "文本"
    encrypted: bool = False
    options: Optional[List[str]] = None
    desc: Optional[str] = ""


def _resolve_code(db: Session, wf: str) -> int:
    """前端 wf 参数 = GraphDocument 的 doc.id（'wf_xxx'），映射为 code。"""
    definition = db.get(WfDefinition, wf)
    if definition is None:
        raise ApiError(WF_NOT_FOUND, status=404)
    return definition.code


def _payload(row: WfVariable, wf: str) -> dict:
    return {
        "id": str(row.id),
        "wf": wf,
        "name": row.name,
        "value": row.value or "",
        "type": row.type,
        "encrypted": bool(row.encrypted),
        "options": row.options or [],
        "desc": row.desc or "",
    }


@router.get("")
def list_variables(wf: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """按工作流列变量（wf=doc.id）。"""
    code = _resolve_code(db, wf)
    rows = db.query(WfVariable).filter(WfVariable.wf_code == code).order_by(WfVariable.id).all()
    return ok([_payload(row, wf) for row in rows])


@router.post("")
def create_variable(
    body: VariableBody,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """新增变量。"""
    if not body.name.strip():
        return fail(4002, "变量名不能为空")
    code = _resolve_code(db, body.wf)
    row = WfVariable(
        wf_code=code,
        name=body.name.strip(),
        value=body.value or "",
        type=body.type,
        encrypted=body.encrypted,
        options=body.options or [],
        desc=body.desc or "",
    )
    db.add(row)
    db.commit()
    logger.info("新增工作流变量: wf=%s name=%s（操作人 %s）", body.wf, row.name, user.user_name)
    return ok(_payload(row, body.wf))


@router.put("/{var_id}")
def update_variable(
    var_id: int,
    body: VariableBody,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """更新变量（按 body 全量覆盖）。"""
    row = db.get(WfVariable, var_id)
    if row is None:
        raise ApiError(4001, "变量不存在", status=404)
    code = _resolve_code(db, body.wf)
    if code != row.wf_code:
        row.wf_code = code
    row.name = body.name.strip()
    row.value = body.value or ""
    row.type = body.type
    row.encrypted = body.encrypted
    row.options = body.options or []
    row.desc = body.desc or ""
    db.commit()
    logger.info("更新工作流变量: id=%s（操作人 %s）", var_id, user.user_name)
    return ok(True)


@router.delete("/{var_id}")
def delete_variable(
    var_id: int,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """删除变量。"""
    row = db.get(WfVariable, var_id)
    if row is None:
        raise ApiError(4001, "变量不存在", status=404)
    db.delete(row)
    db.commit()
    logger.info("删除工作流变量: id=%s（操作人 %s）", var_id, user.user_name)
    return ok(True)
