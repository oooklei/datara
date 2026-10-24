"""Controlled OpenAPI definition administration endpoints.

Definitions are metadata for Datara-owned facades; arbitrary proxy URLs are
never accepted.  The table is intentionally small and uses an explicit status
machine so publication cannot accidentally expose drafts.
"""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Integer, String, Text, func, inspect, select
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base
from rebuild.identity.contracts import Permission, authorize


class ApiDefinitionRecord(Base):
    __tablename__ = "rebuild_api_definition"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    required_permission: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())


class ApiDefinitionInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    path: str = Field(pattern=r"^/rebuild/[a-z0-9/_-]+$")
    method: str = Field(pattern=r"^(GET|POST|PUT|DELETE)$")
    version: str = Field(min_length=1, max_length=32)
    description: str = ""
    requiredPermission: str = Field(min_length=1, max_length=128)


def apply_openapi_admin_migrations(engine):
    if "rebuild_api_definition" not in inspect(engine).get_table_names():
        ApiDefinitionRecord.__table__.create(bind=engine)
    return {"created": True, "revision": "i15_0003_api_definition"}


def build_openapi_admin_router(session_factory, token_service: Any, active_tokens: Any) -> APIRouter:
    router = APIRouter()

    def guard(token: str, authorization: str, manage: bool = False):
        raw = token or (authorization[7:] if authorization.lower().startswith("bearer ") else "")
        try:
            claims = token_service.verify(raw)
        except Exception:
            return _error(401, 1001, "invalid token")
        permission = Permission.SECURITY_MANAGE if manage else Permission.SECURITY_READ
        if claims.get("capability") is not None or not authorize(str(claims.get("role", "")), permission):
            return _error(403, 1003, "permission denied")
        return claims

    @router.get("/definitions")
    def list_definitions(token: str = Header(default=""), authorization: str = Header(default="")):
        denial = guard(token, authorization)
        if isinstance(denial, JSONResponse): return denial
        with session_factory() as session:
            rows = session.scalars(select(ApiDefinitionRecord).order_by(ApiDefinitionRecord.id.desc())).all()
            return _ok([_payload(r) for r in rows])

    @router.post("/definitions", status_code=201)
    def create_definition(body: ApiDefinitionInput, token: str = Header(default=""), authorization: str = Header(default="")):
        claims = guard(token, authorization, True)
        if isinstance(claims, JSONResponse): return claims
        with session_factory() as session:
            if session.scalar(select(ApiDefinitionRecord).where(ApiDefinitionRecord.path == body.path, ApiDefinitionRecord.method == body.method, ApiDefinitionRecord.version == body.version)):
                return _error(409, 4091, "duplicate definition")
            row = ApiDefinitionRecord(**body.model_dump(by_alias=False, exclude={"requiredPermission"}), required_permission=body.requiredPermission, created_by=str(claims.get("sub", "admin")))
            session.add(row); session.commit(); session.refresh(row)
            return _ok(_payload(row))

    @router.put("/definitions/{definition_id}")
    def update_definition(definition_id: int, body: ApiDefinitionInput, token: str = Header(default=""), authorization: str = Header(default="")):
        claims = guard(token, authorization, True)
        if isinstance(claims, JSONResponse): return claims
        with session_factory() as session:
            row = session.get(ApiDefinitionRecord, definition_id)
            if not row: return _error(404, 4041, "API definition not found")
            if row.status != "draft": return _error(409, 4092, "invalid status transition")
            for key, value in body.model_dump().items():
                setattr(row, {"requiredPermission": "required_permission"}.get(key, key), value)
            session.commit(); session.refresh(row); return _ok(_payload(row))

    @router.delete("/definitions/{definition_id}")
    def delete_definition(definition_id: int, token: str = Header(default=""), authorization: str = Header(default="")):
        claims = guard(token, authorization, True)
        if isinstance(claims, JSONResponse): return claims
        with session_factory() as session:
            row = session.get(ApiDefinitionRecord, definition_id)
            if not row: return _error(404, 4041, "API definition not found")
            if row.status != "draft": return _error(409, 4092, "invalid status transition")
            session.delete(row); session.commit(); return _ok({"deleted": True})

    def transition(definition_id: int, target: str, token: str, authorization: str):
        claims = guard(token, authorization, True)
        if isinstance(claims, JSONResponse): return claims
        with session_factory() as session:
            row = session.get(ApiDefinitionRecord, definition_id)
            if not row: return _error(404, 4041, "API definition not found")
            allowed = {"published": {"draft"}, "disabled": {"published"}, "draft": {"disabled"}}
            if row.status not in allowed[target]: return _error(409, 4092, "invalid status transition")
            row.status = target; session.commit(); session.refresh(row); return _ok(_payload(row))

    @router.post("/definitions/{definition_id}/publish")
    def publish_definition(definition_id: int, token: str = Header(default=""), authorization: str = Header(default="")): return transition(definition_id, "published", token, authorization)
    @router.post("/definitions/{definition_id}/disable")
    def disable_definition(definition_id: int, token: str = Header(default=""), authorization: str = Header(default="")): return transition(definition_id, "disabled", token, authorization)
    @router.post("/definitions/{definition_id}/enable")
    def enable_definition(definition_id: int, token: str = Header(default=""), authorization: str = Header(default="")): return transition(definition_id, "draft", token, authorization)
    return router


def _payload(row):
    return {"id": row.id, "name": row.name, "path": row.path, "method": row.method, "version": row.version, "description": row.description, "requiredPermission": row.required_permission, "status": row.status, "createdBy": row.created_by, "createdAt": row.created_at.isoformat() if row.created_at else "", "updatedAt": row.updated_at.isoformat() if row.updated_at else ""}


def _ok(data): return {"code": 0, "msg": "success", "data": data}
def _error(status, code, message): return JSONResponse(status_code=status, content={"code": code, "msg": message, "data": None})
