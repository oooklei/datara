"""STREAM 工作流实例执行链（2026-10-28 裁决项 3「STREAM 列入本轮后端修补」）.

新域 POST /workflow-instances(instance_type=STREAM) 的执行编排：

1. 画布校验：新域草稿（workflow_node/workflow_edge，version_id IS NULL）
   → GraphDocument → 复用 api.streamjob.extract_stream_spec（混编/缺源汇/
   join 入边校验与旧前端口径同源）。
2. 跨域启动：legacy 通道（REBUILD_LEGACY_DB_URL 指向旧库）复用
   preflight_stream + register_stream_job——t_stream_job upsert（doc_id
   命名空间 "rebuild-{workflow_id}"，worker 只消费 spec_json 不读
   doc_id，与 legacy 画布 id 天然零撞号）+ legacy 实例/任务/日志行 +
   Redis 广播 datara:flink:ctl，全部按既有语义零改动复用。
3. 桥注册：新域 StreamJobRecord 以 legacy_job_id 交叉关联；worker engine
   的四类回报（legacy_bridge sync_state/checkpoints/metrics/failure）据此
   自动落观测面——观摩面板按 workflow_id 绑定、produce/fuse/observe 免接线。

失败语义：legacy 链内部 commit 先于新域桥注册；桥注册失败时流已在
worker 侧启动但暂不可观测，重跑（register upsert + 幂等桥注册）自动补齐。
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from types import SimpleNamespace
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from rebuild.execution.repository import ExecutionDomainError
from rebuild.stream.models import StreamJobRecord
from rebuild.stream.repository import StreamDomainError, StreamRepository
from rebuild.workflow.models import WorkflowDefinitionRecord, WorkflowEdgeRecord, WorkflowNodeRecord

# 桥注册后 UI 生产（produce）面的兜底生产配置：固定速率单列最小合法模式
_PRODUCER_RUNTIME_CONFIG: dict[str, Any] = {"mode": "fixed_rate", "rows_per_sec": 1, "columns": ["id"]}


@lru_cache(maxsize=2)
def _legacy_factory(url: str) -> sessionmaker:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    return sessionmaker(bind=engine, expire_on_commit=False)


def legacy_session_factory() -> sessionmaker | None:
    """legacy 库通道；未配置 REBUILD_LEGACY_DB_URL 时返回 None（调用方报错）。"""
    url = os.environ.get("REBUILD_LEGACY_DB_URL", "").strip()
    return _legacy_factory(url) if url else None


def _draft_graph_document(session: Session, definition_id: int) -> dict[str, Any]:
    """新域草稿节点/边行 → GraphDocument dict（与画布 JSON 同形）。"""
    nodes = session.scalars(
        select(WorkflowNodeRecord)
        .where(WorkflowNodeRecord.definition_id == definition_id, WorkflowNodeRecord.version_id.is_(None))
        .order_by(WorkflowNodeRecord.id)
    ).all()
    edges = session.scalars(
        select(WorkflowEdgeRecord).where(
            WorkflowEdgeRecord.definition_id == definition_id, WorkflowEdgeRecord.version_id.is_(None)
        )
    ).all()
    return {
        "nodes": [
            {"id": node.node_code, "type": node.node_type, "data": json.loads(node.params_json or "{}")}
            for node in nodes
        ],
        "edges": [{"source": edge.from_node, "target": edge.to_node} for edge in edges],
    }


def _derive_mq_topic(spec: dict[str, Any], workflow_id: int) -> str:
    """取首个 stream_input 的 kafka topic；非 kafka 源回落合成 topic。"""
    for node in spec["nodes"]:
        if node["type"] == "stream_input":
            topic = str((node.get("params") or {}).get("topic") or "").strip()
            if topic:
                return topic
    return f"datara.stream.{workflow_id}"


def start_stream_execution(
    *, rebuild_session: Session, definition: WorkflowDefinitionRecord, project_id: int
) -> dict[str, Any]:
    """STREAM 实例启动链：校验 → legacy 图启动 → 桥注册；返回关联信息。"""
    if definition.workflow_type != "STREAM":
        raise ExecutionDomainError(4001, "instance_type=STREAM requires a STREAM workflow definition")
    factory = legacy_session_factory()
    if factory is None:
        raise ExecutionDomainError(5031, "stream legacy channel is not configured (REBUILD_LEGACY_DB_URL)")

    # 局部导入：legacy api 面仅在流启动时加载（隔离 import 副作用）
    from api.auth import ApiError
    from api.streamjob import extract_stream_spec, preflight_stream, register_stream_job

    doc = _draft_graph_document(rebuild_session, definition.id)
    # extract 只读 name；register 另读 id（doc_id）/code（展示冗余，新域无此概念置 0）/version
    stub = SimpleNamespace(
        id=f"rebuild-{definition.id}", code=None, version=definition.current_version or 0, name=definition.name
    )
    try:
        spec = extract_stream_spec(stub, doc)
        with factory() as legacy:
            preflight_stream(legacy, spec)
            legacy_job, restarted = register_stream_job(legacy, stub, spec)
            legacy_job_id = int(legacy_job.id)
    except ApiError as exc:
        raise ExecutionDomainError(4001, str(exc.msg or "stream start failed")) from exc

    record = rebuild_session.scalar(select(StreamJobRecord).where(StreamJobRecord.legacy_job_id == legacy_job_id))
    if record is None:
        try:
            record = StreamRepository(rebuild_session).register(
                definition.name,
                definition.id,
                _derive_mq_topic(spec, definition.id),
                dict(_PRODUCER_RUNTIME_CONFIG),
                legacy_job_id=legacy_job_id,
                project_id=project_id,
            )
        except StreamDomainError as exc:
            raise ExecutionDomainError(exc.code, exc.msg) from exc
    return {
        "legacy_job_id": legacy_job_id,
        "stream_job_id": int(record.id),
        "restarted": restarted,
        "mq_topic": record.mq_topic,
    }
