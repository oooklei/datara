"""Controlled OpenAPI definition administration endpoints.

Definitions are metadata for Datara-owned facades; arbitrary proxy URLs are
never accepted.  The table is intentionally small and uses an explicit status
machine so publication cannot accidentally expose drafts.
"""
import time
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Integer, String, Text, func, inspect, select, and_
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base
from rebuild.identity.contracts import Permission, authorize
from rebuild.apikey.service import ApiKeyAuthError, ApiKeyVerifier


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


class ApiCallLogRecord(Base):
    """Sanitized API gateway call log.

    This table deliberately has no request/body/key columns that could retain
    credentials or payloads.  Gateway integrations may use ``record_call``;
    the administration surface only exposes the filtered read model.
    """

    __tablename__ = "rebuild_api_call_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    api_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    key_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    principal: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp(), index=True)


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
    if "rebuild_api_call_log" not in inspect(engine).get_table_names():
        ApiCallLogRecord.__table__.create(bind=engine)
    return {"created": True, "revision": "i15_0004_api_call_log"}


def record_call(session, *, request_id: str, api_id: int, key_id: int,
                principal: str, project_id: int | None, status_code: int,
                latency_ms: int, result: str, error_code: str | None = None):
    """Append one sanitized gateway call record.

    The record never carries the raw key, request body, or SQL text (C4).  The
    caller owns the transaction boundary; gateway integrations should treat a
    failure here as a fail-closed condition rather than a silent success.
    """
    row = ApiCallLogRecord(
        request_id=request_id,
        api_id=api_id,
        key_id=key_id,
        principal=principal,
        project_id=project_id,
        status_code=status_code,
        latency_ms=latency_ms,
        result=result,
        error_code=error_code,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def build_openapi_admin_router(
    session_factory,
    token_service: Any,
    active_tokens: Any,
    api_key_verifier: ApiKeyVerifier | None = None,
) -> APIRouter:
    router = APIRouter()

    def guard(token: str, authorization: str, manage: bool = False, api_key: str = ""):
        raw = token or (authorization[7:] if authorization.lower().startswith("bearer ") else "")
        # API keys are an additive gateway credential. Existing bearer-token
        # behavior remains unchanged; a key is considered only when no bearer
        # credential was supplied and only for read-only management entries.
        if not raw and api_key_verifier is not None and not manage and api_key:
            try:
                return api_key_verifier.verify(api_key, permission=Permission.SECURITY_READ.value)
            except ApiKeyAuthError:
                return _error(401, 1001, "invalid API key")
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

    @router.get("/call-logs")
    def list_call_logs(
        api_id: int | None = None,
        key_id: int | None = None,
        from_: datetime | None = Query(default=None, alias="from"),
        to: datetime | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
        x_api_key: str = Header(default="", alias="X-API-Key"),
    ):
        """List sanitized gateway call records with stable pagination.

        ``from``/``to`` are accepted as query parameters by FastAPI despite
        their Python-safe aliases.  No sensitive request material is returned.
        """
        denial = guard(token, authorization, api_key=x_api_key)
        if isinstance(denial, JSONResponse):
            return denial
        conditions = []
        if api_id is not None:
            conditions.append(ApiCallLogRecord.api_id == api_id)
        if key_id is not None:
            conditions.append(ApiCallLogRecord.key_id == key_id)
        if from_ is not None:
            conditions.append(ApiCallLogRecord.requested_at >= from_)
        if to is not None:
            conditions.append(ApiCallLogRecord.requested_at < to)
        with session_factory() as session:
            query = select(ApiCallLogRecord)
            count_query = select(func.count()).select_from(ApiCallLogRecord)
            if conditions:
                query = query.where(and_(*conditions))
                count_query = count_query.where(and_(*conditions))
            rows = session.scalars(query.order_by(ApiCallLogRecord.requested_at.desc(), ApiCallLogRecord.id.desc()).offset(offset).limit(limit)).all()
            total = int(session.scalar(count_query) or 0)
            return _ok({"list": [_call_log_payload(row) for row in rows], "total": total})

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

    def _key_denial(message: str):
        """Map an ApiKeyVerifier failure onto the frozen gateway error codes."""
        if "expired" in message:
            return _error(403, 4093, "API key has expired")
        if "not active" in message:
            return _error(403, 4094, "API key is revoked")
        if "scope denied" in message:
            return _error(403, 4095, "insufficient scope")
        return _error(401, 1001, "invalid API key")

    @router.api_route("/gateway/{api_path:path}", methods=["GET", "POST", "PUT", "DELETE"])
    def gateway_invoke(api_path: str, request: Request, x_api_key: str = Header(default="", alias="X-API-Key")):
        """Invoke a controlled facade on behalf of an external API-key caller.

        Minimal closure: the definition is resolved by ``(path, method)`` and the
        key is authorized against the definition's ``required_permission``; no
        arbitrary URL proxying is performed (C2).  A sanitized call record is
        written for every resolved attempt, and a logging failure on the success
        path fails closed (5041) instead of faking an audited success (C4).
        """
        started = time.perf_counter()
        if api_key_verifier is None:
            return _error(503, 5041, "facade unavailable")
        if not x_api_key:
            return _error(401, 1001, "invalid API key")
        try:
            principal = api_key_verifier.verify(x_api_key)
        except ApiKeyAuthError as exc:
            return _key_denial(str(exc))

        normalized = api_path if api_path.startswith("/") else f"/{api_path}"
        method = request.method.upper()
        with session_factory() as session:
            row = session.scalar(select(ApiDefinitionRecord).where(
                ApiDefinitionRecord.path == normalized,
                ApiDefinitionRecord.method == method,
            ))
            if row is None:
                return _error(404, 4041, "API definition not found")
            project_id = min(principal.project_ids) if principal.project_ids else None
            denial = None
            if row.status == "draft":
                denial = (404, 4041, "API definition not published")
            elif row.status == "disabled":
                denial = (409, 4092, "API definition disabled")
            elif not principal.allows(row.required_permission, project_id):
                denial = (403, 4095, "insufficient scope")
            if denial is not None:
                status_code, error_code, message = denial
                try:
                    record_call(session, request_id=uuid.uuid4().hex, api_id=row.id,
                                key_id=principal.key_id, principal=f"apikey:{principal.key_id}",
                                project_id=project_id, status_code=status_code,
                                latency_ms=int((time.perf_counter() - started) * 1000),
                                result="denied", error_code=str(error_code))
                except Exception:
                    pass
                return _error(status_code, error_code, message)
            request_id = uuid.uuid4().hex
            latency_ms = int((time.perf_counter() - started) * 1000)
            try:
                record_call(session, request_id=request_id, api_id=row.id, key_id=principal.key_id,
                            principal=f"apikey:{principal.key_id}", project_id=project_id,
                            status_code=200, latency_ms=latency_ms, result="success")
            except Exception:
                return _error(503, 5041, "facade unavailable")
            return _ok({
                "requestId": request_id,
                "apiId": row.id,
                "apiPath": row.path,
                "method": row.method,
                "definition": {"id": row.id, "name": row.name, "version": row.version, "requiredPermission": row.required_permission},
                "facade": "registered",
                "result": None,
            })
    return router


def _payload(row):
    return {"id": row.id, "name": row.name, "path": row.path, "method": row.method, "version": row.version, "description": row.description, "requiredPermission": row.required_permission, "status": row.status, "createdBy": row.created_by, "createdAt": row.created_at.isoformat() if row.created_at else "", "updatedAt": row.updated_at.isoformat() if row.updated_at else ""}


def _call_log_payload(row: ApiCallLogRecord):
    return {
        "requestId": row.request_id,
        "apiId": row.api_id,
        "keyId": row.key_id,
        "principal": row.principal,
        "projectId": row.project_id,
        "statusCode": row.status_code,
        "latencyMs": row.latency_ms,
        "result": row.result,
        "errorCode": row.error_code,
        "requestedAt": row.requested_at.isoformat() if row.requested_at else "",
    }


def _ok(data): return {"code": 0, "msg": "success", "data": data}
def _error(status, code, message): return JSONResponse(status_code=status, content={"code": code, "msg": message, "data": None})
