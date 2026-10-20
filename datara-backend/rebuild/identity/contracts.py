"""I1 身份契约：无旧 Backend 运行时依赖的最小 token/RBAC 实现。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import secrets
from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    DEVELOPER = "developer"
    OPERATOR = "operator"
    VIEWER = "viewer"


class Permission(StrEnum):
    MANAGE_USER = "manage_user"
    EDIT_DEFINITION = "edit_definition"
    RUN_INSTANCE = "run_instance"
    VIEW_ALL = "view_all"
    EXECUTE_SQL = "execute_sql"
    PROJECT_READ = "project:read"
    PROJECT_WRITE = "project:write"
    WORKFLOW_READ = "workflow:read"
    WORKFLOW_WRITE = "workflow:write"
    WORKFLOW_PUBLISH = "workflow:publish"
    WORKFLOW_RUN = "workflow:run"
    WORKFLOW_DELETE = "workflow:delete"
    TASK_READ = "task:read"
    TASK_WRITE = "task:write"
    TASK_RUN = "task:run"
    DATASOURCE_READ = "datasource:read"
    DATASOURCE_USE = "datasource:use"
    DATASOURCE_MANAGE = "datasource:manage"
    SQL_READ = "sql:read"
    SQL_WRITE_DDL = "sql:write-ddl"
    SCHEDULE_READ = "schedule:read"
    SCHEDULE_MANAGE = "schedule:manage"
    LINEAGE_READ = "lineage:read"
    QUALITY_READ = "quality:read"
    QUALITY_WRITE = "quality:write"
    QUALITY_RUN = "quality:run"
    STANDARD_READ = "standard:read"
    STANDARD_WRITE = "standard:write"
    STANDARD_APPROVE = "standard:approve"
    SECURITY_READ = "security:read"
    SECURITY_MANAGE = "security:manage"
    AUDIT_READ = "audit:read"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.DEVELOPER: frozenset({
        Permission.EDIT_DEFINITION, Permission.RUN_INSTANCE, Permission.VIEW_ALL, Permission.EXECUTE_SQL,
        Permission.PROJECT_READ, Permission.PROJECT_WRITE,
        Permission.WORKFLOW_READ, Permission.WORKFLOW_WRITE, Permission.WORKFLOW_PUBLISH,
        Permission.WORKFLOW_RUN, Permission.WORKFLOW_DELETE,
        Permission.TASK_READ, Permission.TASK_WRITE, Permission.TASK_RUN,
        Permission.DATASOURCE_READ, Permission.DATASOURCE_USE, Permission.DATASOURCE_MANAGE,
        Permission.SQL_READ, Permission.SQL_WRITE_DDL,
        Permission.SCHEDULE_READ, Permission.SCHEDULE_MANAGE,
        Permission.LINEAGE_READ,
        Permission.QUALITY_READ, Permission.QUALITY_WRITE, Permission.QUALITY_RUN,
        Permission.STANDARD_READ, Permission.STANDARD_WRITE, Permission.STANDARD_APPROVE,
        Permission.SECURITY_READ, Permission.SECURITY_MANAGE,
        Permission.AUDIT_READ,
    }),
    Role.OPERATOR: frozenset({
        Permission.RUN_INSTANCE, Permission.VIEW_ALL, Permission.EXECUTE_SQL,
        Permission.PROJECT_READ,
        Permission.WORKFLOW_READ, Permission.WORKFLOW_RUN,
        Permission.TASK_READ, Permission.TASK_RUN,
        Permission.DATASOURCE_READ, Permission.DATASOURCE_USE,
        Permission.SQL_READ,
        Permission.SCHEDULE_READ,
        Permission.LINEAGE_READ,
        Permission.QUALITY_READ, Permission.QUALITY_RUN,
        Permission.STANDARD_READ,
        Permission.AUDIT_READ,
    }),
    Role.VIEWER: frozenset({
        Permission.VIEW_ALL,
        Permission.PROJECT_READ,
        Permission.WORKFLOW_READ,
        Permission.TASK_READ,
        Permission.DATASOURCE_READ,
        Permission.SQL_READ,
        Permission.SCHEDULE_READ,
        Permission.LINEAGE_READ,
        Permission.QUALITY_READ,
        Permission.STANDARD_READ,
    }),
}


def authorize(role: Role | str, permission: Permission | str) -> bool:
    """返回角色是否拥有权限；未知角色/权限默认拒绝。"""
    try:
        resolved_role = Role(role)
        resolved_permission = Permission(permission)
    except ValueError:
        return False
    return resolved_permission in ROLE_PERMISSIONS[resolved_role]


class TokenService:
    """无状态 HMAC token 服务；撤销/TTL 由 ActiveTokenStore 数据库持久化。"""

    def __init__(self, secret: str, ttl_seconds: int = 86_400) -> None:
        if not secret:
            raise ValueError("token secret is required")
        if ttl_seconds <= 0:
            raise ValueError("token ttl must be positive")
        self._secret = secret.encode("utf-8")
        self._ttl_seconds = ttl_seconds

    def issue(
        self,
        *,
        user_id: int,
        username: str,
        role: Role,
        capability: str | None = None,
    ) -> str:
        now = int(time.time())
        payload = {
            "jti": secrets.token_urlsafe(18),
            "user_id": user_id,
            "username": username,
            "role": role.value,
            "iat": now,
            "exp": now + self._ttl_seconds,
        }
        if capability is not None:
            if not capability or len(capability) > 128:
                raise ValueError("token capability must be between 1 and 128 characters")
            payload["capability"] = capability
        encoded = _encode(payload)
        signature = hmac.new(self._secret, encoded, hashlib.sha256).digest()
        return f"{_b64(encoded)}.{_b64(signature)}"

    def verify(self, token: str) -> dict[str, object]:
        try:
            encoded_part, signature_part = token.split(".", 1)
            encoded = _unb64(encoded_part)
            signature = _unb64(signature_part)
            expected = hmac.new(self._secret, encoded, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError("invalid token signature")
            payload = json.loads(encoded.decode("utf-8"))
            if int(payload["exp"]) < int(time.time()):
                raise ValueError("token expired")
            Role(payload["role"])
            claims = {key: payload[key] for key in ("user_id", "username", "role")}
            if "capability" in payload:
                capability = payload["capability"]
                if not isinstance(capability, str) or not capability or len(capability) > 128:
                    raise ValueError("invalid token capability")
                claims["capability"] = capability
            return claims
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("invalid token") from exc


def _encode(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
