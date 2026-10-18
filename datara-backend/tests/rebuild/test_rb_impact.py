"""TDD 测试：rb/impact/（B4-C impact_snapshot）。

B4-C 新增：验证影响面快照服务。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from hashlib import sha256

import pytest

from rebuild.rb.errors.rb_errors import RbErrorCode
from rebuild.rb.models.rb_models import ObjectRef, ImpactItem, ImpactSnapshot
from rebuild.rb.impact.impact_snapshot import ImpactSnapshotService


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


# ========== ImpactSnapshotService ==========

class TestImpactSnapshotService:
    def test_preview_and_snapshot(self):
        service = ImpactSnapshotService()
        snapshot = service.preview_and_snapshot(
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_text="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
        )
        assert snapshot.snapshot_id is not None
        assert snapshot.project_id == 1
        assert snapshot.datasource_id == 101
        assert snapshot.source_version == "etag-abc123"
        assert snapshot.impacts is not None
        assert snapshot.unknown_reasons is not None

    def test_preview_and_snapshot_with_policy_id(self):
        service = ImpactSnapshotService()
        snapshot = service.preview_and_snapshot(
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_text="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
            policy_snapshot_id="policy-uuid-123",
        )
        assert snapshot.policy_snapshot_id == "policy-uuid-123"

    def test_preview_and_snapshot_digest(self):
        service = ImpactSnapshotService()
        ddl_text = "ALTER TABLE users ADD COLUMN email VARCHAR(255);"
        snapshot = service.preview_and_snapshot(
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_text=ddl_text,
        )
        expected_digest = sha256(ddl_text.encode("utf-8")).hexdigest()
        assert snapshot.next_ddl_digest == expected_digest

    def test_preview_and_snapshot_expiry(self):
        service = ImpactSnapshotService()
        snapshot = service.preview_and_snapshot(
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_text="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
        )
        assert snapshot.expires_at > snapshot.created_at

    def test_preview_and_snapshot_drop_table(self):
        service = ImpactSnapshotService()
        snapshot = service.preview_and_snapshot(
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_text="DROP TABLE users;",
        )
        # DROP TABLE should still produce a snapshot (may have impacts or unknown reasons)
        assert snapshot.snapshot_id is not None
        assert snapshot.impacts is not None

    def test_get_snapshot(self):
        service = ImpactSnapshotService()
        snapshot = service.preview_and_snapshot(
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_text="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
        )
        retrieved = service.get_snapshot(snapshot.snapshot_id)
        assert retrieved is not None
        assert retrieved.snapshot_id == snapshot.snapshot_id

    def test_get_snapshot_not_found(self):
        service = ImpactSnapshotService()
        retrieved = service.get_snapshot("non-existent-id")
        assert retrieved is None

    def test_validate_snapshot_success(self):
        service = ImpactSnapshotService()
        ddl_text = "ALTER TABLE users ADD COLUMN email VARCHAR(255);"
        snapshot = service.preview_and_snapshot(
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_text=ddl_text,
        )
        validated = service.validate_snapshot(
            snapshot_id=snapshot.snapshot_id,
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_text=ddl_text,
        )
        assert validated.snapshot_id == snapshot.snapshot_id

    def test_validate_snapshot_version_conflict(self):
        service = ImpactSnapshotService()
        ddl_text = "ALTER TABLE users ADD COLUMN email VARCHAR(255);"
        snapshot = service.preview_and_snapshot(
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_text=ddl_text,
        )
        with pytest.raises(Exception) as exc_info:
            service.validate_snapshot(
                snapshot_id=snapshot.snapshot_id,
                project_id=1,
                datasource_id=101,
                object_ref=_make_ref(),
                source_version="etag-def456",  # different version
                next_ddl_text=ddl_text,
            )
        assert "SOURCE_VERSION_CONFLICT" in str(exc_info.value) or "409" in str(exc_info.value)

    def test_validate_snapshot_ddl_changed(self):
        service = ImpactSnapshotService()
        snapshot = service.preview_and_snapshot(
            project_id=1,
            datasource_id=101,
            object_ref=_make_ref(),
            source_version="etag-abc123",
            next_ddl_text="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
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
