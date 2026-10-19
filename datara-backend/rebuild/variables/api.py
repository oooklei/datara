"""R2 variables API — six endpoints matching the frozen FE contract.

Contract source (frozen): datara-web/src/services/rebuild/variableApi.ts +
docs/increments/2026-10-17-R系列GREEN接线计划.md Task 2 契约面表.

- Base path ``/api/v1/rebuild/variables``; envelope ``{code, msg, data}``
  (success code 0; errors use the rebuild-domain codes 1001/1003/4001/4002/4041).
- Authentication accepts the FE ``token`` header (frozen FE contract) and, for
  internal callers, the ``Authorization: Bearer`` header.
- Request/response keys are snake_case; the FE adapter converts camelCase.
- Sensitive values are returned in plaintext (declaration §5 Q11).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from rebuild.identity.contracts import Permission
from rebuild.variables.repository import VariableRepository
from rebuild.variables.service import (
    PERSISTABLE_SCOPES,
    VariableDomainError,
    VariableResolver,
    parse_context,
)


class VariableDefinitionRequest(BaseModel):
    scope: str
    name: str
    value_type: str = "string"
    value: str
    description: str = ""
    sensitive: bool = False
    # Optional ids required to address workflow/task scopes (parse-key authority).
    workflow_id: int | None = None
    task_id: str | None = None
    # VAR-06: definition fields (design §13.5)
    default_value: str | None = None
    nullable: bool = True
    format: str | None = None
    timezone: str | None = None
    business_calendar: str | None = None


class CompleteRequest(BaseModel):
    prefix: str
    context: dict[str, Any]


class ReferenceRequest(BaseModel):
    expression: str
    context: dict[str, Any]


def build_variables_router(
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

    def domain_error(exc: VariableDomainError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"code": exc.code, "msg": exc.msg, "data": None})

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

    def resolver_for(session) -> VariableResolver:
        repo = VariableRepository(session)
        return VariableResolver(lambda owner_key: repo.list_owner(owner_key))

    # -- 1. listVariables: GET ``?project_id=&scopes=`` --------------------

    @router.get("")
    def list_variables(
        project_id: int = Query(...),
        scopes: str = Query(default=""),
        workflow_id: int | None = Query(default=None),
        task_id: str | None = Query(default=None),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            wanted = {item.strip() for item in scopes.split(",") if item.strip()}
            items = [
                {
                    "scope": item.scope,
                    "name": item.name,
                    "value_type": item.value_type,
                    "value": item.value,
                    "description": item.description,
                    "sensitive": item.sensitive,
                    "default_value": item.default_value,
                    "nullable": item.nullable,
                    "format": item.format,
                    "timezone": item.timezone,
                    "business_calendar": item.business_calendar,
                }
                for item in VariableRepository(outcome).list_all_with_scope(
                    project_id, workflow_id=workflow_id, task_id=task_id
                )
                if not wanted or item.scope in wanted
            ]
        return {"code": 0, "msg": "success", "data": items}

    # -- 2. saveVariable: POST ``?project_id=`` ----------------------------

    @router.post("")
    def save_variable(
        body: VariableDefinitionRequest,
        project_id: int = Query(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            with authorized_session(project_id, Permission.EDIT_DEFINITION, token, authorization) as outcome:
                if isinstance(outcome, JSONResponse):
                    return outcome
                if body.scope not in PERSISTABLE_SCOPES:
                    raise VariableDomainError(
                        4001,
                        f"scope {body.scope!r} is not persistable; storeable scopes are {sorted(PERSISTABLE_SCOPES)}",
                    )
                VariableRepository(outcome).upsert(
                    scope=body.scope,
                    project_id=project_id if body.scope in ("project", "tmp", "workflow", "task") else None,
                    name=body.name,
                    value=body.value,
                    value_type=body.value_type,
                    sensitive=body.sensitive,
                    description=body.description,
                    workflow_id=body.workflow_id,
                    task_id=body.task_id,
                    default_value=body.default_value,
                    nullable=body.nullable,
                    format=body.format,
                    timezone=body.timezone,
                    business_calendar=body.business_calendar,
                )
                outcome.commit()
        except VariableDomainError as exc:
            return domain_error(exc)
        return {"code": 0, "msg": "success", "data": {"saved": True, "scope": body.scope, "name": body.name}}

    # -- 3. completeVariables: POST ``/complete`` --------------------------

    @router.post("/complete")
    def complete_variables(
        body: CompleteRequest, token: str = Header(default=""), authorization: str = Header(default="")
    ):
        try:
            user = principal(token, authorization)
            context = parse_context(body.context)
        except VariableDomainError as exc:
            return domain_error(exc)
        except ValueError:
            return unauthorized()
        with authorized_session(context.project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            items = resolver_for(outcome).complete(body.prefix, context)
        return {"code": 0, "msg": "success", "data": items}

    # -- 4. checkReference: POST ``/check-reference`` ----------------------

    @router.post("/check-reference")
    def check_reference(
        body: ReferenceRequest, token: str = Header(default=""), authorization: str = Header(default="")
    ):
        try:
            user = principal(token, authorization)
            context = parse_context(body.context)
        except VariableDomainError as exc:
            return domain_error(exc)
        except ValueError:
            return unauthorized()
        with authorized_session(context.project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            result = resolver_for(outcome).check_reference(body.expression, context)
        return {"code": 0, "msg": "success", "data": result}

    # -- 5. previewResolution: POST ``/preview`` ---------------------------

    @router.post("/preview")
    def preview_resolution(
        body: ReferenceRequest, token: str = Header(default=""), authorization: str = Header(default="")
    ):
        try:
            user = principal(token, authorization)
            context = parse_context(body.context)
        except VariableDomainError as exc:
            return domain_error(exc)
        except ValueError:
            return unauthorized()
        with authorized_session(context.project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            result = resolver_for(outcome).preview_resolution(body.expression, context)
        return {"code": 0, "msg": "success", "data": result}

    # -- 6. getRunSnapshot: GET ``/run-snapshot`` --------------------------
    # P0-7 security patch: project_id is a required query parameter and the
    # standard VIEW_ALL permission chain applies; snapshot rows are filtered
    # by that project so cross-project instance ids leak nothing.

    @router.get("/run-snapshot")
    def get_run_snapshot(
        instance_id: int = Query(...),
        project_id: int | None = Query(default=None),
        attempt_no: int | None = Query(default=None),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            principal(token, authorization)
        except ValueError:
            return unauthorized()
        if project_id is None:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "project_id is required", "data": None})
        with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            entries = VariableRepository(outcome).read_snapshot(instance_id, attempt_no, project_id)
        return {"code": 0, "msg": "success", "data": entries}

    return router
