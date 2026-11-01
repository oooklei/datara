"""Owner and explicit-sharing rules for dbx connection IDs.

P2 双写：claim / share / unshare 操作同时写 rebuild_resource_acl（若表存在）。
旧表始终保留写入，保证现有测试与旧行为不受影响。
"""

import logging

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from .models import DbxConnectionOwnershipRecord, DbxConnectionShareRecord, DbxObjectOwnershipRecord, DbxObjectShareRecord

logger = logging.getLogger(__name__)

# 延迟导入 ACL 模块（避免循环依赖；且 ACL 表不一定在所有单元测试中 create_all）。
_ACL_MODULE = None


def _acl_service(session: Session):
    """返回 AclService 实例；ACL 表不存在则返回 None。"""
    global _ACL_MODULE
    try:
        from rebuild.acl.service import AclService  # noqa: PLC0415
    except Exception:  # pragma: no cover - 环境缺依赖时降级
        return None
    try:
        inspector = inspect(session.connection())
        if "rebuild_resource_acl" not in inspector.get_table_names():
            return None
    except Exception:  # pragma: no cover
        return None
    return AclService(session)


def _dbx_object_resource_id(kind: str, object_id: str) -> str:
    """dbx_object 以 (kind, object_id) 唯一；ACL resource_id 编码为 f"{kind}:{object_id}"。"""
    return f"{kind}:{object_id}"


class DbxConnectionAccess:
    def __init__(self, session: Session) -> None:
        self.session = session

    def claim(self, *, connection_id: str, project_id: int, owner_id: int) -> DbxConnectionOwnershipRecord:
        if not connection_id or project_id < 1 or owner_id < 1:
            raise ValueError("connection, project and owner are required")
        existing = self.session.get(DbxConnectionOwnershipRecord, connection_id)
        if existing is not None:
            if existing.project_id != project_id or existing.owner_id != owner_id:
                raise PermissionError("connection already belongs to another owner")
            return existing
        record = DbxConnectionOwnershipRecord(connection_id=connection_id, project_id=project_id, owner_id=owner_id)
        self.session.add(record)
        # --- P2 ACL 双写 ---
        acl = _acl_service(self.session)
        if acl is not None:
            try:
                acl.claim_owner(
                    resource_kind="dbx_connection",
                    resource_id=connection_id,
                    owner_id=owner_id,
                    project_id=project_id,
                )
                self.session.flush()
            except Exception:  # noqa: BLE001 - ACL 写失败不阻断旧表写入
                logger.exception("acl_claim failed for dbx_connection %s", connection_id)
        return record

    def share(self, *, connection_id: str, owner_id: int, user_id: int) -> None:
        record = self.session.get(DbxConnectionOwnershipRecord, connection_id)
        if record is None or record.owner_id != owner_id:
            raise PermissionError("only the connection owner can share it")
        if user_id == owner_id:
            return
        existing = self.session.scalar(select(DbxConnectionShareRecord).where(
            DbxConnectionShareRecord.connection_id == connection_id,
            DbxConnectionShareRecord.user_id == user_id,
        ))
        if existing is None:
            self.session.add(DbxConnectionShareRecord(connection_id=connection_id, user_id=user_id))
        # --- P2 ACL 双写 ---
        acl = _acl_service(self.session)
        if acl is not None:
            try:
                acl.grant(
                    resource_kind="dbx_connection",
                    resource_id=connection_id,
                    grantee_type="user",
                    grantee_id=str(user_id),
                    permission="view",
                    project_id=record.project_id,
                    owner_id=owner_id,
                    granted_by=owner_id,
                )
                self.session.flush()
            except Exception:  # noqa: BLE001
                logger.exception("acl_grant failed for dbx_connection %s → user %d", connection_id, user_id)

    def unshare(self, *, connection_id: str, owner_id: int, user_id: int) -> None:
        record = self.session.get(DbxConnectionOwnershipRecord, connection_id)
        if record is None or record.owner_id != owner_id:
            raise PermissionError("only the connection owner can revoke a share")
        shared = self.session.scalar(select(DbxConnectionShareRecord).where(
            DbxConnectionShareRecord.connection_id == connection_id,
            DbxConnectionShareRecord.user_id == user_id,
        ))
        if shared is not None:
            self.session.delete(shared)
        # --- P2 ACL 双写（按 resource + grantee 定位后删除）---
        acl = _acl_service(self.session)
        if acl is not None:
            try:
                rows = [
                    r for r in acl.rows_for_resource("dbx_connection", connection_id)
                    if r.grantee_type == "user" and r.grantee_id == str(user_id) and r.granted_by is not None
                ]
                for r in rows:
                    acl.revoke(r.id)
                self.session.flush()
            except Exception:  # noqa: BLE001
                logger.exception("acl_revoke failed for dbx_connection %s → user %d", connection_id, user_id)

    def visible_ids(self, *, project_id: int, user_id: int, is_admin: bool = False) -> set[str]:
        query = select(DbxConnectionOwnershipRecord.connection_id).where(DbxConnectionOwnershipRecord.project_id == project_id)
        if not is_admin:
            shared = select(DbxConnectionShareRecord.connection_id).where(DbxConnectionShareRecord.user_id == user_id)
            query = query.where(
                (DbxConnectionOwnershipRecord.owner_id == user_id)
                | DbxConnectionOwnershipRecord.connection_id.in_(shared)
            )
        return set(self.session.scalars(query).all())

    def project_ids(self, project_id: int) -> set[str]:
        return set(self.session.scalars(
            select(DbxConnectionOwnershipRecord.connection_id).where(DbxConnectionOwnershipRecord.project_id == project_id)
        ).all())


class DbxObjectAccess:
    """Owner and explicit sharing for objects stored in dbx's single-user DB."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, kind: str, object_id: str) -> DbxObjectOwnershipRecord | None:
        return self.session.get(DbxObjectOwnershipRecord, (kind, object_id))

    def visible_ids(self, *, kind: str, project_id: int, user_id: int, is_admin: bool) -> set[str]:
        query = select(DbxObjectOwnershipRecord.object_id).where(
            DbxObjectOwnershipRecord.kind == kind,
            DbxObjectOwnershipRecord.project_id == project_id,
        )
        if not is_admin:
            shared = select(DbxObjectShareRecord.object_id).where(
                DbxObjectShareRecord.kind == kind, DbxObjectShareRecord.user_id == user_id,
            )
            query = query.where(
                (DbxObjectOwnershipRecord.owner_id == user_id)
                | DbxObjectOwnershipRecord.object_id.in_(shared)
            )
        return set(self.session.scalars(query).all())

    def claim(self, *, kind: str, object_id: str, project_id: int, owner_id: int, connection_id: str | None = None) -> None:
        if self.get(kind, object_id) is not None:
            raise ValueError("dbx object already claimed")
        self.session.add(DbxObjectOwnershipRecord(
            kind=kind, object_id=object_id, project_id=project_id, owner_id=owner_id, connection_id=connection_id,
        ))
        # --- P2 ACL 双写 ---
        acl = _acl_service(self.session)
        if acl is not None:
            try:
                acl.claim_owner(
                    resource_kind="dbx_object",
                    resource_id=_dbx_object_resource_id(kind, object_id),
                    owner_id=owner_id,
                    project_id=project_id,
                )
                self.session.flush()
            except Exception:  # noqa: BLE001
                logger.exception("acl_claim failed for dbx_object %s:%s", kind, object_id)

    def share(self, *, kind: str, object_id: str, owner_id: int, user_id: int) -> None:
        owner = self.get(kind, object_id)
        if owner is None or owner.owner_id != owner_id:
            raise PermissionError("DBX object owner required")
        if user_id == owner_id:
            return
        existing = self.session.scalar(select(DbxObjectShareRecord).where(
            DbxObjectShareRecord.kind == kind,
            DbxObjectShareRecord.object_id == object_id,
            DbxObjectShareRecord.user_id == user_id,
        ))
        if existing is None:
            self.session.add(DbxObjectShareRecord(kind=kind, object_id=object_id, user_id=user_id))
        # --- P2 ACL 双写 ---
        acl = _acl_service(self.session)
        if acl is not None:
            try:
                acl.grant(
                    resource_kind="dbx_object",
                    resource_id=_dbx_object_resource_id(kind, object_id),
                    grantee_type="user",
                    grantee_id=str(user_id),
                    permission="view",
                    project_id=owner.project_id,
                    owner_id=owner.owner_id,
                    granted_by=owner.owner_id,
                )
                self.session.flush()
            except Exception:  # noqa: BLE001
                logger.exception("acl_grant failed for dbx_object %s:%s → user %d", kind, object_id, user_id)

    def unshare(self, *, kind: str, object_id: str, owner_id: int, user_id: int) -> None:
        owner = self.get(kind, object_id)
        if owner is None or owner.owner_id != owner_id:
            raise PermissionError("DBX object owner required")
        shared = self.session.scalar(select(DbxObjectShareRecord).where(
            DbxObjectShareRecord.kind == kind,
            DbxObjectShareRecord.object_id == object_id,
            DbxObjectShareRecord.user_id == user_id,
        ))
        if shared is not None:
            self.session.delete(shared)
        # --- P2 ACL 双写 ---
        acl = _acl_service(self.session)
        if acl is not None:
            try:
                rid = _dbx_object_resource_id(kind, object_id)
                rows = [
                    r for r in acl.rows_for_resource("dbx_object", rid)
                    if r.grantee_type == "user" and r.grantee_id == str(user_id) and r.granted_by is not None
                ]
                for r in rows:
                    acl.revoke(r.id)
                self.session.flush()
            except Exception:  # noqa: BLE001
                logger.exception("acl_revoke failed for dbx_object %s:%s → user %d", kind, object_id, user_id)
