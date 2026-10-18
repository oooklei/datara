"""R5-B 数据模型（§2.1 五模型 frozen dataclass）。

依 P2-3 v3 实施设计 §2.1：
- ObjectRef: 完整对象引用
- PolicyFinding: 策略发现项
- PolicySnapshot: 策略快照
- ImpactItem: 影响项
- ImpactSnapshot: 影响快照
- ExecutionRecord: 执行记录
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class ObjectRef:
    """完整对象引用。"""
    datasource_id: int
    database: str
    catalog: Optional[str]
    schema: Optional[str]
    kind: str  # table/view/function/procedure/trigger
    name: str
    parent: Optional[str] = None


@dataclass(frozen=True)
class PolicyFinding:
    """策略发现项。"""
    level: str  # block/warn/info
    code: str
    message: str
    impacts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PolicySnapshot:
    """策略快照。"""
    snapshot_id: str  # UUID
    project_id: int
    datasource_id: int
    object_ref: ObjectRef
    source_version: str  # ETag from getDefinition
    next_ddl_digest: str  # SHA-256 of nextDdlText
    policy_version: str
    findings: list[PolicyFinding]
    blocked: bool
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class ImpactItem:
    """影响项。"""
    object_ref: ObjectRef
    relation_type: str  # dependent/downstream/permission
    detail: str


@dataclass(frozen=True)
class ImpactSnapshot:
    """影响快照。"""
    snapshot_id: str  # UUID
    project_id: int
    datasource_id: int
    object_ref: ObjectRef
    source_version: str
    next_ddl_digest: str
    policy_snapshot_id: str  # 绑定同一 policy snapshot
    impacts: list[ImpactItem]
    unknown_reasons: list[str]
    created_at: datetime
    expires_at: datetime


@dataclass
class ExecutionRecord:
    """执行记录。"""
    record_id: str  # UUID
    project_id: int
    datasource_id: int
    object_ref: ObjectRef
    action: str  # DDL action type
    script_hash: str  # SHA-256 of executed DDL
    executed_at: datetime
    status: str  # success/failure/rolled-back/compensated/recovery-failed
    failure_summary: Optional[str]
    policy_snapshot_id: str
    impact_snapshot_id: str
    compensation_refs: list[str]
    actor_id: int  # user who confirmed
