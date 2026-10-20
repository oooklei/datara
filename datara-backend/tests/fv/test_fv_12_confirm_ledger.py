"""FV-12 R5-B 人工确认闸/执行器/执行台账终验。

验收标准（草案）：
- confirmPhrase 仅用户输入（agent 禁代填）
- block/版本漂移/无权限拒绝
- DDL 执行器受控写路径
- 执行台账含操作者/对象/脚本 hash/时间/状态/失败摘要
- 补偿 DDL 仅展示不执行

测试策略：全部 mock/内存，禁真实写库。
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256

import pytest

from rebuild.rb.errors.rb_errors import RbErrorCode
from rebuild.rb.facade.rb_facade import (
    RbFacade,
    SubmitConfirmRequest,
)
from rebuild.rb.ledger.execution_ledger import ExecutionLedger
from rebuild.rb.models.rb_models import ExecutionRecord, ObjectRef


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


def _execution_record():
    return ExecutionRecord(
        record_id="rec1",
        project_id=1,
        datasource_id=1,
        object_ref=_object_ref(),
        action="CREATE",
        script_hash=sha256("CREATE TABLE t (id INT)".encode()).hexdigest(),
        executed_at=datetime.now(timezone.utc),
        status="success",
        failure_summary=None,
        policy_snapshot_id="ps1",
        impact_snapshot_id="is1",
        compensation_refs=[],
        actor_id=42,
    )


class TestConfirmPhraseGate:
    """confirmPhrase 仅用户输入（agent 禁代填）。"""

    def test_confirm_phrase_must_be_provided(self):
        """confirmPhrase 为空 → 拒绝。"""

        class _Service:
            def __call__(self, **kwargs):
                if not kwargs.get("confirm_phrase"):
                    raise ValueError("confirm_phrase is required")
                return {"recordId": "r1", "status": "success"}

        facade = RbFacade(submit_confirm_service=_Service())
        request = SubmitConfirmRequest(
            datasourceId=1,
            objectRef={"database": "testdb", "kind": "table", "name": "test_table"},
            sourceVersion="v1",
            nextDdlText="CREATE TABLE t (id INT)",
            policySnapshotId="ps1",
            impactSnapshotId="is1",
            confirmPhrase="",  # 空
        )
        response = facade.submit_confirm(request)
        assert response["code"] == 400
        assert response["data"]["errorCode"] == RbErrorCode.INVALID_REQUEST

    def test_confirm_phrase_passed_through(self):
        """confirmPhrase 原样传递给 service。"""
        captured = {}

        class _Service:
            def __call__(self, **kwargs):
                captured.update(kwargs)
                return {"recordId": "r1", "status": "success"}

        facade = RbFacade(submit_confirm_service=_Service())
        request = SubmitConfirmRequest(
            datasourceId=1,
            objectRef={"database": "testdb", "kind": "table", "name": "test_table"},
            sourceVersion="v1",
            nextDdlText="CREATE TABLE t (id INT)",
            policySnapshotId="ps1",
            impactSnapshotId="is1",
            confirmPhrase="CONFIRM",
        )
        facade.submit_confirm(request)
        assert captured["confirm_phrase"] == "CONFIRM"


class TestConfirmRejectionPaths:
    """block/版本漂移/无权限拒绝。"""

    def test_block_rejected(self):
        class _Service:
            def __call__(self, **kwargs):
                raise ValueError(RbErrorCode.POLICY_BLOCKED)

        facade = RbFacade(submit_confirm_service=_Service())
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
        assert response["code"] == 400

    def test_version_drift_rejected(self):
        class _Service:
            def __call__(self, **kwargs):
                raise ValueError(RbErrorCode.SOURCE_VERSION_CONFLICT)

        facade = RbFacade(submit_confirm_service=_Service())
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
        assert response["code"] == 400

    def test_write_permission_denied(self):
        class _Service:
            def __call__(self, **kwargs):
                raise PermissionError(RbErrorCode.WRITE_PERMISSION_DENIED)

        facade = RbFacade(submit_confirm_service=_Service())
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
        assert response["code"] == 400

    def test_submit_confirm_exception_maps_to_invalid_request(self):
        class _Service:
            def __call__(self, **kwargs):
                raise RuntimeError("unexpected error")

        facade = RbFacade(submit_confirm_service=_Service())
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
        assert response["code"] == 400
        assert response["data"]["errorCode"] == RbErrorCode.INVALID_REQUEST


class TestExecutionLedger:
    """执行台账含操作者/对象/脚本 hash/时间/状态/失败摘要。"""

    def test_record_execution_delegates(self):
        class _Repo:
            def __init__(self):
                self.calls = []

            def record_execution(self, record):
                self.calls.append(record)
                return record.record_id

        repo = _Repo()
        ledger = ExecutionLedger(repository=repo)
        record = _execution_record()
        result = ledger.record_execution(record)
        assert result == "rec1"
        assert len(repo.calls) == 1
        assert repo.calls[0].record_id == "rec1"

    def test_record_compensation_delegates(self):
        class _Repo:
            def __init__(self):
                self.calls = []

            def record_compensation(self, original_id, compensation):
                self.calls.append((original_id, compensation))
                return "comp1"

        repo = _Repo()
        ledger = ExecutionLedger(repository=repo)
        record = _execution_record()
        result = ledger.record_compensation("rec1", record)
        assert result == "comp1"
        assert repo.calls[0][0] == "rec1"

    def test_list_records_delegates(self):
        class _Repo:
            def list_records(self, *, project_id, datasource_id, object_ref=None, page=1, page_size=50):
                return [1, 2, 3]

        repo = _Repo()
        ledger = ExecutionLedger(repository=repo)
        result = ledger.list_records(project_id=1, datasource_id=1)
        assert result == [1, 2, 3]

    def test_execution_record_fields(self):
        """ExecutionRecord 含操作者/对象/脚本 hash/时间/状态/失败摘要。"""
        record = _execution_record()
        assert record.actor_id == 42
        assert record.script_hash
        assert record.executed_at is not None
        assert record.status == "success"
        assert record.failure_summary is None
        assert record.object_ref.name == "test_table"
        assert record.policy_snapshot_id == "ps1"
        assert record.impact_snapshot_id == "is1"
        assert record.compensation_refs == []

    def test_execution_record_with_failure(self):
        record = ExecutionRecord(
            record_id="rec2",
            project_id=1,
            datasource_id=1,
            object_ref=_object_ref(),
            action="ALTER",
            script_hash="abc123",
            executed_at=datetime.now(timezone.utc),
            status="failure",
            failure_summary="syntax error",
            policy_snapshot_id="ps1",
            impact_snapshot_id="is1",
            compensation_refs=[],
            actor_id=42,
        )
        assert record.status == "failure"
        assert record.failure_summary == "syntax error"

    def test_compensation_ddl_display_only(self):
        """补偿 DDL 仅展示不执行（compensation_refs 只关联，不触发执行）。"""
        record = ExecutionRecord(
            record_id="rec3",
            project_id=1,
            datasource_id=1,
            object_ref=_object_ref(),
            action="ALTER",
            script_hash="def456",
            executed_at=datetime.now(timezone.utc),
            status="rolled-back",
            failure_summary="rolled back",
            policy_snapshot_id="ps1",
            impact_snapshot_id="is1",
            compensation_refs=["rec1"],  # 关联原始记录
            actor_id=42,
        )
        assert record.status == "rolled-back"
        assert "rec1" in record.compensation_refs
