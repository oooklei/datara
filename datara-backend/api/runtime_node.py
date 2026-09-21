"""运行时节点 API（C14 表单下拉，设计 §12）：GET /runtime-nodes 只读列表。

注册/编辑 UI 归 I7（F53），本期仅读 t_runtime_node（含内置 seed『1.9宿主机』）。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.auth import get_current_user
from common.db import get_db
from common.models import RuntimeNode, User
from common.resp import fmt_dt, ok

router = APIRouter(prefix="/runtime-nodes", tags=["runtime-node"])


@router.get("")
def list_runtime_nodes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """运行时节点列表（只读，SSH 节点 runtimeNode 字段下拉数据源）。"""
    rows = db.query(RuntimeNode).order_by(RuntimeNode.id).all()
    return ok([
        {
            "id": row.id,
            "name": row.name,
            "kind": row.kind,
            "host": row.host,
            "port": row.port,
            "user": row.user,
            "runtimeDir": row.runtime_dir,
            "status": row.status,
            "lastHeartbeat": fmt_dt(row.last_heartbeat),
        }
        for row in rows
    ])
