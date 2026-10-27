from __future__ import annotations

import sys
import types
from unittest.mock import Mock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from rebuild.sql_ide.orchestrator import build_sql_ide_services
from rebuild.sql_ide.routes import SqlIdeRouteError, build_sql_ide_router


def _services(*, status_store=None, result_store=None, history_store=None):
    return build_sql_ide_services(
        status_store=status_store or Mock(),
        result_store=result_store or Mock(),
        history_store=history_store or Mock(),
    )


def _dispatch(services, operation: str, payload: dict):
    return services.dispatch(
        operation,
        project_id=23,
        principal={"user_id": 7},
        payload=payload,
    )


def test_unassembled_operation_fails_with_frozen_capability_error():
    services = _services()

    with pytest.raises(SqlIdeRouteError) as caught:
        _dispatch(services, "executeSql", {"datasourceId": 9, "sql": "select 1"})

    assert caught.value.error_code == "CAPABILITY_UNSUPPORTED"
    assert caught.value.details == {"operation": "executeSql"}


def test_status_result_and_history_operations_keep_project_user_scope():
    status_store = Mock()
    status_store.get_execution_status.return_value = {"task_id": "task-1", "status": "running"}
    result_store = Mock()
    result_store.fetch_page.return_value = {"rows": [[1]], "page": {"offset": 0, "limit": 25}}
    history_store = Mock()
    history_store.list_history.return_value = [
        {
            "history_id": "history-1",
            "datasource_id": 9,
            "db": "analytics",
            "sql_text": "select 1",
            "status": "succeeded",
            "stmt_count": 1,
            "elapsed_ms": 12,
            "created_at": "2026-10-20T00:00:00Z",
        }
    ]
    services = _services(
        status_store=status_store,
        result_store=result_store,
        history_store=history_store,
    )

    assert _dispatch(services, "getExecutionStatus", {"task_id": "task-1"})["status"] == "running"
    assert _dispatch(
        services,
        "fetchResultPage",
        {"history_id": "history-1", "resultSetId": "result-1", "offset": "0", "limit": "25"},
    )["rows"] == [[1]]
    assert _dispatch(services, "listHistory", {"datasourceId": "9", "limit": "50"}) == [
        {
            "historyId": "history-1",
            "datasourceId": 9,
            "db": "analytics",
            "sqlText": "select 1",
            "status": "succeeded",
            "stmtCount": 1,
            "elapsedMs": 12,
            "createdAt": "2026-10-20T00:00:00Z",
        }
    ]

    status_store.get_execution_status.assert_called_once_with(
        task_id="task-1", project_id=23, user_id=7
    )
    result_store.fetch_page.assert_called_once_with(
        project_id=23,
        user_id=7,
        history_id="history-1",
        stmt_index=None,
        result_set_id="result-1",
        offset=0,
        limit=25,
    )
    history_store.list_history.assert_called_once_with(
        project_id=23, user_id=7, datasource_id=9, limit=50
    )


def test_history_and_script_mutations_translate_http_payload_names():
    history_store = Mock()
    history_store.delete_history.return_value = True
    history_store.save_script.return_value = {
        "script_id": "script-1",
        "name": "daily",
        "sql_text": "select 1",
        "revision": 2,
        "updated_at": "2026-10-20T00:00:00Z",
    }
    history_store.delete_script.return_value = True
    services = _services(history_store=history_store)

    assert _dispatch(services, "deleteHistory", {"history_id": "history-1"}) is None
    assert _dispatch(
        services,
        "saveScript",
        {
            "id": "script-1",
            "name": "daily",
            "sqlText": "select 1",
            "expectedRevision": 1,
        },
    )["revision"] == 2
    assert _dispatch(
        services,
        "deleteScript",
        {"script_id": "script-1", "expectedRevision": "2"},
    ) is None

    history_store.delete_history.assert_called_once_with(
        project_id=23, user_id=7, history_id="history-1"
    )
    history_store.save_script.assert_called_once_with(
        project_id=23,
        user_id=7,
        script_id="script-1",
        name="daily",
        sql_text="select 1",
        expected_revision=1,
    )
    history_store.delete_script.assert_called_once_with(
        project_id=23,
        user_id=7,
        script_id="script-1",
        expected_revision=2,
    )


def test_missing_owned_resource_uses_hidden_not_found_error():
    status_store = Mock()
    status_store.get_execution_status.return_value = None
    services = _services(status_store=status_store)

    with pytest.raises(SqlIdeRouteError) as caught:
        _dispatch(services, "getExecutionStatus", {"task_id": "unknown"})

    assert caught.value.error_code == "RESOURCE_NOT_FOUND"


def test_lint_resolves_dialect_from_project_datasource_context():
    resolver = Mock(return_value="postgresql")
    services = build_sql_ide_services(
        status_store=Mock(),
        result_store=Mock(),
        history_store=Mock(),
        dialect_resolver=resolver,
    )

    result = _dispatch(
        services,
        "lintSql",
        {"datasourceId": "9", "sql": "select 1"},
    )

    assert result == {"valid": True, "diagnostics": []}
    resolver.assert_called_once_with(23, 9)


def test_router_serializes_unassembled_operation_with_frozen_error_envelope():
    services = _services()
    app = FastAPI()
    app.include_router(
        build_sql_ide_router(
            dispatch=services.dispatch,
            authenticate=lambda _token, _authorization: {"user_id": 7},
            authorize=lambda *_args: None,
        )
    )

    response = TestClient(app).post(
        "/api/v1/projects/23/sql-ide/executions",
        headers={"token": "test-token"},
        json={"datasourceId": 9, "sql": "select 1"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": 422,
        "msg": "Capability is unsupported",
        "data": {
            "errorCode": "CAPABILITY_UNSUPPORTED",
            "details": {"operation": "executeSql"},
        },
    }


def test_application_factory_wires_sql_ide_orchestrator(monkeypatch):
    execution_api = types.ModuleType("rebuild.execution.api")
    execution_api.build_execution_router = lambda *_args: APIRouter()
    monkeypatch.setitem(sys.modules, "rebuild.execution.api", execution_api)

    from rebuild.api.app import create_app

    app = create_app("sqlite:///:memory:", token_secret="test-secret")

    assert app.state.sql_ide_dispatch == app.state.sql_ide_services.dispatch
    with TestClient(app) as client:
        response = client.get("/api/v1/projects/1/sql-ide/scripts")
    assert response.status_code == 401

