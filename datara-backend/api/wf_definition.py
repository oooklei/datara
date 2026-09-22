"""工作流定义路由：列表分页 / 新建 / 读取 / 保存 / 删除 / 版本列表 / 回滚。

契约对齐前端 IGraphService（src/services/types.ts）：
- get(id) → GET  /{id}                返回 graph_json 原样 JSON
- save(doc, remark) → PUT /{id}/save  version+1 + 追加版本快照 → {version}
- listVersions(id) → GET /{id}/versions  [{version, updatedAt, operator, remark}]
- rollback(id, version) → POST /{id}/rollback  恢复快照内容并再追加新版本
"""

import json
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.auth import ApiError, require_perm
from api.commands import submit_command
from api.streamjob import STREAM_TYPES, extract_stream_spec, register_stream_job
from common.db import get_db
from common.log import get_logger
from common.models import (
    StreamJob,
    StreamOffset,
    User,
    WfCategory,
    WfDefinition,
    WfDefinitionLog,
    WfSchedule,
    WorkflowInstance,
    now,
)
from common.resp import (
    WF_NOT_FOUND,
    WF_PARAM_INVALID,
    WF_VERSION_CONFLICT,
    WF_VERSION_NOT_FOUND,
    PageQuery,
    fail,
    fmt_dt,
    ok,
    page_result,
)
from master.state import ACTIVE_STATES

logger = get_logger("api.wf_definition")

router = APIRouter(prefix="/workflow-definitions", tags=["wf-definition"])


class CreateBody(BaseModel):
    name: str


class SaveBody(BaseModel):
    doc: dict
    remark: Optional[str] = None
    tags: Optional[List[str]] = None  # I6：C23 保存自动打「同步」标签通道（缺省不改动既有标签）
    base_version: Optional[int] = None  # I12-D2 并发保护：加载时的版本号；缺省=不校验（兼容旧客户端）


class RollbackBody(BaseModel):
    version: int


def _empty_doc(wf_id: str, name: str) -> dict:
    """最小空 GraphDocument（形状对齐 datara-web/src/graph/model 的 GraphDocument）。"""
    return {"id": wf_id, "name": name, "version": 1, "meta": {"profile": "dag"}, "nodes": [], "edges": []}


def _next_code(db: Session) -> int:
    """雪花式数字编码：max(code)+1（I1 单实例写入，I3 再精化为真雪花）。"""
    max_code = db.query(func.max(WfDefinition.code)).scalar()
    return (max_code or 0) + 1


def _get_or_404(db: Session, wf_id: str) -> WfDefinition:
    definition = db.get(WfDefinition, wf_id)
    if definition is None:
        raise ApiError(WF_NOT_FOUND, status=404)
    return definition


def _append_log(db: Session, definition: WfDefinition, operator: str, remark: Optional[str]) -> None:
    """追加版本快照（save/回滚共用）。"""
    db.add(
        WfDefinitionLog(
            wf_code=definition.code,
            version=definition.version,
            graph_json=definition.graph_json,
            operator=operator,
            remark=remark,
        )
    )


def _node_count(graph_json: Optional[str]) -> int:
    """graph_json 节点数（I1 遗留回填 §12；解析失败计 0）。"""
    if not graph_json:
        return 0
    try:
        doc = json.loads(graph_json)
        return len(doc.get("nodes") or [])
    except (ValueError, TypeError):
        return 0


@router.get("")
def list_definitions(page: PageQuery = Depends(), search: Optional[str] = None, db: Session = Depends(get_db)):
    """定义列表（分页 + name 模糊），倒序按更新时间；回填 cron/nodeCount（I3 §12）。"""
    query = db.query(WfDefinition)
    if search:
        query = query.filter(WfDefinition.name.like("%" + search + "%"))
    total = query.count()
    rows = (
        query.order_by(WfDefinition.update_time.desc(), WfDefinition.code.desc())
        .offset(page.offset)
        .limit(page.page_size)
        .all()
    )
    # owner 批量取用户名（避免 N+1 查询）
    owner_ids = {row.owner_id for row in rows if row.owner_id}
    owners = {}
    if owner_ids:
        for user in db.query(User).filter(User.id.in_(owner_ids)).all():
            owners[user.id] = user.user_name
    # cron 回填：各 code 最新 online schedule 的 crontab（单查询避免 N+1）
    cron_map = {}
    codes = {row.code for row in rows}
    if codes:
        schedules = (
            db.query(WfSchedule)
            .filter(WfSchedule.wf_code.in_(codes), WfSchedule.state == "online")
            .order_by(WfSchedule.id.desc())
            .all()
        )
        for schedule in schedules:
            cron_map.setdefault(schedule.wf_code, schedule.crontab)
    items = [
        {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "version": row.version,
            "releaseState": row.release_state,
            "owner": owners.get(row.owner_id, ""),
            "updatedAt": fmt_dt(row.update_time),
            "tags": row.tags or [],
            "cron": cron_map.get(row.code),
            "nodeCount": _node_count(row.graph_json),
        }
        for row in rows
    ]
    return ok(page_result(total, items))


@router.post("")
def create_definition(
    body: CreateBody,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """新建定义：id='wf_'+uuid8、code 自增、version=1、空 GraphDocument + v1 快照。"""
    if not body.name or not body.name.strip():
        return fail(WF_PARAM_INVALID, "工作流名称不能为空")
    wf_id = "wf_" + uuid.uuid4().hex[:8]
    definition = WfDefinition(
        id=wf_id,
        code=_next_code(db),
        name=body.name.strip(),
        version=1,
        release_state="offline",
        flag="yes",
        project_code="default",
        tags=[],
        graph_json=json.dumps(_empty_doc(wf_id, body.name.strip()), ensure_ascii=False),
        owner_id=user.id,
    )
    db.add(definition)
    db.flush()
    _append_log(db, definition, user.user_name, "创建")
    db.commit()
    logger.info("新建工作流定义: %s %s", definition.id, definition.name)
    return ok({"id": definition.id, "code": definition.code, "version": definition.version})


# ---------------- 分类目录（I11：Palette 工作流分组；内置 同步/ETL/流 + 自定义 t_wf_category） ----------------

BUILTIN_CATEGORIES = ("同步", "ETL", "流")


class CategoryBody(BaseModel):
    name: str


class TagsBody(BaseModel):
    tags: Optional[List[str]] = None


@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    """分类目录清单：内置三组 + 自定义目录（t_wf_category，全用户可见）。"""
    items = [{"id": "builtin:%s" % c, "name": c, "builtin": True} for c in BUILTIN_CATEGORIES]
    for row in db.query(WfCategory).order_by(WfCategory.id).all():
        items.append({"id": "custom:%s" % row.id, "name": row.name, "builtin": False})
    return ok(items)


@router.post("/categories")
def create_category(
    body: CategoryBody,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """新建自定义分类目录（重名拒绝：内置名/已有自定义名）。"""
    name = (body.name or "").strip()
    if not name:
        return fail(WF_PARAM_INVALID, "分类目录名不能为空")
    if name in BUILTIN_CATEGORIES:
        return fail(WF_PARAM_INVALID, "「%s」为内置分类目录，无需新建" % name)
    exists = db.query(WfCategory).filter(WfCategory.name == name).first()
    if exists is not None:
        return fail(WF_PARAM_INVALID, "分类目录「%s」已存在" % name)
    row = WfCategory(name=name)
    db.add(row)
    db.commit()
    logger.info("新建分类目录: %s（操作人 %s）", name, user.user_name)
    return ok({"id": "custom:%s" % row.id, "name": row.name, "builtin": False})


@router.delete("/categories/{cat_id}")
def delete_category(
    cat_id: int,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """删除自定义分类目录：同时摘除各工作流定义上的同名标签（回归普通）。"""
    row = db.get(WfCategory, cat_id)
    if row is None:
        raise ApiError(WF_NOT_FOUND, status=404)
    for definition in db.query(WfDefinition).filter(WfDefinition.tags.isnot(None)).all():
        if row.name in (definition.tags or []):
            definition.tags = [t for t in definition.tags if t != row.name]
    db.delete(row)
    db.commit()
    logger.info("删除分类目录: %s（操作人 %s）", row.name, user.user_name)
    return ok(True)


@router.put("/{wf_id}/tags")
def set_definition_tags(
    wf_id: str,
    body: TagsBody,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """设置工作流分类标签（不 bump version、不动 graph_json；Palette 移动分类落地）。"""
    definition = _get_or_404(db, wf_id)
    definition.tags = [t for t in (body.tags or []) if t.strip()]
    db.commit()
    logger.info("设置分类标签: %s → %s（操作人 %s）", wf_id, definition.tags, user.user_name)
    return ok({"tags": definition.tags})


@router.get("/{wf_id}")
def get_definition(wf_id: str, db: Session = Depends(get_db)):
    """读取：返回当前版本 graph_json 原样 JSON（GraphDocument）。

    I12-D2：doc.version 显式回写库内权威版本号（前端保存时作 base_version 参与乐观锁）。
    """
    definition = _get_or_404(db, wf_id)
    doc = json.loads(definition.graph_json) if definition.graph_json else _empty_doc(definition.id, definition.name)
    doc["version"] = definition.version
    return ok(doc)


@router.put("/{wf_id}/save")
def save_definition(
    wf_id: str,
    body: SaveBody,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """保存：version+1 → 更新 definition + 追加版本快照 → 返回 {version}。

    I12-D2 乐观锁：base_version 非缺省时与库内 version 比对，不一致返回 409（CAS）。
    I12-M1（评审）：写库改 CAS 条件更新（WHERE version=base_version），消除读-写间隙的
    TOCTOU 双过窗口；base_version 缺省（旧客户端）保持原无条件更新路径，行为不变。
    """
    definition = _get_or_404(db, wf_id)
    doc = body.doc
    if not isinstance(doc, dict) or doc.get("id") != wf_id:
        raise ApiError(WF_PARAM_INVALID, "doc.id 与路径不一致")
    base_version = body.base_version
    if base_version is not None and base_version != definition.version:
        logger.warning("保存版本冲突: wf=%s 库内 v%s，提交基于 v%s（操作人 %s）",
                       wf_id, definition.version, base_version, user.user_name)
        raise ApiError(
            WF_VERSION_CONFLICT,
            "定义已被他人更新（当前 v%s，提交基于 v%s），请刷新后重试" % (definition.version, base_version),
            status=409,
        )
    next_version = definition.version + 1
    doc["version"] = next_version
    graph_json = json.dumps(doc, ensure_ascii=False)
    values = {
        "version": next_version,
        "name": doc.get("name") or definition.name,
        "graph_json": graph_json,
        "update_time": now(),
    }
    if body.tags is not None:
        values["tags"] = body.tags
    if base_version is not None:
        # CAS 条件更新：并发窗口内他人已 bump version 时 rowcount=0，拒绝而非覆盖
        matched = (
            db.query(WfDefinition)
            .filter(WfDefinition.id == wf_id, WfDefinition.version == base_version)
            .update(values, synchronize_session=False)
        )
        if matched == 0:
            logger.warning("保存 CAS 失败: wf=%s 库内 v%s，提交基于 v%s（操作人 %s）",
                           wf_id, definition.version, base_version, user.user_name)
            raise ApiError(
                WF_VERSION_CONFLICT,
                "定义已被他人更新（当前 v%s，提交基于 v%s），请刷新后重试" % (definition.version, base_version),
                status=409,
            )
        db.refresh(definition)  # 同步内存对象（_append_log 需读新 version/graph_json）
    else:
        # 旧客户端：无条件更新（原路径），行为不变
        definition.version = next_version
        definition.name = values["name"]
        definition.graph_json = graph_json
        if body.tags is not None:
            definition.tags = body.tags
    _append_log(db, definition, user.user_name, body.remark)
    db.commit()
    logger.info("保存工作流定义: %s → v%s", wf_id, next_version)
    return ok({"version": next_version})


# 流任务活跃状态（宿主 worker 常驻线程在跑，阻塞删除；对齐 api/streamjob.py 状态注释）
STREAM_ACTIVE_STATUS = ("starting", "running", "reconnecting")


@router.delete("/{wf_id}")
def delete_definition(
    wf_id: str,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """删除（I12-D3 级联口径）：

    - 活跃实例（t_workflow_instance，ACTIVE_STATES：submitted/waiting_dependency/running/
      retry/fault_tolerance）→ 拒绝 409
    - 活跃流任务（t_stream_job.doc_id，starting/running/reconnecting）→ 拒绝 409 提示先停
    - 无阻塞 → 级联删除：调度（t_wf_schedule）、停止态流任务行及其位点（t_stream_offset）、
      版本快照（t_wf_definition_log）、定义行
    """
    definition = _get_or_404(db, wf_id)
    running = (
        db.query(WorkflowInstance)
        .filter(WorkflowInstance.wf_code == definition.code, WorkflowInstance.state.in_(ACTIVE_STATES))
        .count()
    )
    if running:
        logger.warning("删除被拒（存在活跃实例）: wf=%s id=%s 活跃实例数=%d（操作人 %s）",
                       definition.code, wf_id, running, user.user_name)
        raise ApiError(WF_PARAM_INVALID, "该工作流存在 %d 个活跃（未终态）实例，请先停止实例后再删除" % running,
                       status=409)
    stream_jobs = db.query(StreamJob).filter(StreamJob.doc_id == definition.id).all()
    active = [j for j in stream_jobs if (j.status or "") in STREAM_ACTIVE_STATUS]
    if active:
        logger.warning("删除被拒（存在活跃流任务）: wf=%s id=%s job=%s（操作人 %s）",
                       definition.code, wf_id,
                       "、".join("#%s %s" % (j.id, j.name or j.wf_name) for j in active[:3]), user.user_name)
        raise ApiError(WF_PARAM_INVALID, "该画布存在未停止的流任务（%s），请先在流任务列表停止后再删除"
                       % "、".join("#%s %s" % (j.id, j.name or j.wf_name) for j in active[:3]), status=409)
    for job in stream_jobs:
        db.query(StreamOffset).filter(StreamOffset.job_id == job.id).delete()
        db.delete(job)
    db.query(WfSchedule).filter(WfSchedule.wf_code == definition.code).delete()
    db.query(WfDefinitionLog).filter(WfDefinitionLog.wf_code == definition.code).delete()
    db.delete(definition)
    db.commit()
    logger.info("删除工作流定义: %s（操作人 %s；级联调度/停止态流任务/快照）", wf_id, user.user_name)
    return ok(True)


@router.get("/{wf_id}/versions")
def list_versions(wf_id: str, db: Session = Depends(get_db)):
    """版本列表：快照倒序 [{version, updatedAt, operator, remark}]。"""
    definition = _get_or_404(db, wf_id)
    rows = (
        db.query(WfDefinitionLog)
        .filter(WfDefinitionLog.wf_code == definition.code)
        .order_by(WfDefinitionLog.version.desc())
        .all()
    )
    items = [
        {
            "version": row.version,
            "updatedAt": fmt_dt(row.operate_time),
            "operator": row.operator or "",
            "remark": row.remark,
        }
        for row in rows
    ]
    return ok(items)


@router.post("/{wf_id}/rollback")
def rollback(
    wf_id: str,
    body: RollbackBody,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """回滚：取指定版本快照 graph_json 覆盖 definition，并再追加新版本（历史不丢）。"""
    definition = _get_or_404(db, wf_id)
    snapshot = (
        db.query(WfDefinitionLog)
        .filter(WfDefinitionLog.wf_code == definition.code, WfDefinitionLog.version == body.version)
        .first()
    )
    if snapshot is None or not snapshot.graph_json:
        raise ApiError(WF_VERSION_NOT_FOUND, status=404)
    definition.version = definition.version + 1
    definition.graph_json = snapshot.graph_json
    doc = json.loads(snapshot.graph_json)
    doc["version"] = definition.version
    definition.graph_json = json.dumps(doc, ensure_ascii=False)
    _append_log(db, definition, user.user_name, "回滚自 v%s" % body.version)
    db.commit()
    logger.info("回滚工作流定义: %s → 恢复 v%s 快照，新版本 v%s", wf_id, body.version, definition.version)
    return ok(doc)


# ---------------- 运行 / 补数（I3 §3.1/§9.2：api 只写 t_command，master 消费） ----------------

def _resolve_wf(db: Session, wf: str) -> WfDefinition:
    """路径参数兼容定义 id（wf_xxx）与数字 code（§12 路由按 code）。"""
    definition = db.get(WfDefinition, wf)
    if definition is None and wf.isdigit():
        definition = db.query(WfDefinition).filter(WfDefinition.code == int(wf)).first()
    if definition is None:
        raise ApiError(WF_NOT_FOUND, status=404)
    return definition


class RunBody(BaseModel):
    env_group_id: Optional[int] = None
    priority: int = 3


@router.post("/{wf}/run")
def run_workflow(
    wf: str,
    body: RunBody,
    user: User = Depends(require_perm("run_instance")),
    db: Session = Depends(get_db),
):
    """手工启动实例：写 START_PROCESS（run_mode=manual）命令，master 2s 内消费建实例。

    I8 流分支：画布全部为流组件（C18/C19/C20）→ 启动/重启常驻流任务（幂等先停再起，
    无发布流程，裁定①），返回 {mode:'stream', streamJobId,...}；混编拒绝。
    """
    definition = _resolve_wf(db, wf)
    doc = json.loads(definition.graph_json) if definition.graph_json else {}
    if not (doc.get("nodes") or []):
        raise ApiError(WF_PARAM_INVALID, "画布为空，无法运行", status=400)
    stream_nodes = [n for n in doc.get("nodes") or [] if isinstance(n, dict) and n.get("type") in STREAM_TYPES]
    if stream_nodes:
        spec = extract_stream_spec(definition, doc)  # 含混编/缺源汇/join/游离校验
        row, restarted = register_stream_job(db, definition, spec)
        logger.info("流任务启动（试运行入口）: job=%s wf=%s（用户 %s）", row.id, wf, user.user_name)
        return ok({
            "mode": "stream",
            "streamJobId": row.id,
            "name": row.name,
            "restarted": restarted,
        })
    command = submit_command(db, "START_PROCESS", {
        "wfCode": definition.code,
        "wfVersion": definition.version,
        "runMode": "manual",
        "envGroupId": body.env_group_id,
    }, priority=body.priority)
    logger.info("运行命令已提交: wf=%s commandId=%s（用户 %s）", definition.code, command.id, user.user_name)
    return ok({"commandId": command.id})


class ComplementBody(BaseModel):
    date_from: str
    date_to: str
    parallel: bool = False
    env_group_id: Optional[int] = None
    priority: int = 3


@router.post("/{wf}/complement")
def complement_workflow(
    wf: str,
    body: ComplementBody,
    user: User = Depends(require_perm("run_instance")),
    db: Session = Depends(get_db),
):
    """补数提交（§9.2）：写 COMPLEMENT_DATA 命令，master 按日期展开 N 条 START_PROCESS。"""
    definition = _resolve_wf(db, wf)
    try:
        start = datetime.strptime(body.date_from, "%Y-%m-%d")
        end = datetime.strptime(body.date_to, "%Y-%m-%d")
    except ValueError:
        raise ApiError(WF_PARAM_INVALID, "补数日期格式应为 YYYY-MM-DD", status=400)
    if end < start:
        raise ApiError(WF_PARAM_INVALID, "date_to 早于 date_from", status=400)
    command = submit_command(db, "COMPLEMENT_DATA", {
        "wfCode": definition.code,
        "wfVersion": definition.version,
        "dateFrom": body.date_from,
        "dateTo": body.date_to,
        "parallel": body.parallel,
        "envGroupId": body.env_group_id,
    }, priority=body.priority)
    days = (end - start).days + 1
    logger.info("补数命令已提交: wf=%s %s ~ %s 共 %d 实例（%s）",
                definition.code, body.date_from, body.date_to, days,
                "并行" if body.parallel else "串行")
    return ok({"commandId": command.id, "instances": days})
