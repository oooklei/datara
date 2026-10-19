"""TDD 测试：rb_facade.py（#21-#25 路由绑定）。

C5 更新：绑定 PolicySnapshotService/ImpactSnapshotService，修正错误映射。
- policy_blocked: 400 → 409
- validate_policy 异常: 502 → 409+POLICY_BLOCKED
- preview_impact 异常: 502 → 422+LINEAGE_UNKNOWN
- submit_confirm 异常: 502 → 400+INVALID_REQUEST
- 新增 RbEnvelope.invalid_request 方法
"""
from __future__ import annotations

import pytest

from rebuild.rb.errors.rb_errors import RbErrorCode
from rebuild.rb.facade.rb_envelope import RbEnvelope
from rebuild.rb.facade.rb_facade import (
    GetDefinitionRequest,
    ListExecutionRecordsRequest,
    PreviewImpactRequest,
    RbFacade,
    SubmitConfirmRequest,
    ValidatePolicyRequest,
)
from rebuild.rb.impact.impact_snapshot import ImpactSnapshotService
from rebuild.rb.policy.policy_snapshot import PolicySnapshotService


def _make_obj_ref() -> dict:
    return {"database": "mydb", "schema": "public", "kind": "table", "name": "users"}


# ========== RbEnvelope ==========

class TestRbEnvelope:
    def test_success(self):
        resp = RbEnvelope.success({"key": "value"})
        assert resp["code"] == 0
        assert resp["msg"] == "ok"
        assert resp["data"] == {"key": "value"}

    def test_success_empty(self):
        resp = RbEnvelope.success()
        assert resp["code"] == 0
        assert resp["data"] == {}

    def test_error(self):
        resp = RbEnvelope.error(409, "conflict", "SOURCE_VERSION_CONFLICT", {"expected": "v1"})
        assert resp["code"] == 409
        assert resp["msg"] == "conflict"
        assert resp["data"]["errorCode"] == "SOURCE_VERSION_CONFLICT"
        assert resp["data"]["details"]["expected"] == "v1"

    def test_policy_blocked_409(self):
        """C5: policy_blocked 应返回 409（非 400）。"""
        resp = RbEnvelope.policy_blocked([{"level": "block"}])
        assert resp["code"] == 409
        assert resp["data"]["errorCode"] == "POLICY_BLOCKED"

    def test_invalid_request(self):
        """C5: 新增 invalid_request 方法，返回 400+INVALID_REQUEST。"""
        resp = RbEnvelope.invalid_request("Missing field: datasourceId")
        assert resp["code"] == 400
        assert resp["data"]["errorCode"] == "INVALID_REQUEST"
        assert resp["msg"] == "Missing field: datasourceId"

    def test_source_version_conflict(self):
        resp = RbEnvelope.source_version_conflict("v1", "v2")
        assert resp["code"] == 409
        assert resp["data"]["errorCode"] == "SOURCE_VERSION_CONFLICT"
        assert resp["data"]["details"]["expectedVersion"] == "v1"
        assert resp["data"]["details"]["actualVersion"] == "v2"

    def test_snapshot_expired(self):
        resp = RbEnvelope.snapshot_expired()
        assert resp["code"] == 409
        assert resp["data"]["errorCode"] == "SNAPSHOT_EXPIRED"

    def test_confirm_phrase_invalid(self):
        resp = RbEnvelope.confirm_phrase_invalid()
        assert resp["code"] == 400
        assert resp["data"]["errorCode"] == "CONFIRM_PHRASE_INVALID"

    def test_ddl_execution_failed(self):
        resp = RbEnvelope.ddl_execution_failed("Permission denied")
        assert resp["code"] == 500
        assert resp["data"]["errorCode"] == "DDL_EXECUTION_FAILED"
        assert resp["data"]["details"]["summary"] == "Permission denied"

    def test_lineage_unknown(self):
        resp = RbEnvelope.lineage_unknown(["dialect not supported"])
        assert resp["code"] == 422
        assert resp["data"]["errorCode"] == "LINEAGE_UNKNOWN"

    def test_write_permission_denied(self):
        resp = RbEnvelope.write_permission_denied()
        assert resp["code"] == 403
        assert resp["data"]["errorCode"] == "WRITE_PERMISSION_DENIED"

    def test_object_not_visible(self):
        resp = RbEnvelope.object_not_visible()
        assert resp["code"] == 404
        assert resp["data"]["errorCode"] == "OBJECT_NOT_VISIBLE"


# ========== RbFacade ==========

class TestRbFacadeGetDefinition:
    def test_get_definition_service_not_available(self):
        facade = RbFacade()
        req = GetDefinitionRequest(datasourceId=101, objectRef=_make_obj_ref())
        resp = facade.get_definition(req)
        assert resp["code"] == 502
        assert resp["data"]["errorCode"] == "CAPABILITY_UNSUPPORTED"

    def test_get_definition_success(self):
        def mock_service(datasource_id, object_ref):
            return {"objectRef": object_ref, "sourceVersion": "etag-abc123"}

        facade = RbFacade(get_definition_service=mock_service)
        req = GetDefinitionRequest(datasourceId=101, objectRef=_make_obj_ref())
        resp = facade.get_definition(req)
        assert resp["code"] == 0
        assert resp["data"]["sourceVersion"] == "etag-abc123"


class TestRbFacadeValidatePolicy:
    def test_validate_policy_service_not_available(self):
        facade = RbFacade()
        req = ValidatePolicyRequest(
            datasourceId=101,
            objectRef=_make_obj_ref(),
            sourceVersion="etag-abc123",
            nextDdlText="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
        )
        resp = facade.validate_policy(req)
        assert resp["code"] == 502
        assert resp["data"]["errorCode"] == "CAPABILITY_UNSUPPORTED"

    def test_validate_policy_success(self):
        """C5: 绑定 PolicySnapshotService 到 #22 validate_policy。"""
        service = PolicySnapshotService()
        facade = RbFacade(policy_snapshot_service=service)
        req = ValidatePolicyRequest(
            datasourceId=101,
            objectRef=_make_obj_ref(),
            sourceVersion="etag-abc123",
            nextDdlText="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
        )
        resp = facade.validate_policy(req)
        assert resp["code"] == 0
        assert "snapshotId" in resp["data"]
        assert isinstance(resp["data"]["findings"], list)
        assert isinstance(resp["data"]["blocked"], bool)

    def test_validate_policy_exception_409(self):
        """C5: validate_policy 异常应返回 409+POLICY_BLOCKED（非 502）。"""
        class MockService:
            def evaluate_and_snapshot(self, **kwargs):
                raise ValueError("Policy evaluation failed")

        facade = RbFacade(policy_snapshot_service=MockService())
        req = ValidatePolicyRequest(
            datasourceId=101,
            objectRef=_make_obj_ref(),
            sourceVersion="etag-abc123",
            nextDdlText="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
        )
        resp = facade.validate_policy(req)
        assert resp["code"] == 409
        assert resp["data"]["errorCode"] == "POLICY_BLOCKED"


class TestRbFacadePreviewImpact:
    def test_preview_impact_service_not_available(self):
        facade = RbFacade()
        req = PreviewImpactRequest(
            datasourceId=101,
            objectRef=_make_obj_ref(),
            sourceVersion="etag-abc123",
            nextDdlText="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
        )
        resp = facade.preview_impact(req)
        assert resp["code"] == 502
        assert resp["data"]["errorCode"] == "CAPABILITY_UNSUPPORTED"

    def test_preview_impact_success(self):
        """C5: 绑定 ImpactSnapshotService 到 #23 preview_impact。"""
        service = ImpactSnapshotService()
        facade = RbFacade(impact_snapshot_service=service)
        req = PreviewImpactRequest(
            datasourceId=101,
            objectRef=_make_obj_ref(),
            sourceVersion="etag-abc123",
            nextDdlText="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
        )
        resp = facade.preview_impact(req)
        assert resp["code"] == 0
        assert "snapshotId" in resp["data"]
        assert isinstance(resp["data"]["impacts"], list)
        assert isinstance(resp["data"]["unknownReasons"], list)

    def test_preview_impact_exception_422(self):
        """C5: preview_impact 异常应返回 422+LINEAGE_UNKNOWN（非 502）。"""
        class MockService:
            def preview_and_snapshot(self, **kwargs):
                raise ValueError("Lineage analysis failed")

        facade = RbFacade(impact_snapshot_service=MockService())
        req = PreviewImpactRequest(
            datasourceId=101,
            objectRef=_make_obj_ref(),
            sourceVersion="etag-abc123",
            nextDdlText="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
        )
        resp = facade.preview_impact(req)
        assert resp["code"] == 422
        assert resp["data"]["errorCode"] == "LINEAGE_UNKNOWN"


class TestRbFacadeSubmitConfirm:
    def test_submit_confirm_service_not_available(self):
        facade = RbFacade()
        req = SubmitConfirmRequest(
            datasourceId=101,
            objectRef=_make_obj_ref(),
            sourceVersion="etag-abc123",
            nextDdlText="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
            policySnapshotId="uuid-xxx",
            impactSnapshotId="uuid-yyy",
            confirmPhrase="CONFIRM-ALTER-TABLE-users-20261019",
        )
        resp = facade.submit_confirm(req)
        assert resp["code"] == 502
        assert resp["data"]["errorCode"] == "CAPABILITY_UNSUPPORTED"

    def test_submit_confirm_success(self):
        def mock_service(datasource_id, object_ref, source_version, next_ddl_text,
                         policy_snapshot_id, impact_snapshot_id, confirm_phrase):
            return {"recordId": "uuid-zzz", "status": "success"}

        facade = RbFacade(submit_confirm_service=mock_service)
        req = SubmitConfirmRequest(
            datasourceId=101,
            objectRef=_make_obj_ref(),
            sourceVersion="etag-abc123",
            nextDdlText="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
            policySnapshotId="uuid-xxx",
            impactSnapshotId="uuid-yyy",
            confirmPhrase="CONFIRM-ALTER-TABLE-users-20261019",
        )
        resp = facade.submit_confirm(req)
        assert resp["code"] == 0
        assert resp["data"]["status"] == "success"

    def test_submit_confirm_exception_400(self):
        """C5: submit_confirm 异常应返回 400+INVALID_REQUEST（非 502）。"""
        def mock_service(**kwargs):
            raise ValueError("Invalid request")

        facade = RbFacade(submit_confirm_service=mock_service)
        req = SubmitConfirmRequest(
            datasourceId=101,
            objectRef=_make_obj_ref(),
            sourceVersion="etag-abc123",
            nextDdlText="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
            policySnapshotId="uuid-xxx",
            impactSnapshotId="uuid-yyy",
            confirmPhrase="CONFIRM-ALTER-TABLE-users-20261019",
        )
        resp = facade.submit_confirm(req)
        assert resp["code"] == 400
        assert resp["data"]["errorCode"] == "INVALID_REQUEST"


class TestRbFacadeListExecutionRecords:
    def test_list_execution_records_service_not_available(self):
        facade = RbFacade()
        req = ListExecutionRecordsRequest(datasourceId=101)
        resp = facade.list_execution_records(req)
        assert resp["code"] == 502
        assert resp["data"]["errorCode"] == "CAPABILITY_UNSUPPORTED"

    def test_list_execution_records_success(self):
        def mock_service(datasource_id, object_ref, page, page_size):
            return {"items": [], "page": {"nextCursor": None, "hasMore": False}}

        facade = RbFacade(list_execution_records_service=mock_service)
        req = ListExecutionRecordsRequest(datasourceId=101)
        resp = facade.list_execution_records(req)
        assert resp["code"] == 0
        assert resp["data"]["items"] == []
