"""Frozen B6 HTTP adapter: /api/v1/rebuild/runtime-nodes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from rebuild.identity.contracts import Permission, authorize
from rebuild.runtime_node.models import RuntimeNodeRecord
from rebuild.runtime_node.sftp import list_dir
from rebuild.runtime_node.service import RuntimeNodeDomainError, RuntimeNodeService

PERMISSION_MAP = {
    "list": Permission.VIEW_ALL,
    "ls": Permission.VIEW_ALL,
}


def build_runtime_node_router(
    session_factory: sessionmaker,
    token_service: Any,
    active_tokens: Any,
    *,
    sftp_func: Callable = list_dir,
) -> APIRouter:
    router = APIRouter()

    def principal(token: str, authorization: str, operation: str) -> dict[str, object] | JSONResponse:
        raw = token or (authorization[7:] if authorization.startswith("Bearer ") else "")
        if not raw or raw not in active_tokens:
            return _error(401, 1001, "invalid token")
        try:
            claims = token_service.verify(raw)
        except ValueError:
            return _error(401, 1001, "invalid token")
        if claims.get("capability") is not None:
            return _error(401, 1001, "invalid token")
        if not authorize(str(claims["role"]), PERMISSION_MAP[operation]):
            return _error(403, 1003, "permission denied")
        return claims

    @router.get("")
    def list_runtime_nodes(token: str = Header(default=""), authorization: str = Header(default="")):
        denial = principal(token, authorization, "list")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            return _success(
                [_payload(item) for item in RuntimeNodeService(session, sftp_func).list()]
            )

    @router.get("/{node_id}/ls")
    def ls_runtime_node_dir(
        node_id: int,
        path: str = "",
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        denial = principal(token, authorization, "ls")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            try:
                return _success(RuntimeNodeService(session, sftp_func).ls(node_id, path))
            except RuntimeNodeDomainError as exc:
                return _domain_error(exc)

    return router


def _payload(record: RuntimeNodeRecord) -> dict[str, object]:
    # B6-1 frozen nine-field payload: credentials are never echoed.
    return {
        "id": record.id,
        "name": record.name,
        "kind": record.kind,
        "host": record.host,
        "port": record.port,
        "user": record.user,
        "runtimeDir": record.runtime_dir,
        "status": record.status,
        "lastHeartbeat": _date(record.last_heartbeat),
    }


def _date(value: datetime | None) -> str | None:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value is not None else None


def _success(data: object) -> dict[str, object]:
    return {"code": 0, "msg": "success", "data": data}


def _error(status: int, code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "msg": message, "data": None})


def _domain_error(exc: RuntimeNodeDomainError) -> JSONResponse:
    return _error(exc.status, exc.code, exc.message)
