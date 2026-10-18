"""R5-B facade 入口（#21-#25 路由绑定）。

依 P2-3 v3 设计 §1.1/§4：
- #21 getDefinition: 复用 R5-A shared read，不新增第二条读取路由
- #22 validatePolicy: 调用 PolicySnapshotService（stub，阶段 C 实施）
- #23 previewImpact: 调用 ImpactSnapshotService（stub，阶段 C 实施）
- #24 submitConfirm: 调用 ConfirmGate + DdlExecutor（stub，阶段 D 实施）
- #25 listExecutionRecords: 调用 ExecutionLedger（stub，阶段 D 实施）

文件域红线：只改 rebuild/rb/ 包及 tests/rebuild/test_rb_*
"""
from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from rebuild.rb.errors.rb_errors import RbErrorCode
from rebuild.rb.facade.rb_envelope import RbEnvelope
from rebuild.rb.models.rb_models import ObjectRef

logger = logging.getLogger(__name__)


# ========== Request Models ==========

class GetDefinitionRequest(BaseModel):
    """#21 getDefinition 请求。"""
    datasourceId: int
    objectRef: dict


class ValidatePolicyRequest(BaseModel):
    """#22 validatePolicy 请求。"""
    datasourceId: int
    objectRef: dict
    sourceVersion: str
    nextDdlText: str


class PreviewImpactRequest(BaseModel):
    """#23 previewImpact 请求。"""
    datasourceId: int
    objectRef: dict
    sourceVersion: str
    nextDdlText: str


class SubmitConfirmRequest(BaseModel):
    """#24 submitConfirm 请求。"""
    datasourceId: int
    objectRef: dict
    sourceVersion: str
    nextDdlText: str
    policySnapshotId: str
    impactSnapshotId: str
    confirmPhrase: str


class ListExecutionRecordsRequest(BaseModel):
    """#25 listExecutionRecords 请求。"""
    datasourceId: int
    objectRef: Optional[dict] = None
    page: int = Field(default=1, ge=1)
    pageSize: int = Field(default=50, ge=1, le=200)


# ========== Response Models ==========

class GetDefinitionResponse(BaseModel):
    """#21 getDefinition 响应。"""
    objectRef: dict
    sourceKind: str
    definitionText: str
    sourceVersion: str
    capability: str
    constraints: list = Field(default_factory=list)
    generatedAt: str


class ValidatePolicyResponse(BaseModel):
    """#22 validatePolicy 响应。"""
    snapshotId: str
    findings: list = Field(default_factory=list)
    blocked: bool


class PreviewImpactResponse(BaseModel):
    """#23 previewImpact 响应。"""
    snapshotId: str
    impacts: list = Field(default_factory=list)
    unknownReasons: list = Field(default_factory=list)


class SubmitConfirmResponse(BaseModel):
    """#24 submitConfirm 响应。"""
    recordId: str
    status: str


class ListExecutionRecordsResponse(BaseModel):
    """#25 listExecutionRecords 响应。"""
    items: list = Field(default_factory=list)
    page: dict = Field(default_factory=dict)


# ========== R5-B Facade ==========

class RbFacade:
    """R5-B facade 入口。

    #21 复用 R5-A shared read（不新增第二条读取路由）。
    #22-#25 调用对应 service（当前为 stub，后续批次替换为真实实现）。
    """

    def __init__(
        self,
        get_definition_service=None,
        validate_policy_service=None,
        preview_impact_service=None,
        submit_confirm_service=None,
        list_execution_records_service=None,
    ):
        self._get_definition = get_definition_service
        self._validate_policy = validate_policy_service
        self._preview_impact = preview_impact_service
        self._submit_confirm = submit_confirm_service
        self._list_execution_records = list_execution_records_service

    # ========== #21 getDefinition ==========

    def get_definition(self, request: GetDefinitionRequest) -> dict:
        """#21 getDefinition — 复用 R5-A shared read。

        不新增第二条读取路由；此方法由 R5-A shared read endpoint 内部调用。
        """
        if self._get_definition is None:
            return RbEnvelope.error(
                http_code=502,
                msg="GetDefinition service not available",
                error_code=RbErrorCode.CAPABILITY_UNSUPPORTED,
            )
        try:
            result = self._get_definition(
                datasource_id=request.datasourceId,
                object_ref=request.objectRef,
            )
            return RbEnvelope.success(result)
        except Exception as e:
            logger.exception("getDefinition failed")
            return RbEnvelope.error(
                http_code=502,
                msg="GetDefinition failed",
                error_code=RbErrorCode.DDL_EXECUTION_FAILED,
                details={"error": type(e).__name__},
            )

    # ========== #22 validatePolicy ==========

    def validate_policy(self, request: ValidatePolicyRequest) -> dict:
        """#22 validatePolicy — 策略校验。"""
        if self._validate_policy is None:
            return RbEnvelope.error(
                http_code=502,
                msg="ValidatePolicy service not available",
                error_code=RbErrorCode.CAPABILITY_UNSUPPORTED,
            )
        try:
            result = self._validate_policy(
                datasource_id=request.datasourceId,
                object_ref=request.objectRef,
                source_version=request.sourceVersion,
                next_ddl_text=request.nextDdlText,
            )
            return RbEnvelope.success(result)
        except Exception as e:
            logger.exception("validatePolicy failed")
            return RbEnvelope.error(
                http_code=502,
                msg="ValidatePolicy failed",
                error_code=RbErrorCode.POLICY_BLOCKED,
                details={"error": type(e).__name__},
            )

    # ========== #23 previewImpact ==========

    def preview_impact(self, request: PreviewImpactRequest) -> dict:
        """#23 previewImpact — 影响预览。"""
        if self._preview_impact is None:
            return RbEnvelope.error(
                http_code=502,
                msg="PreviewImpact service not available",
                error_code=RbErrorCode.CAPABILITY_UNSUPPORTED,
            )
        try:
            result = self._preview_impact(
                datasource_id=request.datasourceId,
                object_ref=request.objectRef,
                source_version=request.sourceVersion,
                next_ddl_text=request.nextDdlText,
            )
            return RbEnvelope.success(result)
        except Exception as e:
            logger.exception("previewImpact failed")
            return RbEnvelope.error(
                http_code=502,
                msg="PreviewImpact failed",
                error_code=RbErrorCode.LINEAGE_UNKNOWN,
                details={"error": type(e).__name__},
            )

    # ========== #24 submitConfirm ==========

    def submit_confirm(self, request: SubmitConfirmRequest) -> dict:
        """#24 submitConfirm — 人工确认执行。

        人工闸能力，测试用 mock，禁止对目标库真实写入。
        """
        if self._submit_confirm is None:
            return RbEnvelope.error(
                http_code=502,
                msg="SubmitConfirm service not available",
                error_code=RbErrorCode.CAPABILITY_UNSUPPORTED,
            )
        try:
            result = self._submit_confirm(
                datasource_id=request.datasourceId,
                object_ref=request.objectRef,
                source_version=request.sourceVersion,
                next_ddl_text=request.nextDdlText,
                policy_snapshot_id=request.policySnapshotId,
                impact_snapshot_id=request.impactSnapshotId,
                confirm_phrase=request.confirmPhrase,
            )
            return RbEnvelope.success(result)
        except Exception as e:
            logger.exception("submitConfirm failed")
            return RbEnvelope.error(
                http_code=502,
                msg="SubmitConfirm failed",
                error_code=RbErrorCode.DDL_EXECUTION_FAILED,
                details={"error": type(e).__name__},
            )

    # ========== #25 listExecutionRecords ==========

    def list_execution_records(self, request: ListExecutionRecordsRequest) -> dict:
        """#25 listExecutionRecords — 执行记录查询。"""
        if self._list_execution_records is None:
            return RbEnvelope.error(
                http_code=502,
                msg="ListExecutionRecords service not available",
                error_code=RbErrorCode.CAPABILITY_UNSUPPORTED,
            )
        try:
            result = self._list_execution_records(
                datasource_id=request.datasourceId,
                object_ref=request.objectRef,
                page=request.page,
                page_size=request.pageSize,
            )
            return RbEnvelope.success(result)
        except Exception as e:
            logger.exception("listExecutionRecords failed")
            return RbEnvelope.error(
                http_code=502,
                msg="ListExecutionRecords failed",
                error_code=RbErrorCode.DDL_EXECUTION_FAILED,
                details={"error": type(e).__name__},
            )
