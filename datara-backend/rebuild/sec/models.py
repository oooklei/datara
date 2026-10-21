"""SQLAlchemy models for the security (access audit) domain."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base


class SecTimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


RESULT_ALLOW = "allow"
RESULT_DENY = "deny"
ALLOWED_RESULTS = (RESULT_ALLOW, RESULT_DENY)


class SecAccessLogRecord(SecTimestampMixin, Base):
    """One audited access event.

    Field semantics follow the legacy demo reference (who / when / what /
    how many rows / allowed or denied / why), adapted to the rebuild
    contract conventions: English enum values, explicit request id, and
    server-side timestamps.
    """

    __tablename__ = "rebuild_sec_access_log"
    __table_args__ = (
        Index("ix_sec_access_log_user_time", "user_name", "accessed_at"),
        Index("ix_sec_access_log_result_time", "result", "accessed_at"),
        CheckConstraint("rows_seen >= 0", name="ck_sec_access_log_rows"),
        CheckConstraint("result IN ('allow', 'deny')", name="ck_sec_access_log_result"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(256), nullable=False)
    rows_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    request_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    accessed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp(), index=True
    )


SEC_TABLES = (SecAccessLogRecord.__table__,)
