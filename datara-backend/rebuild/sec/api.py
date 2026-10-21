"""Access-audit query API for the isolated rebuild backend.

System-level endpoint (no project scoping): access audit is a
platform-administration capability in the G system-management group.
Reading it requires an authenticated admin bearer token.
"""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from rebuild.sec.models import ALLOWED_RESULTS
from rebuild.sec.service import SecAccessRejected, SecService

_AUDIT_VIEW_ROLES = frozenset({"admin"})


def build_sec_router(
    session_factory: sessionmaker[Session],
    current_user: Callable[[str], dict[str, object]],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/rebuild/sec", tags=["rebuild-sec"])

    def fail(status: int, code: int, message: str) -> JSONResponse:
        return JSONResponse(status_code=status, content={"code": code, "msg": message, "data": None})

    def authenticate(authorization: str) -> dict[str, object] | JSONResponse:
        try:
            return current_user(authorization)
        except ValueError:
            return fail(401, 1001, "invalid token")

    @router.get("/access-logs")
    def list_access_logs(
        authorization: str = Header(default=""),
        user_name: str | None = Query(default=None, max_length=128),
        action: str | None = Query(default=None, max_length=64),
        result: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        if str(user.get("role", "")) not in _AUDIT_VIEW_ROLES:
            return fail(403, 1003, "access audit view is admin-only")
        if result is not None and result not in ALLOWED_RESULTS:
            return fail(422, 4221, "result must be allow or deny")
        try:
            with session_factory() as session:
                data = SecService(session).access_logs(
                    user_name=user_name,
                    action=action,
                    result=result,
                    limit=limit,
                    offset=offset,
                )
                session.commit()
        except SecAccessRejected as error:
            return fail(422, 4221, str(error))
        except IntegrityError:
            return fail(500, 5001, "access log persistence failed")
        return {"code": 0, "msg": "success", "data": data}

    return router
