"""New-Backend workflow domain API — design §3.1/§4 (大盘缺口 #2/#12).

- Base path ``/api/v1/rebuild/workflows``; envelope ``{code, msg, data}``.
- Definition CRUD + draft node/edge editing (replace-by-code, draft rows only),
  publish (immutable version snapshot + publish record), version list/detail.
- Error mapping: request-frame malformation → 400 numeric 4001; domain
  rejections carry their WF_* code at the contract status (400 default, 404
  not-found, 409 conflict); auth/permission reuse the host callbacks.
- Version content mutation is intentionally NOT exposed over HTTP: published
  version rows are frozen (design §3.1); the repository-level guard raises
  WF_VERSION_IMMUTABLE for the future DRAFT-version (结果转正式版本) path.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator

from fastapi import APIRouter, Body, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from rebuild.identity.contracts import Permission
from rebuild.workflow.repository import WorkflowDomainError, WorkflowRepository


class MalformedRequest(ValueError):
    """Request-frame malformation → 400 {code: 4001} (numeric, ruling in handoff #75)."""


def build_workflow_router(
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
        assert isinstance(exc, WorkflowDomainError)
        return JSONResponse(status_code=exc.status, content=exc.payload())

    def frame_int(payload: dict[str, Any], key: str, minimum: int = 1) -> int:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise MalformedRequest(f"{key} must be an integer >= {minimum}")
        return value

    def frame_str(payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise MalformedRequest(f"{key} must be a non-empty string")
        return value

    def frame_optional_str(payload: dict[str, Any], key: str) -> str | None:
        value = payload.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise MalformedRequest(f"{key} must be a string")
        return value

    def frame_optional_int(payload: dict[str, Any], key: str) -> int | None:
        value = payload.get(key)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise MalformedRequest(f"{key} must be an integer")
        return value

    def frame_optional_dict(payload: dict[str, Any], key: str) -> dict[str, Any] | None:
        value = payload.get(key)
        if value is None:
            return None
        if not isinstance(value, dict):
            raise MalformedRequest(f"{key} must be an object")
        return value

    # -- 1. createWorkflowDefinition: POST ``""``
    #       body {project_id, name, description?} ----------------------------

    @router.post("")
    def create_definition(
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            name = frame_str(body, "name")
            description = frame_optional_str(body, "description") or ""
        except MalformedRequest as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.EDIT_DEFINITION, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                data = WorkflowRepository(outcome).create_definition(project_id, name, description)
                outcome.commit()
            except WorkflowDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    # -- 2. listWorkflowDefinitions: GET ``""?project_id=`` ------------------

    @router.get("")
    def list_definitions(
        project_id: int | None = Query(default=None),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        if project_id is None:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "project_id is required", "data": None})
        with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            items = WorkflowRepository(outcome).list_definitions(project_id)
        return {"code": 0, "msg": "success", "data": items}

    # -- 3. getWorkflowDefinition: GET ``/{definition_id}?project_id=`` ------
    #       (definition meta + current editing draft nodes/edges)

    @router.get("/{definition_id}")
    def get_definition(
        definition_id: int,
        project_id: int | None = Query(default=None),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        if project_id is None:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "project_id is required", "data": None})
        with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                data = WorkflowRepository(outcome).get_definition(project_id, definition_id)
            except WorkflowDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    # -- 4. updateWorkflowDefinition: POST ``/{definition_id}/updates``
    #       body {project_id, name?, description?} ---------------------------

    @router.post("/{definition_id}/updates")
    def update_definition(
        definition_id: int,
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            name = frame_optional_str(body, "name")
            description = frame_optional_str(body, "description")
            if name is None and description is None:
                raise MalformedRequest("name or description is required")
        except MalformedRequest as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.EDIT_DEFINITION, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                data = WorkflowRepository(outcome).update_definition(project_id, definition_id, name, description)
                outcome.commit()
            except WorkflowDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    # -- 5. deleteWorkflowDefinition: POST ``/{definition_id}/delete``
    #       body {project_id}; draft-only definitions only -------------------

    @router.post("/{definition_id}/delete")
    def delete_definition(
        definition_id: int,
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
        except MalformedRequest as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.EDIT_DEFINITION, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                WorkflowRepository(outcome).delete_definition(project_id, definition_id)
                outcome.commit()
            except WorkflowDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": {"deleted": True}}

    # -- 6. upsertDraftNode: POST ``/{definition_id}/nodes``
    #       body {project_id, node_code, node_type, name?, params?,
    #             position_x?, position_y?} ---------------------------------

    @router.post("/{definition_id}/nodes")
    def upsert_draft_node(
        definition_id: int,
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            node = {
                "node_code": frame_str(body, "node_code"),
                "node_type": frame_str(body, "node_type"),
                "name": frame_optional_str(body, "name"),
                "params": frame_optional_dict(body, "params"),
                "position_x": frame_optional_int(body, "position_x"),
                "position_y": frame_optional_int(body, "position_y"),
            }
        except MalformedRequest as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.EDIT_DEFINITION, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                data = WorkflowRepository(outcome).upsert_draft_node(project_id, definition_id, node)
                outcome.commit()
            except WorkflowDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    # -- 7. deleteDraftNode: POST ``/{definition_id}/nodes/delete``
    #       body {project_id, node_code} (cascades touching draft edges) -----

    @router.post("/{definition_id}/nodes/delete")
    def delete_draft_node(
        definition_id: int,
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            node_code = frame_str(body, "node_code")
        except MalformedRequest as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.EDIT_DEFINITION, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                WorkflowRepository(outcome).delete_draft_node(project_id, definition_id, node_code)
                outcome.commit()
            except WorkflowDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": {"deleted": True}}

    # -- 8. upsertDraftEdge: POST ``/{definition_id}/edges``
    #       body {project_id, from_node, to_node, name?} ----------------------

    @router.post("/{definition_id}/edges")
    def upsert_draft_edge(
        definition_id: int,
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            edge = {
                "from_node": frame_str(body, "from_node"),
                "to_node": frame_str(body, "to_node"),
                "name": frame_optional_str(body, "name"),
            }
        except MalformedRequest as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.EDIT_DEFINITION, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                data = WorkflowRepository(outcome).upsert_draft_edge(project_id, definition_id, edge)
                outcome.commit()
            except WorkflowDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    # -- 9. deleteDraftEdge: POST ``/{definition_id}/edges/delete``
    #       body {project_id, from_node, to_node} -----------------------------

    @router.post("/{definition_id}/edges/delete")
    def delete_draft_edge(
        definition_id: int,
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            from_node = frame_str(body, "from_node")
            to_node = frame_str(body, "to_node")
        except MalformedRequest as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.EDIT_DEFINITION, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                WorkflowRepository(outcome).delete_draft_edge(project_id, definition_id, from_node, to_node)
                outcome.commit()
            except WorkflowDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": {"deleted": True}}

    # -- 10. publishWorkflow: POST ``/{definition_id}/publish``
    #        body {project_id, remark?}; immutable version snapshot ----------

    @router.post("/{definition_id}/publish")
    def publish_definition(
        definition_id: int,
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            remark = frame_optional_str(body, "remark") or ""
        except MalformedRequest as exc:
            return request_error(exc)
        with session_factory() as session:
            try:
                user = principal(token, authorization)
            except ValueError:
                return unauthorized()
            denial = project_permission_error(session, project_id, user, Permission.EDIT_DEFINITION)
            if denial is not None:
                return denial
            try:
                data = WorkflowRepository(session).publish(
                    project_id, definition_id, remark=remark, published_by=int(user["user_id"])  # type: ignore[arg-type]
                )
                session.commit()
            except WorkflowDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    # -- 11. listWorkflowVersions: GET ``/{definition_id}/versions?project_id=``

    @router.get("/{definition_id}/versions")
    def list_versions(
        definition_id: int,
        project_id: int | None = Query(default=None),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        if project_id is None:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "project_id is required", "data": None})
        with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                items = WorkflowRepository(outcome).list_versions(project_id, definition_id)
            except WorkflowDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": items}

    # -- 12. getWorkflowVersion: GET ``/{definition_id}/versions/{version}``
    #        (version meta + snapshot nodes/edges + publish record) ----------

    @router.get("/{definition_id}/versions/{version}")
    def get_version(
        definition_id: int,
        version: int,
        project_id: int | None = Query(default=None),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        if project_id is None:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "project_id is required", "data": None})
        with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                data = WorkflowRepository(outcome).get_version(project_id, definition_id, version)
            except WorkflowDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    return router
