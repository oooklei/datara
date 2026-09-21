"""同步任务监控 API（I6 设计文档 §6，F34）。

- GET /sync-tasks                       打「同步」标签的工作流定义 + 最近实例与读写统计聚合（监控视角）
- GET /sync-tasks/{wf_code}/instances   指定同步工作流实例明细（含 sync 节点读写统计）
- 批次号=运行实例 instance_id（裁定③）；读写统计读 t_task_instance.outputs（F33 执行器输出）
- 同步标签定位：定义数小（几十级），Python 侧过滤 tags JSON（避免 MySQL JSON contains 方言差异）
"""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.auth import ApiError, get_current_user, require_perm
from common.db import get_db
from common.models import TaskInstance, User, WfDefinition, WorkflowInstance
from common.resp import WF_NOT_FOUND, WF_PARAM_INVALID, PageQuery, fmt_dt, ok, page_result

router = APIRouter(prefix="/sync-tasks", tags=["sync"])

SYNC_TAG = "同步"


def _sync_outputs(db: Session, instance_id: str) -> dict:
    """实例内全部 sync 节点任务输出聚合（多 sync 节点求和；schemas 取并集保序）。"""
    rows = (
        db.query(TaskInstance)
        .filter(TaskInstance.instance_id == instance_id, TaskInstance.node_type == "sync")
        .all()
    )
    agg = {"readRows": 0, "writeRows": 0, "badRows": 0, "batchId": instance_id, "schemas": []}
    for row in rows:
        out = row.outputs or {}
        agg["readRows"] += int(out.get("read_rows") or 0)
        agg["writeRows"] += int(out.get("write_rows") or 0)
        agg["badRows"] += int(out.get("bad_rows") or 0)
        for s in out.get("schemas_included") or []:
            if s and s not in agg["schemas"]:
                agg["schemas"].append(str(s))
    return agg


def _tagged_definitions(db: Session, keyword: str) -> list:
    """tags 含「同步」的定义列表（关键字过滤 name，按 id 倒序）。"""
    rows = db.query(WfDefinition).order_by(WfDefinition.id.desc()).all()
    out = []
    for row in rows:
        tags = row.tags or []
        if SYNC_TAG not in tags:
            continue
        if keyword and keyword.lower() not in str(row.name or "").lower():
            continue
        out.append(row)
    return out


@router.get("")
def list_sync_tasks(
    page: PageQuery = Depends(),
    keyword: Optional[str] = None,
    state: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """同步任务列表（F34）：打标定义聚合最近实例状态与读写统计；keyword/state 筛选。"""
    defs = _tagged_definitions(db, str(keyword or "").strip())
    items = []
    for d in defs:
        inst_query = db.query(WorkflowInstance).filter(WorkflowInstance.wf_code == d.code)
        instance_count = inst_query.count()
        last = inst_query.order_by(WorkflowInstance.id.desc()).first()
        item = {
            "wfCode": d.code,
            "name": d.name,
            "tags": d.tags or [],
            "instanceCount": instance_count,
            "lastInstanceId": None,
            "lastState": None,
            "lastTime": None,
            "readRows": 0,
            "writeRows": 0,
            "badRows": 0,
            "schemas": [],
        }
        if last is not None and (not state or last.state == state):
            agg = _sync_outputs(db, last.instance_id)
            item.update(
                {
                    "lastInstanceId": last.instance_id,
                    "lastState": last.state,
                    "lastTime": fmt_dt(last.start_time or last.create_time),
                    "readRows": agg["readRows"],
                    "writeRows": agg["writeRows"],
                    "badRows": agg["badRows"],
                    "schemas": agg["schemas"],
                }
            )
        items.append(item)
    if state:
        items = [i for i in items if i["lastState"] == state]
    total = len(items)
    start = page.offset
    return ok(page_result(total, items[start: start + page.page_size]))


@router.get("/{wf_code}/instances")
def list_sync_instances(
    wf_code: int,
    page: PageQuery = Depends(),
    state: Optional[str] = None,
    user: User = Depends(require_perm("view_all")),
    db: Session = Depends(get_db),
):
    """同步工作流实例明细（分页倒序；每实例聚合 sync 节点读写统计，批次号=instance_id）。"""
    definition = db.query(WfDefinition).filter(WfDefinition.code == wf_code).first()
    if definition is None:
        raise ApiError(WF_NOT_FOUND, status=404)
    tags = definition.tags or []
    if SYNC_TAG not in tags:
        raise ApiError(WF_PARAM_INVALID, "工作流未打同步标签: %s" % definition.name)
    query = db.query(WorkflowInstance).filter(WorkflowInstance.wf_code == wf_code)
    if state:
        query = query.filter(WorkflowInstance.state == state)
    total = query.count()
    rows = query.order_by(WorkflowInstance.id.desc()).offset(page.offset).limit(page.page_size).all()
    items = []
    for row in rows:
        agg = _sync_outputs(db, row.instance_id)
        items.append(
            {
                "instanceId": row.instance_id,
                "state": row.state,
                "runMode": row.run_mode or "manual",
                "startTime": fmt_dt(row.start_time),
                "endTime": fmt_dt(row.end_time),
                "batchId": agg["batchId"],
                "readRows": agg["readRows"],
                "writeRows": agg["writeRows"],
                "badRows": agg["badRows"],
                "schemas": agg["schemas"],
            }
        )
    return ok(page_result(total, items))
