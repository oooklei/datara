"""TDD 测试：rb/policy/（B4-A policy_snapshot + policy_evaluator）。

B4-A 新增：验证策略快照构建与评估器。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from hashlib import sha256

import pytest

from rebuild.rb.errors.rb_errors import RbErrorCode
from rebuild.rb.models.rb_models import ObjectRef, PolicyFinding, PolicySnapshot
from rebuild.rb.policy.policy_evaluator import PolicyEvaluator
from rebuild.rb.policy.policy_snapshot import PolicySnapshotService


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


# ========== PolicyEvaluator ==========

class TestPolicyEvaluator:
    def test_evaluate_valid_ddl(self):
        evaluator = PolicyEvaluator()
        current_ddl = "CREATE TABLE users (id INT);"
        current_digest = sha256(current_ddl.encode("utf-8")).hexdigest()
        result = evaluator.evaluate(
            dialect="mysql",
            object_kind="table",
            current_definition=current_ddl,
            current_definition_digest=current_digest,
            expected_definition="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
        )
        assert result.blocked is False
        assert len(result.findings) >= 0

    def test_evaluate_unsupported_dialect(self):
        evaluator = PolicyEvaluator()
        current_ddl = "CREATE TABLE users (id INT);"
        current_digest = sha256(current_ddl.encode("utf-8")).hexdigest()
        result = evaluator.evaluate(
            dialect="oracle",
            object_kind="table",
            current_definition=current_ddl,
            current_definition_digest=current_digest,
            expected_definition="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
        )
        # Unsupported dialect should produce a finding
        assert any(f.level in ("block", "warn") for f in result.findings)

    def test_evaluate_drop_table_blocked(self):
        evaluator = PolicyEvaluator()
        current_ddl = "CREATE TABLE users (id INT);"
        current_digest = sha256(current_ddl.encode("utf-8")).hexdigest()
        result = evaluator.evaluate(
            dialect="mysql",
            object_kind="table",
            current_definition=current_ddl,
            current_definition_digest=current_digest,
            expected_definition="DROP TABLE users;",
        )
        # DROP TABLE should be blocked
        assert result.blocked is True
        assert any(f.level == "block" for f in result.findings)

    def test_evaluate_digest(self):
        evaluator = PolicyEvaluator()
        current_ddl = "CREATE TABLE users (id INT);"
        current_digest = sha256(current_ddl.encode("utf-8")).hexdigest()
        result = evaluator.evaluate(
            dialect="mysql",
            object_kind="table",
            current_definition=current_ddl,
            current_definition_digest=current_digest,
            expected_definition="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
        )
        # Digest should be SHA-256
        assert len(result.digest) == 64
        assert all(c in "0123456789abcdef" for c in result.digest)


# ========== PolicySnapshotService ==========

class TestPolicySnapshotService:
    def test_evaluate_and_snapshot(self):
        service = PolicySnapshotService()
        current_ddl = "CREATE TABLE users (id INT);"
        current_digest = sha256(current_ddl.encode("utf-8")).hexdigest()
        snapshot = service.evaluate_and_snapshot(
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_text="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
            current_definition=current_ddl,
            current_definition_digest=current_digest,
        )
        assert snapshot.snapshot_id is not None
        assert snapshot.project_id == 1
        assert snapshot.datasource_id == 101
        assert snapshot.source_version == "etag-abc123"
        assert snapshot.blocked is False
        assert snapshot.findings is not None

    def test_evaluate_and_snapshot_blocked(self):
        service = PolicySnapshotService()
        current_ddl = "CREATE TABLE users (id INT);"
        current_digest = sha256(current_ddl.encode("utf-8")).hexdigest()
        snapshot = service.evaluate_and_snapshot(
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_text="DROP TABLE users;",
            current_definition=current_ddl,
            current_definition_digest=current_digest,
        )
        assert snapshot.blocked is True

    def test_validate_snapshot_success(self):
        service = PolicySnapshotService()
        current_ddl = "CREATE TABLE users (id INT);"
        current_digest = sha256(current_ddl.encode("utf-8")).hexdigest()
        snapshot = service.evaluate_and_snapshot(
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_text="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
            current_definition=current_ddl,
            current_definition_digest=current_digest,
        )
        validated = service.validate_snapshot(
            snapshot_id=snapshot.snapshot_id,
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_text="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
        )
        assert validated.snapshot_id == snapshot.snapshot_id

    def test_validate_snapshot_version_conflict(self):
        service = PolicySnapshotService()
        current_ddl = "CREATE TABLE users (id INT);"
        current_digest = sha256(current_ddl.encode("utf-8")).hexdigest()
        snapshot = service.evaluate_and_snapshot(
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_text="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
            current_definition=current_ddl,
            current_definition_digest=current_digest,
        )
        with pytest.raises(Exception) as exc_info:
            service.validate_snapshot(
                snapshot_id=snapshot.snapshot_id,
                project_id=1,
                datasource_id=101,
                object_ref=_make_ref(),
                source_version="etag-def456",  # different version
                next_ddl_text="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
            )
        assert "SOURCE_VERSION_CONFLICT" in str(exc_info.value) or "409" in str(exc_info.value)

    def test_validate_snapshot_ddl_changed(self):
        service = PolicySnapshotService()
        current_ddl = "CREATE TABLE users (id INT);"
        current_digest = sha256(current_ddl.encode("utf-8")).hexdigest()
        snapshot = service.evaluate_and_snapshot(
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_text="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
            current_definition=current_ddl,
            current_definition_digest=current_digest,
        )
        with pytest.raises(Exception) as exc_info:
            service.validate_snapshot(
                snapshot_id=snapshot.snapshot_id,
                project_id=1,
                datasource_id=101,
                object_ref=_make_ref(),
                source_version="etag-abc123",
                next_ddl_text="ALTER TABLE users ADD COLUMN phone VARCHAR(20);",  # different DDL
            )
        assert "SNAPSHOT_MISMATCH" in str(exc_info.value) or "409" in str(exc_info.value)
