"""TDD 测试：rb_models.py（§2.1 五模型 frozen dataclass）。

RED 先行：先写测试确认模型行为，再验证 GREEN。
"""
from __future__ import annotations

import uuid
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta

import pytest

from rebuild.rb.models.rb_models import (
    ExecutionRecord,
    ImpactItem,
    ImpactSnapshot,
    ObjectRef,
    PolicyFinding,
    PolicySnapshot,
)


# ========== ObjectRef ==========

class TestObjectRef:
    def test_create_frozen(self):
        ref = ObjectRef(
            datasource_id=101,
            database="mydb",
            catalog=None,
            schema="public",
            kind="table",
            name="users",
        )
        assert ref.datasource_id == 101
        assert ref.database == "mydb"
        assert ref.schema == "public"
        assert ref.kind == "table"
        assert ref.name == "users"
        assert ref.parent is None

    def test_frozen_immutable(self):
        ref = ObjectRef(
            datasource_id=101,
            database="mydb",
            catalog=None,
            schema="public",
            kind="table",
            name="users",
        )
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
        )
        assert finding.impacts == []


# ========== PolicySnapshot ==========

class TestPolicySnapshot:
    def test_create_minimal(self):
        ref = ObjectRef(
            datasource_id=101,
            database="mydb",
            catalog=None,
            schema="public",
            kind="table",
            name="users",
        )
        snapshot = PolicySnapshot(
            snapshot_id=str(uuid.uuid4()),
            project_id=1,
            datasource_id=101,
            object_ref=ref,
            source_version="etag-abc123",
            next_ddl_digest="a" * 64,
            policy_version="1.0",
        )
        assert snapshot.blocked is False
        assert snapshot.findings == []

    def test_create_blocked(self):
        ref = ObjectRef(
            datasource_id=101,
            database="mydb",
            catalog=None,
            schema="public",
            kind="table",
            name="users",
        )
        finding = PolicyFinding(
            level="block",
            code="DESTRUCTIVE",
            message="Destructive operation",
        )
        snapshot = PolicySnapshot(
            snapshot_id=str(uuid.uuid4()),
            project_id=1,
            datasource_id=101,
            object_ref=ref,
            source_version="etag-abc123",
            next_ddl_digest="a" * 64,
            policy_version="1.0",
            findings=[finding],
            blocked=True,
        )
        assert snapshot.blocked is True
        assert len(snapshot.findings) == 1


# ========== ImpactItem ==========

class TestImpactItem:
    def test_create(self):
        ref = ObjectRef(
            datasource_id=101,
            database="mydb",
            catalog=None,
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
        ref = ObjectRef(
            datasource_id=101,
            database="mydb",
            catalog=None,
            schema="public",
            kind="table",
            name="users",
        )
        snapshot = ImpactSnapshot(
            snapshot_id=str(uuid.uuid4()),
            project_id=1,
            datasource_id=101,
            object_ref=ref,
            source_version="etag-abc123",
            next_ddl_digest="a" * 64,
            policy_snapshot_id=str(uuid.uuid4()),
        )
        assert snapshot.impacts == []
        assert snapshot.unknown_reasons == []

    def test_with_unknown(self):
        ref = ObjectRef(
            datasource_id=101,
            database="mydb",
            catalog=None,
            schema="public",
            kind="table",
            name="users",
        )
        snapshot = ImpactSnapshot(
            snapshot_id=str(uuid.uuid4()),
            project_id=1,
            datasource_id=101,
            object_ref=ref,
            source_version="etag-abc123",
            next_ddl_digest="a" * 64,
            policy_snapshot_id=str(uuid.uuid4()),
            unknown_reasons=["dialect not supported"],
        )
        assert len(snapshot.unknown_reasons) == 1


# ========== ExecutionRecord ==========

class TestExecutionRecord:
    def test_create_minimal(self):
        ref = ObjectRef(
            datasource_id=101,
            database="mydb",
            catalog=None,
            schema="public",
            kind="table",
            name="users",
        )
        record = ExecutionRecord(
            record_id=str(uuid.uuid4()),
            project_id=1,
            datasource_id=101,
            object_ref=ref,
            action="ALTER_TABLE",
            script_hash="a" * 64,
            policy_snapshot_id=str(uuid.uuid4()),
            impact_snapshot_id=str(uuid.uuid4()),
            actor_id=1,
        )
        assert record.status == "pending"
        assert record.failure_summary is None
        assert record.compensation_refs == []

    def test_create_success(self):
        ref = ObjectRef(
            datasource_id=101,
            database="mydb",
            catalog=None,
            schema="public",
            kind="table",
            name="users",
        )
        record = ExecutionRecord(
            record_id=str(uuid.uuid4()),
            project_id=1,
            datasource_id=101,
            object_ref=ref,
            action="ALTER_TABLE",
            script_hash="a" * 64,
            status="success",
            policy_snapshot_id=str(uuid.uuid4()),
            impact_snapshot_id=str(uuid.uuid4()),
            actor_id=1,
        )
        assert record.status == "success"
