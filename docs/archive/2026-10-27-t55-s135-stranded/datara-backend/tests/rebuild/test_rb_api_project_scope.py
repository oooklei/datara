"""Project-scope contract tests for the R5-B HTTP adapter."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from rebuild.identity.contracts import Role, TokenService
from rebuild.rb.api import build_rb_router
from rebuild.rb.facade.rb_facade import RbFacade


def _client(*, submit_service=None, list_service=None, authorizer=None):
    token_service = TokenService("rb-project-scope-secret")
    token = token_service.issue(user_id=11, username="dev", role=Role.DEV)
    app = FastAPI()
    app.include_router(
        build_rb_router(
            RbFacade(
                submit_confirm_service=submit_service,
                list_execution_records_service=list_service,
            ),
            token_service,
            {token},
            authorizer or (lambda _project_id, _principal, _permission: None),
        )
    )
    return TestClient(app), {"token": token}


def test_list_records_uses_authorized_path_project_id():
    calls = []

    def list_service(**values):
        calls.append(values)
        return {"items": [], "page": {"nextCursor": None, "hasMore": False}}

    client, headers = _client(list_service=list_service)
    response = client.post(
        "/api/v1/projects/3/sql-ide-ddl/execution-records",
        headers=headers,
        json={"datasourceId": 7},
    )

    assert response.status_code == 200
    assert calls[0]["project_id"] == 3
    assert calls[0]["datasource_id"] == 7


def test_confirm_uses_authenticated_actor_and_write_permission():
    service_calls = []
    authorization_calls = []

    def submit_service(**values):
        service_calls.append(values)
        return {"recordId": "record-1", "status": "success"}

    def authorize(project_id, principal, permission):
        authorization_calls.append((project_id, principal, permission))

    client, headers = _client(submit_service=submit_service, authorizer=authorize)
    response = client.post(
        "/api/v1/projects/3/sql-ide-ddl/confirm",
        headers=headers,
        json={
            "datasourceId": 7,
            "objectRef": {"database": "warehouse", "kind": "table", "name": "orders"},
            "sourceVersion": "etag-1",
            "nextDdlText": "ALTER TABLE orders ADD COLUMN note TEXT",
            "policySnapshotId": "policy-1",
            "impactSnapshotId": "impact-1",
            "confirmPhrase": "user-input",
        },
    )

    assert response.status_code == 200
    assert authorization_calls[0][0] == 3
    assert authorization_calls[0][1]["user_id"] == 11
    assert authorization_calls[0][2] == "EDIT_DEFINITION"
    assert service_calls[0]["project_id"] == 3
    assert service_calls[0]["actor_id"] == 11


def test_project_authorization_denial_stops_service_call():
    calls = []

    def list_service(**values):
        calls.append(values)
        return {"items": []}

    def deny(_project_id, _principal, _permission):
        return JSONResponse(status_code=404, content={"code": 404, "msg": "not found", "data": None})

    client, headers = _client(list_service=list_service, authorizer=deny)
    response = client.post(
        "/api/v1/projects/999/sql-ide-ddl/execution-records",
        headers=headers,
        json={"datasourceId": 7},
    )

    assert response.status_code == 404
    assert calls == []


def test_legacy_unscoped_route_is_not_mounted():
    client, headers = _client(list_service=lambda **_values: {"items": []})

    response = client.post(
        "/api/v1/rebuild/sql-ide-ddl/execution-records",
        headers=headers,
        json={"datasourceId": 7},
    )

    assert response.status_code == 404
