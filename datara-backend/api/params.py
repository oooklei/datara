"""全局参数 CRUD（I10 设计文档 G3：IDE 全局参数抽屉 env 三分组；M12 mock 页后续接真实端点）。

- GET    /params/global?env=      清单（env 可选过滤；按名称排序）
- POST   /params/global           新增（同 env 内名称唯一）
- PUT    /params/global/{id}      更新
- DELETE /params/global/{id}      删除

引擎侧 master.variables.load_levels 不分 env 全量加载（行为不变）；env 仅 IDE 执行渲染链使用。
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth import ApiError, get_current_user, require_perm
from common.db import get_db
from common.log import get_logger
from common.models import GlobalParam, User
from common.resp import PARAM_INVALID, fmt_dt, ok

logger = get_logger("api.params")

router = APIRouter(prefix="/params", tags=["params"])

ENV_LIST = ("dev", "staging", "prod")


def _payload(row: GlobalParam) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "value": row.value or "",
        "type": row.type,
        "env": row.env,
        "desc": row.desc,
        "createTime": fmt_dt(row.create_time),
        "updateTime": fmt_dt(row.update_time),
    }


class GlobalParamBody(BaseModel):
    name: str
    value: str = ""
    type: str = Field(default="文本")
    env: str = Field(default="dev")
    desc: Optional[str] = None


@router.get("/global")
def list_global_params(
    env: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """全局参数清单（env 可选过滤，G3 三分组）。"""
    query = db.query(GlobalParam)
    if env:
        if env not in ENV_LIST:
            raise ApiError(PARAM_INVALID, f"env 仅支持 {'/'.join(ENV_LIST)}", status=400)
        query = query.filter(GlobalParam.env == env)
    rows = query.order_by(GlobalParam.env, GlobalParam.name).all()
    return ok([_payload(row) for row in rows])


@router.post("/global")
def create_global_param(
    body: GlobalParamBody,
    user: User = Depends(require_perm("run_instance")),
    db: Session = Depends(get_db),
):
    """新增全局参数（同 env 内名称唯一）。"""
    name = (body.name or "").strip()
    if not name:
        raise ApiError(PARAM_INVALID, "参数名不能为空", status=400)
    if body.env not in ENV_LIST:
        raise ApiError(PARAM_INVALID, f"env 仅支持 {'/'.join(ENV_LIST)}", status=400)
    dup = db.query(GlobalParam).filter(GlobalParam.env == body.env, GlobalParam.name == name).first()
    if dup is not None:
        raise ApiError(PARAM_INVALID, f"该环境下参数名已存在: {name}", status=400)
    row = GlobalParam(
        name=name,
        value=body.value,
        type=body.type or "文本",
        env=body.env,
        desc=body.desc,
    )
    db.add(row)
    db.commit()
    logger.info("全局参数新增: id=%d %s env=%s（操作人 %s）", row.id, row.name, row.env, user.user_name)
    return ok(_payload(row))


@router.put("/global/{param_id}")
def update_global_param(
    param_id: int,
    body: GlobalParamBody,
    user: User = Depends(require_perm("run_instance")),
    db: Session = Depends(get_db),
):
    """更新全局参数（改名/改 env 时校验目标 env 内唯一）。"""
    row = db.get(GlobalParam, param_id)
    if row is None:
        raise ApiError(PARAM_INVALID, "参数不存在", status=404)
    name = (body.name or "").strip()
    if not name:
        raise ApiError(PARAM_INVALID, "参数名不能为空", status=400)
    if body.env not in ENV_LIST:
        raise ApiError(PARAM_INVALID, f"env 仅支持 {'/'.join(ENV_LIST)}", status=400)
    dup = db.query(GlobalParam).filter(GlobalParam.env == body.env, GlobalParam.name == name)
    dup = dup.filter(GlobalParam.id != param_id)
    if dup.first() is not None:
        raise ApiError(PARAM_INVALID, f"该环境下参数名已存在: {name}", status=400)
    row.name = name
    row.value = body.value
    row.type = body.type or "文本"
    row.env = body.env
    row.desc = body.desc
    db.commit()
    logger.info("全局参数更新: id=%d %s env=%s（操作人 %s）", row.id, row.name, row.env, user.user_name)
    return ok(_payload(row))


@router.delete("/global/{param_id}")
def delete_global_param(
    param_id: int,
    user: User = Depends(require_perm("run_instance")),
    db: Session = Depends(get_db),
):
    """删除全局参数。"""
    row = db.get(GlobalParam, param_id)
    if row is None:
        raise ApiError(PARAM_INVALID, "参数不存在", status=404)
    db.delete(row)
    db.commit()
    logger.info("全局参数删除: id=%d %s（操作人 %s）", row.id, row.name, user.user_name)
    return ok(True)
