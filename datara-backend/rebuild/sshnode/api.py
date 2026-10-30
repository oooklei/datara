"""Frozen B7 HTTP adapter: /api/v1/rebuild/ssh-nodes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.orm import sessionmaker

from rebuild.identity.contracts import Permission, Role, authorize
from rebuild.identity.models import UserRecord
from rebuild.sshnode.governance import SshNodeAccess, SshNodeGovernanceRecord, SshNodeShareRecord
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
    allowTrial: bool = False


class SshNodeShareRequest(BaseModel):
    userId: int = Field(gt=0)


class SshNodeClaimRequest(BaseModel):
    ownerId: int = Field(gt=0)
    allowTrial: bool = False


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

    def access_denial(session, node_id: int, claims: dict[str, object], *, manage: bool = False) -> JSONResponse | None:
        if session.get(SshNodeRecord, node_id) is None:
            return _error(404, 4101, "SSH node not found")
        access = SshNodeAccess(session)
        user_id = int(claims["user_id"])
        is_admin = claims.get("role") == Role.ADMIN.value
        allowed = access.can_manage(node_id, user_id, is_admin=is_admin) if manage else access.can_view(node_id, user_id, is_admin=is_admin)
        return None if allowed else _error(403, 1003, "SSH node not shared")

    @router.get("")
    def list_ssh_nodes(token: str = Header(default=""), authorization: str = Header(default="")):
        denial = principal(token, authorization, "list")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            access = SshNodeAccess(session)
            admin = denial.get("role") == Role.ADMIN.value
            return _success([_payload(item, access.get(item.id)) for item in service(session).list()
                             if access.can_view(item.id, int(denial["user_id"]), is_admin=admin)])

    @router.get("/trial-candidates")
    def trial_candidates(token: str = Header(default=""), authorization: str = Header(default="")):
        claims = principal(token, authorization, "list")
        if isinstance(claims, JSONResponse):
            return claims
        with session_factory() as session:
            access = SshNodeAccess(session)
            admin = claims.get("role") == Role.ADMIN.value
            return _success([_payload(item, governance) for item in service(session).list()
                             if (governance := access.get(item.id)) is not None and item.enabled and governance.allow_trial
                             and access.can_view(item.id, int(claims["user_id"]), is_admin=admin)])

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
                governance = SshNodeAccess(session).claim(record.id, int(denial["user_id"]), allow_trial=body.allowTrial)
                session.commit()
            except SshNodeDomainError as exc:
                return _domain_error(exc)
            return _success(_payload(record, governance))

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
            blocked = access_denial(session, node_id, denial, manage=True)
            if blocked is not None:
                return blocked
            try:
                record = service(session).update(node_id, _input(body))
                governance = SshNodeAccess(session).get(node_id)
                if governance is None:
                    governance = SshNodeAccess(session).claim(node_id, int(denial["user_id"]), allow_trial=body.allowTrial)
                else:
                    governance.allow_trial = body.allowTrial
                session.commit()
            except SshNodeDomainError as exc:
                return _domain_error(exc)
            return _success(_payload(record, governance))

    @router.delete("/{node_id}")
    def delete_ssh_node(
        node_id: int, token: str = Header(default=""), authorization: str = Header(default="")
    ):
        denial = principal(token, authorization, "delete")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            blocked = access_denial(session, node_id, denial, manage=True)
            if blocked is not None:
                return blocked
            try:
                session.execute(delete(SshNodeShareRecord).where(SshNodeShareRecord.node_id == node_id))
                session.execute(delete(SshNodeGovernanceRecord).where(SshNodeGovernanceRecord.node_id == node_id))
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
            blocked = access_denial(session, node_id, denial)
            if blocked is not None:
                return blocked
            try:
                result = service(session).probe(node_id)
            except SshNodeDomainError as exc:
                return _domain_error(exc)
            return _success(result)

    @router.post("/{node_id}/share")
    def share_ssh_node(node_id: int, body: SshNodeShareRequest, token: str = Header(default=""), authorization: str = Header(default="")):
        claims = principal(token, authorization, "update")
        if isinstance(claims, JSONResponse):
            return claims
        with session_factory() as session:
            blocked = access_denial(session, node_id, claims, manage=True)
            if blocked is not None:
                return blocked
            if session.get(SshNodeGovernanceRecord, node_id) is None or session.get(UserRecord, body.userId) is None:
                return _error(404, 4101, "SSH node or user not found")
            SshNodeAccess(session).share(node_id, body.userId)
            session.commit()
            return _success({"nodeId": node_id, "userId": body.userId})

    @router.post("/{node_id}/claim")
    def claim_ssh_node(node_id: int, body: SshNodeClaimRequest, token: str = Header(default=""), authorization: str = Header(default="")):
        claims = principal(token, authorization, "update")
        if isinstance(claims, JSONResponse):
            return claims
        if claims.get("role") != Role.ADMIN.value:
            return _error(403, 1003, "admin required")
        with session_factory() as session:
            if session.get(SshNodeRecord, node_id) is None or session.get(UserRecord, body.ownerId) is None:
                return _error(404, 4101, "SSH node or owner not found")
            try:
                SshNodeAccess(session).claim(node_id, body.ownerId, allow_trial=body.allowTrial)
            except PermissionError:
                return _error(409, 4102, "SSH node already claimed")
            session.commit()
            return _success({"nodeId": node_id, "ownerId": body.ownerId})

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


def _payload(record: SshNodeRecord, governance: SshNodeGovernanceRecord | None = None) -> dict[str, object]:
    return {
        "id": record.id,
        "name": record.name,
        "host": record.host,
        "port": record.port,
        "sshUser": record.ssh_user,
        "hasCredential": bool(record.cred),
        "allowTrial": bool(governance.allow_trial) if governance is not None else False,
        "ownerId": governance.owner_id if governance is not None else None,
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
