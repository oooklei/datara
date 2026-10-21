"""Application services for the security (access audit) domain."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from rebuild.sec.models import ALLOWED_RESULTS, RESULT_ALLOW, RESULT_DENY, SecAccessLogRecord
from rebuild.sec.repository import SecRepository


class SecAccessRejected(ValueError):
    """Raised when an access event carries a value outside the contract."""


class SecService:
    def __init__(self, session: Session) -> None:
        self.repository = SecRepository(session)

    def record_access(
        self,
        *,
        user_name: str,
        action: str,
        target: str,
        rows_seen: int,
        allowed: bool,
        reason: str = "",
        request_id: str = "",
        accessed_at: datetime | None = None,
    ) -> SecAccessLogRecord:
        if not user_name:
            raise SecAccessRejected("user_name is required")
        if not action:
            raise SecAccessRejected("action is required")
        if not target:
            raise SecAccessRejected("target is required")
        if rows_seen < 0:
            raise SecAccessRejected("rows_seen must be >= 0")
        result = RESULT_ALLOW if allowed else RESULT_DENY
        if result not in ALLOWED_RESULTS:  # defensive; kept aligned with the model check constraint
            raise SecAccessRejected("result must be allow or deny")
        return self.repository.add_access_log(
            user_name=user_name,
            action=action,
            target=target,
            rows_seen=rows_seen if allowed else 0,
            result=result,
            reason=reason,
            request_id=request_id,
            accessed_at=accessed_at,
        )

    def access_logs(
        self,
        *,
        user_name: str | None = None,
        action: str | None = None,
        result: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, object]:
        if result is not None and result not in ALLOWED_RESULTS:
            raise SecAccessRejected("result must be allow or deny")
        rows, total = self.repository.query_access_logs(
            user_name=user_name,
            action=action,
            result=result,
            limit=limit,
            offset=offset,
        )
        return {
            "list": [access_log_payload(row) for row in rows],
            "total": total,
            "facets": self.repository.result_facets(),
        }


def access_log_payload(record: SecAccessLogRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "user_name": record.user_name,
        "action": record.action,
        "target": record.target,
        "rows_seen": record.rows_seen,
        "result": record.result,
        "reason": record.reason,
        "request_id": record.request_id,
        "accessed_at": record.accessed_at.isoformat() if record.accessed_at else None,
    }
