"""健康检查：GET /api/v1/health → 各组件连通性（db/redis/zk）。"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from common.db import get_db
from common import queue
from common.resp import ok

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request, db: Session = Depends(get_db)):
    """组件探活：status 恒为 UP（进程存活即 UP），db/redis/zk 为布尔连通性。"""
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 探活只报状态
        db_ok = False

    redis_ok = queue.ping()

    registry = getattr(request.app.state, "registry", None) if request is not None else None
    zk_ok = bool(registry is not None and registry.connected)

    return ok({"status": "UP", "db": db_ok, "redis": redis_ok, "zk": zk_ok})


@router.api_route("/echo", methods=["GET", "POST", "PUT", "DELETE"])
async def echo(request: Request):
    """内网回显测试端点（I4 C16 HTTP 组件实测用，免鉴权）：

    回显 method/headers/body，并附固定嵌套结构（items/nested）供响应提取（点路径）断言。
    """
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 非 JSON body 原样置 None
        body = None
    return ok(
        {
            "method": request.method,
            "headers": dict(request.headers),
            "body": body,
            "items": [{"name": "alpha", "value": 1}, {"name": "beta", "value": 2}],
            "nested": {"deep": 42},
        }
    )
