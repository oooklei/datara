"""SSH 运行节点路由（I7 F53，设计 §3.3）：/api/v1/ssh-nodes CRUD + 手动探活。

- t_ssh_node 注册表：标签（tags）供 ssh 执行器派发路由匹配；enabled=false 派发剔除
- 探活：paramiko 连接执行 `echo ok`（3s 超时）；即时结果返回，状态落库统一由
  master 探活线程管理（避免多入口写竞态）
- 凭证明文裁定（I1）：密码或 -----BEGIN 开头私钥内容，多算法依次尝试
"""

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth import ApiError, get_current_user, require_perm
from common.db import get_db
from common.log import get_logger
from common.models import SshNode, User
from common.resp import fmt_dt, ok

logger = get_logger("api.sshnode")

router = APIRouter(prefix="/ssh-nodes", tags=["ssh-node"])


class SshNodeBody(BaseModel):
    name: str
    host: str
    port: int = 22
    sshUser: str = "root"
    cred: Optional[str] = ""
    tags: List[str] = Field(default_factory=list)
    enabled: bool = True


def _payload(row: SshNode) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "host": row.host,
        "port": row.port,
        "sshUser": row.ssh_user,
        "cred": row.cred_enc or "",
        "tags": row.tags or [],
        "enabled": bool(row.enabled),
        "heartbeatState": row.heartbeat_state,
        "lastSeen": fmt_dt(row.last_seen),
        "createTime": fmt_dt(row.create_time),
    }


def _get_row(db: Session, node_id: int) -> SshNode:
    row = db.get(SshNode, node_id)
    if row is None:
        raise ApiError(4101, "SSH 节点不存在", status=404)
    return row


@router.get("")
def list_ssh_nodes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """SSH 节点列表（管理页 + 画布「执行节点标签」下拉数据源）。"""
    rows = db.query(SshNode).order_by(SshNode.id).all()
    return ok([_payload(r) for r in rows])


@router.post("")
def create_ssh_node(
    body: SshNodeBody,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """新增 SSH 节点。"""
    if not body.name.strip() or not body.host.strip():
        raise ApiError(4103, "节点名与主机地址不能为空", status=400)
    if db.query(SshNode).filter(SshNode.name == body.name.strip()).first() is not None:
        raise ApiError(4102, "节点名已存在", status=409)
    row = SshNode(
        name=body.name.strip(),
        host=body.host.strip(),
        port=body.port,
        ssh_user=body.sshUser.strip() or "root",
        cred_enc=body.cred or "",
        tags=[str(t).strip() for t in body.tags if str(t).strip()],
        enabled=body.enabled,
    )
    db.add(row)
    db.commit()
    logger.info("新增 SSH 节点: %s (%s:%s)（操作人 %s）", row.name, row.host, row.port, user.user_name)
    return ok(_payload(row))


@router.put("/{node_id}")
def update_ssh_node(
    node_id: int,
    body: SshNodeBody,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """更新 SSH 节点（body 全量覆盖）。"""
    row = _get_row(db, node_id)
    if not body.name.strip() or not body.host.strip():
        raise ApiError(4103, "节点名与主机地址不能为空", status=400)
    dup = db.query(SshNode).filter(SshNode.name == body.name.strip()).first()
    if dup is not None and dup.id != node_id:
        raise ApiError(4102, "节点名已存在", status=409)
    row.name = body.name.strip()
    row.host = body.host.strip()
    row.port = body.port
    row.ssh_user = body.sshUser.strip() or "root"
    row.cred_enc = body.cred or ""
    row.tags = [str(t).strip() for t in body.tags if str(t).strip()]
    row.enabled = body.enabled
    db.commit()
    logger.info("更新 SSH 节点: id=%s（操作人 %s）", node_id, user.user_name)
    return ok(_payload(row))


@router.delete("/{node_id}")
def delete_ssh_node(
    node_id: int,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """删除 SSH 节点。"""
    row = _get_row(db, node_id)
    db.delete(row)
    db.commit()
    logger.info("删除 SSH 节点: %s（操作人 %s）", row.name, user.user_name)
    return ok(True)


@router.post("/{node_id}/probe")
def probe_ssh_node(
    node_id: int,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """手动探活：SSH 执行 echo ok；结果即时返回（状态落库归 master 探活线程）。"""
    row = _get_row(db, node_id)
    ok_flag, msg = probe(row.host, row.port, row.ssh_user, row.cred_enc or "")
    logger.info("SSH 节点手动探活: %s → %s（操作人 %s）", row.name, "通过" if ok_flag else msg, user.user_name)
    return ok({"ok": ok_flag, "message": msg})


def probe(host: str, port: int, user: str, cred: str) -> tuple:
    """探活委托 common.sshprobe（与 master 探活线程同一实现）。"""
    from common.sshprobe import probe as _probe

    return _probe(host, port, user, cred)
