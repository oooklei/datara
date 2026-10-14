"""I1 项目持久化模型。"""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base


class ProjectRecord(Base):
    __tablename__ = "rebuild_project"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[int] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: _now_shanghai())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: _now_shanghai(), onupdate=lambda: _now_shanghai()
    )


def _now_shanghai() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)

