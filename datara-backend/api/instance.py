"""运行实例 API（I3 §12）：列表/详情扩展 + 停止/重跑/失败节点重跑（api 写命令，master 消费）。

- GET  /instances                          列表（分页倒序，run_mode/state/wf_code 筛选）
- GET  /instances/{instance_id}            详情（补 runMode/scheduleTime；任务行补 loopIter/delayUntil）
- GET  /instances/{instance_id}/stream     状态 SSE 流（E1：task_state_changed/instance_finished + 心跳）
- POST /instances/{instance_id}/stop       停止 → STOP 命令（运行中实例方可停止）
- POST /instances/{instance_id}/rerun      整实例重跑 → REPEAT_RUNNING（终态实例方可重跑）
- POST /instances/{instance_id}/rerun-failed 失败节点重跑 → START_FAILURE_TASKS（同一实例内续跑）
"""

import json
import time
from typing import Optional

from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.auth import ApiError, get_current_user, require_perm
from api.commands import submit_command
from common.db import get_db, new_session
from common.log import get_logger
from common.models import TRunEvent, TaskInstance, TaskLog, User, WorkflowInstance
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


def _run_event_data(row: TRunEvent) -> dict:
    """Convert a durable run event to the public API/SSE representation."""
    try:
        payload = json.loads(row.payload_json) if row.payload_json else {}
    except (TypeError, ValueError):
        logger.warning("invalid run event payload: id=%s", row.id)
        payload = {}
    return {
        "id": row.id,
        "runId": row.run_id,
        "nodeId": row.node_id,
        "type": row.event_type,
        "payload": payload,
        "ts": fmt_dt(row.ts),
    }


@router.get("")
def list_instances(
    page: PageQuery = Depends(),
    run_mode: Optional[str] = None,
    state: Optional[str] = None,
    wf_code: Optional[int] = None,
    sync_logs: Optional[bool] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """实例列表（分页倒序；run_mode=manual/schedule/complement、state、wf_code 筛选）。

    sync_logs=True（I12 运行监控页）：终态实例若无任何 t_task_log 索引行（日志已被清理），
    视为悬空实例不展示，保证前端与后端日志真实状态同步；运行中/已提交实例始终展示
    （日志可能尚未落盘）。其他调用方不带该参数，行为不变。
    """
    query = db.query(WorkflowInstance)
    if run_mode:
        query = query.filter(WorkflowInstance.run_mode == run_mode)
    if state:
        query = query.filter(WorkflowInstance.state == state)
    if wf_code is not None:
        query = query.filter(WorkflowInstance.wf_code == wf_code)
    if sync_logs:
        # 终态且无日志索引 → 悬空实例，过滤（保证前端与后端日志真实状态同步）
        log_exists = (
            db.query(TaskLog.id)
            .filter(TaskLog.instance_id == WorkflowInstance.instance_id)
            .exists()
        )
        query = query.filter(or_(WorkflowInstance.state.notin_(TERMINAL_STATES), log_exists))
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


@router.get("/{instance_id}/events")
def list_run_events(
    instance_id: str,
    page: PageQuery = Depends(),
    after_id: Optional[int] = None,
    user: User = Depends(require_perm("view_all")),
    db: Session = Depends(get_db),
):
    """Return durable node/execution events, newest first unless resuming by id."""
    _get_instance(db, instance_id)
    query = db.query(TRunEvent).filter(TRunEvent.run_id == instance_id)
    if after_id is not None:
        query = query.filter(TRunEvent.id > after_id).order_by(TRunEvent.id)
    else:
        query = query.order_by(TRunEvent.id.desc())
    total = query.count()
    rows = query.offset(page.offset).limit(page.page_size).all()
    return ok(page_result(total, [_run_event_data(row) for row in rows]))


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


# E1 SSE 节奏（模块常量：测试 monkeypatch 调速；生产 1s diff / 15s 心跳）
SSE_POLL_SEC = 1.0
SSE_HEARTBEAT_SEC = 15.0


def _stream_session() -> Session:
    """SSE 流内每轮独立短会话：长连接不占用请求级会话，轮询完即还连接池（及时释放）。"""
    return new_session()


@router.get("/{instance_id}/stream")
def stream_instance(
    instance_id: str,
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
    user: User = Depends(require_perm("view_all")),
    db: Session = Depends(get_db),
):
    """实例状态 SSE 流（E1）：event=task_state_changed / instance_finished + 心跳注释行。

    - 连接即推一轮基线快照（幂等 patch，闭合 loadDetail→订阅 窗口的状态漏推）；
    - 之后每 SSE_POLL_SEC 查库做 diff，仅推状态变更的任务行（前端只 patch 单节点，不整幅重画）；
    - 实例转终态推 instance_finished 后服务端主动关流（EventSource 不再重连）；
    - 已终态实例：基线 + instance_finished 立即关流；实例中途被清理（悬空）则静默收流；
    - 鉴权 ?token= 兜底（EventSource 无法携带 header，api/auth 口径）；断线由前端降级 3s 轮询。
    """
    row = _get_instance(db, instance_id)  # 404 闸门（存在性校验后请求级会话即还池）

    try:
        event_cursor = max(0, int(last_event_id or 0)) if isinstance(last_event_id, (str, int)) else 0
    except ValueError:
        event_cursor = 0

    def gen():
        nonlocal event_cursor
        baseline: dict[int, str] = {}  # task_id -> state（diff 基线）
        last_state: Optional[str] = None
        first = True
        idle = 0.0
        while True:
            events: list[tuple[str, dict]] = []
            finished = False
            session = _stream_session()
            try:
                inst = (
                    session.query(WorkflowInstance)
                    .filter(WorkflowInstance.instance_id == instance_id)
                    .first()
                )
                if inst is None:  # 实例被清理（悬空）→ 收流，前端 onError 降级轮询兜底
                    return
                tasks = (
                    session.query(TaskInstance)
                    .filter(TaskInstance.instance_id == instance_id)
                    .order_by(TaskInstance.id)
                    .all()
                )
                run_events = (
                    session.query(TRunEvent)
                    .filter(TRunEvent.run_id == instance_id, TRunEvent.id > event_cursor)
                    .order_by(TRunEvent.id)
                    .limit(200)
                    .all()
                )
                for run_event in run_events:
                    events.append(("node_event", _run_event_data(run_event)))
                    event_cursor = run_event.id
                for t in tasks:
                    if first or t.state != baseline.get(t.id):
                        events.append(("task_state_changed", {
                            "taskId": t.id, "nodeId": t.node_id, "nodeType": t.node_type,
                            "name": t.name, "state": t.state, "attempt": t.attempt,
                            "loopIter": t.loop_iter or 0,
                            "startTime": fmt_dt(t.start_time), "endTime": fmt_dt(t.end_time),
                        }))
                    baseline[t.id] = t.state
                if inst.state in TERMINAL_STATES and (first or inst.state != last_state):
                    events.append(("instance_finished", {
                        "instanceId": instance_id, "state": inst.state,
                        "endTime": fmt_dt(inst.end_time),
                    }))
                    finished = True
                last_state = inst.state
                first = False
            finally:
                session.close()
            if events:
                idle = 0.0
                for name, payload in events:
                    yield f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
                if finished:
                    return
            else:
                idle += SSE_POLL_SEC
                if idle >= SSE_HEARTBEAT_SEC:
                    yield ": heartbeat\n\n"
                    idle = 0.0
            time.sleep(SSE_POLL_SEC)

    logger.info("实例状态流开启: instance=%s state=%s（用户 %s）", instance_id, row.state, user.user_name)
    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
