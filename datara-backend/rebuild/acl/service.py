"""统一 ACL 服务与业务审计写入（设计 §7.3 / §7.4 / §7.5）。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from rebuild.identity.contracts import Role

from .models import ACL_PERMISSIONS, GRANTEE_TYPES, AclAuditRecord, IdentityAuditRecord, ResourceAclRecord

# 授权级别由低到高；有效权限取「分享上限」与「角色上限」的较小值。
ACL_PERMISSION_RANK: dict[str, int] = {"view": 1, "use": 2, "manage": 3}

# 平台角色能支撑的最高授权级别（角色上限）。
ROLE_ACL_CEILING: dict[str, str] = {
    Role.ADMIN.value: "manage",
    Role.DEVELOPER.value: "manage",
    Role.OPERATOR.value: "use",
    Role.VIEWER.value: "view",
}


class AclError(ValueError):
    """ACL 入参非法（调用方应映射为 422/400）。"""


def _now_shanghai() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)


def min_acl_permission(left: str, right: str) -> str:
    """取两个授权级别的较小值；未知级别按最低处理（fail-closed）。"""
    left_rank = ACL_PERMISSION_RANK.get(left, 0)
    right_rank = ACL_PERMISSION_RANK.get(right, 0)
    if left_rank <= right_rank:
        return left if left_rank else "view"
    return right if right_rank else "view"


def role_acl_ceiling(platform_role: str | Role | None) -> str:
    """平台角色能支撑的最高授权级别；未知角色按 view 处理（fail-closed）。"""
    text = platform_role.value if isinstance(platform_role, Role) else str(platform_role or "")
    return ROLE_ACL_CEILING.get(text.strip().lower(), "view")


@dataclass(frozen=True)
class AclRowView:
    """ACL 行的对外视图（避免路由层直接依赖 ORM 字段命名）。"""

    id: int
    resource_kind: str
    resource_id: str
    project_id: int | None
    owner_id: int | None
    grantee_type: str
    grantee_id: str
    permission: str
    expires_at: datetime | None
    granted_by: int | None
    created_at: datetime | None


class AclService:
    """资源 ACL 的唯一读写入口。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ---- 查询 ----

    def rows_for_resource(self, resource_kind: str, resource_id: str) -> list[ResourceAclRecord]:
        return list(
            self.session.scalars(
                select(ResourceAclRecord)
                .where(
                    ResourceAclRecord.resource_kind == resource_kind,
                    ResourceAclRecord.resource_id == resource_id,
                )
                .order_by(ResourceAclRecord.id)
            ).all()
        )

    def owner_of(self, resource_kind: str, resource_id: str) -> int | None:
        row = self.session.scalar(
            select(ResourceAclRecord).where(
                ResourceAclRecord.resource_kind == resource_kind,
                ResourceAclRecord.resource_id == resource_id,
                ResourceAclRecord.grantee_type == "user",
                ResourceAclRecord.permission == "manage",
                ResourceAclRecord.granted_by.is_(None),
            )
        )
        return row.owner_id if row is not None else None

    def resource_project(self, resource_kind: str, resource_id: str) -> int | None:
        row = self.session.scalar(
            select(ResourceAclRecord).where(
                ResourceAclRecord.resource_kind == resource_kind,
                ResourceAclRecord.resource_id == resource_id,
            )
        )
        return row.project_id if row is not None else None

    def shares_for_subject(
        self,
        *,
        user_id: int,
        platform_role: str | Role | None,
        project_ids: set[int] | None = None,
        resource_kind: str | None = None,
    ) -> list[ResourceAclRecord]:
        """返回直接授予该主体的 ACL 行（user / project / role 三种粒度合并）。"""
        conditions = [
            (ResourceAclRecord.grantee_type == "user")
            & (ResourceAclRecord.grantee_id == str(user_id))
        ]
        role_text = platform_role.value if isinstance(platform_role, Role) else str(platform_role or "")
        if role_text:
            conditions.append(
                (ResourceAclRecord.grantee_type == "role")
                & (ResourceAclRecord.grantee_id == role_text.strip().lower())
            )
        if project_ids:
            conditions.append(
                (ResourceAclRecord.grantee_type == "project")
                & (ResourceAclRecord.grantee_id.in_([str(pid) for pid in project_ids]))
            )
        query = select(ResourceAclRecord).where(or_(*conditions))
        if resource_kind is not None:
            query = query.where(ResourceAclRecord.resource_kind == resource_kind)
        return list(self.session.scalars(query.order_by(ResourceAclRecord.id)).all())

    def granted_by_user(self, user_id: int) -> list[ResourceAclRecord]:
        return list(
            self.session.scalars(
                select(ResourceAclRecord)
                .where(ResourceAclRecord.granted_by == user_id)
                .order_by(ResourceAclRecord.id)
            ).all()
        )

    def effective_permission(
        self,
        *,
        user_id: int,
        platform_role: str | Role | None,
        resource_kind: str,
        resource_id: str,
        project_ids: set[int] | None = None,
    ) -> str | None:
        """计算有效授权级别：min(分享上限, 平台角色上限)；无有效分享返回 None。"""
        now = _now_shanghai()
        rows = [
            row
            for row in self.shares_for_subject(
                user_id=user_id,
                platform_role=platform_role,
                project_ids=project_ids,
                resource_kind=resource_kind,
            )
            if row.resource_id == resource_id and (row.expires_at is None or row.expires_at > now)
        ]
        if not rows:
            return None
        share_ceiling = "view"
        for row in rows:
            if ACL_PERMISSION_RANK.get(row.permission, 0) > ACL_PERMISSION_RANK.get(share_ceiling, 0):
                share_ceiling = row.permission
        return min_acl_permission(share_ceiling, role_acl_ceiling(platform_role))

    # ---- 写入 ----

    def grant(
        self,
        *,
        resource_kind: str,
        resource_id: str,
        grantee_type: str,
        grantee_id: str | int,
        permission: str = "view",
        project_id: int | None = None,
        owner_id: int | None = None,
        granted_by: int | None = None,
        expires_at: datetime | None = None,
    ) -> ResourceAclRecord:
        if grantee_type not in GRANTEE_TYPES:
            raise AclError(f"unsupported grantee_type: {grantee_type}")
        if permission not in ACL_PERMISSIONS:
            raise AclError(f"unsupported permission: {permission}")
        kind_text = str(resource_kind or "").strip()
        resource_text = str(resource_id or "").strip()
        grantee_text = str(grantee_id or "").strip()
        if not kind_text or not resource_text or not grantee_text:
            raise AclError("resource_kind, resource_id and grantee_id are required")
        existing = self.session.scalar(
            select(ResourceAclRecord).where(
                ResourceAclRecord.resource_kind == kind_text,
                ResourceAclRecord.resource_id == resource_text,
                ResourceAclRecord.grantee_type == grantee_type,
                ResourceAclRecord.grantee_id == grantee_text,
            )
        )
        if existing is not None:
            existing.permission = permission
            existing.expires_at = expires_at
            existing.granted_by = granted_by
            if project_id is not None:
                existing.project_id = project_id
            if owner_id is not None:
                existing.owner_id = owner_id
            self.session.flush()
            return existing
        record = ResourceAclRecord(
            resource_kind=kind_text,
            resource_id=resource_text,
            project_id=project_id,
            owner_id=owner_id,
            grantee_type=grantee_type,
            grantee_id=grantee_text,
            permission=permission,
            expires_at=expires_at,
            granted_by=granted_by,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def claim_owner(
        self,
        *,
        resource_kind: str,
        resource_id: str,
        owner_id: int,
        project_id: int | None = None,
    ) -> ResourceAclRecord:
        """登记资源归属行（grantee_type=user / grantee_id=owner_id / permission=manage）。"""
        return self.grant(
            resource_kind=resource_kind,
            resource_id=resource_id,
            grantee_type="user",
            grantee_id=owner_id,
            permission="manage",
            project_id=project_id,
            owner_id=owner_id,
            granted_by=None,
        )

    def revoke(self, acl_id: int) -> ResourceAclRecord | None:
        record = self.session.get(ResourceAclRecord, acl_id)
        if record is None:
            return None
        self.session.delete(record)
        self.session.flush()
        return record

    def revoke_grantee_user(self, user_id: int) -> int:
        """用户停用/删除时级联回收其作为 grantee 的 ACL；保留 grantor 记录（审计需要）。"""
        rows = self.session.scalars(
            select(ResourceAclRecord).where(
                ResourceAclRecord.grantee_type == "user",
                ResourceAclRecord.grantee_id == str(user_id),
                ResourceAclRecord.granted_by.is_not(None),
            )
        ).all()
        count = 0
        for row in rows:
            self.session.delete(row)
            count += 1
        if count:
            self.session.flush()
        return count

    def purge_project(self, project_id: int) -> int:
        """项目删除时清理该项目下的全部 ACL 行。"""
        rows = self.session.scalars(
            select(ResourceAclRecord).where(ResourceAclRecord.project_id == project_id)
        ).all()
        for row in rows:
            self.session.delete(row)
        if rows:
            self.session.flush()
        return len(rows)


# ---- 业务审计写入 ----

def _dump(payload: object) -> str | None:
    if payload is None:
        return None
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        return None


class AuditWriter:
    """身份与授权业务审计的统一写入器；append-only，不提供更新/删除。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    def identity(
        self,
        *,
        actor_id: int | None,
        actor_name: str,
        action: str,
        target_user_id: int | None = None,
        target_username: str = "",
        before: object = None,
        after: object = None,
        result: str = "allow",
        ip: str = "",
        user_agent: str = "",
    ) -> IdentityAuditRecord:
        record = IdentityAuditRecord(
            actor_id=actor_id,
            actor_name=actor_name or "",
            target_user_id=target_user_id,
            target_username=target_username or "",
            action=action,
            before_json=_dump(before),
            after_json=_dump(after),
            result=result,
            ip=ip or "",
            user_agent=(user_agent or "")[:255],
        )
        self.session.add(record)
        return record

    def acl(
        self,
        *,
        actor_id: int | None,
        actor_name: str,
        object_kind: str,
        object_id: str,
        action: str,
        before: object = None,
        after: object = None,
        result: str = "allow",
        ip: str = "",
        user_agent: str = "",
    ) -> AclAuditRecord:
        record = AclAuditRecord(
            actor_id=actor_id,
            actor_name=actor_name or "",
            object_kind=object_kind or "",
            object_id=str(object_id or ""),
            action=action,
            before_json=_dump(before),
            after_json=_dump(after),
            result=result,
            ip=ip or "",
            user_agent=(user_agent or "")[:255],
        )
        self.session.add(record)
        return record
