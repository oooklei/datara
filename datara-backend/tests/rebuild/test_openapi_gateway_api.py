"""Gateway endpoint G contract tests (15-P0 freeze: /api/v1/open/gateway/{api_path}).

Covers the minimal closure: key authentication, definition resolution by
(path, method), status gating, scope enforcement and the sanitized call-log
write on success.
"""
import json
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.apikey.models import ApiKeyRecord
from rebuild.apikey.service import _digest
from rebuild.openapi_admin import ApiDefinitionRecord

GATEWAY = "/api/v1/open/gateway"


def _seed_key(session, *, name="gw-key", permissions=("security:read",), project_ids=(),
              status="active", expires_at=None, revoked_at=None):
    plain = f"dk_live_{name}"
    session.add(ApiKeyRecord(
        name=name,
        key_hash=_digest(plain),
        key_prefix=plain[:16],
        scopes_json=json.dumps({"permissions": list(permissions), "projectIds": list(project_ids)}),
        created_by="admin",
        status=status,
        expires_at=expires_at,
        revoked_at=revoked_at,
    ))
    session.commit()
    return plain


def _seed_definition(session, *, path="/rebuild/gateway/ping", method="GET",
                     status="published", required_permission="security:read"):
    row = ApiDefinitionRecord(
        name="gateway-ping",
        path=path,
        method=method,
        version="v1",
        description="",
        required_permission=required_permission,
        status=status,
        created_by="admin",
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def _app():
    return create_app("sqlite+pysqlite:///:memory:", token_secret="openapi-gateway-test")


def test_gateway_without_key_is_unauthorized():
    app = _app()
    with TestClient(app) as client:
        response = client.get(f"{GATEWAY}/rebuild/gateway/ping")
        assert response.status_code == 401
        assert response.json()["code"] == 1001


def test_gateway_unknown_path_is_not_found():
    app = _app()
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            plain = _seed_key(session)
        response = client.get(f"{GATEWAY}/rebuild/gateway/missing", headers={"X-API-Key": plain})
        assert response.status_code == 404
        assert response.json()["code"] == 4041


def test_gateway_draft_definition_is_not_found():
    app = _app()
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            plain = _seed_key(session)
            _seed_definition(session, status="draft")
        response = client.get(f"{GATEWAY}/rebuild/gateway/ping", headers={"X-API-Key": plain})
        assert response.status_code == 404
        assert response.json()["code"] == 4041


def test_gateway_disabled_definition_is_conflict():
    app = _app()
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            plain = _seed_key(session)
            _seed_definition(session, status="disabled")
        response = client.get(f"{GATEWAY}/rebuild/gateway/ping", headers={"X-API-Key": plain})
        assert response.status_code == 409
        assert response.json()["code"] == 4092


def test_gateway_scope_denied_is_rejected():
    app = _app()
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            plain = _seed_key(session, permissions=("quality:read",))
            _seed_definition(session, required_permission="security:manage")
        response = client.get(f"{GATEWAY}/rebuild/gateway/ping", headers={"X-API-Key": plain})
        assert response.status_code == 403
        assert response.json()["code"] == 4095


def test_gateway_expired_key_is_rejected():
    app = _app()
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            plain = _seed_key(session, expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc))
            _seed_definition(session)
        response = client.get(f"{GATEWAY}/rebuild/gateway/ping", headers={"X-API-Key": plain})
        assert response.status_code == 403
        assert response.json()["code"] == 4093


def test_gateway_revoked_key_is_rejected():
    app = _app()
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            plain = _seed_key(session, status="revoked", revoked_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
            _seed_definition(session)
        response = client.get(f"{GATEWAY}/rebuild/gateway/ping", headers={"X-API-Key": plain})
        assert response.status_code == 403
        assert response.json()["code"] == 4094


def test_gateway_success_records_sanitized_call_log():
    app = _app()
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            plain = _seed_key(session)
            definition = _seed_definition(session)
        response = client.get(f"{GATEWAY}/rebuild/gateway/ping", headers={"X-API-Key": plain})
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        request_id = body["data"]["requestId"]
        assert body["data"]["apiId"] == definition.id
        assert body["data"]["apiPath"] == "/rebuild/gateway/ping"

        logs = client.get("/api/v1/open/call-logs", headers={"X-API-Key": plain}).json()
        assert logs["code"] == 0
        assert logs["data"]["total"] == 1
        row = logs["data"]["list"][0]
        assert row["requestId"] == request_id
        assert row["apiId"] == definition.id
        assert row["statusCode"] == 200
        assert row["result"] == "success"
        assert "key" not in row and "body" not in row and "sql" not in row
