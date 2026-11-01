"""Hash-only API-key issuance, rotation and revocation endpoints."""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from rebuild.apikey.models import ApiKeyRecord
from rebuild.identity.contracts import Permission, authorize


class ApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scopes: dict[str, list] = {"permissions": [], "projectIds": []}
    expiresAt: datetime | None = None


def build_apikey_router(session_factory, token_service: Any, active_tokens: Any) -> APIRouter:
    router = APIRouter()

    def guard(token: str, authorization: str, manage: bool = False):
        raw = token or (authorization[7:] if authorization.startswith("Bearer ") else "")
        if not raw or raw not in active_tokens:
            return _error(401, 1001, "invalid token")
        try:
            claims = token_service.verify(raw)
        except ValueError:
            return _error(401, 1001, "invalid token")
        permission = Permission.MANAGE_USER if manage else Permission.VIEW_ALL
        if claims.get("capability") is not None or not authorize(str(claims["role"]), permission):
            return _error(403, 1003, "permission denied")
        return claims

    @router.get("/api-keys")
    def list_keys(token: str = Header(default=""), authorization: str = Header(default="")):
        if isinstance((denial := guard(token, authorization)), JSONResponse):
            return denial
        with session_factory() as session:
            rows = session.scalars(select(ApiKeyRecord).order_by(ApiKeyRecord.id.desc())).all()
            return _ok([_payload(row) for row in rows])

    @router.post("/api-keys", status_code=201)
    def issue_key(body: ApiKeyRequest, token: str = Header(default=""), authorization: str = Header(default="")):
        claims = guard(token, authorization, manage=True)
        if isinstance(claims, JSONResponse):
            return claims
        plain = "dk_live_" + secrets.token_urlsafe(32)
        # claims 里只有 user_id/username/role，没有 sub；归属必须落用户 ID 才能抗改名与删除。
        creator_id = int(claims["user_id"]) if claims.get("user_id") is not None else None
        row = ApiKeyRecord(name=body.name, key_hash=_digest(plain), key_prefix=plain[:16],
                           scopes_json=_scopes(body.scopes), expires_at=body.expiresAt,
                           created_by=str(claims.get("username", "")), created_by_user_id=creator_id)
        with session_factory() as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            return _ok({"key": _payload(row), "plainKey": plain})

    @router.post("/api-keys/{key_id}/rotate", status_code=201)
    def rotate_key(key_id: int, token: str = Header(default=""), authorization: str = Header(default="")):
        claims = guard(token, authorization, manage=True)
        if isinstance(claims, JSONResponse):
            return claims
        with session_factory() as session:
            row = session.get(ApiKeyRecord, key_id)
            if row is None:
                return _error(404, 4042, "API key not found")
            plain = "dk_live_" + secrets.token_urlsafe(32)
            row.key_hash, row.key_prefix = _digest(plain), plain[:16]
            row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            session.commit()
            return _ok({"key": _payload(row), "plainKey": plain})

    @router.post("/api-keys/{key_id}/revoke")
    def revoke_key(key_id: int, token: str = Header(default=""), authorization: str = Header(default="")):
        if isinstance((denial := guard(token, authorization, manage=True)), JSONResponse):
            return denial
        with session_factory() as session:
            row = session.get(ApiKeyRecord, key_id)
            if row is None:
                return _error(404, 4042, "API key not found")
            row.status, row.revoked_at = "revoked", datetime.now(timezone.utc).replace(tzinfo=None)
            session.commit()
            return _ok(_payload(row))

    return router


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _scopes(value: dict) -> str:
    return __import__("json").dumps({"permissions": list(value.get("permissions", [])), "projectIds": list(value.get("projectIds", []))}, separators=(",", ":"))


def _payload(row: ApiKeyRecord) -> dict:
    return {"id": row.id, "name": row.name, "keyPrefix": row.key_prefix, "scopes": row.scopes,
            "status": row.status, "expiresAt": row.expires_at.isoformat() if row.expires_at else None,
            "lastUsedAt": row.last_used_at.isoformat() if row.last_used_at else None,
            "createdBy": row.created_by, "createdByUserId": row.created_by_user_id,
            "revokedAt": row.revoked_at.isoformat() if row.revoked_at else None,
            "createdAt": row.created_at.isoformat() if row.created_at else "", "updatedAt": row.updated_at.isoformat() if row.updated_at else ""}


def _ok(data):
    return {"code": 0, "msg": "success", "data": data}


def _error(status, code, message):
    return JSONResponse(status_code=status, content={"code": code, "msg": message, "data": None})
