"""logger 模块：日志查询 API（按 t_task_log 索引读共享卷内日志文件，I1 骨架）。"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.auth import ApiError, get_current_user
from common.db import get_db
from common.models import TaskLog, User
from common.resp import PARAM_INVALID, ok

router = APIRouter(tags=["logs"])


def _read_log(path: str) -> str:
    """读日志文件正文；文件缺失/不可读时返回提示（不抛异常）。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return "（日志文件不存在或不可读: %s）" % path


@router.get("/logs")
def query_logs(instance_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """按运行实例编号查任务日志：[{taskInstanceId, logPath, content}]。"""
    if not instance_id.strip():
        raise ApiError(PARAM_INVALID, "instance_id 不能为空", status=400)
    rows = (
        db.query(TaskLog)
        .filter(TaskLog.instance_id == instance_id.strip())
        .order_by(TaskLog.id)
        .all()
    )
    items = [
        {
            "taskInstanceId": row.task_instance_id,
            "logPath": row.log_path,
            "content": _read_log(row.log_path),
        }
        for row in rows
    ]
    return ok(items)


@router.get("/logs/task/{task_id}")
def query_task_log(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """单任务日志正文（I3 §11.1 新增：前端节点日志抽屉 2s 轮询增量可见）。"""
    row = db.query(TaskLog).filter(TaskLog.task_instance_id == task_id).first()
    if row is None:
        raise ApiError(PARAM_INVALID, "任务日志索引不存在: task_id=%s" % task_id, status=404)
    return ok({
        "taskInstanceId": row.task_instance_id,
        "instanceId": row.instance_id,
        "logPath": row.log_path,
        "content": _read_log(row.log_path),
    })
