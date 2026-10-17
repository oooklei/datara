"""R4-RESOURCE API — five endpoints matching the frozen FE contract (A2 v2.1).

Contract source (frozen): datara-web/src/services/rebuild/resourceApi.ts
+ docs/increments/2026-10-17-R4-DEP-RES-API-contract-pending.md §2/§4 + B2 §3.

- Base path ``/api/v1/rebuild/resources``; envelope ``{code, msg, data}``.
- uploadResource is multipart (project_id/kind/file); the server re-validates
  kind/extension/size and computes sha256 itself.
- Error mapping: request-frame malformation → 400 numeric 4001; domain
  rejections carry their RES_* code at the contract status (400 default,
  404 not-found, 409 RES_BINDING_CONFLICT); auth/permission reuse the host
  callbacks.
- Narrow scope (disclosed in repository.py): published-version binding
  rejection lands with the registry domain.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator

from fastapi import APIRouter, Body, File, Form, Header, Query, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from rebuild.identity.contracts import Permission
from rebuild.resources.repository import (
    MAX_SIZE_BYTES,
    ResourceDomainError,
    ResourceRepository,
)


class MalformedRequest(ValueError):
    """Request-frame malformation → 400 {code: 4001} (numeric, ruling in handoff #75)."""


def build_resources_router(
    session_factory: sessionmaker,
    token_service: Any,
    active_tokens: set[str],
    project_permission_error: Callable[..., JSONResponse | None],
) -> APIRouter:
    router = APIRouter()

    def principal(token: str, authorization: str) -> dict[str, object]:
        """Authenticate via the FE ``token`` header first, then Bearer fallback."""
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
        """Yield an open session after auth+permission, or a denial JSONResponse."""
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
        assert isinstance(exc, ResourceDomainError)
        return JSONResponse(status_code=exc.status, content=exc.payload())

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

    # -- 1. uploadResource: POST ``/uploads`` (multipart) ------------------

    @router.post("/uploads")
    async def upload_resource(
        project_id: int | None = Form(default=None),
        kind: str | None = Form(default=None),
        file: UploadFile | None = File(default=None),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        if project_id is None:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "project_id is required", "data": None})
        if file is None:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "file is required", "data": None})
        # Read one byte past the cap so oversized uploads are rejected here,
        # not by a partial write (server-side size re-validation, §4).
        content = await file.read(MAX_SIZE_BYTES + 1)
        try:
            if len(content) > MAX_SIZE_BYTES:
                raise ResourceDomainError("RES_SIZE_EXCEEDED", f"size exceeds the {MAX_SIZE_BYTES} byte limit")
            if kind is None:
                raise ResourceDomainError("RES_KIND_UNKNOWN", "kind is required")
        except ResourceDomainError as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.EDIT_DEFINITION, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                data = ResourceRepository(outcome).save_upload(
                    project_id, kind, file.filename or "", content
                )
                outcome.commit()
            except ResourceDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    # -- 2. listResources: GET ``?project_id=&kind=`` ----------------------

    @router.get("")
    def list_resources(
        project_id: int | None = Query(default=None),
        kind: str | None = Query(default=None),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        if project_id is None:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "project_id is required", "data": None})
        try:
            with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
                if isinstance(outcome, JSONResponse):
                    return outcome
                items = ResourceRepository(outcome).list_resources(project_id, kind)
        except ResourceDomainError as exc:
            return request_error(exc)
        return {"code": 0, "msg": "success", "data": items}

    # -- 3. listResourceVersions: GET ``/{id}/versions?project_id=`` -------

    @router.get("/{resource_id}/versions")
    def list_resource_versions(
        resource_id: int,
        project_id: int | None = Query(default=None),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        if project_id is None:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "project_id is required", "data": None})
        try:
            with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
                if isinstance(outcome, JSONResponse):
                    return outcome
                items = ResourceRepository(outcome).list_versions(project_id, resource_id)
        except ResourceDomainError as exc:
            return request_error(exc)
        return {"code": 0, "msg": "success", "data": items}

    # -- 4. getResourceVersion: GET ``/{id}/versions/{version}`` -----------

    @router.get("/{resource_id}/versions/{version}")
    def get_resource_version(
        resource_id: int,
        version: int,
        project_id: int | None = Query(default=None),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        if project_id is None:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "project_id is required", "data": None})
        try:
            with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
                if isinstance(outcome, JSONResponse):
                    return outcome
                data = ResourceRepository(outcome).get_version(project_id, resource_id, version)
        except ResourceDomainError as exc:
            return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    # -- 5. bindResourceVersion: POST ``/bindings`` ------------------------

    @router.post("/bindings")
    def bind_resource_version(
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            workflow_id = frame_int(body, "workflow_id")
            workflow_version = frame_int(body, "workflow_version")
            task_id = frame_task_id(body)
            resource_id = frame_int(body, "resource_id")
            resource_version = frame_int(body, "resource_version")
        except MalformedRequest as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.EDIT_DEFINITION, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                binding_id, _created = ResourceRepository(outcome).bind(
                    project_id, workflow_id, workflow_version, task_id, resource_id, resource_version
                )
                outcome.commit()
            except ResourceDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": {"bound": True, "binding_id": binding_id}}

    return router
