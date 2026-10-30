"""Owner and explicit-sharing rules for dbx connection IDs."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import DbxConnectionOwnershipRecord, DbxConnectionShareRecord, DbxObjectOwnershipRecord, DbxObjectShareRecord


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
        self.session.flush()
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
