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
    DEV = "dev"
    ANALYST = "analyst"
    VIEWER = "viewer"


class Permission(StrEnum):
    MANAGE_USER = "manage_user"
    EDIT_DEFINITION = "edit_definition"
    RUN_INSTANCE = "run_instance"
    VIEW_ALL = "view_all"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(Permission),
    Role.DEV: frozenset({Permission.EDIT_DEFINITION, Permission.RUN_INSTANCE, Permission.VIEW_ALL}),
    Role.ANALYST: frozenset({Permission.RUN_INSTANCE, Permission.VIEW_ALL}),
    Role.VIEWER: frozenset({Permission.VIEW_ALL}),
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
    """无状态 HMAC token 服务，后续 API 层可在外部 Redis 加入撤销/TTL。"""

    def __init__(self, secret: str, ttl_seconds: int = 86_400) -> None:
        if not secret:
            raise ValueError("token secret is required")
        if ttl_seconds <= 0:
            raise ValueError("token ttl must be positive")
        self._secret = secret.encode("utf-8")
        self._ttl_seconds = ttl_seconds

    def issue(self, *, user_id: int, username: str, role: Role) -> str:
        now = int(time.time())
        payload = {
            "jti": secrets.token_urlsafe(18),
            "user_id": user_id,
            "username": username,
            "role": role.value,
            "iat": now,
            "exp": now + self._ttl_seconds,
        }
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
            return {key: payload[key] for key in ("user_id", "username", "role")}
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("invalid token") from exc


def _encode(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

