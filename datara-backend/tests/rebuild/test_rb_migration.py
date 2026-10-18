"""TDD 测试：rb 迁移脚本（§2.2 三表结构 + ENGINE/CHARSET 断言）。

IMPL-B2 新增：验证迁移脚本的表结构正确性。
"""
from __future__ import annotations

import hashlib

import pytest

from rebuild.rb.ledger.ledger_repository import (
    RB_TABLES,
    RbExecutionRecordRecord,
    RbImpactSnapshotRecord,
    RbPolicySnapshotRecord,
)
from rebuild.rb.migrations import RB_MIGRATIONS, RbMigration


class TestRbTables:
    """验证三张 R5-B 表的 SQLAlchemy ORM 定义。"""

    def test_three_tables_defined(self):
        assert len(RB_TABLES) == 3

    def test_policy_snapshot_table(self):
        table = RbPolicySnapshotRecord.__table__
        assert table.name == "rb_policy_snapshots"
        columns = {c.name for c in table.columns}
        assert "snapshot_id" in columns
        assert "project_id" in columns
        assert "datasource_id" in columns
        assert "object_ref" in columns
        assert "source_version" in columns
        assert "next_ddl_digest" in columns
        assert "policy_version" in columns
        assert "findings" in columns
        assert "blocked" in columns
        assert "created_at" in columns
        assert "expires_at" in columns

    def test_impact_snapshot_table(self):
        table = RbImpactSnapshotRecord.__table__
        assert table.name == "rb_impact_snapshots"
        columns = {c.name for c in table.columns}
        assert "snapshot_id" in columns
        assert "policy_snapshot_id" in columns
        assert "impacts" in columns
        assert "unknown_reasons" in columns

    def test_execution_record_table(self):
        table = RbExecutionRecordRecord.__table__
        assert table.name == "rb_execution_records"
        columns = {c.name for c in table.columns}
        assert "record_id" in columns
        assert "action" in columns
        assert "script_hash" in columns
        assert "status" in columns
        assert "failure_summary" in columns
        assert "policy_snapshot_id" in columns
        assert "impact_snapshot_id" in columns
        assert "compensation_refs" in columns
        assert "actor_id" in columns

    def test_primary_keys(self):
        assert RbPolicySnapshotRecord.__table__.primary_key.columns.keys() == ["snapshot_id"]
        assert RbImpactSnapshotRecord.__table__.primary_key.columns.keys() == ["snapshot_id"]
        assert RbExecutionRecordRecord.__table__.primary_key.columns.keys() == ["record_id"]


class TestRbMigrations:
    """验证迁移列表的 revision/checksum/upgrade 约定。"""

    def test_one_migration(self):
        assert len(RB_MIGRATIONS) == 1

    def test_migration_revision(self):
        migration = RB_MIGRATIONS[0]
        assert migration.revision == "rb_0001_r5_b_tables"

    def test_migration_checksum_is_sha256(self):
        migration = RB_MIGRATIONS[0]
        checksum = migration.checksum
        assert len(checksum) == 64
        assert all(c in "0123456789abcdef" for c in checksum)

    def test_migration_checksum_matches_manifest(self):
        migration = RB_MIGRATIONS[0]
        expected_manifest = (
            "rb_0001_r5_b_tables v1: rb_policy_snapshots,rb_impact_snapshots,rb_execution_records; "
            "ENGINE=InnoDB CHARSET=utf8mb4; all indexes"
        )
        expected_checksum = hashlib.sha256(expected_manifest.encode("utf-8")).hexdigest()
        assert migration.checksum == expected_checksum

    def test_migration_tables(self):
        migration = RB_MIGRATIONS[0]
        assert len(migration.tables) == 3

    def test_migration_upgrade_callable(self):
        migration = RB_MIGRATIONS[0]
        assert callable(migration.upgrade)
