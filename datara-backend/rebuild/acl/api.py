"""统一资源分享（ACL）HTTP 接口（设计 §7.4.5 / §7.5）。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from rebuild.identity.contracts import Permission, Role, authorize
from rebuild.identity.models import UserRecord
from rebuild.project.models import ProjectRecord

from .models import ACL_PERMISSIONS, GRANTEE_TYPES, AclAuditRecord, IdentityAuditRecord, ResourceAclRecord
from .policy import PolicyService, Subject
from .service import AclError, AclService, AuditWriter

_AUTH_401 = {"code": 1001, "msg": "invalid token", "data": None}


class ShareCreateRequest(BaseModel):
    resource_kind: str
    resource_id: str
    grantee_type: str
    grantee_id: str | int | None = None
    grantee_username: str | None = None
    permission: str = "view"
    project_id: int | None = None
    expires_at: datetime | None = None


def _row_payload(row: ResourceAclRecord) -> dict[str, object]:
    return {
        "id": row.id,
        "resource_kind": row.resource_kind,
        "resource_id": row.resource_id,
        "project_id": row.project_id,
        "owner_id": row.owner_id,
        "grantee_type": row.grantee_type,
        "grantee_id": row.grantee_id,
        "permission": row.permission,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "granted_by": row.granted_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _client_meta(request: Request) -> tuple[str, str]:
    ip = ""
    if request.client is not None:
        ip = request.client.host or ""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    return ip, request.headers.get("user-agent", "")


def build_acl_router(
    session_factory: sessionmaker,
    current_user: Callable[[str], dict[str, object]],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/rebuild", tags=["rebuild-acl"])

    def subject_of(user: dict[str, object]) -> Subject:
        return Subject(
            user_id=int(user["user_id"]),
            platform_role=str(user.get("role", "")),
            username=str(user.get("username", "")),
        )

    def authenticate(authorization: str) -> tuple[dict[str, object], JSONResponse | None]:
        try:
            return current_user(authorization), None
        except ValueError:
            return {}, JSONResponse(status_code=401, content=dict(_AUTH_401))

    # ---- 授权 ----

    @router.post("/shares")
    def create_share(
        body: ShareCreateRequest,
        request: Request,
        authorization: str = Header(default=""),
    ):
        user, denial = authenticate(authorization)
        if denial is not None:
            return denial
        if body.grantee_type not in GRANTEE_TYPES:
            return JSONResponse(
                status_code=422,
                content={"code": 4002, "msg": "unsupported grantee_type", "data": None},
            )
        if body.permission not in ACL_PERMISSIONS:
            return JSONResponse(
                status_code=422,
                content={"code": 4002, "msg": "unsupported permission", "data": None},
            )
        ip, ua = _client_meta(request)
        with session_factory() as session:
            policy = PolicyService(session)
            subject = subject_of(user)
            if not policy.can_share(subject, resource_kind=body.resource_kind, resource_id=body.resource_id):
                return JSONResponse(
                    status_code=403,
                    content={"code": 1003, "msg": "only the resource owner or admin can share", "data": None},
                )
            grantee_id, grantee_error = _resolve_grantee(session, body)
            if grantee_error is not None:
                return grantee_error
            acl = AclService(session)
            owner_id = acl.owner_of(body.resource_kind, body.resource_id)
            project_id = body.project_id or acl.resource_project(body.resource_kind, body.resource_id)
            try:
                record = acl.grant(
                    resource_kind=body.resource_kind,
                    resource_id=body.resource_id,
                    grantee_type=body.grantee_type,
                    grantee_id=grantee_id,
                    permission=body.permission,
                    project_id=project_id,
                    owner_id=owner_id,
                    granted_by=subject.user_id,
                    expires_at=body.expires_at,
                )
            except AclError as exc:
                return JSONResponse(
                    status_code=422, content={"code": 4002, "msg": str(exc), "data": None}
                )
            AuditWriter(session).acl(
                actor_id=subject.user_id,
                actor_name=subject.username,
                object_kind=body.resource_kind,
                object_id=body.resource_id,
                action="grant",
                after=_row_payload(record),
                ip=ip,
                user_agent=ua,
            )
            session.commit()
            return {"code": 0, "msg": "success", "data": _row_payload(record)}

    @router.delete("/shares/{acl_id}")
    def revoke_share(acl_id: int, request: Request, authorization: str = Header(default="")):
        user, denial = authenticate(authorization)
        if denial is not None:
            return denial
        ip, ua = _client_meta(request)
        with session_factory() as session:
            record = session.get(ResourceAclRecord, acl_id)
            if record is None:
                return JSONResponse(status_code=404, content={"code": 4041, "msg": "share not found", "data": None})
            subject = subject_of(user)
            is_owner = record.owner_id is not None and record.owner_id == subject.user_id
            if not subject.is_admin and not is_owner and record.granted_by != subject.user_id:
                return JSONResponse(
                    status_code=403,
                    content={"code": 1003, "msg": "only the resource owner or admin can revoke", "data": None},
                )
            before = _row_payload(record)
            AclService(session).revoke(acl_id)
            AuditWriter(session).acl(
                actor_id=subject.user_id,
                actor_name=subject.username,
                object_kind=record.resource_kind,
                object_id=record.resource_id,
                action="revoke",
                before=before,
                ip=ip,
                user_agent=ua,
            )
            session.commit()
            return {"code": 0, "msg": "success", "data": None}

    # ---- 查询 ----

    @router.get("/shares/matrix")
    def share_matrix(
        authorization: str = Header(default=""),
        resource_kind: str | None = Query(default=None),
        resource_id: str | None = Query(default=None),
        project_id: int | None = Query(default=None),
    ):
        user, denial = authenticate(authorization)
        if denial is not None:
            return denial
        with session_factory() as session:
            subject = subject_of(user)
            policy = PolicyService(session)
            acl = AclService(session)
            if resource_kind and resource_id:
                if not policy.can_share(subject, resource_kind=resource_kind, resource_id=resource_id):
                    return JSONResponse(
                        status_code=403,
                        content={"code": 1003, "msg": "only the resource owner or admin can view the matrix", "data": None},
                    )
                rows = acl.rows_for_resource(resource_kind, resource_id)
            else:
                if not subject.is_admin:
                    return JSONResponse(
                        status_code=403,
                        content={"code": 1003, "msg": "admin required for global matrix", "data": None},
                    )
                query = select(ResourceAclRecord).where(ResourceAclRecord.granted_by.is_not(None))
                if project_id is not None:
                    query = query.where(ResourceAclRecord.project_id == project_id)
                rows = list(session.scalars(query.order_by(ResourceAclRecord.id)).all())
            return {
                "code": 0,
                "msg": "success",
                "data": {"list": [_row_payload(row) for row in rows]},
            }

    @router.get("/shares/mine")
    def shares_mine(authorization: str = Header(default="")):
        user, denial = authenticate(authorization)
        if denial is not None:
            return denial
        with session_factory() as session:
            subject = subject_of(user)
            policy = PolicyService(session)
            rows = policy.acl.shares_for_subject(
                user_id=subject.user_id,
                platform_role=subject.platform_role,
                project_ids=policy.project_ids_for_user(subject.user_id),
            )
            return {
                "code": 0,
                "msg": "success",
                "data": {"list": [_row_payload(row) for row in rows]},
            }

    @router.get("/shares/granted")
    def shares_granted(authorization: str = Header(default="")):
        user, denial = authenticate(authorization)
        if denial is not None:
            return denial
        with session_factory() as session:
            subject = subject_of(user)
            acl = AclService(session)
            if subject.is_admin:
                rows = list(
                    session.scalars(
                        select(ResourceAclRecord)
                        .where(ResourceAclRecord.granted_by.is_not(None))
                        .order_by(ResourceAclRecord.id)
                    ).all()
                )
            else:
                rows = acl.granted_by_user(subject.user_id)
            return {
                "code": 0,
                "msg": "success",
                "data": {"list": [_row_payload(row) for row in rows]},
            }

    # ---- 审计查询（P3）----

    @router.get("/audit/identity")
    def audit_identity(
        authorization: str = Header(default=""),
        limit: int = Query(default=100, ge=1, le=500),
    ):
        user, denial = authenticate(authorization)
        if denial is not None:
            return denial
        if not authorize(user.get("role", ""), Permission.MANAGE_USER):
            return JSONResponse(status_code=403, content={"code": 1003, "msg": "permission denied", "data": None})
        with session_factory() as session:
            rows = session.scalars(
                select(IdentityAuditRecord).order_by(IdentityAuditRecord.id.desc()).limit(limit)
            ).all()
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "list": [
                        {
                            "id": row.id,
                            "actor_id": row.actor_id,
                            "actor_name": row.actor_name,
                            "target_user_id": row.target_user_id,
                            "target_username": row.target_username,
                            "action": row.action,
                            "before": row.before_json,
                            "after": row.after_json,
                            "result": row.result,
                            "created_at": row.created_at.isoformat() if row.created_at else None,
                        }
                        for row in rows
                    ]
                },
            }

    @router.get("/audit/acl")
    def audit_acl(
        authorization: str = Header(default=""),
        limit: int = Query(default=100, ge=1, le=500),
    ):
        user, denial = authenticate(authorization)
        if denial is not None:
            return denial
        if not authorize(user.get("role", ""), Permission.AUDIT_READ):
            return JSONResponse(status_code=403, content={"code": 1003, "msg": "permission denied", "data": None})
        with session_factory() as session:
            rows = session.scalars(
                select(AclAuditRecord).order_by(AclAuditRecord.id.desc()).limit(limit)
            ).all()
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "list": [
                        {
                            "id": row.id,
                            "actor_id": row.actor_id,
                            "actor_name": row.actor_name,
                            "object_kind": row.object_kind,
                            "object_id": row.object_id,
                            "action": row.action,
                            "before": row.before_json,
                            "after": row.after_json,
                            "result": row.result,
                            "created_at": row.created_at.isoformat() if row.created_at else None,
                        }
                        for row in rows
                    ]
                },
            }

    return router


def _resolve_grantee(session, body: ShareCreateRequest) -> tuple[str | None, JSONResponse | None]:
    """把被授权方解析为统一字符串 ID；非法时返回错误响应。"""
    if body.grantee_type == "user":
        user: UserRecord | None = None
        if body.grantee_username:
            user = session.scalar(select(UserRecord).where(UserRecord.username == body.grantee_username))
        elif body.grantee_id is not None:
            try:
                user = session.get(UserRecord, int(body.grantee_id))
            except (TypeError, ValueError):
                user = None
        if user is None:
            return None, JSONResponse(
                status_code=404, content={"code": 4041, "msg": "grantee user not found", "data": None}
            )
        return str(user.id), None
    if body.grantee_type == "project":
        try:
            project_id = int(body.grantee_id) if body.grantee_id is not None else 0
        except (TypeError, ValueError):
            project_id = 0
        if project_id < 1 or session.get(ProjectRecord, project_id) is None:
            return None, JSONResponse(
                status_code=404, content={"code": 4042, "msg": "grantee project not found", "data": None}
            )
        return str(project_id), None
    if body.grantee_type == "role":
        role_text = str(body.grantee_id or "").strip().lower()
        if role_text not in {role.value for role in Role}:
            return None, JSONResponse(
                status_code=422, content={"code": 4002, "msg": "unsupported grantee role", "data": None}
            )
        return role_text, None
    return None, JSONResponse(
        status_code=422, content={"code": 4002, "msg": "unsupported grantee_type", "data": None}
    )
