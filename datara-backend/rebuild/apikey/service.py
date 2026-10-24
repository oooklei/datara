"""Verification service for hash-only Open API keys.

The management API deliberately never persists the plaintext credential.  This
service is the reusable boundary for consumers that need to authenticate one:
it narrows the lookup by prefix, compares the digest in constant time, checks
the lifecycle fields, and applies the permission/project scopes.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from rebuild.apikey.models import ApiKeyRecord


class ApiKeyAuthError(ValueError):
    """Raised when a presented API key cannot be used."""


@dataclass(frozen=True)
class ApiKeyPrincipal:
    """Safe identity and authorization context returned after verification."""

    key_id: int
    name: str
    created_by: str
    permissions: frozenset[str]
    project_ids: frozenset[int]

    def allows(self, permission: str | None = None, project_id: int | None = None) -> bool:
        """Return whether this key's scopes allow an operation.

        An empty project scope is intentionally treated as all projects; an
        explicitly populated list is restrictive.  Permissions remain
        restrictive even when the list is empty.
        """
        if permission is not None and permission not in self.permissions:
            return False
        return project_id is None or not self.project_ids or project_id in self.project_ids


class ApiKeyVerifier:
    """Verify Open API keys against an injected SQLAlchemy session factory."""

    def __init__(self, session_factory: Any, *, prefix: str = "dk_live_") -> None:
        if not prefix:
            raise ValueError("API key prefix is required")
        self._session_factory = session_factory
        self._prefix = prefix

    def verify(
        self,
        raw_key: str,
        *,
        permission: str | None = None,
        project_id: int | None = None,
    ) -> ApiKeyPrincipal:
        """Verify a key and optionally enforce one permission/project scope."""
        if not isinstance(raw_key, str) or not raw_key.startswith(self._prefix):
            raise ApiKeyAuthError("invalid API key")
        # The persisted prefix is deliberately used as a coarse lookup only;
        # the complete credential is always checked against its hash below.
        key_prefix = raw_key[:16]
        with self._session_factory() as session:
            row = session.scalar(select(ApiKeyRecord).where(ApiKeyRecord.key_prefix == key_prefix))
            if row is None or not hmac.compare_digest(row.key_hash, _digest(raw_key)):
                raise ApiKeyAuthError("invalid API key")
            now = datetime.now(timezone.utc)
            expires_at = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at else None
            if row.status != "active" or row.revoked_at is not None:
                raise ApiKeyAuthError("API key is not active")
            if expires_at is not None and expires_at <= now:
                raise ApiKeyAuthError("API key has expired")
            scopes = row.scopes
            principal = ApiKeyPrincipal(
                key_id=row.id,
                name=row.name,
                created_by=row.created_by,
                permissions=frozenset(str(item) for item in scopes.get("permissions", [])),
                project_ids=frozenset(int(item) for item in scopes.get("projectIds", [])),
            )
            if not principal.allows(permission, project_id):
                raise ApiKeyAuthError("API key scope denied")
            row.last_used_at = now.replace(tzinfo=None)
            session.commit()
            return principal


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = ["ApiKeyAuthError", "ApiKeyPrincipal", "ApiKeyVerifier"]
