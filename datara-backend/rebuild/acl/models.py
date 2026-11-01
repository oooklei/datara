"""统一资源 ACL 与业务审计持久化模型（设计 §7.3 / §7.5）。"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base

# 资源种类（设计 §7.3）。
RESOURCE_KINDS = (
    "datasource",
    "dbx_connection",
    "dbx_object",
    "orchestration_resource",
    "ssh_node",
    "ide_script",
    "workflow",
    "model",
)

# 被授权方粒度（设计 §7.4.3）。
GRANTEE_TYPES = ("user", "project", "role")

# 授权级别（设计 §7.4.1）。
ACL_PERMISSIONS = ("view", "use", "manage")


def _now_shanghai() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)


class ResourceAclRecord(Base):
    """通用资源 ACL：一行表示一条「资源 → 被授权方」的显式授权。

    owner 的首行以 grantee_type=user / grantee_id=owner_id / permission=manage 表达，
    从而消除「归属表 + 分享表」双表结构。
    """

    __tablename__ = "rebuild_resource_acl"
    __table_args__ = (
        UniqueConstraint(
            "resource_kind",
            "resource_id",
            "grantee_type",
            "grantee_id",
            name="uq_rebuild_resource_acl_grant",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_kind: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    resource_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("rebuild_project.id"), index=True, nullable=True
    )
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("rebuild_user.id"), index=True, nullable=True
    )
    grantee_type: Mapped[str] = mapped_column(String(16), nullable=False)
    grantee_id: Mapped[str] = mapped_column(String(64), nullable=False)
    permission: Mapped[str] = mapped_column(String(16), nullable=False, default="view")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    granted_by: Mapped[int | None] = mapped_column(
        ForeignKey("rebuild_user.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: _now_shanghai())


class IdentityAuditRecord(Base):
    """身份业务审计（append-only）：用户增删改、角色变更、密码重置、登录成败。"""

    __tablename__ = "rebuild_identity_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    target_user_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    target_username: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    action: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str] = mapped_column(String(16), nullable=False, default="allow")
    ip: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    user_agent: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: _now_shanghai(), index=True)


class AclAuditRecord(Base):
    """授权业务审计（append-only）：grant / revoke / 过期回收 / admin 穿透访问。"""

    __tablename__ = "rebuild_acl_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    object_kind: Mapped[str] = mapped_column(String(32), index=True, nullable=False, default="")
    object_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False, default="")
    action: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    before_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str] = mapped_column(String(16), nullable=False, default="allow")
    ip: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    user_agent: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: _now_shanghai(), index=True)


ACL_TABLES = (ResourceAclRecord.__table__, IdentityAuditRecord.__table__, AclAuditRecord.__table__)
