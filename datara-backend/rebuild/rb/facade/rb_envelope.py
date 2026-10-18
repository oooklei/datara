"""R5-B 统一响应 envelope（§2.1 common/resp.py 约定）。

依 A5 SQL IDE 后端契约 v1.0 §2.1：
- 成功: {code: 0, msg: "ok", data: {...}}
- 失败: {code: <http_code>, msg: "<message>", data: {errorCode: "<stable_code>", details: {...}}}
"""
from __future__ import annotations

from typing import Any, Optional

from rebuild.rb.errors.rb_errors import RbErrorCode


class RbEnvelope:
    """R5-B 统一响应 envelope。"""

    @staticmethod
    def success(data: Any = None) -> dict:
        """成功响应。"""
        return {"code": 0, "msg": "ok", "data": data if data is not None else {}}

    @staticmethod
    def error(
        http_code: int,
        msg: str,
        error_code: str,
        details: Optional[dict] = None,
    ) -> dict:
        """失败响应。"""
        return {
            "code": http_code,
            "msg": msg,
            "data": {
                "errorCode": error_code,
                "details": details if details is not None else {},
            },
        }

    @staticmethod
    def policy_blocked(findings: list) -> dict:
        """策略阻断。"""
        return RbEnvelope.error(
            http_code=409,
            msg="Policy validation failed",
            error_code=RbErrorCode.POLICY_BLOCKED,
            details={"findings": findings},
        )

    @staticmethod
    def invalid_request(msg: str, details: Optional[dict] = None) -> dict:
        """请求无效。"""
        return RbEnvelope.error(
            http_code=400,
            msg=msg,
            error_code=RbErrorCode.INVALID_REQUEST,
            details=details,
        )

    @staticmethod
    def source_version_conflict(expected: str, actual: str) -> dict:
        """版本漂移。"""
        return RbEnvelope.error(
            http_code=409,
            msg="Source version conflict",
            error_code=RbErrorCode.SOURCE_VERSION_CONFLICT,
            details={"expectedVersion": expected, "actualVersion": actual},
        )

    @staticmethod
    def snapshot_expired() -> dict:
        """快照过期。"""
        return RbEnvelope.error(
            http_code=409,
            msg="Snapshot expired",
            error_code=RbErrorCode.SNAPSHOT_EXPIRED,
        )

    @staticmethod
    def snapshot_mismatch() -> dict:
        """快照不匹配。"""
        return RbEnvelope.error(
            http_code=409,
            msg="Snapshot mismatch",
            error_code=RbErrorCode.SNAPSHOT_MISMATCH,
        )

    @staticmethod
    def confirm_phrase_invalid() -> dict:
        """确认短语无效。"""
        return RbEnvelope.error(
            http_code=400,
            msg="Invalid confirmation phrase",
            error_code=RbErrorCode.CONFIRM_PHRASE_INVALID,
        )

    @staticmethod
    def ddl_execution_failed(summary: str) -> dict:
        """DDL 执行失败。"""
        return RbEnvelope.error(
            http_code=500,
            msg="DDL execution failed",
            error_code=RbErrorCode.DDL_EXECUTION_FAILED,
            details={"summary": summary},
        )

    @staticmethod
    def lineage_unknown(reasons: list) -> dict:
        """血缘未知。"""
        return RbEnvelope.error(
            http_code=422,
            msg="Lineage analysis unknown",
            error_code=RbErrorCode.LINEAGE_UNKNOWN,
            details={"reasons": reasons},
        )

    @staticmethod
    def write_permission_denied() -> dict:
        """写权限不足。"""
        return RbEnvelope.error(
            http_code=403,
            msg="Write permission denied",
            error_code=RbErrorCode.WRITE_PERMISSION_DENIED,
        )

    @staticmethod
    def object_not_visible() -> dict:
        """对象不可见。"""
        return RbEnvelope.error(
            http_code=404,
            msg="Object not visible",
            error_code=RbErrorCode.OBJECT_NOT_VISIBLE,
        )
