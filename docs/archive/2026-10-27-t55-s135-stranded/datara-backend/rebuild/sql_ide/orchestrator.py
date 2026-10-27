"""Operation-to-service orchestration for the SQL IDE HTTP adapter."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from rebuild.sql_ide.routes import SqlIdeRouteError


Service = Callable[..., Any]


class SqlIdeServiceOrchestrator:
    """Route an authorized operation to one explicitly assembled service."""

    def __init__(self, services: Mapping[str, Service]) -> None:
        self._services = dict(services)

    def dispatch(
        self,
        operation: str,
        *,
        project_id: int,
        principal: Mapping[str, Any],
        payload: Mapping[str, Any],
    ) -> Any:
        service = self._services.get(operation)
        if service is None:
            raise SqlIdeRouteError(
                "CAPABILITY_UNSUPPORTED",
                details={"operation": operation},
            )
        return service(
            project_id=project_id,
            principal=principal,
            payload=dict(payload),
        )


def build_sql_ide_services(
    *,
    status_store: Any,
    result_store: Any,
    history_store: Any,
    dialect_resolver: Callable[[int, int], str | None] | None = None,
) -> SqlIdeServiceOrchestrator:
    """Assemble handlers backed by the host's durable SQL IDE stores.

    Operations without a complete service are deliberately absent from the
    map. The orchestrator reports those through the frozen capability error
    contract instead of pretending that a partial implementation succeeded.
    """
    from rebuild.sql_ide.linter import lint_sql

    def lint(*, project_id: int, principal: Mapping[str, Any], payload: Mapping[str, Any]) -> Any:
        del principal
        dialect = payload.get("dialect")
        if dialect is None and dialect_resolver is not None:
            dialect = dialect_resolver(project_id, _required_int(payload, "datasourceId"))
        return lint_sql(payload.get("sql"), dialect=dialect)

    def get_status(*, project_id: int, principal: Mapping[str, Any], payload: Mapping[str, Any]) -> Any:
        result = status_store.get_execution_status(
            task_id=_required_text(payload, "task_id"),
            project_id=project_id,
            user_id=_user_id(principal),
        )
        if result is None:
            raise SqlIdeRouteError("RESOURCE_NOT_FOUND")
        return _status_payload(result)

    def fetch_result(*, project_id: int, principal: Mapping[str, Any], payload: Mapping[str, Any]) -> Any:
        result_set_id = _optional_text(payload.get("resultSetId"))
        stmt_index = _optional_int(payload.get("stmtIndex"))
        if result_set_id is None and stmt_index is None:
            raise SqlIdeRouteError(
                "INVALID_REQUEST",
                details={"field": "resultSetId"},
                message="resultSetId or stmtIndex is required",
            )
        try:
            return result_store.fetch_page(
                project_id=project_id,
                user_id=_user_id(principal),
                history_id=_required_text(payload, "history_id"),
                stmt_index=stmt_index,
                result_set_id=result_set_id,
                offset=_int(payload.get("offset"), 0),
                limit=_int(payload.get("limit"), 100),
            )
        except LookupError as exc:
            code = "RESULT_EXPIRED" if "expired" in str(exc).lower() else "RESULT_NOT_AVAILABLE"
            raise SqlIdeRouteError(code) from None
        except ValueError as exc:
            raise SqlIdeRouteError("INVALID_REQUEST", message=str(exc)) from None

    def list_history(*, project_id: int, principal: Mapping[str, Any], payload: Mapping[str, Any]) -> Any:
        try:
            records = history_store.list_history(
                project_id=project_id,
                user_id=_user_id(principal),
                datasource_id=_required_int(payload, "datasourceId"),
                limit=_int(payload.get("limit"), 100),
            )
            return [_history_payload(record) for record in records]
        except ValueError as exc:
            raise SqlIdeRouteError("INVALID_REQUEST", message=str(exc)) from None

    def delete_history(*, project_id: int, principal: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
        deleted = history_store.delete_history(
            project_id=project_id,
            user_id=_user_id(principal),
            history_id=_required_text(payload, "history_id"),
        )
        if not deleted:
            raise SqlIdeRouteError("RESOURCE_NOT_FOUND")

    def list_scripts(*, project_id: int, principal: Mapping[str, Any], payload: Mapping[str, Any]) -> Any:
        del payload
        records = history_store.list_scripts(project_id=project_id, user_id=_user_id(principal))
        return [_script_payload(record) for record in records]

    def save_script(*, project_id: int, principal: Mapping[str, Any], payload: Mapping[str, Any]) -> Any:
        script_id = payload.get("id", payload.get("scriptId"))
        expected_revision = payload.get("expectedRevision")
        try:
            saved = history_store.save_script(
                project_id=project_id,
                user_id=_user_id(principal),
                script_id=None if script_id is None else str(script_id),
                name=_required_text(payload, "name"),
                sql_text=_required_text(payload, "sqlText"),
                expected_revision=_optional_int(expected_revision),
            )
            return _script_payload(saved)
        except ValueError as exc:
            code = "SCRIPT_REVISION_CONFLICT" if "revision" in str(exc).lower() else "INVALID_REQUEST"
            raise SqlIdeRouteError(code, message=str(exc)) from None

    def delete_script(*, project_id: int, principal: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
        try:
            deleted = history_store.delete_script(
                project_id=project_id,
                user_id=_user_id(principal),
                script_id=_required_text(payload, "script_id"),
                expected_revision=_required_int(payload, "expectedRevision"),
            )
        except ValueError as exc:
            raise SqlIdeRouteError("INVALID_REQUEST", message=str(exc)) from None
        if not deleted:
            raise SqlIdeRouteError("RESOURCE_NOT_FOUND")

    return SqlIdeServiceOrchestrator(
        {
            "lintSql": lint,
            "getExecutionStatus": get_status,
            "fetchResultPage": fetch_result,
            "listHistory": list_history,
            "deleteHistory": delete_history,
            "listScripts": list_scripts,
            "saveScript": save_script,
            "deleteScript": delete_script,
        }
    )


def _user_id(principal: Mapping[str, Any]) -> int:
    try:
        return _strict_int(principal["user_id"])
    except (KeyError, TypeError, ValueError):
        raise SqlIdeRouteError("UNAUTHENTICATED") from None


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, (str, int)) or isinstance(value, bool) or not str(value).strip():
        raise SqlIdeRouteError("INVALID_REQUEST", details={"field": field})
    return str(value)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, (str, int)) or isinstance(value, bool) or not str(value).strip():
        raise SqlIdeRouteError("INVALID_REQUEST")
    return str(value)


def _required_int(payload: Mapping[str, Any], field: str) -> int:
    try:
        return _strict_int(payload[field])
    except (KeyError, TypeError, ValueError):
        raise SqlIdeRouteError("INVALID_REQUEST", details={"field": field}) from None


def _int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return _strict_int(value)
    except (TypeError, ValueError):
        raise SqlIdeRouteError("INVALID_REQUEST") from None


def _optional_int(value: Any) -> int | None:
    return None if value is None else _int(value, 0)


def _strict_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("boolean is not an integer")
    return int(value)


def _status_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": record["status"]}
    _copy_alias(record, payload, "task_id", "taskId")
    _copy_alias(record, payload, "history_id", "historyId")
    _copy_alias(record, payload, "created_at", "createdAt")
    _copy_alias(record, payload, "updated_at", "updatedAt")
    return payload


def _history_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "historyId": record["history_id"],
        "datasourceId": record["datasource_id"],
        "db": record.get("db"),
        "sqlText": record["sql_text"],
        "status": record["status"],
        "stmtCount": record["stmt_count"],
        "elapsedMs": record["elapsed_ms"],
        "createdAt": record["created_at"],
    }
    if "result_sets" in record:
        payload["resultSets"] = record["result_sets"]
    return payload


def _script_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": record["script_id"],
        "name": record["name"],
        "sqlText": record["sql_text"],
        "revision": record["revision"],
        "updatedAt": record["updated_at"],
    }


def _copy_alias(source: Mapping[str, Any], target: dict[str, Any], source_key: str, target_key: str) -> None:
    if source_key in source:
        target[target_key] = source[source_key]
