"""FV-11 R5-B 策略快照与影响面快照终验。

验收标准（草案）：
- policy snapshot 创建/验证/漂移检测（revision 漂移 409）
- 血缘/影响 fail-closed（方言不支持=unknown_reasons、权限拒绝不崩溃）
- block finding 服务端禁入 confirm

测试策略：全部 mock/内存，禁真实写库。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from rebuild.rb.errors.rb_errors import RbErrorCode
from rebuild.rb.facade.rb_envelope import RbEnvelope
from rebuild.rb.facade.rb_facade import RbFacade, ValidatePolicyRequest
from rebuild.rb.impact.impact_snapshot import ImpactSnapshotService
from rebuild.rb.lineage.lineage_analyzer import LineageAnalyzer
from rebuild.rb.models.rb_models import ObjectRef
from rebuild.rb.policy.policy_snapshot import POLICY_TTL, PolicySnapshotService


def _object_ref():
    return ObjectRef(
        datasource_id=1,
        database="testdb",
        catalog=None,
        schema=None,
        kind="table",
        name="test_table",
        parent=None,
    )


class TestPolicySnapshotService:
    """PolicySnapshotService 创建/验证/漂移检测。"""

    def test_evaluate_and_snapshot_creates_snapshot(self):
        service = PolicySnapshotService()
        ddl = "CREATE TABLE t (id INT)"
        snapshot = service.evaluate_and_snapshot(
            project_id=1,
            datasource_id=1,
            object_ref=_object_ref(),
            source_version="v1",
            next_ddl_text=ddl,
            current_definition=ddl,
            current_definition_digest=sha256(ddl.encode()).hexdigest(),
        )
        assert snapshot.snapshot_id
        assert snapshot.project_id == 1
        assert snapshot.source_version == "v1"
        assert snapshot.next_ddl_digest == sha256(ddl.encode()).hexdigest()

    def test_validate_snapshot_passes(self):
        service = PolicySnapshotService()
        snapshot = service.evaluate_and_snapshot(
            project_id=1,
            datasource_id=1,
            object_ref=_object_ref(),
            source_version="v1",
            next_ddl_text="CREATE TABLE t (id INT)",
            current_definition="CREATE TABLE t (id INT)",
            current_definition_digest=sha256("CREATE TABLE t (id INT)".encode()).hexdigest(),
        )
        # 同 DDL + 同 source_version → 通过
        result = service.validate_snapshot(
            snapshot_id=snapshot.snapshot_id,
            project_id=1,
            datasource_id=1,
            object_ref=_object_ref(),
            source_version="v1",
            next_ddl_text="CREATE TABLE t (id INT)",
        )
        assert result.snapshot_id == snapshot.snapshot_id

    def test_validate_snapshot_version_drift(self):
        """版本漂移 → SOURCE_VERSION_CONFLICT。"""
        service = PolicySnapshotService()
        snapshot = service.evaluate_and_snapshot(
            project_id=1,
            datasource_id=1,
            object_ref=_object_ref(),
            source_version="v1",
            next_ddl_text="CREATE TABLE t (id INT)",
            current_definition="CREATE TABLE t (id INT)",
            current_definition_digest=sha256("CREATE TABLE t (id INT)".encode()).hexdigest(),
        )
        with pytest.raises(ValueError, match=RbErrorCode.SOURCE_VERSION_CONFLICT):
            service.validate_snapshot(
                snapshot_id=snapshot.snapshot_id,
                project_id=1,
                datasource_id=1,
                object_ref=_object_ref(),
                source_version="v2",  # 漂移
                next_ddl_text="CREATE TABLE t (id INT)",
            )

    def test_validate_snapshot_ddl_mismatch(self):
        """DDL 变更 → SNAPSHOT_MISMATCH。"""
        service = PolicySnapshotService()
        snapshot = service.evaluate_and_snapshot(
            project_id=1,
            datasource_id=1,
            object_ref=_object_ref(),
            source_version="v1",
            next_ddl_text="CREATE TABLE t (id INT)",
            current_definition="CREATE TABLE t (id INT)",
            current_definition_digest=sha256("CREATE TABLE t (id INT)".encode()).hexdigest(),
        )
        with pytest.raises(ValueError, match=RbErrorCode.SNAPSHOT_MISMATCH):
            service.validate_snapshot(
                snapshot_id=snapshot.snapshot_id,
                project_id=1,
                datasource_id=1,
                object_ref=_object_ref(),
                source_version="v1",
                next_ddl_text="CREATE TABLE t (id INT, name VARCHAR(50))",  # 变更
            )

    def test_validate_snapshot_expired(self):
        """过期 → SNAPSHOT_EXPIRED。"""
        service = PolicySnapshotService()
        snapshot = service.evaluate_and_snapshot(
            project_id=1,
            datasource_id=1,
            object_ref=_object_ref(),
            source_version="v1",
            next_ddl_text="CREATE TABLE t (id INT)",
            current_definition="CREATE TABLE t (id INT)",
            current_definition_digest=sha256("CREATE TABLE t (id INT)".encode()).hexdigest(),
        )
        # 手动过期
        object.__setattr__(snapshot, "expires_at", datetime.now(timezone.utc) - timedelta(minutes=1))
        with pytest.raises(ValueError, match=RbErrorCode.SNAPSHOT_EXPIRED):
            service.validate_snapshot(
                snapshot_id=snapshot.snapshot_id,
                project_id=1,
                datasource_id=1,
                object_ref=_object_ref(),
                source_version="v1",
                next_ddl_text="CREATE TABLE t (id INT)",
            )

    def test_validate_snapshot_not_found(self):
        service = PolicySnapshotService()
        with pytest.raises(ValueError, match="not found"):
            service.validate_snapshot(
                snapshot_id="nonexistent",
                project_id=1,
                datasource_id=1,
                object_ref=_object_ref(),
                source_version="v1",
                next_ddl_text="CREATE TABLE t (id INT)",
            )

    def test_blocked_findings_present(self):
        """block finding 存在时 blocked=True（DROP 阻断）。"""
        service = PolicySnapshotService()
        snapshot = service.evaluate_and_snapshot(
            project_id=1,
            datasource_id=1,
            object_ref=_object_ref(),
            source_version="v1",
            next_ddl_text="DROP TABLE t",
        )
        assert any(f.level == "block" for f in snapshot.findings)
        assert snapshot.blocked is True

    def test_warn_findings_present(self):
        """warn finding 始终存在（identity unverified 等）。"""
        service = PolicySnapshotService()
        snapshot = service.evaluate_and_snapshot(
            project_id=1,
            datasource_id=1,
            object_ref=_object_ref(),
            source_version="v1",
            next_ddl_text="CREATE TABLE t (id INT)",
        )
        assert any(f.level == "warn" for f in snapshot.findings)


class TestImpactSnapshotService:
    """ImpactSnapshotService 影响面快照。"""

    def test_preview_without_analyzer(self):
        """无 analyzer → unknown_reasons=['lineage_unavailable']。"""
        service = ImpactSnapshotService()
        snapshot = service.preview_and_snapshot(
            project_id=1,
            datasource_id=1,
            object_ref=_object_ref(),
            source_version="v1",
            next_ddl_text="CREATE TABLE t (id INT)",
        )
        assert snapshot.impacts == []
        assert snapshot.unknown_reasons == ["lineage_unavailable"]

    def test_preview_with_analyzer(self):
        """有 analyzer → 返回分析结果。"""
        class _FakeAnalyzer:
            def analyze(self, *, datasource_id, object_ref, source_version):
                return [], []

        service = ImpactSnapshotService(analyzer=_FakeAnalyzer())
        snapshot = service.preview_and_snapshot(
            project_id=1,
            datasource_id=1,
            object_ref=_object_ref(),
            source_version="v1",
            next_ddl_text="CREATE TABLE t (id INT)",
        )
        assert snapshot.impacts == []
        assert snapshot.unknown_reasons == []

    def test_get_snapshot(self):
        service = ImpactSnapshotService()
        snapshot = service.preview_and_snapshot(
            project_id=1,
            datasource_id=1,
            object_ref=_object_ref(),
            source_version="v1",
            next_ddl_text="CREATE TABLE t (id INT)",
        )
        found = service.get_snapshot(snapshot.snapshot_id)
        assert found.snapshot_id == snapshot.snapshot_id

    def test_get_snapshot_not_found(self):
        service = ImpactSnapshotService()
        assert service.get_snapshot("nonexistent") is None

    def test_impact_validate_snapshot_version_drift(self):
        service = ImpactSnapshotService()
        snapshot = service.preview_and_snapshot(
            project_id=1,
            datasource_id=1,
            object_ref=_object_ref(),
            source_version="v1",
            next_ddl_text="CREATE TABLE t (id INT)",
        )
        with pytest.raises(ValueError, match=RbErrorCode.SOURCE_VERSION_CONFLICT):
            service.validate_snapshot(
                snapshot_id=snapshot.snapshot_id,
                project_id=1,
                datasource_id=1,
                object_ref=_object_ref(),
                source_version="v2",
                next_ddl_text="CREATE TABLE t (id INT)",
            )


class TestLineageAnalyzerFailClosed:
    """LineageAnalyzer 方言不支持 → fail-closed unknown_reasons。"""

    def test_no_service_returns_unavailable(self):
        analyzer = LineageAnalyzer()
        impacts, unknown = analyzer.analyze(
            datasource_id=1,
            object_ref=_object_ref(),
            source_version="v1",
        )
        assert impacts == []
        assert "lineage_unavailable" in unknown

    def test_service_returns_not_found(self):
        """service 返回 None → definition_not_found。"""
        def _fake_get_definition(*, datasource_id, object_ref):
            return None

        analyzer = LineageAnalyzer(get_definition_service=_fake_get_definition)
        impacts, unknown = analyzer.analyze(
            datasource_id=1,
            object_ref=_object_ref(),
            source_version="v1",
        )
        assert impacts == []
        assert "definition_not_found" in unknown

    def test_service_returns_empty_definition(self):
        """service 返回空 definitionText → definition_empty。"""
        def _fake_get_definition(*, datasource_id, object_ref):
            return {"definitionText": None}

        analyzer = LineageAnalyzer(get_definition_service=_fake_get_definition)
        impacts, unknown = analyzer.analyze(
            datasource_id=1,
            object_ref=_object_ref(),
            source_version="v1",
        )
        assert impacts == []
        assert "definition_empty" in unknown

    def test_unparseable_ddl_returns_dialect_not_supported(self):
        """所有方言解析失败 → dialect_not_supported。"""
        def _fake_get_definition(*, datasource_id, object_ref):
            return {"definitionText": "CREATE TABLE ((( {{{ ["}

        analyzer = LineageAnalyzer(get_definition_service=_fake_get_definition)
        impacts, unknown = analyzer.analyze(
            datasource_id=1,
            object_ref=_object_ref(),
            source_version="v1",
        )
        assert impacts == []
        assert "dialect_not_supported" in unknown


class TestRbFacadePolicyBlocked:
    """RbFacade block finding 服务端禁入 confirm。"""

    def test_validate_policy_blocked(self):
        """策略阻断 → blocked=True（DROP TABLE 触发 destructive_ddl block）。"""
        service = PolicySnapshotService()
        facade = RbFacade(policy_snapshot_service=service)
        request = ValidatePolicyRequest(
            datasourceId=1,
            objectRef={"database": "testdb", "kind": "table", "name": "test_table"},
            sourceVersion="v1",
            nextDdlText="DROP TABLE t",
        )
        response = facade.validate_policy(request)
        assert response["code"] == 0
        assert response["data"]["blocked"] is True
        assert any(f["level"] == "block" for f in response["data"]["findings"])

    def test_validate_policy_service_unavailable(self):
        facade = RbFacade(policy_snapshot_service=None)
        request = ValidatePolicyRequest(
            datasourceId=1,
            objectRef={"database": "testdb", "kind": "table", "name": "test_table"},
            sourceVersion="v1",
            nextDdlText="CREATE TABLE t (id INT)",
        )
        response = facade.validate_policy(request)
        assert response["code"] == 502
        assert response["data"]["errorCode"] == RbErrorCode.CAPABILITY_UNSUPPORTED

    def test_preview_impact_service_unavailable(self):
        facade = RbFacade(impact_snapshot_service=None)
        from rebuild.rb.facade.rb_facade import PreviewImpactRequest

        request = PreviewImpactRequest(
            datasourceId=1,
            objectRef={"database": "testdb", "kind": "table", "name": "test_table"},
            sourceVersion="v1",
            nextDdlText="CREATE TABLE t (id INT)",
        )
        response = facade.preview_impact(request)
        assert response["code"] == 502

    def test_submit_confirm_service_unavailable(self):
        facade = RbFacade(submit_confirm_service=None)
        from rebuild.rb.facade.rb_facade import SubmitConfirmRequest

        request = SubmitConfirmRequest(
            datasourceId=1,
            objectRef={"database": "testdb", "kind": "table", "name": "test_table"},
            sourceVersion="v1",
            nextDdlText="CREATE TABLE t (id INT)",
            policySnapshotId="ps1",
            impactSnapshotId="is1",
            confirmPhrase="CONFIRM",
        )
        response = facade.submit_confirm(request)
        assert response["code"] == 502


class TestRbEnvelope:
    """RbEnvelope 统一响应 envelope。"""

    def test_success(self):
        env = RbEnvelope.success({"key": "value"})
        assert env["code"] == 0
        assert env["msg"] == "ok"
        assert env["data"] == {"key": "value"}

    def test_success_empty(self):
        env = RbEnvelope.success()
        assert env["code"] == 0
        assert env["data"] == {}

    def test_error(self):
        env = RbEnvelope.error(400, "bad request", "INVALID_REQUEST")
        assert env["code"] == 400
        assert env["data"]["errorCode"] == "INVALID_REQUEST"

    def test_policy_blocked(self):
        env = RbEnvelope.policy_blocked([{"code": "test"}])
        assert env["code"] == 409
        assert env["data"]["errorCode"] == RbErrorCode.POLICY_BLOCKED

    def test_source_version_conflict(self):
        env = RbEnvelope.source_version_conflict("v1", "v2")
        assert env["code"] == 409
        assert env["data"]["errorCode"] == RbErrorCode.SOURCE_VERSION_CONFLICT
        assert env["data"]["details"]["expectedVersion"] == "v1"

    def test_confirm_phrase_invalid(self):
        env = RbEnvelope.confirm_phrase_invalid()
        assert env["code"] == 400
        assert env["data"]["errorCode"] == RbErrorCode.CONFIRM_PHRASE_INVALID

    def test_lineage_unknown(self):
        env = RbEnvelope.lineage_unknown(["lineage_unavailable"])
        assert env["code"] == 422
        assert env["data"]["errorCode"] == RbErrorCode.LINEAGE_UNKNOWN

    def test_write_permission_denied(self):
        env = RbEnvelope.write_permission_denied()
        assert env["code"] == 403
        assert env["data"]["errorCode"] == RbErrorCode.WRITE_PERMISSION_DENIED
