"""R4-DEPENDENCY API — five endpoints matching the frozen FE contract (A2 v2.1).

Contract source (frozen, double-line signoff): datara-web/src/services/rebuild/dependencyApi.ts
+ docs/increments/2026-10-17-R4-DEP-RES-API-contract-pending.md §2/§3.1/§7.

- Base path ``/api/v1/rebuild/dependency``; envelope ``{code, msg, data}``.
- Error mapping: request-frame malformation → 400 numeric 4001; domain
  validation → 400 string code (DEP_INVALID_WINDOW / DEP_INVALID_TIMEOUT_POLICY)
  carrying field-level diagnostics; auth/permission reuse the host callbacks.
- ``as_of`` is an optional ISO-8601 timestamp (Z suffix accepted); ``evaluated_at``
  echoes the normalized as_of so evaluations stay deterministic.
- ``timeout_seconds`` on preview/evaluate is the §7.3 config-policy extension;
  absent → timeout never fires (pending/terminal only from history).
- Narrow scope (disclosed in repository.py, mirrored in handoff): no workflow
  registry on main yet → candidate/task listing returns an honest empty list and
  published-version immutability is not enforceable; both land with the registry
  domain.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from fastapi import APIRouter, Body, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from rebuild.dependency.repository import (
    DependencyDomainError,
    DependencyRepository,
    compose_expression,
    evaluate_expression,
    metrics_history_lookup,
    parse_groups,
)
from rebuild.identity.contracts import Permission


class MalformedRequest(ValueError):
    """Request-frame malformation → 400 {code: 4001} (numeric, ruling in handoff #75)."""


def build_dependency_router(
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
        assert isinstance(exc, DependencyDomainError)
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

    def frame_timeout(payload: dict[str, Any]) -> int | None:
        timeout_seconds = payload.get("timeout_seconds")
        if timeout_seconds is None:
            return None
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds <= 0:
            raise MalformedRequest("timeout_seconds must be a positive integer")
        return timeout_seconds

    def parse_as_of(raw: Any) -> datetime:
        if raw is None:
            return datetime.now(timezone.utc)
        if not isinstance(raw, str) or not raw.strip():
            raise MalformedRequest("as_of must be an ISO-8601 string")
        try:
            parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise MalformedRequest("as_of is not a valid ISO-8601 timestamp") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def iso_z(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    # -- 1. listCandidateWorkflows: GET ``/workflows?project_id=`` ----------

    @router.get("/workflows")
    def list_candidate_workflows(
        project_id: int | None = Query(default=None),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        if project_id is None:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "project_id is required", "data": None})
        with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            # Narrow scope: no workflow registry on main — honest empty list.
            items: list[dict[str, Any]] = []
        return {"code": 0, "msg": "success", "data": items}

    # -- 2. listWorkflowTasks: GET ``/workflows/{id}/tasks`` ---------------

    @router.get("/workflows/{workflow_id}/tasks")
    def list_workflow_tasks(
        workflow_id: int,
        project_id: int | None = Query(default=None),
        workflow_version: int | None = Query(default=None),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        if project_id is None:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "project_id is required", "data": None})
        with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            # Narrow scope: task registry lands with the workflow domain; the
            # workflow_version default (latest published) is unenforceable yet.
            items: list[dict[str, Any]] = []
        return {"code": 0, "msg": "success", "data": items}

    # -- 3. previewExpression: POST ``/preview`` (read-only) ---------------

    @router.post("/preview")
    def preview_expression(
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            frame_int(body, "workflow_id")
            frame_int(body, "workflow_version")
            frame_task_id(body)
            conditions, group_relation, _policy = parse_groups(body)
            as_of = parse_as_of(body.get("as_of"))
            timeout_seconds = frame_timeout(body)
        except (MalformedRequest, DependencyDomainError) as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            expression = compose_expression(conditions, group_relation)
            overall, resolved = evaluate_expression(
                conditions, group_relation, as_of, timeout_seconds, metrics_history_lookup(outcome)
            )
        return {
            "code": 0,
            "msg": "success",
            "data": {"expression": expression, "resolved": resolved, "verdict": overall},
        }

    # -- 4. saveDependency: POST ``/saves`` -------------------------------

    @router.post("/saves")
    def save_dependency(
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            workflow_id = frame_int(body, "workflow_id")
            workflow_version = frame_int(body, "workflow_version")
            task_id = frame_task_id(body)
            conditions, group_relation, policy = parse_groups(body)
        except (MalformedRequest, DependencyDomainError) as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.EDIT_DEFINITION, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            # Narrow scope: §2 "already-published version rejects rewrite" is
            # unenforceable until the registry domain lands (disclosed).
            DependencyRepository(outcome).save_config(
                project_id, workflow_id, workflow_version, task_id, conditions, group_relation, policy
            )
            outcome.commit()
        return {"code": 0, "msg": "success", "data": {"saved": True, "version": workflow_version}}

    # -- 5. evaluateDependency: POST ``/evaluate`` ------------------------

    @router.post("/evaluate")
    def evaluate_dependency(
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            frame_int(body, "workflow_id")
            frame_int(body, "workflow_version")
            frame_task_id(body)
            conditions, group_relation, _policy = parse_groups(body)
            as_of = parse_as_of(body.get("as_of"))
            timeout_seconds = frame_timeout(body)
        except (MalformedRequest, DependencyDomainError) as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            expression = compose_expression(conditions, group_relation)
            overall, resolved = evaluate_expression(
                conditions, group_relation, as_of, timeout_seconds, metrics_history_lookup(outcome)
            )
        return {
            "code": 0,
            "msg": "success",
            "data": {
                "expression": expression,
                "resolved": resolved,
                "verdict": overall,
                "evaluated_at": iso_z(as_of),
            },
        }

    return router
