from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from unittest.mock import patch

from rebuild.sql_ide.routes import build_sql_ide_router


def _router():
    calls = []

    def authenticate(token, authorization):
        assert token == "test-token"
        return {"user_id": 7}

    def authorize(project_id, principal, permission, operation, payload):
        calls.append(("authorize", project_id, permission, operation))
        return None

    def dispatch(operation, *, project_id, principal, payload):
        calls.append(("dispatch", project_id, operation, payload))
        return {"operation": operation}

    app = FastAPI()
    router = build_sql_ide_router(
        dispatch=dispatch,
        authenticate=authenticate,
        authorize=authorize,
    )
    app.include_router(router)
    return TestClient(app), calls, router


def test_router_exposes_project_scoped_a5_routes_without_app_factory_wiring():
    client, _, router = _router()
    paths = {route.path for route in router.routes}
    assert "/api/v1/projects/{project_id}/sql-ide/lint" in paths
    assert "/api/v1/projects/{project_id}/sql-ide/executions/{task_id}/events" in paths
    assert "/api/v1/projects/{project_id}/sql-ide/results/{history_id}" in paths
    assert "/api/v1/projects/{project_id}/sql-ide/scripts/{script_id}" in paths


def test_lint_route_uses_authenticated_project_scope_and_success_envelope():
    client, calls, _ = _router()
    response = client.post(
        "/api/v1/projects/23/sql-ide/lint",
        headers={"token": "test-token"},
        json={"datasourceId": 9, "sql": "select 1"},
    )
    assert response.status_code == 200
    assert response.json() == {"code": 0, "msg": "success", "data": {"operation": "lintSql"}}
    assert calls == [
        ("authorize", 23, "VIEW_ALL", "lintSql"),
        ("dispatch", 23, "lintSql", {"datasourceId": 9, "sql": "select 1"}),
    ]


def test_execution_is_write_scoped_and_dispatches_request_payload():
    client, calls, _ = _router()
    response = client.post(
        "/api/v1/projects/23/sql-ide/executions",
        headers={"token": "test-token"},
        json={"datasourceId": 9, "sql": "select 1", "mode": "auto"},
    )
    assert response.status_code == 200
    assert calls[0] == ("authorize", 23, "EXECUTE_SQL", "executeSql")
    assert calls[1][0:3] == ("dispatch", 23, "executeSql")


def test_result_set_pagination_history_script_cas_and_export_contracts():
    client, calls, _ = _router()
    headers = {"token": "test-token"}

    page = client.get(
        "/api/v1/projects/23/sql-ide/results/81?resultSetId=rs-9&offset=500&limit=500",
        headers=headers,
    )
    assert page.status_code == 200
    assert calls[-1] == (
        "dispatch", 23, "fetchResultPage",
        {"resultSetId": "rs-9", "offset": "500", "limit": "500", "history_id": "81"},
    )

    saved = client.post(
        "/api/v1/projects/23/sql-ide/scripts",
        headers=headers,
        json={"id": 8, "name": "daily", "sqlText": "select 1", "expectedRevision": 3},
    )
    assert saved.status_code == 200
    assert calls[-1][2] == "saveScript"
    assert calls[-1][3]["expectedRevision"] == 3

    deleted = client.delete(
        "/api/v1/projects/23/sql-ide/scripts/8?expectedRevision=4", headers=headers
    )
    assert deleted.status_code == 200
    assert calls[-1][2] == "deleteScript"
    assert calls[-1][3] == {"expectedRevision": "4", "script_id": "8"}

    exported = client.post(
        "/api/v1/projects/23/sql-ide/exports",
        headers=headers,
        json={"historyId": 81, "resultSetId": "rs-9", "format": "xlsx"},
    )
    assert exported.status_code == 200
    assert calls[-1][2] == "exportResult"
    assert calls[-1][3]["resultSetId"] == "rs-9"


def test_hidden_or_denied_resources_keep_injected_authorization_response():
    def authorize(project_id, principal, permission, operation, payload):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"code": 404, "msg": "not found", "data": None})

    app = FastAPI()
    app.include_router(
        build_sql_ide_router(
            dispatch=lambda *args, **kwargs: pytest.fail("unauthorized request dispatched"),
            authenticate=lambda token, authorization: {"user_id": 7},
            authorize=authorize,
        )
    )
    response = TestClient(app).delete(
        "/api/v1/projects/23/sql-ide/history/44", headers={"token": "test-token"}
    )
    assert response.status_code == 404
    assert response.json()["msg"] == "not found"


def test_execution_sets_task_scoped_secure_cookie_and_events_authenticate_from_it():
    authenticated = []

    def authenticate(token, authorization):
        authenticated.append((token, authorization))
        if token != "test-token":
            raise ValueError("invalid token")
        return {"user_id": 7}

    app = FastAPI()
    app.include_router(
        build_sql_ide_router(
            dispatch=lambda operation, **kwargs: (
                {"accepted": True, "taskId": "task-1"}
                if operation == "executeSql"
                else {"events": []}
            ),
            authenticate=authenticate,
            authorize=lambda *args: None,
        )
    )
    client = TestClient(app, base_url="https://testserver")

    started = client.post(
        "/api/v1/projects/23/sql-ide/executions",
        headers={"token": "test-token"},
        json={"datasourceId": 9, "sql": "select 1"},
    )
    assert started.status_code == 200
    cookie = started.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=strict" in cookie
    assert "Path=/api/v1/projects/23/sql-ide/executions/task-1/events" in cookie

    events = client.get("/api/v1/projects/23/sql-ide/executions/task-1/events")
    assert events.status_code == 200
    assert client.get("/api/v1/projects/23/sql-ide/executions/task-2/events").status_code == 401
    assert authenticated == [("test-token", ""), ("test-token", ""), ("", "")]


def test_application_factory_mounts_project_scoped_sql_ide_routes():
    from rebuild.api.app import create_app

    with patch.dict(
        "os.environ",
        {"REBUILD_DB_URL": "sqlite:///:memory:", "REBUILD_TOKEN_SECRET": "test-secret"},
        clear=True,
    ):
        app = create_app()
    with TestClient(app) as client:
        assert client.get("/api/v1/projects/1/sql-ide/results/1").status_code == 401
        assert client.get("/api/v1/projects/1/sql-ide/scripts").status_code == 401
        assert client.get("/api/v1/projects/1/sql-ide/exports/export-1/download").status_code == 401



