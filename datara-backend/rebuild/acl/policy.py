"""授权判定单点：PolicyService（设计 §7.1）。

判定顺序保持「平台角色优先」不变：
  1) admin 直通；
  2) 平台角色不具该权限 → 拒绝（硬门槛，不可被项目角色放宽）；
  3) 项目 owner 直通；
  4) 项目成员按项目角色上限裁剪后判定；
  5) 非成员 → 拒绝。
资源级（ACL）判定：有效权限 = min(分享上限, 平台角色上限)。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.identity.contracts import Permission, Role, authorize, project_role_allows
from rebuild.identity.models import ProjectMemberRecord
from rebuild.project.models import ProjectRecord

from .service import ACL_PERMISSION_RANK, AclService, role_acl_ceiling


@dataclass(frozen=True)
class Subject:
    """请求主体：平台角色是权限上限，项目角色只在项目内裁剪。"""

    user_id: int
    platform_role: str
    username: str = ""

    @property
    def is_admin(self) -> bool:
        return str(self.platform_role).strip().lower() == Role.ADMIN.value


@dataclass(frozen=True)
class Decision:
    """判定结果；reason 供审计与前端解释 403 原因。"""

    allowed: bool
    reason: str
    detail: str = ""

    def as_payload(self) -> dict[str, object]:
        return {"allowed": self.allowed, "reason": self.reason, "detail": self.detail}


ALLOW_ADMIN = "allow:platform_admin"
ALLOW_OWNER = "allow:project_owner"
ALLOW_PROJECT_ROLE = "allow:project_role"
ALLOW_ACL = "allow:acl"
DENY_PROJECT_NOT_FOUND = "deny:project_not_found"
DENY_PLATFORM_ROLE = "deny:platform_role"
DENY_NOT_MEMBER = "deny:not_member"
DENY_PROJECT_ROLE = "deny:project_role"
DENY_ACL_MISSING = "deny:acl_missing"
DENY_ACL_EXPIRED = "deny:acl_expired"
DENY_ACL_INSUFFICIENT = "deny:acl_insufficient"
DENY_DEFAULT = "deny:default"

_REASON_TEXT: dict[str, str] = {
    ALLOW_ADMIN: "管理员全局权限",
    ALLOW_OWNER: "项目负责人",
    ALLOW_PROJECT_ROLE: "项目角色授权",
    ALLOW_ACL: "资源分享授权",
    DENY_PROJECT_NOT_FOUND: "项目不存在",
    DENY_PLATFORM_ROLE: "平台角色不具备该权限",
    DENY_NOT_MEMBER: "不是该项目成员",
    DENY_PROJECT_ROLE: "项目角色在该项目内被裁剪，不允许此操作",
    DENY_ACL_MISSING: "资源未授权给你",
    DENY_ACL_EXPIRED: "资源分享已过期",
    DENY_ACL_INSUFFICIENT: "分享级别不足以执行该操作",
    DENY_DEFAULT: "默认拒绝",
}


def reason_text(reason: str) -> str:
    return _REASON_TEXT.get(reason, "权限不足")


class PolicyService:
    """所有受保护请求的唯一判定入口。"""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.acl = AclService(session)

    # ---- 项目级判定 ----

    def project_role_of(self, project_id: int, user_id: int) -> str | None:
        member = self.session.scalar(
            select(ProjectMemberRecord).where(
                ProjectMemberRecord.project_id == project_id,
                ProjectMemberRecord.user_id == user_id,
            )
        )
        return member.role if member is not None else None

    def decide_project(
        self,
        subject: Subject,
        project_id: int,
        permission: Permission | str,
    ) -> Decision:
        project = self.session.get(ProjectRecord, project_id)
        if project is None:
            return Decision(False, DENY_PROJECT_NOT_FOUND, reason_text(DENY_PROJECT_NOT_FOUND))
        if subject.is_admin:
            return Decision(True, ALLOW_ADMIN, reason_text(ALLOW_ADMIN))
        if not authorize(subject.platform_role, permission):
            return Decision(False, DENY_PLATFORM_ROLE, reason_text(DENY_PLATFORM_ROLE))
        if project.owner_id == subject.user_id:
            return Decision(True, ALLOW_OWNER, reason_text(ALLOW_OWNER))
        member_role = self.project_role_of(project_id, subject.user_id)
        if member_role is None:
            return Decision(False, DENY_NOT_MEMBER, reason_text(DENY_NOT_MEMBER))
        if not project_role_allows(member_role, permission):
            return Decision(False, DENY_PROJECT_ROLE, reason_text(DENY_PROJECT_ROLE))
        return Decision(True, ALLOW_PROJECT_ROLE, reason_text(ALLOW_PROJECT_ROLE))

    # ---- 资源级判定（ACL 分享）----

    def project_ids_for_user(self, user_id: int) -> set[int]:
        return set(
            self.session.scalars(
                select(ProjectMemberRecord.project_id).where(ProjectMemberRecord.user_id == user_id)
            ).all()
        )

    def decide_resource(
        self,
        subject: Subject,
        *,
        resource_kind: str,
        resource_id: str,
        required_permission: str = "view",
    ) -> Decision:
        if subject.is_admin:
            return Decision(True, ALLOW_ADMIN, reason_text(ALLOW_ADMIN))
        project_ids = self.project_ids_for_user(subject.user_id)
        effective = self.acl.effective_permission(
            user_id=subject.user_id,
            platform_role=subject.platform_role,
            resource_kind=resource_kind,
            resource_id=resource_id,
            project_ids=project_ids,
        )
        if effective is None:
            rows = self.acl.shares_for_subject(
                user_id=subject.user_id,
                platform_role=subject.platform_role,
                project_ids=project_ids,
                resource_kind=resource_kind,
            )
            if any(row.resource_id == resource_id for row in rows):
                return Decision(False, DENY_ACL_EXPIRED, reason_text(DENY_ACL_EXPIRED))
            return Decision(False, DENY_ACL_MISSING, reason_text(DENY_ACL_MISSING))
        if ACL_PERMISSION_RANK.get(effective, 0) < ACL_PERMISSION_RANK.get(required_permission, 0):
            return Decision(False, DENY_ACL_INSUFFICIENT, reason_text(DENY_ACL_INSUFFICIENT))
        return Decision(True, ALLOW_ACL, reason_text(ALLOW_ACL))

    def effective_level(self, subject: Subject, *, resource_kind: str, resource_id: str) -> str | None:
        """返回主体对资源的有效授权级别；admin 视为 manage。"""
        if subject.is_admin:
            return "manage"
        return self.acl.effective_permission(
            user_id=subject.user_id,
            platform_role=subject.platform_role,
            resource_kind=resource_kind,
            resource_id=resource_id,
            project_ids=self.project_ids_for_user(subject.user_id),
        )

    # ---- 分享资格 ----

    def can_share(self, subject: Subject, *, resource_kind: str, resource_id: str) -> bool:
        """分享资格：admin 可分享任意资源；资源 owner 可分享自有资源；其余拒绝。"""
        if subject.is_admin:
            return True
        owner_id = self.acl.owner_of(resource_kind, resource_id)
        return owner_id is not None and owner_id == subject.user_id

    def role_ceiling(self, subject: Subject) -> str:
        return role_acl_ceiling(subject.platform_role)
