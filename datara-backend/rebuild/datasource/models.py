"""项目范围内持久化的数据源连接配置。"""

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base


class ProjectDatasourceRecord(Base):
    __tablename__ = "rebuild_project_datasource"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_rebuild_project_datasource_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32))
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer)
    database_name: Mapped[str] = mapped_column(String(128))
    username: Mapped[str] = mapped_column(String(128))
    password: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: _now_shanghai())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: _now_shanghai(), onupdate=lambda: _now_shanghai()
    )


def _now_shanghai() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)
