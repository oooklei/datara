"""I1 身份持久化模型。"""

from sqlalchemy import DateTime, ForeignKey, String
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base


class UserRecord(Base):
    __tablename__ = "rebuild_user"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="enabled")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: _now_shanghai())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: _now_shanghai(), onupdate=lambda: _now_shanghai()
    )


class ProjectMemberRecord(Base):
    __tablename__ = "rebuild_project_member"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("rebuild_user.id"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="viewer")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: _now_shanghai())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: _now_shanghai(), onupdate=lambda: _now_shanghai()
    )


def _now_shanghai() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)

