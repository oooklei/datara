"""I1 身份持久化仓储。"""

import hashlib

from sqlalchemy import select
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

