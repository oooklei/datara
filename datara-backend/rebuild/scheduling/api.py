"""Rebuild schedule CRUD API (RT-01~04 + RT-06 contract surface)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from fastapi import APIRouter, Body, Header
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from rebuild.identity.contracts import Permission
from rebuild.workflow.models import WorkflowDefinitionRecord, WorkflowScheduleRecord


SCHEDULE_PERMISSION_MAP = {
    "preview": Permission.EDIT_DEFINITION,
    "list": Permission.VIEW_ALL,
    "create": Permission.EDIT_DEFINITION,
    "update": Permission.EDIT_DEFINITION,
    "delete": Permission.EDIT_DEFINITION,
    "online": Permission.RUN_INSTANCE,
    "offline": Permission.RUN_INSTANCE,
}


class ScheduleError(ValueError):
    def __init__(self, code: str | int, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def build_schedule_router(
    session_factory: sessionmaker,
    token_service: Any,
    active_tokens: Any,
    project_permission_error: Callable[..., JSONResponse | None],
) -> APIRouter:
    router = APIRouter()

    def error(exc: ScheduleError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={"code": exc.code, "msg": exc.message, "data": None})

    def principal(token: str, authorization: str) -> dict[str, object]:
        raw = token or (authorization[7:] if authorization.startswith("Bearer ") else "")
        if not raw or raw not in active_tokens:
            raise ScheduleError(1001, "invalid token", 401)
        try:
            return token_service.verify(raw)
        except ValueError as exc:
            raise ScheduleError(1001, "invalid token", 401) from exc

    def definition(session: Session, wf: str) -> WorkflowDefinitionRecord:
        row = session.get(WorkflowDefinitionRecord, int(wf)) if wf.isdigit() else None
        if row is None:
            raise ScheduleError("WF_DEFINITION_NOT_FOUND", "workflow definition not found", 404)
        return row

    def schedule(session: Session, schedule_id: int) -> WorkflowScheduleRecord:
        row = session.get(WorkflowScheduleRecord, schedule_id)
        if row is None:
            raise ScheduleError("WF_SCHEDULE_NOT_FOUND", "schedule not found", 404)
        return row

    @contextmanager
    def authorized(
        session: Session,
        project_id: int,
        operation: str,
        token: str,
        authorization: str,
    ) -> Iterator[JSONResponse | None]:
        try:
            user = principal(token, authorization)
        except ScheduleError as exc:
            yield error(exc)
            return
        denial = project_permission_error(session, project_id, user, SCHEDULE_PERMISSION_MAP[operation])
        yield denial

    def parse_time(value: Any, field: str) -> datetime | None:
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            raise ScheduleError(4001, f"{field} must be a string")
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError as exc:
            raise ScheduleError(4001, f"{field} has an invalid datetime") from exc

    def preview(cron_expr: str, timezone: str) -> list[str]:
        try:
            iterator = croniter(cron_expr.replace("?", "*"), datetime.now(ZoneInfo(timezone)))
            return [iterator.get_next(datetime).strftime("%Y-%m-%d %H:%M:%S") for _ in range(3)]
        except ZoneInfoNotFoundError as exc:
            raise ScheduleError(4001, f"invalid timezone: {timezone}") from exc
        except (TypeError, ValueError) as exc:
            raise ScheduleError(4001, f"invalid crontab: {exc}") from exc

    def normalized(body: dict[str, Any]) -> dict[str, Any]:
        cron_expr = body.get("crontab")
        if not isinstance(cron_expr, str) or not cron_expr.strip():
            raise ScheduleError(4001, "crontab must be a non-empty string")
        timezone = body.get("timezone", "Asia/Shanghai")
        misfire = body.get("misfirePolicy", "FIRE_ONCE")
        concurrency = body.get("concurrencyPolicy", "ALLOW")
        maximum = body.get("maxRunningInstances", 1)
        if misfire not in {"FIRE_ONCE", "SKIP", "FIRE_ALL_LIMITED"}:
            raise ScheduleError(4001, "misfirePolicy is invalid")
        if concurrency not in {"ALLOW", "FORBID", "QUEUE"}:
            raise ScheduleError(4001, "concurrencyPolicy is invalid")
        if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 1:
            raise ScheduleError(4001, "maxRunningInstances must be >= 1")
        times = preview(cron_expr.strip(), timezone)
        return {
            "name": str(body.get("name") or "默认定时").strip(),
            "cron_expr": cron_expr.strip(),
            "start_time": parse_time(body.get("startTime"), "startTime"),
            "end_time": parse_time(body.get("endTime"), "endTime"),
            "priority": max(1, min(int(body.get("priority") or 3), 5)),
            "worker_group": body.get("workerGroup"),
            "fail_retry_times": max(0, int(body.get("failRetryTimes") or 0)),
            "fail_retry_interval": max(1, int(body.get("failRetryInterval") or 60)),
            "misfire_policy": misfire,
            "concurrency_policy": concurrency,
            "max_running_instances": maximum,
            "timezone": timezone,
            "next_fire_times": times,
        }

    def iso(value: datetime | None) -> str | None:
        return value.isoformat(sep=" ", timespec="seconds") if value else None

    def payload(row: WorkflowScheduleRecord) -> dict[str, Any]:
        return {
            "id": row.id, "wfCode": row.definition_id, "name": row.name,
            "crontab": row.cron_expr, "startTime": iso(row.start_time), "endTime": iso(row.end_time),
            "state": "online" if row.enabled else "offline", "priority": row.priority,
            "workerGroup": row.worker_group, "failRetryTimes": row.fail_retry_times,
            "failRetryInterval": row.fail_retry_interval, "misfirePolicy": row.misfire_policy,
            "concurrencyPolicy": row.concurrency_policy, "maxRunningInstances": row.max_running_instances,
            "timezone": row.timezone, "createTime": iso(row.created_at), "updateTime": iso(row.updated_at),
        }

    @router.post("/crontab-preview")
    def preview_crontab(body: dict[str, Any] = Body(...), token: str = Header(default=""), authorization: str = Header(default="")):
        project_id = body.get("projectId")
        if isinstance(project_id, bool) or not isinstance(project_id, int) or project_id < 1:
            return error(ScheduleError(4001, "projectId must be an integer >= 1"))
        with session_factory() as session:
            with authorized(session, project_id, "preview", token, authorization) as denial:
                if denial is not None: return denial
                try:
                    times = preview(body.get("crontab", ""), body.get("timezone", "Asia/Shanghai"))
                except ScheduleError as exc: return error(exc)
        return {"code": 0, "msg": "success", "data": {"valid": True, "nextFireTimes": times}}

    @router.get("/workflow-definitions/{wf}/schedules")
    def list_schedules(wf: str, token: str = Header(default=""), authorization: str = Header(default="")):
        with session_factory() as session:
            try: definition_row = definition(session, wf)
            except ScheduleError as exc: return error(exc)
            with authorized(session, definition_row.project_id, "list", token, authorization) as denial:
                if denial is not None: return denial
                rows = session.scalars(select(WorkflowScheduleRecord).where(WorkflowScheduleRecord.definition_id == definition_row.id).order_by(WorkflowScheduleRecord.id.desc())).all()
                data = [payload(row) for row in rows]
        return {"code": 0, "msg": "success", "data": data}

    @router.post("/workflow-definitions/{wf}/schedules")
    def create_schedule(wf: str, body: dict[str, Any] = Body(...), token: str = Header(default=""), authorization: str = Header(default="")):
        with session_factory() as session:
            try: definition_row = definition(session, wf)
            except ScheduleError as exc: return error(exc)
            with authorized(session, definition_row.project_id, "create", token, authorization) as denial:
                if denial is not None: return denial
                try: values = normalized(body)
                except (ScheduleError, TypeError, ValueError) as exc:
                    return error(exc if isinstance(exc, ScheduleError) else ScheduleError(4001, "schedule fields are invalid"))
                times = values.pop("next_fire_times")
                row = WorkflowScheduleRecord(definition_id=definition_row.id, enabled=False, **values)
                session.add(row); session.commit(); session.refresh(row)
                data = {**payload(row), "nextFireTimes": times}
        return {"code": 0, "msg": "success", "data": data}

    @router.put("/schedules/{schedule_id}")
    def update_schedule(schedule_id: int, body: dict[str, Any] = Body(...), token: str = Header(default=""), authorization: str = Header(default="")):
        with session_factory() as session:
            try: row = schedule(session, schedule_id); definition_row = definition(session, str(row.definition_id))
            except ScheduleError as exc: return error(exc)
            with authorized(session, definition_row.project_id, "update", token, authorization) as denial:
                if denial is not None: return denial
                try: values = normalized(body)
                except (ScheduleError, TypeError, ValueError) as exc:
                    return error(exc if isinstance(exc, ScheduleError) else ScheduleError(4001, "schedule fields are invalid"))
                times = values.pop("next_fire_times")
                for key, value in values.items(): setattr(row, key, value)
                session.commit(); session.refresh(row); data = {**payload(row), "nextFireTimes": times}
        return {"code": 0, "msg": "success", "data": data}

    def mutate(schedule_id: int, operation: str, token: str, authorization: str):
        with session_factory() as session:
            try: row = schedule(session, schedule_id); definition_row = definition(session, str(row.definition_id))
            except ScheduleError as exc: return error(exc)
            with authorized(session, definition_row.project_id, operation, token, authorization) as denial:
                if denial is not None: return denial
                if operation == "delete":
                    row.enabled = False; session.delete(row); session.commit(); data: Any = True
                else:
                    if operation == "online":
                        try: preview(row.cron_expr, row.timezone)
                        except ScheduleError as exc: return error(exc)
                    row.enabled = operation == "online"; session.commit(); session.refresh(row); data = payload(row)
        return {"code": 0, "msg": "success", "data": data}

    @router.delete("/schedules/{schedule_id}")
    def delete_schedule(schedule_id: int, token: str = Header(default=""), authorization: str = Header(default="")):
        return mutate(schedule_id, "delete", token, authorization)

    @router.post("/schedules/{schedule_id}/online")
    def online_schedule(schedule_id: int, token: str = Header(default=""), authorization: str = Header(default="")):
        return mutate(schedule_id, "online", token, authorization)

    @router.post("/schedules/{schedule_id}/offline")
    def offline_schedule(schedule_id: int, token: str = Header(default=""), authorization: str = Header(default="")):
        return mutate(schedule_id, "offline", token, authorization)

    return router
