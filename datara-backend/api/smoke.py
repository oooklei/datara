"""冒烟链路提交 + 注册中心节点查看。

- POST /smoke/run → 写 t_command(command_type='START_PROCESS_SMOKE', state='wait')
- GET /registry/nodes → ZK /datara/live 递归列表（ZK 挂时返回 zkAvailable=false）
"""

from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import get_current_user, require_perm
from common.db import get_db
from common.log import get_logger
from common.models import Command, User
from common.registry import list_live_nodes
from common.resp import ok

logger = get_logger("api.smoke")

router = APIRouter(tags=["smoke"])


class SmokeBody(BaseModel):
    name: Optional[str] = None
    delaySec: Optional[int] = 1


@router.post("/smoke/run")
def run_smoke(
    body: SmokeBody,
    user: User = Depends(require_perm("run_instance")),
    db: Session = Depends(get_db),
):
    """冒烟提交：写命令表，master 2s 轮询消费（冒烟链路第①步）。"""
    delay = body.delaySec if body.delaySec and body.delaySec > 0 else 1
    command = Command(
        command_type="START_PROCESS_SMOKE",
        command_param={"name": body.name or "smoke", "delaySec": delay},
        priority=0,
        state="wait",
    )
    db.add(command)
    db.commit()
    logger.info("冒烟命令已提交: commandId=%s（用户 %s）", command.id, user.user_name)
    return ok({"commandId": command.id})


@router.get("/registry/nodes")
def registry_nodes(request: Request, user: User = Depends(get_current_user)):
    """注册中心节点列表（掉线感知：临时节点随会话消失）。"""
    registry = getattr(request.app.state, "registry", None)
    zk = registry.zk if registry is not None else None
    available, nodes = list_live_nodes(zk)
    return ok({"zkAvailable": available, "nodes": nodes})
