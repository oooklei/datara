"""Read and refresh project-scoped daily SQL impact results."""

from collections.abc import Callable
from datetime import date, timedelta
from zoneinfo import ZoneInfo
from datetime import datetime

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from rebuild.dbx import DbxClient, DbxError
from rebuild.dbx.access import DbxConnectionAccess
from rebuild.identity.contracts import Permission, Role
from .models import DailyImpactRecord, DailyImpactRunRecord
from .service import refresh_daily_impact


def build_impact_router(session_factory: sessionmaker, current_user: Callable, project_permission_error: Callable, *, client_factory: Callable[[], DbxClient] = DbxClient) -> APIRouter:
    router = APIRouter(prefix="/api/v1/rebuild/projects/{project_id}/impact", tags=["daily-impact"])

    def authorize(project_id: int, authorization: str, permission: Permission):
        try:
            user = current_user(authorization)
        except ValueError:
            return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})
        with session_factory() as session:
            denial = project_permission_error(session, project_id, user, permission)
        return denial if denial is not None else user

    @router.get("/daily")
    def list_daily(project_id: int, day: date | None = Query(default=None), authorization: str = Header(default="")):
        user = authorize(project_id, authorization, Permission.DATASOURCE_READ)
        if isinstance(user, JSONResponse):
            return user
        target = day or (datetime.now(ZoneInfo("Asia/Shanghai")).date() - timedelta(days=1))
        with session_factory() as session:
            visible = DbxConnectionAccess(session).visible_ids(
                project_id=project_id, user_id=int(user["user_id"]), is_admin=user.get("role") == Role.ADMIN.value,
            )
            run = session.scalar(select(DailyImpactRunRecord).where(DailyImpactRunRecord.project_id == project_id, DailyImpactRunRecord.day == target))
            rows = session.scalars(select(DailyImpactRecord).where(DailyImpactRecord.project_id == project_id, DailyImpactRecord.day == target, DailyImpactRecord.connection_id.in_(visible)).order_by(DailyImpactRecord.executed_at, DailyImpactRecord.id)).all()
            data = {"day": target.isoformat(), "collected": run is not None, "items": [
                {"history_id": row.history_id, "connection_id": row.connection_id, "database": row.database,
                 "executed_at": row.executed_at, "success": row.success, "status": row.status,
                 "reads": row.reads, "writes": row.writes} for row in rows
            ]}
        return {"code": 0, "msg": "success", "data": data}

    @router.post("/daily/refresh")
    def refresh(project_id: int, day: date = Query(), authorization: str = Header(default="")):
        user = authorize(project_id, authorization, Permission.DATASOURCE_MANAGE)
        if isinstance(user, JSONResponse):
            return user
        if user.get("role") != Role.ADMIN.value:
            return JSONResponse(status_code=403, content={"code": 1003, "msg": "admin required", "data": None})
        try:
            count = refresh_daily_impact(day, project_id, session_factory, client_factory())
        except DbxError:
            return JSONResponse(status_code=503, content={"code": 503, "msg": "dbx unavailable", "data": None})
        return {"code": 0, "msg": "success", "data": {"day": day.isoformat(), "row_count": count}}

    return router
