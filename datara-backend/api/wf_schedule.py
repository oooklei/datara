"""定时调度 API（F46，设计 §9.1/§12）：t_wf_schedule CRUD + 上线/下线。

- GET  /workflow-definitions/{wf}/schedules   定时列表（{wf} 兼容定义 id 与数字 code）
- POST /workflow-definitions/{wf}/schedules   新建（crontab 校验 + 预览未来 3 次触发时间）
- PUT  /schedules/{schedule_id}               更新（crontab 变更即重校验）
- DELETE /schedules/{schedule_id}             删除
- POST /schedules/{schedule_id}/online|offline 上线/下线（master 定时线程 10s 扫描触发）

权限：CRUD=edit_definition；上线/下线=run_instance（触发实例运行）。
"""

from datetime import datetime
from typing import Optional

from croniter import croniter
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import ApiError, get_current_user, require_perm
from common.db import get_db
from common.log import get_logger
from common.models import User, WfDefinition, WfSchedule, now
from common.resp import PARAM_INVALID, WF_NOT_FOUND, fmt_dt, ok

logger = get_logger("api.wf_schedule")

router = APIRouter(tags=["wf-schedule"])

_DT_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d")


def _parse_dt(raw: Optional[str], field: str) -> Optional[datetime]:
    if not raw:
        return None
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    raise ApiError(PARAM_INVALID, "%s 时间格式非法: %s" % (field, raw), status=400)


def _validate_crontab(crontab: str) -> list:
    """crontab 校验（6 段含秒，`?` 自动替换）；返回未来 3 次触发时间（ISO 文本）。"""
    try:
        it = croniter(crontab.replace("?", "*"), now())
        preview = [it.get_next(datetime).strftime("%Y-%m-%d %H:%M:%S") for _ in range(3)]
    except Exception as exc:  # noqa: BLE001 croniter 各类异常统一转参数错误
        raise ApiError(PARAM_INVALID, "crontab 表达式非法: %s" % exc, status=400)
    return preview


def _resolve_wf(db: Session, wf: str) -> WfDefinition:
    """路径参数兼容定义 id（wf_xxx）与数字 code（§12 路由按 code）。"""
    definition = db.get(WfDefinition, wf)
    if definition is None and wf.isdigit():
        definition = db.query(WfDefinition).filter(WfDefinition.code == int(wf)).first()
    if definition is None:
        raise ApiError(WF_NOT_FOUND, status=404)
    return definition


def _get_schedule(db: Session, schedule_id: int) -> WfSchedule:
    schedule = db.get(WfSchedule, schedule_id)
    if schedule is None:
        raise ApiError(WF_NOT_FOUND, "定时计划不存在", status=404)
    return schedule


def _payload(row: WfSchedule) -> dict:
    return {
        "id": row.id,
        "wfCode": row.wf_code,
        "name": row.name,
        "crontab": row.crontab,
        "startTime": fmt_dt(row.start_time),
        "endTime": fmt_dt(row.end_time),
        "state": row.state,
        "priority": row.priority,
        "workerGroup": row.worker_group,
        "failRetryTimes": row.fail_retry_times,
        "failRetryInterval": row.fail_retry_interval,
        "createTime": fmt_dt(row.create_time),
        "updateTime": fmt_dt(row.update_time),
    }


class ScheduleBody(BaseModel):
    name: Optional[str] = None
    crontab: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    priority: int = 3
    worker_group: Optional[str] = None
    fail_retry_times: int = 0
    fail_retry_interval: int = 60


class CrontabBody(BaseModel):
    crontab: str


@router.post("/crontab-preview")
def preview_crontab(body: CrontabBody, user: User = Depends(require_perm("edit_definition"))):
    """crontab 校验 + 未来 3 次触发时间预览（前端定时对话框即时预览用）。"""
    return ok({"valid": True, "nextFireTimes": _validate_crontab(body.crontab)})


@router.get("/workflow-definitions/{wf}/schedules")
def list_schedules(
    wf: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """某工作流的定时列表（倒序）。"""
    definition = _resolve_wf(db, wf)
    rows = (
        db.query(WfSchedule)
        .filter(WfSchedule.wf_code == definition.code)
        .order_by(WfSchedule.id.desc())
        .all()
    )
    return ok([_payload(row) for row in rows])


@router.post("/workflow-definitions/{wf}/schedules")
def create_schedule(
    wf: str,
    body: ScheduleBody,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """新建定时：crontab 校验；返回预览未来 3 次触发时间（初始 offline）。"""
    definition = _resolve_wf(db, wf)
    preview = _validate_crontab(body.crontab)
    schedule = WfSchedule(
        wf_code=definition.code,
        name=(body.name or "默认定时").strip(),
        crontab=body.crontab.strip(),
        start_time=_parse_dt(body.start_time, "start_time"),
        end_time=_parse_dt(body.end_time, "end_time"),
        state="offline",
        priority=max(1, min(int(body.priority or 3), 5)),
        worker_group=body.worker_group,
        fail_retry_times=max(0, int(body.fail_retry_times or 0)),
        fail_retry_interval=max(1, int(body.fail_retry_interval or 60)),
    )
    db.add(schedule)
    db.commit()
    logger.info("定时计划新建: id=%s wf=%s crontab=%s（%s）",
                schedule.id, definition.code, schedule.crontab, user.user_name)
    return ok({**_payload(schedule), "nextFireTimes": preview})


@router.put("/schedules/{schedule_id}")
def update_schedule(
    schedule_id: int,
    body: ScheduleBody,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """更新定时（crontab 变更重校验；update_time 变化驱动 master 缓存重算 next_fire）。"""
    schedule = _get_schedule(db, schedule_id)
    preview = _validate_crontab(body.crontab)
    schedule.name = (body.name or schedule.name).strip()
    schedule.crontab = body.crontab.strip()
    schedule.start_time = _parse_dt(body.start_time, "start_time")
    schedule.end_time = _parse_dt(body.end_time, "end_time")
    schedule.priority = max(1, min(int(body.priority or 3), 5))
    schedule.worker_group = body.worker_group
    schedule.fail_retry_times = max(0, int(body.fail_retry_times or 0))
    schedule.fail_retry_interval = max(1, int(body.fail_retry_interval or 60))
    db.commit()
    logger.info("定时计划更新: id=%s crontab=%s（%s）", schedule.id, schedule.crontab, user.user_name)
    return ok({**_payload(schedule), "nextFireTimes": preview})


@router.delete("/schedules/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """删除定时（online 状态先下线再删，避免 master 空引用）。"""
    schedule = _get_schedule(db, schedule_id)
    schedule.state = "offline"
    db.delete(schedule)
    db.commit()
    logger.info("定时计划删除: id=%s（%s）", schedule_id, user.user_name)
    return ok(True)


@router.post("/schedules/{schedule_id}/online")
def online_schedule(
    schedule_id: int,
    user: User = Depends(require_perm("run_instance")),
    db: Session = Depends(get_db),
):
    """上线：state=online（master 定时线程扫描触发；有效期外不触发）。"""
    schedule = _get_schedule(db, schedule_id)
    _validate_crontab(schedule.crontab)  # 上线前再校验（防建后直改库脏数据）
    schedule.state = "online"
    db.commit()
    logger.info("定时上线: id=%s wf=%s crontab=%s（%s）",
                schedule.id, schedule.wf_code, schedule.crontab, user.user_name)
    return ok(_payload(schedule))


@router.post("/schedules/{schedule_id}/offline")
def offline_schedule(
    schedule_id: int,
    user: User = Depends(require_perm("run_instance")),
    db: Session = Depends(get_db),
):
    """下线：state=offline（不再触发）。"""
    schedule = _get_schedule(db, schedule_id)
    schedule.state = "offline"
    db.commit()
    logger.info("定时下线: id=%s（%s）", schedule.id, user.user_name)
    return ok(_payload(schedule))
