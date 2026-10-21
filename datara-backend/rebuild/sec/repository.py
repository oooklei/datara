"""Persistence operations for the security (access audit) domain."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rebuild.sec.models import SecAccessLogRecord


class SecRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def add_access_log(
        self,
        *,
        user_name: str,
        action: str,
        target: str,
        rows_seen: int,
        result: str,
        reason: str,
        request_id: str = "",
        accessed_at: datetime | None = None,
    ) -> SecAccessLogRecord:
        event = SecAccessLogRecord(
            user_name=user_name,
            action=action,
            target=target,
            rows_seen=rows_seen,
            result=result,
            reason=reason,
            request_id=request_id,
        )
        if accessed_at is not None:
            event.accessed_at = accessed_at
        self.session.add(event)
        return event

    def query_access_logs(
        self,
        *,
        user_name: str | None = None,
        action: str | None = None,
        result: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[SecAccessLogRecord], int]:
        conditions = []
        if user_name:
            conditions.append(SecAccessLogRecord.user_name == user_name)
        if action:
            conditions.append(SecAccessLogRecord.action == action)
        if result:
            conditions.append(SecAccessLogRecord.result == result)
        total = self.session.scalar(
            select(func.count()).select_from(SecAccessLogRecord).where(*conditions)
        )
        rows = self.session.scalars(
            select(SecAccessLogRecord)
            .where(*conditions)
            .order_by(SecAccessLogRecord.accessed_at.desc(), SecAccessLogRecord.id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return list(rows), int(total or 0)

    def result_facets(self) -> dict[str, int]:
        counts = self.session.execute(
            select(SecAccessLogRecord.result, func.count()).group_by(SecAccessLogRecord.result)
        ).all()
        return {result: int(count) for result, count in counts}
