"""运行实例 API（I3 §12）：列表/详情扩展 + 停止/重跑/失败节点重跑（api 写命令，master 消费）。

- GET  /instances                          列表（分页倒序，run_mode/state/wf_code 筛选）
- GET  /instances/{instance_id}            详情（补 runMode/scheduleTime；任务行补 loopIter/delayUntil）
- POST /instances/{instance_id}/stop       停止 → STOP 命令（运行中实例方可停止）
- POST /instances/{instance_id}/rerun      整实例重跑 → REPEAT_RUNNING（终态实例方可重跑）
- POST /instances/{instance_id}/rerun-failed 失败节点重跑 → START_FAILURE_TASKS（同一实例内续跑）
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import ApiError, get_current_user, require_perm
from api.commands import submit_command
from common.db import get_db
from common.log import get_logger
from common.models import TaskInstance, User, WorkflowInstance
from common.resp import INSTANCE_NOT_FOUND, COMMAND_FAIL, PageQuery, fmt_dt, ok, page_result
from master.state import INSTANCE_RUNNING_STATES, TERMINAL_STATES

logger = get_logger("api.instance")

router = APIRouter(prefix="/instances", tags=["instance"])


class RerunBody(BaseModel):
    priority: int = 3


def _get_instance(db: Session, instance_id: str) -> WorkflowInstance:
    row = db.query(WorkflowInstance).filter(WorkflowInstance.instance_id == instance_id).first()
    if row is None:
        raise ApiError(INSTANCE_NOT_FOUND, status=404)
    return row


@router.get("")
def list_instances(
    page: PageQuery = Depends(),
    run_mode: Optional[str] = None,
    state: Optional[str] = None,
    wf_code: Optional[int] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """实例列表（分页倒序；run_mode=manual/schedule/complement、state、wf_code 筛选）。"""
    query = db.query(WorkflowInstance)
    if run_mode:
        query = query.filter(WorkflowInstance.run_mode == run_mode)
    if state:
        query = query.filter(WorkflowInstance.state == state)
    if wf_code is not None:
        query = query.filter(WorkflowInstance.wf_code == wf_code)
    total = query.count()
    rows = query.order_by(WorkflowInstance.id.desc()).offset(page.offset).limit(page.page_size).all()
    items = [
        {
            "id": row.id,
            "instanceId": row.instance_id,
            "wfCode": row.wf_code,
            "wfVersion": row.wf_version,
            "state": row.state,
            "runMode": row.run_mode or "manual",
            "scheduleTime": fmt_dt(row.schedule_time),
            "startTime": fmt_dt(row.start_time),
            "endTime": fmt_dt(row.end_time),
            "host": row.host,
            "commandType": row.command_type,
        }
        for row in rows
    ]
    return ok(page_result(total, items))


@router.get("/{instance_id}")
def get_instance(
    instance_id: str,
    user: User = Depends(require_perm("view_all")),
    db: Session = Depends(get_db),
):
    """实例详情（含 task_instances 列表；补 runMode/scheduleTime/loopIter/delayUntil，I3 §12）。"""
    row = _get_instance(db, instance_id)
    tasks = (
        db.query(TaskInstance)
        .filter(TaskInstance.instance_id == instance_id)
        .order_by(TaskInstance.id)
        .all()
    )
    return ok(
        {
            "id": row.id,
            "instanceId": row.instance_id,
            "wfCode": row.wf_code,
            "wfVersion": row.wf_version,
            "state": row.state,
            "runMode": row.run_mode or "manual",
            "scheduleTime": fmt_dt(row.schedule_time),
            "startTime": fmt_dt(row.start_time),
            "endTime": fmt_dt(row.end_time),
            "host": row.host,
            "commandType": row.command_type,
            "variables": row.variables,
            "recovery": row.recovery,
            "taskInstances": [
                {
                    "id": task.id,
                    "instanceId": task.instance_id,
                    "nodeId": task.node_id,
                    "nodeType": task.node_type,
                    "name": task.name,
                    "state": task.state,
                    "attempt": task.attempt,
                    "loopIter": task.loop_iter or 0,
                    "delayUntil": fmt_dt(task.delay_until),
                    "startTime": fmt_dt(task.start_time),
                    "endTime": fmt_dt(task.end_time),
                    "host": task.host,
                    "logPath": task.log_path,
                    "outputs": task.outputs,
                }
                for task in tasks
            ],
        }
    )


@router.post("/{instance_id}/stop")
def stop_instance(
    instance_id: str,
    user: User = Depends(require_perm("run_instance")),
    db: Session = Depends(get_db),
):
    """停止实例（§8）：写 STOP 命令 → master 置 kill + 未终态任务 kill 标记 → worker 中断。"""
    row = _get_instance(db, instance_id)
    if row.state not in INSTANCE_RUNNING_STATES:
        raise ApiError(COMMAND_FAIL, "实例非运行中（%s），无需停止" % row.state, status=400)
    command = submit_command(db, "STOP", {"instanceId": instance_id})
    logger.info("停止命令已提交: instance=%s commandId=%s（用户 %s）", instance_id, command.id, user.user_name)
    return ok({"commandId": command.id})


@router.post("/{instance_id}/rerun")
def rerun_instance(
    instance_id: str,
    body: RerunBody,
    user: User = Depends(require_perm("run_instance")),
    db: Session = Depends(get_db),
):
    """整实例重跑（§9.3）：新 instance_id 全量新建任务行，复用原实例变量快照。"""
    row = _get_instance(db, instance_id)
    if row.state not in TERMINAL_STATES:
        raise ApiError(COMMAND_FAIL, "实例未终态（%s），不可重跑" % row.state, status=400)
    command = submit_command(db, "REPEAT_RUNNING", {"instanceId": instance_id}, priority=body.priority)
    logger.info("整实例重跑已提交: instance=%s commandId=%s（用户 %s）", instance_id, command.id, user.user_name)
    return ok({"commandId": command.id})


@router.post("/{instance_id}/rerun-failed")
def rerun_failed(
    instance_id: str,
    body: RerunBody,
    user: User = Depends(require_perm("run_instance")),
    db: Session = Depends(get_db),
):
    """失败节点重跑（§9.3）：仅 failure 任务及其下游重置重派，同实例内续跑。"""
    _get_instance(db, instance_id)  # 存在性校验（失败任务有无由 master 校验，缺失败置命令 fail）
    command = submit_command(db, "START_FAILURE_TASKS", {"instanceId": instance_id}, priority=body.priority)
    logger.info("失败节点重跑已提交: instance=%s commandId=%s（用户 %s）", instance_id, command.id, user.user_name)
    return ok({"commandId": command.id})
