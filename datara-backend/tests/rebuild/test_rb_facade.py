"""TDD 测试：rb_facade.py（#21-#25 路由绑定）。

B3-A 新增：验证 facade 层路由绑定与 envelope 响应。
"""
from __future__ import annotations

import pytest

from rebuild.rb.facade.rb_envelope import RbEnvelope
from rebuild.rb.facade.rb_facade import (
    GetDefinitionRequest,
    ListExecutionRecordsRequest,
    PreviewImpactRequest,
    RbFacade,
    SubmitConfirmRequest,
    ValidatePolicyRequest,
)


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

    def test_policy_blocked(self):
        resp = RbEnvelope.policy_blocked([{"level": "block"}])
        assert resp["code"] == 400
        assert resp["data"]["errorCode"] == "POLICY_BLOCKED"

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

class TestRbFacade:
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

    def test_validate_policy_success(self):
        def mock_service(datasource_id, object_ref, source_version, next_ddl_text):
            return {"snapshotId": "uuid-xxx", "findings": [], "blocked": False}

        facade = RbFacade(validate_policy_service=mock_service)
        req = ValidatePolicyRequest(
            datasourceId=101,
            objectRef=_make_obj_ref(),
            sourceVersion="etag-abc123",
            nextDdlText="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
        )
        resp = facade.validate_policy(req)
        assert resp["code"] == 0
        assert resp["data"]["blocked"] is False

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

    def test_preview_impact_success(self):
        def mock_service(datasource_id, object_ref, source_version, next_ddl_text):
            return {"snapshotId": "uuid-yyy", "impacts": [], "unknownReasons": []}

        facade = RbFacade(preview_impact_service=mock_service)
        req = PreviewImpactRequest(
            datasourceId=101,
            objectRef=_make_obj_ref(),
            sourceVersion="etag-abc123",
            nextDdlText="ALTER TABLE users ADD COLUMN email VARCHAR(255);",
        )
        resp = facade.preview_impact(req)
        assert resp["code"] == 0
        assert resp["data"]["snapshotId"] == "uuid-yyy"

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

    def test_list_execution_records_service_not_available(self):
        facade = RbFacade()
        req = ListExecutionRecordsRequest(datasourceId=101)
        resp = facade.list_execution_records(req)
        assert resp["code"] == 502

    def test_list_execution_records_success(self):
        def mock_service(datasource_id, object_ref, page, page_size):
            return {"items": [], "page": {"nextCursor": None, "hasMore": False}}

        facade = RbFacade(list_execution_records_service=mock_service)
        req = ListExecutionRecordsRequest(datasourceId=101)
        resp = facade.list_execution_records(req)
        assert resp["code"] == 0
        assert resp["data"]["items"] == []
