"""R5-B DDL 专用执行记录持久化仓库（§2.2 表定义）。

依 P2-3 v3 实施设计 §2.2 + S36 勘误②：
统一 ENGINE=InnoDB CHARSET=utf8mb4。

使用 SQLAlchemy ORM Base，通过 MigrationRunner 管理迁移。
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base


class RbPolicySnapshotRecord(Base):
    """rb_policy_snapshots 表。"""
    __tablename__ = "rb_policy_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    datasource_id: Mapped[int] = mapped_column(Integer, nullable=False)
    object_ref: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_version: Mapped[str] = mapped_column(String(128), nullable=False)
    next_ddl_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    findings: Mapped[list] = mapped_column(JSON, nullable=False)
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class RbImpactSnapshotRecord(Base):
    """rb_impact_snapshots 表。"""
    __tablename__ = "rb_impact_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    datasource_id: Mapped[int] = mapped_column(Integer, nullable=False)
    object_ref: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_version: Mapped[str] = mapped_column(String(128), nullable=False)
    next_ddl_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    impacts: Mapped[list] = mapped_column(JSON, nullable=False)
    unknown_reasons: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class RbExecutionRecordRecord(Base):
    """rb_execution_records 表。"""
    __tablename__ = "rb_execution_records"

    record_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    datasource_id: Mapped[int] = mapped_column(Integer, nullable=False)
    object_ref: Mapped[dict] = mapped_column(JSON, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    script_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    failure_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    policy_snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False)
    impact_snapshot_id: Mapped[str] = mapped_column(String(36), nullable=False)
    compensation_refs: Mapped[list] = mapped_column(JSON, nullable=False)
    actor_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)


RB_TABLES = (
    RbPolicySnapshotRecord.__table__,
    RbImpactSnapshotRecord.__table__,
    RbExecutionRecordRecord.__table__,
)


class ExecutionLedgerRepository:
    """R5-B DDL 专用执行记录仓库。"""

    def __init__(self, session_factory):
        self.session_factory = session_factory

    def record_execution(self, record) -> str:
        """记录 DDL 执行结果。append-only。"""
        db_record = RbExecutionRecordRecord(
            record_id=record.record_id,
            project_id=record.project_id,
            datasource_id=record.datasource_id,
            object_ref=record.object_ref.__dict__,
            action=record.action,
            script_hash=record.script_hash,
            executed_at=record.executed_at,
            status=record.status,
            failure_summary=record.failure_summary,
            policy_snapshot_id=record.policy_snapshot_id,
            impact_snapshot_id=record.impact_snapshot_id,
            compensation_refs=record.compensation_refs,
            actor_id=record.actor_id,
        )
        with self.session_factory() as session, session.begin():
            session.add(db_record)
        return record.record_id

    def record_compensation(self, original_record_id: str, compensation_record) -> str:
        """记录补偿动作。关联原始 record。"""
        db_record = RbExecutionRecordRecord(
            record_id=compensation_record.record_id,
            project_id=compensation_record.project_id,
            datasource_id=compensation_record.datasource_id,
            object_ref=compensation_record.object_ref.__dict__,
            action=compensation_record.action,
            script_hash=compensation_record.script_hash,
            executed_at=compensation_record.executed_at,
            status=compensation_record.status,
            failure_summary=compensation_record.failure_summary,
            policy_snapshot_id=compensation_record.policy_snapshot_id,
            impact_snapshot_id=compensation_record.impact_snapshot_id,
            compensation_refs=compensation_record.compensation_refs,
            actor_id=compensation_record.actor_id,
        )
        with self.session_factory() as session, session.begin():
            session.add(db_record)
        return compensation_record.record_id

    def list_records(
        self,
        project_id: int,
        datasource_id: int,
        object_ref=None,
        page: int = 1,
        page_size: int = 50,
    ) -> list[RbExecutionRecordRecord]:
        """分页查询执行记录。只读。"""
        with self.session_factory() as session:
            query = session.query(RbExecutionRecordRecord).filter(
                RbExecutionRecordRecord.project_id == project_id,
                RbExecutionRecordRecord.datasource_id == datasource_id,
            )
            if object_ref is not None:
                query = query.filter(RbExecutionRecordRecord.object_ref == object_ref.__dict__)
            return query.order_by(RbExecutionRecordRecord.executed_at.desc()).offset(
                (page - 1) * page_size
            ).limit(page_size).all()
