from datetime import datetime, timezone

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.openapi_admin import ApiCallLogRecord
from rebuild.apikey.models import ApiKeyRecord
from rebuild.apikey.service import _digest


def test_call_log_list_is_sanitized_and_filterable():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="open-call-log-test")
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            admin = UserRepository(session).create(username="open-admin", password="pw", role=Role.ADMIN)
            session.add(
                ApiCallLogRecord(
                    request_id="req-1",
                    api_id=7,
                    key_id=3,
                    principal="project:1",
                    project_id=1,
                    status_code=200,
                    latency_ms=12,
                    result="success",
                    requested_at=datetime(2026, 10, 25, tzinfo=timezone.utc),
                )
            )
            session.commit()
        token = client.post("/api/v1/rebuild/login", json={"username": "open-admin", "password": "pw"}).json()["data"]["token"]
        response = client.get("/api/v1/open/call-logs?api_id=7", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        assert body["data"]["total"] == 1
        row = body["data"]["list"][0]
        assert row["requestId"] == "req-1"
        assert row["statusCode"] == 200
        assert "key" not in row and "body" not in row and "sql" not in row


def test_call_log_list_accepts_scoped_api_key_without_bearer_token():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="open-call-log-key-test")
    with TestClient(app) as client:
        plain = "dk_live_call-log-secret"
        with app.state.session_factory() as session:
            session.add(ApiKeyRecord(
                name="call-log-reader", key_hash=_digest(plain), key_prefix=plain[:16],
                scopes_json='{"permissions":["security:read"],"projectIds":[]}',
                created_by="admin",
            ))
            session.commit()
        response = client.get("/api/v1/open/call-logs", headers={"X-API-Key": plain})
        assert response.status_code == 200
        assert response.json()["code"] == 0

