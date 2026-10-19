"""R4-SYNC API — sync node definition/mapping/explore contract (design 正本 §6.4).

Unlocked after R3 closure (user ruling e217ce3; 大盘盘点 #21 排序约束解除).
- Base path ``/api/v1/rebuild/sync`` (mounted by app.py); envelope ``{code, msg, data}``.
- ``GET  /capabilities`` — static §6.4 contract surface (13 form fields + 8 mapping fields).
- ``GET  /explore``      — 字段/类型探查 via the datasource domain metadata catalog
  (reuses ``rebuild.datasource.metadata``; no second exploration implementation).
- ``POST /mappings/auto`` — 自动映射 generation by name match over explored columns.
- ``POST /plans``         — 保存 the mapping snapshot (auto or 用户调整), slot-keyed
  by (project, workflow version, task); resaving replaces the draft.
- ``GET  /plans``         — 映射随版本引用 listing for one workflow version.
- Auth/permission reuse the host callbacks (token_service/active_tokens/
  project_permission_error), same pattern as R4-DEPENDENCY.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from fastapi import APIRouter, Body, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from rebuild.datasource.contracts import DataSourceDraft
from rebuild.datasource.metadata import metadata_catalog_for
from rebuild.datasource.repository import ProjectDatasourceRepository
from rebuild.identity.contracts import Permission
from rebuild.sync.repository import (
    MAPPING_FIELDS,
    MAPPING_STATUSES,
    SyncDomainError,
    SyncRepository,
    generate_auto_mappings,
    serialize_plan,
    validate_mappings,
)

logger = logging.getLogger(__name__)


class MalformedRequest(ValueError):
    """Request-frame malformation → 400 {code: 4001}."""


# §6.4 同步表单 13 字段 (form fields 5–6 are read-time explore capabilities).
SYNC_FORM_FIELDS: tuple[str, ...] = (
    "source_datasource",
    "source_object",
    "target_datasource",
    "target_object",
    "column_explore",
    "type_explore",
    "auto_mapping",
    "manual_mapping_adjust",
    "transform_expression",
    "filter_condition",
    "partition_incremental",
    "primary_key_conflict",
    "batch_concurrency",
)


def build_sync_router(
    session_factory: sessionmaker,
    token_service: Any,
    active_tokens: set[str],
    project_permission_error: Callable[..., JSONResponse | None],
    datasource_connector_factory: Callable[[int, int], Callable[[Any], Any]],
) -> APIRouter:
    router = APIRouter()

    def principal(token: str, authorization: str) -> dict[str, object]:
        raw = token or (authorization[7:] if authorization.startswith("Bearer ") else "")
        if not raw:
            raise ValueError("missing token")
        if raw not in active_tokens:
            raise ValueError("token revoked or unknown")
        return token_service.verify(raw)

    def unauthorized() -> JSONResponse:
        return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})

    @contextmanager
    def authorized_session(
        project_id: int, permission: Permission, token: str, authorization: str
    ) -> Iterator[Any]:
        with session_factory() as session:
            try:
                user = principal(token, authorization)
            except ValueError:
                yield unauthorized()
                return
            denial = project_permission_error(session, project_id, user, permission)
            if denial is not None:
                yield denial
                return
            yield session

    def request_error(exc: Exception) -> JSONResponse:
        if isinstance(exc, MalformedRequest):
            return JSONResponse(status_code=400, content={"code": 4001, "msg": str(exc), "data": None})
        assert isinstance(exc, SyncDomainError)
        return JSONResponse(status_code=400, content=exc.payload())

    def frame_int(payload: dict[str, Any], key: str, minimum: int = 1) -> int:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise MalformedRequest(f"{key} must be an integer >= {minimum}")
        return value

    def frame_task_id(payload: dict[str, Any]) -> str:
        task_id = payload.get("task_id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise MalformedRequest("task_id must be a non-empty string")
        return task_id

    def frame_ref(payload: dict[str, Any], key: str) -> dict[str, Any]:
        ref = payload.get(key)
        if not isinstance(ref, dict):
            raise MalformedRequest(f"{key} must be an object")
        datasource_id = ref.get("datasource_id")
        schema = ref.get("schema")
        object_name = ref.get("object")
        if isinstance(datasource_id, bool) or not isinstance(datasource_id, int) or datasource_id < 1:
            raise MalformedRequest(f"{key}.datasource_id must be an integer >= 1")
        if not isinstance(schema, str) or not schema.strip() or len(schema) > 255:
            raise MalformedRequest(f"{key}.schema must be a non-empty string (<= 255)")
        if not isinstance(object_name, str) or not object_name.strip() or len(object_name) > 255:
            raise MalformedRequest(f"{key}.object must be a non-empty string (<= 255)")
        return {"datasource_id": datasource_id, "schema": schema, "object": object_name}

    def catalog_for(session: Any, project_id: int, datasource_id: int):
        record = ProjectDatasourceRepository(session).get(project_id, datasource_id)
        if record is None:
            raise LookupError("datasource not found")
        draft = DataSourceDraft(
            name=record.name,
            kind=record.kind,
            host=record.host,
            port=record.port,
            database=record.database_name,
            username=record.username,
            password=record.password,
        )
        connector = datasource_connector_factory(project_id, datasource_id)
        return metadata_catalog_for(draft, connector=connector)

    def explore_error(exc: Exception) -> JSONResponse:
        if isinstance(exc, LookupError):
            return JSONResponse(status_code=404, content={"code": 4042, "msg": "datasource not found", "data": None})
        if isinstance(exc, ValueError):
            return JSONResponse(status_code=400, content={"code": 4001, "msg": str(exc), "data": None})
        logger.warning("sync_explore_failed exception_type=%s", type(exc).__name__)
        return JSONResponse(status_code=502, content={"code": 5022, "msg": "metadata explore failed", "data": None})

    # -- 1. GET /capabilities: static §6.4 contract surface -----------------

    @router.get("/capabilities")
    def sync_capabilities(
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            principal(token, authorization)
        except ValueError:
            return unauthorized()
        return {
            "code": 0,
            "msg": "success",
            "data": {
                "form_fields": list(SYNC_FORM_FIELDS),
                "mapping_fields": list(MAPPING_FIELDS),
                "mapping_status": list(MAPPING_STATUSES),
            },
        }

    # -- 2. GET /explore: 字段探查/类型探查 (datasource catalog reuse) ------

    @router.get("/explore")
    def explore_columns(
        project_id: int | None = Query(default=None),
        datasource_id: int | None = Query(default=None),
        schema: str = Query(default="", min_length=1, max_length=255),
        object_name: str = Query(default="", min_length=1, max_length=255),
        limit: int = Query(default=200, ge=1, le=500),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        if project_id is None or datasource_id is None:
            return JSONResponse(
                status_code=400,
                content={"code": 4001, "msg": "project_id and datasource_id are required", "data": None},
            )
        with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                catalog = catalog_for(outcome, project_id, datasource_id)
                rows = catalog.columns(schema, object_name, limit=limit)
            except Exception as exc:
                return explore_error(exc)
        return {
            "code": 0,
            "msg": "success",
            "data": {"items": rows[:limit], "truncated": len(rows) > limit, "limit": limit},
        }

    # -- 3. POST /mappings/auto: §6.4 自动映射 -------------------------------

    @router.post("/mappings/auto")
    def auto_mappings(
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            src = frame_ref(body, "source")
            tgt = frame_ref(body, "target")
        except MalformedRequest as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                src_catalog = catalog_for(outcome, project_id, src["datasource_id"])
                tgt_catalog = catalog_for(outcome, project_id, tgt["datasource_id"])
                source_columns = src_catalog.columns(src["schema"], src["object"])
                target_columns = tgt_catalog.columns(tgt["schema"], tgt["object"])
            except Exception as exc:
                return explore_error(exc)
            mappings = generate_auto_mappings(source_columns, target_columns)
        return {"code": 0, "msg": "success", "data": {"mappings": mappings}}

    # -- 4. POST /plans: save the §6.4 snapshot (auto or 用户调整) -----------

    @router.post("/plans")
    def save_plan(
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            workflow_id = frame_int(body, "workflow_id")
            workflow_version = frame_int(body, "workflow_version")
            task_id = frame_task_id(body)
            src = frame_ref(body, "source")
            tgt = frame_ref(body, "target")
            mappings = validate_mappings(body.get("mappings"))
            transform_config = body.get("transform_config") or {}
            target_properties = body.get("target_properties") or {}
            if not isinstance(transform_config, dict) or not isinstance(target_properties, dict):
                raise MalformedRequest("transform_config and target_properties must be objects")
        except (MalformedRequest, SyncDomainError) as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.EDIT_DEFINITION, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            SyncRepository(outcome).save_plan(
                project_id=project_id,
                workflow_id=workflow_id,
                workflow_version=workflow_version,
                task_id=task_id,
                src_ref=src,
                tgt_ref=tgt,
                mappings=mappings,
                transform_config=transform_config,
                target_properties=target_properties,
            )
            outcome.commit()
        return {
            "code": 0,
            "msg": "success",
            "data": {"saved": True, "workflow_version": workflow_version, "task_id": task_id},
        }

    # -- 5. GET /plans: 映射随版本引用 ---------------------------------------

    @router.get("/plans")
    def list_plans(
        project_id: int | None = Query(default=None),
        workflow_id: int | None = Query(default=None),
        workflow_version: int | None = Query(default=None),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        if project_id is None or workflow_id is None or workflow_version is None:
            return JSONResponse(
                status_code=400,
                content={
                    "code": 4001,
                    "msg": "project_id, workflow_id and workflow_version are required",
                    "data": None,
                },
            )
        with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            records = SyncRepository(outcome).list_plans(project_id, workflow_id, workflow_version)
        return {"code": 0, "msg": "success", "data": {"items": [serialize_plan(record) for record in records]}}

    return router
