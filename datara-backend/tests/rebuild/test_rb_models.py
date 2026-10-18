"""TDD 测试：rb_models.py（§2.1 五模型 frozen dataclass）。

IMPL-B2 更新：模型去多余默认值后，测试传入所有必需字段。
"""
from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone, timedelta

import pytest

from rebuild.rb.models.rb_models import (
    ExecutionRecord,
    ImpactItem,
    ImpactSnapshot,
    ObjectRef,
    PolicyFinding,
    PolicySnapshot,
)


def _make_ref() -> ObjectRef:
    return ObjectRef(
        datasource_id=101,
        database="mydb",
        catalog=None,
        schema="public",
        kind="table",
        name="users",
        parent=None,
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _later() -> datetime:
    return _now() + timedelta(minutes=30)


# ========== ObjectRef ==========

class TestObjectRef:
    def test_create_frozen(self):
        ref = _make_ref()
        assert ref.datasource_id == 101
        assert ref.database == "mydb"
        assert ref.schema == "public"
        assert ref.kind == "table"
        assert ref.name == "users"
        assert ref.parent is None

    def test_frozen_immutable(self):
        ref = _make_ref()
        with pytest.raises(FrozenInstanceError):
            ref.name = "other"

    def test_with_parent(self):
        ref = ObjectRef(
            datasource_id=101,
            database="mydb",
            catalog=None,
            schema="public",
            kind="column",
            name="email",
            parent="users",
        )
        assert ref.parent == "users"


# ========== PolicyFinding ==========

class TestPolicyFinding:
    def test_create(self):
        finding = PolicyFinding(
            level="warn",
            code="NEW_COLUMN",
            message="Adding new column",
            impacts=["existing_data"],
        )
        assert finding.level == "warn"
        assert finding.code == "NEW_COLUMN"
        assert finding.message == "Adding new column"
        assert finding.impacts == ["existing_data"]

    def test_empty_impacts(self):
        finding = PolicyFinding(
            level="info",
            code="COMMENT",
            message="Adding comment",
            impacts=[],
        )
        assert finding.impacts == []


# ========== PolicySnapshot ==========

class TestPolicySnapshot:
    def test_create_minimal(self):
        snapshot = PolicySnapshot(
            snapshot_id=str(uuid.uuid4()),
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_digest="a" * 64,
            policy_version="1.0",
            findings=[],
            blocked=False,
            created_at=_now(),
            expires_at=_later(),
        )
        assert snapshot.blocked is False
        assert snapshot.findings == []

    def test_create_blocked(self):
        finding = PolicyFinding(
            level="block",
            code="DESTRUCTIVE",
            message="Destructive operation",
            impacts=[],
        )
        snapshot = PolicySnapshot(
            snapshot_id=str(uuid.uuid4()),
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_digest="a" * 64,
            policy_version="1.0",
            findings=[finding],
            blocked=True,
            created_at=_now(),
            expires_at=_later(),
        )
        assert snapshot.blocked is True
        assert len(snapshot.findings) == 1

    def test_frozen_immutable(self):
        snapshot = PolicySnapshot(
            snapshot_id=str(uuid.uuid4()),
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_digest="a" * 64,
            policy_version="1.0",
            findings=[],
            blocked=False,
            created_at=_now(),
            expires_at=_later(),
        )
        with pytest.raises(FrozenInstanceError):
            snapshot.blocked = True


# ========== ImpactItem ==========

class TestImpactItem:
    def test_create(self):
        ref = ObjectRef(
            datasource_id=101,
            database="mydb",
            catalog=None,
            parent=None,
            schema="public",
            kind="view",
            name="user_view",
        )
        item = ImpactItem(
            object_ref=ref,
            relation_type="dependent",
            detail="View depends on table users",
        )
        assert item.relation_type == "dependent"
        assert "depends" in item.detail


# ========== ImpactSnapshot ==========

class TestImpactSnapshot:
    def test_create_minimal(self):
        snapshot = ImpactSnapshot(
            snapshot_id=str(uuid.uuid4()),
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_digest="a" * 64,
            policy_snapshot_id=str(uuid.uuid4()),
            impacts=[],
            unknown_reasons=[],
            created_at=_now(),
            expires_at=_later(),
        )
        assert snapshot.impacts == []
        assert snapshot.unknown_reasons == []

    def test_with_unknown(self):
        snapshot = ImpactSnapshot(
            snapshot_id=str(uuid.uuid4()),
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_digest="a" * 64,
            policy_snapshot_id=str(uuid.uuid4()),
            impacts=[],
            unknown_reasons=["dialect not supported"],
            created_at=_now(),
            expires_at=_later(),
        )
        assert len(snapshot.unknown_reasons) == 1


# ========== ExecutionRecord ==========

class TestExecutionRecord:
    def test_create_minimal(self):
        record = ExecutionRecord(
            record_id=str(uuid.uuid4()),
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            action="ALTER_TABLE",
            script_hash="a" * 64,
            executed_at=_now(),
            status="success",
            failure_summary=None,
            policy_snapshot_id=str(uuid.uuid4()),
            impact_snapshot_id=str(uuid.uuid4()),
            compensation_refs=[],
            actor_id=1,
        )
        assert record.status == "success"
        assert record.failure_summary is None
        assert record.compensation_refs == []

    def test_create_failure(self):
        record = ExecutionRecord(
            record_id=str(uuid.uuid4()),
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            action="DROP_TABLE",
            script_hash="b" * 64,
            executed_at=_now(),
            status="failure",
            failure_summary="Permission denied",
            policy_snapshot_id=str(uuid.uuid4()),
            impact_snapshot_id=str(uuid.uuid4()),
            compensation_refs=[],
            actor_id=1,
        )
        assert record.status == "failure"
        assert "denied" in record.failure_summary
