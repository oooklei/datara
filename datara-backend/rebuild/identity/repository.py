"""I1 身份持久化仓储。"""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from rebuild.identity.contracts import Role
from rebuild.identity.models import UserRecord
from rebuild.identity.passwords import hash_password


def digest_token(token: str) -> str:
    """Return the one-way lookup key used for bearer-token persistence."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class UserRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, *, username: str, password: str, role: Role) -> UserRecord:
        record = UserRecord(username=username, password_hash=hash_password(password), role=role.value)
        self._session.add(record)
        self._session.flush()
        return record

    def find_by_username(self, username: str) -> UserRecord | None:
        return self._session.scalar(select(UserRecord).where(UserRecord.username == username))

    def find_by_id(self, user_id: int) -> UserRecord | None:
        return self._session.get(UserRecord, user_id)

    def list_users(self) -> list[UserRecord]:
        return list(self._session.scalars(select(UserRecord).order_by(UserRecord.id)).all())

    def update_password(self, user_id: int, password: str) -> UserRecord:
        record = self._session.get(UserRecord, user_id)
        if record is None:
            raise ValueError("user not found")
        record.password_hash = hash_password(password)
        self._session.flush()
        return record

    def update_role(self, user_id: int, role: Role) -> UserRecord:
        record = self._session.get(UserRecord, user_id)
        if record is None:
            raise ValueError("user not found")
        record.role = role.value
        self._session.flush()
        return record

    def count_enabled_admins_excluding(self, user_id: int) -> int:
        return int(
            self._session.scalar(
                select(func.count(UserRecord.id)).where(
                    UserRecord.role == Role.ADMIN.value,
                    UserRecord.status == "enabled",
                    UserRecord.id != user_id,
                )
            )
            or 0
        )

