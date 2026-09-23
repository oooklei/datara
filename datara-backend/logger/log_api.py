"""logger 模块：日志查询/删除 API（按 t_task_log 索引读共享卷内日志文件，I1 骨架）。"""

import os

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.auth import ApiError, get_current_user, require_perm
from common.config import get_settings
from common.db import get_db
from common.log import get_logger
from common.models import TaskLog, User
from common.resp import PARAM_INVALID, ok

logger = get_logger("logger.log_api")

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


def _is_under_log_dir(path: str) -> bool:
    """路径白名单：仅允许删除共享日志目录（config.log_dir）内的文件，防穿越/防误删外部文件。"""
    log_root = os.path.abspath(os.path.normpath(get_settings().log_dir))
    target = os.path.abspath(os.path.normpath(path))
    return target == log_root or target.startswith(log_root + os.sep)


@router.delete("/logs")
def delete_instance_logs(
    instance_id: str = Query(""),
    instance_ids: str = Query(""),
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """删除运行实例的任务日志：删 t_task_log 索引行 + 对应日志文件（I11 运行监控「删除日志」）。

    - 单实例：instance_id=xxx（兼容既有调用）；
    - 批量：instance_ids=a,b,c（逗号分隔，前端多选全选删除）。
    """
    if instance_ids.strip():
        targets = [x.strip() for x in instance_ids.split(",") if x.strip()]
    else:
        targets = [instance_id.strip()] if instance_id.strip() else []
    if not targets:
        raise ApiError(PARAM_INVALID, "instance_id 不能为空", status=400)
    total_deleted = 0
    total_files = 0
    total_skipped = 0
    for target in targets:
        rows = (
            db.query(TaskLog)
            .filter(TaskLog.instance_id == target)
            .order_by(TaskLog.id)
            .all()
        )
        removed_files = 0
        skipped_files = 0
        for row in rows:
            if row.log_path and _is_under_log_dir(row.log_path):
                try:
                    os.remove(row.log_path)
                    removed_files += 1
                    # 文件删除成功后，若所在目录已空则清理（os.rmdir 仅删除空目录，非空抛 OSError）
                    _remove_empty_dir(os.path.dirname(row.log_path))
                except OSError:
                    # 文件已不存在/权限问题：不阻断，索引行照删
                    pass
            elif row.log_path:
                skipped_files += 1
                logger.warning("日志路径不在白名单内，跳过删文件（仅删索引）: %s", row.log_path)
        for row in rows:
            db.delete(row)
        total_deleted += len(rows)
        total_files += removed_files
        total_skipped += skipped_files
        logger.info("删除实例日志: instance=%s rows=%s files=%s skipped=%s（用户 %s）",
                    target, len(rows), removed_files, skipped_files, user.user_name)
    db.commit()
    return ok({
        "deleted": total_deleted, "files": total_files, "skipped": total_skipped,
        "instances": len(targets),
    })


def _remove_empty_dir(path: str) -> None:
    """尝试移除空目录（仅限日志根目录内，防误删外部目录）；目录非空/不存在时静默忽略。"""
    if not path:
        return
    try:
        if _is_under_log_dir(path) and os.path.isdir(path) and not os.listdir(path):
            os.rmdir(path)
    except OSError:
        pass
