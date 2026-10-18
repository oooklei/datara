"""G-B5 ExecutionLedger 服务测试（TDD 红灯先行）。

依 P2-3 v3 设计 §2.2/§3.4：
- ExecutionLedger 薄封装委托给 ExecutionLedgerRepository
- record_execution: 记录 DDL 执行结果（append-only）
- record_compensation: 记录补偿动作
- list_records: 分页查询执行记录

测试一律 mock/内存库，禁止对目标库真实写入。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.rb.ledger.ledger_repository import (
    ExecutionLedgerRepository,
    RbExecutionRecordRecord,
    RB_TABLES,
)
from rebuild.rb.ledger.execution_ledger import ExecutionLedger
from rebuild.rb.migrations import RB_MIGRATIONS, RbMigrationRunner
from rebuild.rb.models.rb_models import ExecutionRecord, ObjectRef


def _make_object_ref() -> ObjectRef:
    return ObjectRef(
        datasource_id=1,
        database="test_db",
        catalog=None,
        schema="public",
        kind="table",
        name="orders",
        parent=None,
    )


def _make_execution_record(
    *,
    project_id: int = 1,
    datasource_id: int = 1,
    object_ref: ObjectRef | None = None,
    action: str = "ALTER_TABLE",
    script_hash: str = "a" * 64,
    status: str = "success",
    failure_summary: str | None = None,
    policy_snapshot_id: str = "policy-001",
    impact_snapshot_id: str = "impact-001",
    compensation_refs: list[str] | None = None,
    actor_id: int = 42,
) -> ExecutionRecord:
    return ExecutionRecord(
        record_id=str(uuid.uuid4()),
        project_id=project_id,
        datasource_id=datasource_id,
        object_ref=object_ref or _make_object_ref(),
        action=action,
        script_hash=script_hash,
        executed_at=datetime.now(timezone.utc),
        status=status,
        failure_summary=failure_summary,
        policy_snapshot_id=policy_snapshot_id,
        impact_snapshot_id=impact_snapshot_id,
        compensation_refs=compensation_refs or [],
        actor_id=actor_id,
    )


@pytest.fixture()
def engine():
    """创建内存 SQLite 引擎并应用 RB 迁移。"""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    # 应用 RB 迁移（创建 rb_execution_records 等表）
    result = RbMigrationRunner(engine, RB_MIGRATIONS).apply()
    assert result.applied == ("rb_0001_r5_b_tables",)
    return engine


@pytest.fixture()
def session_factory(engine):
    """返回一个 session factory 兼容 callable。"""
    def _factory():
        return Session(engine)
    return _factory


@pytest.fixture()
def repository(session_factory):
    return ExecutionLedgerRepository(session_factory)


@pytest.fixture()
def ledger(repository):
    return ExecutionLedger(repository)


# ========== 迁移测试 ==========


def test_rb_migration_creates_execution_records_table(engine):
    """验证 rb_0001 迁移创建了 rb_execution_records 表。"""
    table_names = set(inspect(engine).get_table_names())
    assert "rb_execution_records" in table_names


def test_rb_migration_is_idempotent(engine):
    """验证迁移幂等：第二次 apply 跳过。"""
    result = RbMigrationRunner(engine, RB_MIGRATIONS).apply()
    assert result.skipped == ("rb_0001_r5_b_tables",)
    assert result.applied == ()


def test_execution_records_table_has_expected_columns(engine):
    """验证 rb_execution_records 表包含所有预期列。"""
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("rb_execution_records")}
    expected = {
        "record_id",
        "project_id",
        "datasource_id",
        "object_ref",
        "action",
        "script_hash",
        "executed_at",
        "status",
        "failure_summary",
        "policy_snapshot_id",
        "impact_snapshot_id",
        "compensation_refs",
        "actor_id",
    }
    assert expected <= columns


# ========== ExecutionLedger.record_execution 测试 ==========


def test_record_execution_persists_record(ledger, engine):
    """record_execution 应持久化 ExecutionRecord。"""
    record = _make_execution_record()
    record_id = ledger.record_execution(record)

    assert record_id == record.record_id

    with Session(engine) as session:
        db_record = session.query(RbExecutionRecordRecord).filter_by(record_id=record_id).first()
        assert db_record is not None
        assert db_record.project_id == record.project_id
        assert db_record.datasource_id == record.datasource_id
        assert db_record.action == record.action
        assert db_record.script_hash == record.script_hash
        assert db_record.status == record.status
        assert db_record.actor_id == record.actor_id


def test_record_execution_is_append_only(ledger, engine):
    """record_execution 是 append-only：同一 record_id 重复记录应失败。"""
    record = _make_execution_record()
    ledger.record_execution(record)

    # 重复 record_id 应触发 IntegrityError（主键冲突）
    with pytest.raises(Exception):
        ledger.record_execution(record)


def test_record_execution_with_failure_status(ledger, engine):
    """record_execution 应支持 failure 状态和 failure_summary。"""
    record = _make_execution_record(
        status="failure",
        failure_summary="Syntax error near 'ALTER'",
    )
    record_id = ledger.record_execution(record)

    with Session(engine) as session:
        db_record = session.query(RbExecutionRecordRecord).filter_by(record_id=record_id).first()
        assert db_record.status == "failure"
        assert db_record.failure_summary == "Syntax error near 'ALTER'"


# ========== ExecutionLedger.record_compensation 测试 ==========


def test_record_compensation_persists_compensation_record(ledger, engine):
    """record_compensation 应持久化补偿记录。"""
    original = _make_execution_record()
    ledger.record_execution(original)

    compensation = _make_execution_record(
        action="DROP_TABLE",
        status="compensated",
        compensation_refs=[original.record_id],
    )
    comp_id = ledger.record_compensation(original.record_id, compensation)

    assert comp_id == compensation.record_id

    with Session(engine) as session:
        db_record = session.query(RbExecutionRecordRecord).filter_by(record_id=comp_id).first()
        assert db_record is not None
        assert db_record.action == "DROP_TABLE"
        assert db_record.status == "compensated"
        assert original.record_id in db_record.compensation_refs


# ========== ExecutionLedger.list_records 测试 ==========


def test_list_records_returns_empty_when_no_records(ledger):
    """无记录时 list_records 应返回空列表。"""
    records = ledger.list_records(project_id=1, datasource_id=1)
    assert records == []


def test_list_records_returns_paginated_results(ledger, engine):
    """list_records 应返回分页结果。"""
    # 创建 5 条记录
    for i in range(5):
        record = _make_execution_record(
            action=f"ACTION_{i}",
        )
        ledger.record_execution(record)

    # 第一页：3 条
    page1 = ledger.list_records(project_id=1, datasource_id=1, page=1, page_size=3)
    assert len(page1) == 3

    # 第二页：2 条
    page2 = ledger.list_records(project_id=1, datasource_id=1, page=2, page_size=3)
    assert len(page2) == 2


def test_list_records_filters_by_project_and_datasource(ledger, engine):
    """list_records 应按 project_id 和 datasource_id 过滤。"""
    # 不同 project 的记录
    record_p1 = _make_execution_record(project_id=1)
    record_p2 = _make_execution_record(project_id=2)
    ledger.record_execution(record_p1)
    ledger.record_execution(record_p2)

    # 只返回 project_id=1 的记录
    records = ledger.list_records(project_id=1, datasource_id=1)
    assert len(records) == 1
    assert records[0].project_id == 1


def test_list_records_filters_by_object_ref(ledger, engine):
    """list_records 应按 object_ref 过滤。"""
    ref1 = _make_object_ref()
    ref2 = ObjectRef(
        datasource_id=1,
        database="test_db",
        catalog=None,
        schema="public",
        kind="table",
        name="customers",
        parent=None,
    )

    record1 = _make_execution_record(object_ref=ref1)
    record2 = _make_execution_record(object_ref=ref2)
    ledger.record_execution(record1)
    ledger.record_execution(record2)

    # 只返回 object_ref=ref1 的记录
    records = ledger.list_records(project_id=1, datasource_id=1, object_ref=ref1)
    assert len(records) == 1
    assert records[0].object_ref["name"] == "orders"


def test_list_records_orders_by_executed_at_desc(ledger, engine):
    """list_records 应按 executed_at 降序排列。"""
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    record_old = _make_execution_record(action="OLD")
    record_old.executed_at = now - timedelta(hours=1)
    record_new = _make_execution_record(action="NEW")
    record_new.executed_at = now

    ledger.record_execution(record_old)
    ledger.record_execution(record_new)

    records = ledger.list_records(project_id=1, datasource_id=1)
    assert len(records) == 2
    assert records[0].action == "NEW"
    assert records[1].action == "OLD"


# ========== ExecutionLedger 委托测试 ==========


def test_ledger_delegates_to_repository(repository):
    """ExecutionLedger 应委托给 ExecutionLedgerRepository。"""
    ledger = ExecutionLedger(repository)

    # 验证 ledger 持有 repository 引用
    assert ledger._repository is repository


def test_ledger_uses_provided_repository(repository):
    """ExecutionLedger 应使用注入的 repository。"""
    ledger = ExecutionLedger(repository)
    assert ledger._repository is repository
