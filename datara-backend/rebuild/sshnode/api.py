"""Frozen B7 HTTP adapter: /api/v1/rebuild/ssh-nodes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import sessionmaker

from rebuild.identity.contracts import Permission, authorize
from rebuild.sshnode.models import SshNodeRecord
from rebuild.sshnode.probe import probe
from rebuild.sshnode.service import SshNodeDomainError, SshNodeInput, SshNodeService


class SshNodeRequest(BaseModel):
    name: str
    host: str
    port: int = Field(default=22, ge=1, le=65535)
    sshUser: str = "root"
    cred: str | None = ""
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True


PERMISSION_MAP = {
    "list": Permission.VIEW_ALL,
    "create": Permission.EDIT_DEFINITION,
    "update": Permission.EDIT_DEFINITION,
    "delete": Permission.EDIT_DEFINITION,
    "probe": Permission.EDIT_DEFINITION,
}


def build_sshnode_router(
    session_factory: sessionmaker,
    token_service: Any,
    active_tokens: Any,
    *,
    probe_func: Callable[[str, int, str, str], tuple[bool, str]] = probe,
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

    def service(session) -> SshNodeService:
        return SshNodeService(session, probe_func)

    @router.get("")
    def list_ssh_nodes(token: str = Header(default=""), authorization: str = Header(default="")):
        denial = principal(token, authorization, "list")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            return _success([_payload(item) for item in service(session).list()])

    @router.post("")
    def create_ssh_node(
        body: SshNodeRequest, token: str = Header(default=""), authorization: str = Header(default="")
    ):
        denial = principal(token, authorization, "create")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            try:
                record = service(session).create(_input(body))
            except SshNodeDomainError as exc:
                return _domain_error(exc)
            return _success(_payload(record))

    @router.put("/{node_id}")
    def update_ssh_node(
        node_id: int,
        body: SshNodeRequest,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        denial = principal(token, authorization, "update")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            try:
                record = service(session).update(node_id, _input(body))
            except SshNodeDomainError as exc:
                return _domain_error(exc)
            return _success(_payload(record))

    @router.delete("/{node_id}")
    def delete_ssh_node(
        node_id: int, token: str = Header(default=""), authorization: str = Header(default="")
    ):
        denial = principal(token, authorization, "delete")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            try:
                result = service(session).delete(node_id)
            except SshNodeDomainError as exc:
                return _domain_error(exc)
            return _success(result)

    @router.post("/{node_id}/probe")
    def probe_ssh_node(
        node_id: int, token: str = Header(default=""), authorization: str = Header(default="")
    ):
        denial = principal(token, authorization, "probe")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            try:
                result = service(session).probe(node_id)
            except SshNodeDomainError as exc:
                return _domain_error(exc)
            return _success(result)

    return router


def _input(body: SshNodeRequest) -> SshNodeInput:
    return SshNodeInput(
        name=body.name,
        host=body.host,
        port=body.port,
        ssh_user=body.sshUser,
        cred=body.cred or "",
        tags=body.tags,
        enabled=body.enabled,
    )


def _payload(record: SshNodeRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "name": record.name,
        "host": record.host,
        "port": record.port,
        "sshUser": record.ssh_user,
        # R-34 security debt: migration-period full credential echo is frozen.
        "cred": record.cred,
        "tags": record.tags or [],
        "enabled": bool(record.enabled),
        "heartbeatState": record.heartbeat_state,
        "lastSeen": _date(record.last_seen),
        "createTime": _date(record.created_at),
    }


def _date(value: datetime | None) -> str | None:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value is not None else None


def _success(data: object) -> dict[str, object]:
    return {"code": 0, "msg": "success", "data": data}


def _error(status: int, code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "msg": message, "data": None})


def _domain_error(exc: SshNodeDomainError) -> JSONResponse:
    return _error(exc.status, exc.code, exc.message)
