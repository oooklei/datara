"""WF-12 draft snapshot API tests — design §4.1/§13.4.

Covers: snapshot creation via POST, idempotent re-create, GET by id,
auth/permission gates (401/403), frame validation (4001).
"""

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.project.models import ProjectRecord


TRIAL = "/api/v1/rebuild/trial"


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="trial-snap-test-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        admin = UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        dev = UserRepository(session).create(username="dev", password="dev-pass", role=Role.DEV)
        viewer = UserRepository(session).create(username="viewer", password="viewer-pass", role=Role.VIEWER)
        project = ProjectRecord(name="trial-snap-proj", description="", owner_id=dev.id)
        session.add(project)
        session.commit()
        project_id = project.id
    tokens = {}
    for username, password in (("admin", "admin-pass"), ("dev", "dev-pass"), ("viewer", "viewer-pass")):
        response = client.post("/api/v1/rebuild/login", json={"username": username, "password": password})
        tokens[username] = {"Authorization": f"Bearer {response.json()['data']['token']}"}
    return client, app, project_id, tokens


def _create_definition(client, headers, project_id, name="trial-flow"):
    return client.post(
        "/api/v1/rebuild/workflows",
        headers=headers,
        json={"project_id": project_id, "name": name},
    )


def _add_node(client, headers, project_id, definition_id, node_code):
    return client.post(
        f"/api/v1/rebuild/workflows/{definition_id}/nodes",
        headers=headers,
        json={"project_id": project_id, "node_code": node_code, "node_type": "SQL"},
    )


def test_create_snapshot_success_and_idempotent():
    client, app, project_id, tokens = _client()
    try:
        definition_id = _create_definition(client, tokens["dev"], project_id).json()["data"]["definition_id"]
        _add_node(client, tokens["dev"], project_id, definition_id, "extract")

        resp = client.post(
            f"{TRIAL}/definitions/{definition_id}/snapshot",
            headers=tokens["dev"],
            json={"project_id": project_id},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["definition_id"] == definition_id
        assert data["status"] == "ACTIVE"
        assert len(data["snapshot_digest"]) == 64
        first_id = data["snapshot_id"]

        # Idempotent: same digest returns same snapshot_id.
        resp2 = client.post(
            f"{TRIAL}/definitions/{definition_id}/snapshot",
            headers=tokens["dev"],
            json={"project_id": project_id},
        )
        assert resp2.json()["data"]["snapshot_id"] == first_id
    finally:
        client.__exit__(None, None, None)


def test_snapshot_digest_changes_with_draft():
    client, app, project_id, tokens = _client()
    try:
        definition_id = _create_definition(client, tokens["dev"], project_id).json()["data"]["definition_id"]
        _add_node(client, tokens["dev"], project_id, definition_id, "a")

        first = client.post(
            f"{TRIAL}/definitions/{definition_id}/snapshot",
            headers=tokens["dev"],
            json={"project_id": project_id},
        ).json()["data"]

        _add_node(client, tokens["dev"], project_id, definition_id, "b")
        second = client.post(
            f"{TRIAL}/definitions/{definition_id}/snapshot",
            headers=tokens["dev"],
            json={"project_id": project_id},
        ).json()["data"]

        assert first["snapshot_digest"] != second["snapshot_digest"]
    finally:
        client.__exit__(None, None, None)


def test_get_snapshot_by_id():
    client, app, project_id, tokens = _client()
    try:
        definition_id = _create_definition(client, tokens["dev"], project_id).json()["data"]["definition_id"]
        _add_node(client, tokens["dev"], project_id, definition_id, "x")
        created = client.post(
            f"{TRIAL}/definitions/{definition_id}/snapshot",
            headers=tokens["dev"],
            json={"project_id": project_id},
        ).json()["data"]

        resp = client.get(
            f"{TRIAL}/snapshots/{created['snapshot_id']}",
            headers=tokens["dev"],
            params={"project_id": project_id},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["snapshot_id"] == created["snapshot_id"]
    finally:
        client.__exit__(None, None, None)


def test_auth_and_permission_gates():
    client, app, project_id, tokens = _client()
    try:
        definition_id = _create_definition(client, tokens["dev"], project_id).json()["data"]["definition_id"]

        # No token → 401.
        anon = client.post(
            f"{TRIAL}/definitions/{definition_id}/snapshot",
            json={"project_id": project_id},
        )
        assert anon.status_code == 401 and anon.json()["code"] == 1001

        # Viewer → 403 on write.
        viewer = client.post(
            f"{TRIAL}/definitions/{definition_id}/snapshot",
            headers=tokens["viewer"],
            json={"project_id": project_id},
        )
        assert viewer.status_code == 403 and viewer.json()["code"] == 1003

        # Missing project_id → 400/4001.
        missing = client.post(
            f"{TRIAL}/definitions/{definition_id}/snapshot",
            headers=tokens["dev"],
            json={},
        )
        assert missing.status_code == 400 and missing.json()["code"] == 4001
    finally:
        client.__exit__(None, None, None)
