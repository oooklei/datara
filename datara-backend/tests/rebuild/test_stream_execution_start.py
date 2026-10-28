"""STREAM 图执行器测试 — 2026-10-28 裁决项 3「STREAM 列入本轮后端修补」.

Covers: start_stream_execution 的 legacy 图启动链复用（extract/preflight/
register/广播）、doc_id 命名空间、桥注册（StreamJobRecord.legacy_job_id
交叉关联）、重跑 upsert 语义、以及四类失败前置校验。
"""

import json
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session

from rebuild.common.db import Base as RebuildBase
from common import queue
from common.models import Base as LegacyBase, StreamJob as LegacyStreamJob, WorkflowInstance as LegacyWorkflowInstance
from rebuild.execution.stream_executor import (
    start_stream_execution,
)
from rebuild.execution.repository import ExecutionDomainError
from rebuild.stream.models import (
    StreamCheckpointRecord,
    StreamFailureEventRecord,
    StreamJobAttemptRecord,
    StreamJobRecord,
    StreamMetricSnapshotRecord,
    StreamRecoveryEventRecord,
)
from rebuild.workflow.models import (
    WorkflowDefinitionRecord,
    WorkflowEdgeRecord,
    WorkflowNodeRecord,
)

_STREAM_TABLES = (
    StreamJobRecord.__table__,
    StreamJobAttemptRecord.__table__,
    StreamCheckpointRecord.__table__,
    StreamMetricSnapshotRecord.__table__,
    StreamFailureEventRecord.__table__,
    StreamRecoveryEventRecord.__table__,
)


class _PublishStub:
    def __init__(self) -> None:
        self.publishes: list[tuple[str, dict]] = []

    def publish(self, channel: str, payload: str) -> None:
        self.publishes.append((channel, json.loads(payload)))


@pytest.fixture()
def channel(tmp_path, monkeypatch):
    """rebuild 内存库 + legacy 文件库 + 广播/日志桩；返回 (session, stub, tmp_path)。"""
    rebuild_engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    RebuildBase.metadata.create_all(
        rebuild_engine,
        tables=[
            WorkflowDefinitionRecord.__table__,
            WorkflowNodeRecord.__table__,
            WorkflowEdgeRecord.__table__,
            *_STREAM_TABLES,
        ],
    )
    session = Session(rebuild_engine)

    legacy_url = f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}"
    LegacyBase.metadata.create_all(create_engine(legacy_url))
    monkeypatch.setenv("REBUILD_LEGACY_DB_URL", legacy_url)

    stub = _PublishStub()
    monkeypatch.setattr(queue, "get_client", lambda: stub)
    monkeypatch.setattr(
        "api.streamjob.get_settings", lambda: SimpleNamespace(log_dir=str(tmp_path / "logs"))
    )
    yield session, stub, tmp_path
    session.close()


def _seed_definition(
    session: Session,
    *,
    project_id: int = 7,
    wf_type: str = "STREAM",
    nodes: list[tuple[str, str, dict]] | None = None,
    edges: list[tuple[str, str]] | None = None,
) -> WorkflowDefinitionRecord:
    nodes = nodes or [("si1", "stream_input", {"srcType": "simulate"}), ("so1", "stream_output", {})]
    edges = edges or [("si1", "so1")]
    definition = WorkflowDefinitionRecord(
        project_id=project_id, name=f"流图-{uuid.uuid4().hex[:8]}", workflow_type=wf_type
    )
    session.add(definition)
    session.flush()
    for code, node_type, params in nodes:
        session.add(
            WorkflowNodeRecord(
                definition_id=definition.id, node_code=code, node_type=node_type,
                name=code, params_json=json.dumps(params, ensure_ascii=False),
            )
        )
    for source, target in edges:
        session.add(WorkflowEdgeRecord(definition_id=definition.id, from_node=source, to_node=target))
    session.commit()
    return definition


def _legacy_row(legacy_url: str, job_id: int) -> LegacyStreamJob:
    engine = create_engine(legacy_url)
    try:
        with Session(engine) as session:
            return session.get(LegacyStreamJob, job_id)
    finally:
        engine.dispose()


def _legacy_session_of(channel, legacy_url: str, *, run_mode: str = "stream"):
    session, _stub, _tmp = channel
    _ = session
    engine = create_engine(legacy_url)
    try:
        with Session(engine) as legacy:
            return legacy.scalars(
                select(LegacyWorkflowInstance).where(LegacyWorkflowInstance.run_mode == run_mode)
            ).all()
    finally:
        engine.dispose()


def test_stream_start_executes_legacy_chain_and_registers_bridge(channel, monkeypatch):
    session, stub, tmp_path = channel
    definition = _seed_definition(session)
    monkeypatch.setenv("REBUILD_LEGACY_DB_URL", f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}")

    result = start_stream_execution(rebuild_session=session, definition=definition, project_id=7)

    # 返回面：legacy 关联 + 新域桥记录 + 未重启 + 合成 topic（simulate 源无 topic）
    assert result["restarted"] is False
    assert result["mq_topic"] == f"datara.stream.{definition.id}"
    legacy_row = _legacy_row(f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}", result["legacy_job_id"])
    assert legacy_row.doc_id == f"rebuild-{definition.id}"  # 命名空间防撞 legacy 画布 id
    assert legacy_row.generation == 1
    assert legacy_row.status == "starting"
    spec = json.loads(legacy_row.spec_json or "{}")
    assert [node["id"] for node in spec["nodes"]] == ["si1", "so1"]
    assert spec["edges"] == [{"source": "si1", "target": "so1"}]

    # 广播：worker 控制面既有契约
    assert stub.publishes == [
        ("datara:flink:ctl", {"action": "start", "jobId": result["legacy_job_id"], "generation": 1})
    ]

    # 桥记录：legacy_job_id 交叉关联 + workflow 绑定（观摩面板按 workflow_id 定位）
    record = session.scalar(select(StreamJobRecord).where(StreamJobRecord.id == result["stream_job_id"]))
    assert record is not None
    assert record.legacy_job_id == result["legacy_job_id"]
    assert record.workflow_id == definition.id
    assert record.state == "CREATED"

    # legacy 运行实例（旧运行监控可见性保持）
    assert _legacy_session_of(channel, f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}")


def test_stream_start_kafka_topic_derived_from_input_node(channel, monkeypatch):
    session, _stub, tmp_path = channel
    definition = _seed_definition(
        session,
        nodes=[("si1", "stream_input", {"srcType": "kafka", "brokers": "b:9092", "topic": "t1"}), ("so1", "stream_output", {})],
    )
    monkeypatch.setenv("REBUILD_LEGACY_DB_URL", f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}")

    result = start_stream_execution(rebuild_session=session, definition=definition, project_id=7)
    assert result["mq_topic"] == "t1"


def test_stream_start_rerun_reuses_jobs_upsert(channel, monkeypatch):
    session, stub, tmp_path = channel
    definition = _seed_definition(session)
    monkeypatch.setenv("REBUILD_LEGACY_DB_URL", f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}")

    first = start_stream_execution(rebuild_session=session, definition=definition, project_id=7)
    second = start_stream_execution(rebuild_session=session, definition=definition, project_id=7)

    assert first["restarted"] is False and second["restarted"] is True
    assert second["legacy_job_id"] == first["legacy_job_id"]
    assert second["stream_job_id"] == first["stream_job_id"]
    row = _legacy_row(f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}", first["legacy_job_id"])
    assert row.generation == 2  # 先停再起语义
    assert len(session.scalars(select(StreamJobRecord)).all()) == 1  # 桥记录幂等复用
    assert len(stub.publishes) == 2


def test_stream_start_requires_legacy_channel(channel, monkeypatch):
    session, _stub, _tmp = channel
    definition = _seed_definition(session)
    monkeypatch.delenv("REBUILD_LEGACY_DB_URL", raising=False)

    with pytest.raises(ExecutionDomainError) as ei:
        start_stream_execution(rebuild_session=session, definition=definition, project_id=7)
    assert ei.value.code == 5031
    assert "REBUILD_LEGACY_DB_URL" in ei.value.msg


def test_stream_start_rejects_non_stream_definition(channel, monkeypatch):
    session, _stub, tmp_path = channel
    definition = _seed_definition(session, wf_type="NORMAL")
    monkeypatch.setenv("REBUILD_LEGACY_DB_URL", f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}")

    with pytest.raises(ExecutionDomainError) as ei:
        start_stream_execution(rebuild_session=session, definition=definition, project_id=7)
    assert ei.value.code == 4001
    assert "STREAM workflow" in ei.value.msg


def test_stream_start_rejects_mixed_canvas(channel, monkeypatch):
    session, _stub, tmp_path = channel
    definition = _seed_definition(
        session,
        nodes=[("si1", "stream_input", {"srcType": "simulate"}), ("so1", "stream_output", {}), ("x1", "sql", {})],
    )
    monkeypatch.setenv("REBUILD_LEGACY_DB_URL", f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}")

    with pytest.raises(ExecutionDomainError) as ei:
        start_stream_execution(rebuild_session=session, definition=definition, project_id=7)
    assert ei.value.code == 4001
    assert "混编批处理组件" in ei.value.msg


def test_stream_start_requires_sink(channel, monkeypatch):
    session, _stub, tmp_path = channel
    definition = _seed_definition(session, nodes=[("si1", "stream_input", {"srcType": "simulate"})], edges=[])
    monkeypatch.setenv("REBUILD_LEGACY_DB_URL", f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}")

    with pytest.raises(ExecutionDomainError) as ei:
        start_stream_execution(rebuild_session=session, definition=definition, project_id=7)
    assert ei.value.code == 4001
    assert "stream_output" in ei.value.msg
