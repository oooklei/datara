"""Project-scoped HTTP adapter for the frozen SQL IDE contract.

The router is deliberately independent from the application factory. Hosts inject
principal validation, project authorization, and operation dispatch so the
application can wire its existing identity and service implementations without
moving those concerns into this module.
"""

from __future__ import annotations

import inspect
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from rebuild.sql_ide.error_catalog import build_error_envelope, http_status_for


@dataclass(frozen=True)
class SqlIdeRouteError(Exception):
    """A safe, stable domain error to translate into the A5 HTTP envelope."""

    error_code: str
    details: Mapping[str, object] | None = None
    message: str | None = None

    def __str__(self) -> str:
        return self.message or self.error_code


Authenticate = Callable[[str, str], Any | Awaitable[Any]]
Authorize = Callable[[int, Any, str, str, Mapping[str, Any]], Any | Awaitable[Any]]
Dispatch = Callable[..., Any | Awaitable[Any]]


# (verb, suffix, operation, minimum permission, has_json_body)
_ROUTE_SPECS = (
    ("GET", "/databases", "listDatabases", "VIEW_ALL", False),
    ("GET", "/schemas", "listSchemas", "VIEW_ALL", False),
    ("GET", "/relations", "listRelations", "VIEW_ALL", False),
    ("GET", "/columns", "listColumns", "VIEW_ALL", False),
    ("GET", "/routines", "listRoutines", "VIEW_ALL", False),
    ("GET", "/indexes", "listIndexes", "VIEW_ALL", False),
    ("GET", "/objects/search", "searchObjects", "VIEW_ALL", False),
    ("POST", "/definitions", "getDefinition", "VIEW_ALL", True),
    ("POST", "/lint", "lintSql", "VIEW_ALL", True),
    ("POST", "/executions", "executeSql", "EXECUTE_SQL", True),
    ("POST", "/executions/{task_id}/cancel", "cancelExecution", "EXECUTE_SQL", False),
    ("GET", "/executions/{task_id}/events", "openEventStream", "VIEW_ALL", False),
    ("GET", "/executions/{task_id}", "getExecutionStatus", "VIEW_ALL", False),
    ("GET", "/results/{history_id}", "fetchResultPage", "VIEW_ALL", False),
    ("GET", "/history", "listHistory", "VIEW_ALL", False),
    ("DELETE", "/history/{history_id}", "deleteHistory", "EDIT_DEFINITION", False),
    ("GET", "/scripts", "listScripts", "VIEW_ALL", False),
    ("POST", "/scripts", "saveScript", "EDIT_DEFINITION", True),
    ("DELETE", "/scripts/{script_id}", "deleteScript", "EDIT_DEFINITION", False),
    ("POST", "/exports", "exportResult", "VIEW_ALL", True),
    ("POST", "/table-exports", "exportTable", "VIEW_ALL", True),
    ("GET", "/exports/{export_id}", "getExport", "VIEW_ALL", False),
    ("GET", "/exports/{export_id}/download", "downloadExport", "VIEW_ALL", False),
    ("DELETE", "/exports/{export_id}", "cancelExport", "VIEW_ALL", False),
)


def build_sql_ide_router(
    *,
    dispatch: Dispatch,
    authenticate: Authenticate,
    authorize: Authorize,
) -> APIRouter:
    """Build an unmounted-by-default SQL IDE router for host app integration.

    ``authenticate(token, authorization)`` returns the trusted principal.
    ``authorize(project_id, principal, permission, operation, payload)`` must
    return ``None`` to allow or a ``Response`` to stop (including hidden 404s).
    ``dispatch(operation, project_id=..., principal=..., payload=...)`` invokes
    the selected domain service. The payload combines query, path, then JSON
    body fields, with later sources taking precedence.
    """
    router = APIRouter(prefix="/api/v1/projects/{project_id}/sql-ide", tags=["sql-ide"])

    async def invoke(request: Request, project_id: int, operation: str, permission: str,
                     has_body: bool, path_values: Mapping[str, Any]) -> Any:
        payload: dict[str, Any] = dict(request.query_params)
        payload.update(path_values)
        if has_body:
            try:
                body = await request.json()
            except (json.JSONDecodeError, UnicodeDecodeError):
                return _error_response(SqlIdeRouteError("INVALID_REQUEST"))
            if not isinstance(body, Mapping):
                return _error_response(SqlIdeRouteError("INVALID_REQUEST"))
            payload.update(body)
        token = request.headers.get("token", "")
        authorization = request.headers.get("authorization", "")
        if operation == "openEventStream" and not token and not authorization:
            token = request.cookies.get(_event_cookie_name(str(path_values.get("task_id", ""))), "")
        try:
            principal = await _maybe_await(
                authenticate(token, authorization)
            )
        except Exception:
            return _error_response(SqlIdeRouteError("UNAUTHENTICATED"))
        try:
            denial = await _maybe_await(authorize(project_id, principal, permission, operation, payload))
        except Exception:
            return _error_response(SqlIdeRouteError("PERMISSION_DENIED"))
        if isinstance(denial, Response):
            return denial
        if denial is not None:
            return _error_response(SqlIdeRouteError("PERMISSION_DENIED"))
        try:
            result = await _maybe_await(
                dispatch(operation, project_id=project_id, principal=principal, payload=payload)
            )
        except SqlIdeRouteError as exc:
            return _error_response(exc)
        if isinstance(result, Response):
            return result
        response = JSONResponse(content={"code": 0, "msg": "success", "data": result})
        if operation == "executeSql" and isinstance(result, Mapping):
            task_id = result.get("taskId") or result.get("task_id")
            if task_id and result.get("accepted", True):
                response.set_cookie(
                    key=_event_cookie_name(str(task_id)),
                    value=token or _bearer_token(authorization),
                    httponly=True,
                    secure=True,
                    samesite="strict",
                    path=f"/api/v1/projects/{project_id}/sql-ide/executions/{task_id}/events",
                    max_age=3600,
                )
        return response

    def make_endpoint(operation: str, permission: str, has_body: bool, path_parameters: tuple[str, ...]):
        async def endpoint(request: Request, **path_values: Any) -> Any:
            project_id = int(request.path_params["project_id"])
            values = {name: request.path_params[name] for name in path_parameters}
            return await invoke(request, project_id, operation, permission, has_body, values)

        # FastAPI uses this signature to validate and document the route's path
        # variables. Request.path_params supplies the values to the closure.
        parameters = [
            inspect.Parameter("request", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Request),
            inspect.Parameter("project_id", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=int),
        ]
        parameters.extend(
            inspect.Parameter(name, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=str)
            for name in path_parameters
        )
        endpoint.__signature__ = inspect.Signature(parameters=parameters)  # type: ignore[attr-defined]
        endpoint.__name__ = f"sql_ide_{operation}"
        return endpoint

    for method, suffix, operation, permission, has_body in _ROUTE_SPECS:
        path_parameters = tuple(part[1:-1] for part in suffix.split("/") if part.startswith("{") and part.endswith("}"))
        router.add_api_route(
            suffix,
            make_endpoint(operation, permission, has_body, path_parameters),
            methods=[method],
            name=operation,
        )

    return router


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _bearer_token(authorization: str) -> str:
    return authorization[7:] if authorization.startswith("Bearer ") else ""


def _event_cookie_name(task_id: str) -> str:
    # Hash the identifier so caller-controlled task IDs cannot alter cookie syntax.
    suffix = hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:24]
    return f"sql_ide_event_{suffix}"


def _error_response(error: SqlIdeRouteError) -> JSONResponse:
    try:
        status = http_status_for(error.error_code)
        content = build_error_envelope(error.error_code, message=error.message, details=error.details)
    except ValueError:
        status = 500
        content = build_error_envelope("DRIVER_ERROR")
    return JSONResponse(status_code=status, content=content)
