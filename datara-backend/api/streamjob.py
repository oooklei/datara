"""流任务 API（I8 F40/F41，裁定②：master 只注册/透传，不持有引擎）。

- POST /stream-jobs/start：解析画布流子图 → spec 校验 → upsert t_stream_job（generation+1、
  status=starting、host=NULL）→ Redis 广播 datara:flink:ctl start（worker 原子认领后起线程）
- POST /stream-jobs/{id}/stop：status=stopped + host=NULL + 广播 stop
- GET  /stream-jobs：列表（doc_id 筛选，合并 Redis 指标镜像）
- GET  /stream-jobs/{id}：详情；GET /stream-jobs/{id}/logs：日志尾（Redis List Last-500）
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from common import queue
from common.db import get_db
from common.log import get_logger
from common.models import StreamJob, WfDefinition
from common.resp import (
    INSTANCE_NOT_FOUND,
    WF_NOT_FOUND,
    WF_PARAM_INVALID,
    fmt_dt,
    ok,
)
from api.auth import ApiError, require_perm

logger = get_logger("api.streamjob")

router = APIRouter(prefix="/stream-jobs", tags=["stream-job"])

STREAM_TYPES = ("stream_input", "stream_fuse", "stream_output")


class StartBody(BaseModel):
    doc_id: str


def _load_doc(db: Session, doc_id: str) -> tuple[WfDefinition, dict]:
    definition = db.get(WfDefinition, doc_id)
    if definition is None:
        raise ApiError(WF_NOT_FOUND, status=404)
    try:
        doc = json.loads(definition.graph_json) if definition.graph_json else {}
    except ValueError:
        raise ApiError(WF_PARAM_INVALID, "画布 JSON 解析失败", status=400) from None
    if not isinstance(doc, dict):
        raise ApiError(WF_PARAM_INVALID, "画布 JSON 非法", status=400)
    return definition, doc


def extract_stream_spec(definition: WfDefinition, doc: dict) -> dict:
    """GraphDocument → 流子图 spec（校验混编/缺源汇/join 入边/游离，与前端 streamSubgraphIssues 同口径）。"""
    raw_nodes = doc.get("nodes") or []
    nodes = [n for n in raw_nodes if isinstance(n, dict) and n.get("type") in STREAM_TYPES]
    if not nodes:
        raise ApiError(WF_PARAM_INVALID, "画布无流组件（需 stream_input/stream_fuse/stream_output）", status=400)
    if len(nodes) != len(raw_nodes):
        raise ApiError(WF_PARAM_INVALID, "流任务画布不允许混编批处理组件", status=400)
    ids = {str(n["id"]) for n in nodes}
    edges = [
        {"source": str(e["source"]), "target": str(e["target"])}
        for e in (doc.get("edges") or [])
        if isinstance(e, dict) and e.get("source") in ids and e.get("target") in ids
    ]
    ins: dict[str, int] = {}
    outs: dict[str, int] = {}
    for e in edges:
        outs[e["source"]] = outs.get(e["source"], 0) + 1
        ins[e["target"]] = ins.get(e["target"], 0) + 1
    n_src = sum(1 for n in nodes if n["type"] == "stream_input")
    n_sink = sum(1 for n in nodes if n["type"] == "stream_output")
    if n_src == 0:
        raise ApiError(WF_PARAM_INVALID, "流子图缺少输入源（stream_input）", status=400)
    if n_sink == 0:
        raise ApiError(WF_PARAM_INVALID, "流子图缺少输出汇（stream_output）", status=400)
    for n in nodes:
        nid = str(n["id"])
        if ins.get(nid, 0) == 0 and outs.get(nid, 0) == 0:
            raise ApiError(WF_PARAM_INVALID, f"存在游离节点: {nid}", status=400)
        if n["type"] == "stream_fuse" and str((n.get("data") or {}).get("fuseType") or "") == "join" \
                and ins.get(nid, 0) != 2:
            raise ApiError(WF_PARAM_INVALID, f"join 融合节点须两条入边: {nid}", status=400)
    return {
        "name": definition.name,
        "nodes": [{"id": str(n["id"]), "type": n["type"], "params": dict(n.get("data") or {})} for n in nodes],
        "edges": edges,
    }


def register_stream_job(db: Session, definition: WfDefinition, spec: dict) -> tuple[StreamJob, bool]:
    """upsert t_stream_job（一画布一流任务，先停再起语义）+ Redis 广播；返回 (任务行, 是否重启)。"""
    row = db.query(StreamJob).filter(StreamJob.doc_id == definition.id).first()
    restarted = row is not None
    if row is None:
        row = StreamJob(doc_id=definition.id, generation=0)
        db.add(row)
    row.generation = int(row.generation or 0) + 1
    row.status = "starting"
    row.host = None
    row.last_error = None
    row.wf_code = int(definition.code) if definition.code else 0
    row.wf_name = definition.name
    row.name = definition.name
    row.spec_json = json.dumps(spec, ensure_ascii=False)
    db.commit()

    queue.get_client().publish("datara:flink:ctl", json.dumps(
        {"action": "start", "jobId": row.id, "generation": int(row.generation)}))
    logger.info("流任务启动广播: job=%s doc=%s gen=%s", row.id, definition.id, row.generation)
    return row, restarted


@router.post("/start")
def start_stream_job(
    body: StartBody,
    user=Depends(require_perm("run_instance")),
    db: Session = Depends(get_db),
):
    """启动/重启流任务（同画布唯一；已有任务先停再起，幂等）。"""
    definition, doc = _load_doc(db, body.doc_id)
    spec = extract_stream_spec(definition, doc)
    row, restarted = register_stream_job(db, definition, spec)
    logger.info("流任务启动请求: job=%s doc=%s（用户 %s）", row.id, body.doc_id, user.user_name)
    return ok({"id": row.id, "name": row.name, "restarted": restarted})


@router.post("/{job_id}/stop")
def stop_stream_job(
    job_id: int,
    user=Depends(require_perm("run_instance")),
    db: Session = Depends(get_db),
):
    """停止流任务：置终态 + 清宿主 + 广播（worker 本地命中即停线程）。"""
    row = db.get(StreamJob, job_id)
    if row is None:
        raise ApiError(INSTANCE_NOT_FOUND, status=404)
    row.status = "stopped"
    row.host = None
    db.commit()
    queue.get_client().publish("datara:flink:ctl", json.dumps(
        {"action": "stop", "jobId": job_id, "generation": int(row.generation or 0)}))
    logger.info("流任务停止广播: job=%s（用户 %s）", job_id, user.user_name)
    return ok(True)


def _row_payload(row: StreamJob, client) -> dict:
    metrics = None
    try:
        raw = client.hgetall(f"datara:flink:metrics:{row.id}")
        if raw:
            metrics = raw
    except Exception:  # noqa: BLE001 指标镜像缺失不阻断列表
        pass
    return {
        "id": row.id,
        "docId": row.doc_id,
        "wfName": row.wf_name,
        "name": row.name,
        "status": row.status,
        "lastError": row.last_error,
        "startedAt": fmt_dt(row.started_at),
        "updatedAt": fmt_dt(row.update_time),
        "metrics": metrics,
    }


@router.get("")
def list_stream_jobs(
    doc_id: Optional[str] = None,
    page_size: int = Query(default=50, ge=1, le=200),
    user=Depends(require_perm("view_all")),
    db: Session = Depends(get_db),
):
    """流任务列表（doc_id 筛选；合并 Redis 指标镜像，无则 null）。"""
    q = db.query(StreamJob)
    if doc_id:
        q = q.filter(StreamJob.doc_id == doc_id)
    rows = q.order_by(StreamJob.id.desc()).limit(page_size).all()
    client = queue.get_client()
    return ok([_row_payload(r, client) for r in rows])


@router.get("/{job_id}")
def get_stream_job(
    job_id: int,
    user=Depends(require_perm("view_all")),
    db: Session = Depends(get_db),
):
    """流任务详情（含指标镜像）。"""
    row = db.get(StreamJob, job_id)
    if row is None:
        raise ApiError(INSTANCE_NOT_FOUND, status=404)
    return ok(_row_payload(row, queue.get_client()))


@router.get("/{job_id}/logs")
def get_stream_job_logs(
    job_id: int,
    lines: int = Query(default=60, ge=1, le=500),
    user=Depends(require_perm("view_all")),
    db: Session = Depends(get_db),
):
    """日志尾：Redis List datara:flink:logs:{id}（LPUSH 存储，倒序取尾翻正）。"""
    if db.get(StreamJob, job_id) is None:
        raise ApiError(INSTANCE_NOT_FOUND, status=404)
    raw = queue.get_client().lrange(f"datara:flink:logs:{job_id}", 0, lines - 1)
    return ok(list(reversed(raw)))
