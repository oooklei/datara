from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from rebuild.api.app import create_app
from rebuild.governance.migrations import MigrationRunner, R3_GOVERNANCE_MIGRATIONS
from rebuild.governance.models import LegacyIdentityMappingRecord
from rebuild.identity.models import UserRecord


class _I23Reader:
    def __init__(self):
        row = {
            "id": 71,
            "user_name": "analyst-a",
            "user_role": "analyst",
            "state": "enabled",
            "create_time": datetime(2024, 1, 2, 3, 4, 5),
            "update_time": datetime(2024, 2, 3, 4, 5, 6),
        }
        self.snapshot = SimpleNamespace(
            schema="datara_meta",
            captured_at=datetime(2026, 10, 15, 9, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
            digest="a" * 64,
            counts={"t_user": 1},
            rows={"t_user": (row,)},
        )
        self.calls = 0
        self.engine = None

    def read_snapshot(self, **_kwargs):
        self.calls += 1
        return self.snapshot


def _client(*, validation_key="i23-validation-key"):
    reader = _I23Reader()
    app = create_app(
        "sqlite+pysqlite:///:memory:",
        token_secret="i23-preview-test-secret",
        validation_key=validation_key,
        legacy_i23_source_reader_factory=lambda: reader,
    )
    client = TestClient(app)
    client.__enter__()
    MigrationRunner(app.state.session_factory.kw["bind"], R3_GOVERNANCE_MIGRATIONS).apply()
    return client, app, reader


def _issue_i23_capability(client):
    return client.post(
        "/api/v1/rebuild/validation-capabilities/legacy-i23-preview",
        headers={"X-Backend-Validation-Key": "i23-validation-key"},
    )


def test_i23_capability_is_endpoint_only_and_preview_is_read_only():
    client, app, reader = _client()
    try:
        with app.state.session_factory() as session:
            user = UserRecord(
                username="analyst-a",
                password_hash="must-never-be-selected-or-returned",
                role="analyst",
                status="enabled",
            )
            session.add(user)
            session.commit()
            target_user_id = user.id

        statements = []
        target_engine = app.state.session_factory.kw["bind"]
        event.listen(
            target_engine, "before_cursor_execute", lambda _conn, _cursor, statement, *_: statements.append(statement)
        )

        issued = _issue_i23_capability(client)
        assert issued.status_code == 200
        capability = issued.json()["data"]["token"]
        scoped_headers = {"Authorization": f"Bearer {capability}"}
        preview = client.post(
            "/api/v1/rebuild/governance/legacy/i23/identity-preview",
            headers=scoped_headers,
            json={"selections": [{"source_id": "71", "target_user_id": target_user_id}]},
        )
        ordinary_route = client.get("/api/v1/rebuild/projects", headers=scoped_headers)
        with app.state.session_factory() as session:
            identity_mappings = session.scalar(select(func.count()).select_from(LegacyIdentityMappingRecord))
            target_users = session.scalar(select(func.count()).select_from(UserRecord))
    finally:
        client.__exit__(None, None, None)

    assert preview.status_code == 200
    data = preview.json()["data"]
    assert data["source"]["counts"] == {"t_user": 1}
    assert data["preview"]["counts"] == {
        "identity_candidate": 1,
        "target_identity_match": 0,
        "unresolved": 0,
        "blocked": 0,
    }
    assert data["preview"]["entries"][0]["selected_target_user_id"] == target_user_id
    assert data["preview"]["parity_verified"] is False
    assert data["preview"]["import_enabled"] is False
    assert "must-never-be-selected-or-returned" not in preview.text
    assert ordinary_route.status_code == 401
    assert reader.calls == 1
    assert identity_mappings == 0
    assert target_users == 1
    assert any("SELECT" in statement.upper() and "REBUILD_USER" in statement.upper() for statement in statements)
    assert all("PASSWORD_HASH" not in statement.upper() for statement in statements)
    assert not any(
        statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        and "REBUILD_GOVERNANCE_LEGACY_IDENTITY_MAPPING" in statement.upper()
        for statement in statements
    )


def test_i23_preview_rejects_dev_token_before_reading_source():
    client, _app, reader = _client()
    try:
        ordinary = client.post(
            "/api/v1/rebuild/validation-token",
            headers={"X-Backend-Validation-Key": "i23-validation-key"},
        )
        token = ordinary.json()["data"]["token"]
        response = client.post(
            "/api/v1/rebuild/governance/legacy/i23/identity-preview",
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 403
    assert reader.calls == 0


def test_i23_preview_cannot_reassign_an_existing_identity_mapping():
    client, app, _reader = _client()
    try:
        with app.state.session_factory() as session:
            existing_user = UserRecord(
                username="analyst-a",
                password_hash="unused-hash-a",
                role="analyst",
                status="enabled",
            )
            other_user = UserRecord(
                username="other-user",
                password_hash="unused-hash-b",
                role="analyst",
                status="enabled",
            )
            session.add_all([existing_user, other_user])
            session.flush()
            session.add(
                LegacyIdentityMappingRecord(
                    user_id=existing_user.id,
                    source_system="datara_meta",
                    source_table="t_user",
                    source_id="71",
                    source_username="analyst-a",
                    source_role="analyst",
                    mapped_role="analyst",
                    mapping_status="mapped",
                )
            )
            session.commit()
            other_user_id = other_user.id
        capability = _issue_i23_capability(client).json()["data"]["token"]
        response = client.post(
            "/api/v1/rebuild/governance/legacy/i23/identity-preview",
            headers={"Authorization": f"Bearer {capability}"},
            json={"selections": [{"source_id": "71", "target_user_id": other_user_id}]},
        )
    finally:
        client.__exit__(None, None, None)

    entry = response.json()["data"]["preview"]["entries"][0]
    assert response.status_code == 200
    assert entry["disposition"] == "blocked"
    assert "selection_conflicts_with_existing_mapping" in {issue["code"] for issue in entry["issues"]}


def test_i23_scoped_credential_issuer_is_disabled_without_validation_key():
    client, _app, reader = _client(validation_key="")
    try:
        response = client.post(
            "/api/v1/rebuild/validation-capabilities/legacy-i23-preview",
            headers={"X-Backend-Validation-Key": "anything"},
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 404
    assert response.json()["code"] == 4043
    assert reader.calls == 0


def test_i23_capability_issuer_rejects_wrong_runner_key():
    client, _app, reader = _client()
    try:
        response = client.post(
            "/api/v1/rebuild/validation-capabilities/legacy-i23-preview",
            headers={"X-Backend-Validation-Key": "wrong-key"},
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 401
    assert reader.calls == 0
