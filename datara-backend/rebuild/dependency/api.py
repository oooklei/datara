"""R4-DEPENDENCY API — dependency configuration, evaluation and observations.

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
- Candidate/task listing reads the workflow registry and remains project-scoped.
  Published-version immutability is enforced at the workflow publish boundary.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from fastapi import APIRouter, Body, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from rebuild.dependency.models import DependencyObservationRecord
from rebuild.dependency.repository import (
    DependencyDomainError,
    DependencyRepository,
    compose_expression,
    evaluate_expression,
    metrics_history_lookup,
    parse_groups,
)
from rebuild.identity.contracts import Permission
from rebuild.workflow.models import WorkflowDefinitionRecord, WorkflowNodeRecord, WorkflowVersionRecord


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
            definitions = outcome.scalars(
                select(WorkflowDefinitionRecord)
                .where(WorkflowDefinitionRecord.project_id == project_id)
                .order_by(WorkflowDefinitionRecord.name, WorkflowDefinitionRecord.id)
            ).all()
            items = [
                {"workflow_id": row.id, "name": row.name, "workflow_type": row.workflow_type,
                 "latest_version": row.current_version}
                for row in definitions
            ]
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
            definition = outcome.scalar(select(WorkflowDefinitionRecord).where(
                WorkflowDefinitionRecord.id == workflow_id,
                WorkflowDefinitionRecord.project_id == project_id,
            ))
            if definition is None:
                items = []
            else:
                version_id = None
                if workflow_version is not None:
                    version = outcome.scalar(select(WorkflowVersionRecord).where(
                        WorkflowVersionRecord.definition_id == workflow_id,
                        WorkflowVersionRecord.version == workflow_version,
                    ))
                    # An explicitly requested, missing version must not fall
                    # back to draft (version_id IS NULL) nodes.  Besides
                    # returning misleading candidates, that fallback could
                    # expose another workflow's unpublished task shape to a
                    # dependency form.  Keep the project-scoped definition
                    # check above and make an unknown version an honest empty
                    # result.
                    if version is None:
                        return {"code": 0, "msg": "success", "data": []}
                    else:
                        version_id = version.id
                query = select(WorkflowNodeRecord).where(WorkflowNodeRecord.definition_id == workflow_id)
                query = query.where(
                    WorkflowNodeRecord.version_id == version_id
                    if version_id is not None
                    else WorkflowNodeRecord.version_id.is_(None)
                )
                nodes = outcome.scalars(query.order_by(WorkflowNodeRecord.node_code)).all()
                items = [{"task_id": node.node_code, "name": node.name, "node_type": node.node_type} for node in nodes]
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
                conditions, group_relation, as_of, timeout_seconds, metrics_history_lookup(outcome, project_id)
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
            config_id = DependencyRepository(outcome).save_config(
                project_id, workflow_id, workflow_version, task_id, conditions, group_relation, policy
            )
            outcome.commit()
        return {
            "code": 0,
            "msg": "success",
            "data": {"saved": True, "version": workflow_version, "config_id": config_id},
        }

    # -- Extension observation ingestion: POST ``/observations`` ----------

    @router.post("/observations")
    def record_observation(
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            kind = body.get("kind")
            if kind not in ("file", "table_state", "external_task"):
                raise MalformedRequest("kind must be file, table_state or external_task")
            target_key = body.get("target_key")
            if not isinstance(target_key, str) or not target_key.strip() or len(target_key.strip()) > 512:
                raise MalformedRequest("target_key must be a non-empty string of at most 512 characters")
            state = body.get("state")
            if state not in ("success", "failed"):
                raise MalformedRequest("state must be success or failed")
            observed_at = parse_as_of(body.get("observed_at"))
        except MalformedRequest as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.RUN_INSTANCE, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            record = DependencyObservationRecord(
                project_id=project_id,
                kind=kind,
                target_key=target_key.strip(),
                state=state,
                observed_at=observed_at.replace(tzinfo=None),
            )
            outcome.add(record)
            outcome.flush()
            record_id = record.id
            outcome.commit()
        return {"code": 0, "msg": "success", "data": {"recorded": True, "observation_id": record_id}}

    # -- evaluateDependency: POST ``/evaluate`` ---------------------------

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
                conditions, group_relation, as_of, timeout_seconds, metrics_history_lookup(outcome, project_id)
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
