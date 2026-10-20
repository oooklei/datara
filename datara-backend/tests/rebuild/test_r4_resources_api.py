"""R4 resource API contract tests — frozen FE contract (resourceApi.ts / A2 v2.1).

Key assertions: multipart upload with server-computed sha256 (client claims
never trusted), disk storage under REBUILD_RESOURCE_STORAGE_DIR (monkeypatched
to tmp_path), monotonic immutable version chain, kind/extension/size
re-validation (RES_* codes at contract statuses), list/version queries,
binding idempotency (same slot + same payload → same id, different payload →
409 RES_BINDING_CONFLICT), viewer 403 / anonymous 401 / frame 4001 gates.
"""

import hashlib

from fastapi.testclient import TestClient
from sqlalchemy import select

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.models import ProjectMemberRecord
from rebuild.identity.repository import UserRepository
from rebuild.project.models import ProjectRecord
from rebuild.resources.models import ResourceBindingRecord

RESOURCES = "/api/v1/rebuild/resources"
MAX_SIZE_BYTES = 20 * 1024 * 1024  # frozen with FE RESOURCE_MAX_SIZE_BYTES


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="r4-resource-test-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        admin = UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        dev = UserRepository(session).create(username="dev", password="dev-pass", role=Role.DEVELOPER)
        viewer = UserRepository(session).create(username="viewer", password="viewer-pass", role=Role.VIEWER)
        owned = ProjectRecord(name="r4-res-owned", description="", owner_id=dev.id)
        other = ProjectRecord(name="r4-res-other", description="", owner_id=admin.id)
        session.add_all((owned, other))
        session.commit()
        owned_id, other_id = owned.id, other.id
        session.add(ProjectMemberRecord(project_id=owned_id, user_id=viewer.id, role="viewer"))
        session.commit()
    tokens = {}
    for username, password in (("admin", "admin-pass"), ("dev", "dev-pass"), ("viewer", "viewer-pass")):
        response = client.post("/api/v1/rebuild/login", json={"username": username, "password": password})
        tokens[username] = {"Authorization": f"Bearer {response.json()['data']['token']}"}
    return client, app, owned_id, other_id, tokens


def _upload(client, headers, project_id, filename="etl_job.sql", kind="sql", content=b"SELECT 1;"):
    return client.post(
        f"{RESOURCES}/uploads",
        headers=headers,
        data={"project_id": str(project_id), "kind": kind},
        files={"file": (filename, content, "application/octet-stream")},
    )


def test_upload_multipart_digest_and_disk_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path))
    client, app, owned_id, _other_id, tokens = _client()
    try:
        content = b"SELECT 1;\n"
        response = _upload(client, tokens["dev"], owned_id, content=content)
        assert response.status_code == 200
        assert response.json()["code"] == 0
        data = response.json()["data"]
        assert data["version"] == 1
        assert data["size_bytes"] == len(content)
        assert data["digest"] == hashlib.sha256(content).hexdigest()
        assert data["digest"] == data["digest"].lower()  # lowercase hex, contract §4
        assert data["uploaded_at"].endswith("Z")
        # Stored under the pure {resource_id}/v{n} path, original name is metadata only.
        stored = tmp_path / str(data["resource_id"]) / "v1"
        assert stored.read_bytes() == content
    finally:
        client.__exit__(None, None, None)


def test_version_chain_monotonic_and_immutable(tmp_path, monkeypatch):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path))
    client, app, owned_id, _other_id, tokens = _client()
    try:
        first = _upload(client, tokens["dev"], owned_id, content=b"SELECT 1;")
        second = _upload(client, tokens["dev"], owned_id, content=b"SELECT 2;")
        v1, v2 = first.json()["data"], second.json()["data"]
        assert v1["version"] == 1 and v2["version"] == 2
        assert v2["resource_id"] == v1["resource_id"]

        versions = client.get(
            f"{RESOURCES}/{v1['resource_id']}/versions", headers=tokens["dev"], params={"project_id": owned_id}
        )
        assert versions.status_code == 200
        listed = versions.json()["data"]
        assert [row["version"] for row in listed] == [1, 2]
        assert listed[0]["digest"] == hashlib.sha256(b"SELECT 1;").hexdigest()
        assert listed[1]["digest"] == hashlib.sha256(b"SELECT 2;").hexdigest()

        detail = client.get(
            f"{RESOURCES}/{v1['resource_id']}/versions/1", headers=tokens["dev"], params={"project_id": owned_id}
        )
        assert detail.status_code == 200
        assert detail.json()["data"]["digest"] == listed[0]["digest"]

        # v1 content is never rewritten (immutability).
        assert (tmp_path / str(v1["resource_id"]) / "v1").read_bytes() == b"SELECT 1;"
    finally:
        client.__exit__(None, None, None)


def test_upload_validation_family(tmp_path, monkeypatch):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path))
    client, app, owned_id, _other_id, tokens = _client()
    try:
        wrong_extension = _upload(client, tokens["dev"], owned_id, filename="script.py", kind="sql")
        assert wrong_extension.status_code == 400
        assert wrong_extension.json()["code"] == "RES_TYPE_NOT_ALLOWED"

        unknown_kind = _upload(client, tokens["dev"], owned_id, kind="java")
        assert unknown_kind.status_code == 400 and unknown_kind.json()["code"] == "RES_KIND_UNKNOWN"

        oversized = _upload(client, tokens["dev"], owned_id, content=b"x" * (MAX_SIZE_BYTES + 1))
        assert oversized.status_code == 400 and oversized.json()["code"] == "RES_SIZE_EXCEEDED"

        missing_project = client.post(
            f"{RESOURCES}/uploads",
            headers=tokens["dev"],
            data={"kind": "sql"},
            files={"file": ("etl_job.sql", b"SELECT 1;")},
        )
        assert missing_project.status_code == 400 and missing_project.json()["code"] == 4001

        missing_file = client.post(
            f"{RESOURCES}/uploads", headers=tokens["dev"], data={"project_id": str(owned_id), "kind": "sql"}
        )
        assert missing_file.status_code == 400 and missing_file.json()["code"] == 4001
    finally:
        client.__exit__(None, None, None)


def test_kind_is_extension_locked_and_list_filters(tmp_path, monkeypatch):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path))
    client, app, owned_id, _other_id, tokens = _client()
    try:
        sql = _upload(client, tokens["dev"], owned_id, filename="etl_job.sql", kind="sql")
        resource_id = sql.json()["data"]["resource_id"]

        # Same name re-uploaded under python kind: extension .sql is not allowed for python.
        flip = _upload(client, tokens["dev"], owned_id, filename="etl_job.sql", kind="python", content=b"print(1)")
        assert flip.status_code == 400 and flip.json()["code"] == "RES_TYPE_NOT_ALLOWED"

        _upload(client, tokens["dev"], owned_id, filename="helper.py", kind="python", content=b"print(1)")

        sql_only = client.get(RESOURCES, headers=tokens["dev"], params={"project_id": owned_id, "kind": "sql"})
        assert sql_only.status_code == 200
        rows = sql_only.json()["data"]
        assert [row["name"] for row in rows] == ["etl_job.sql"]
        assert rows[0]["resource_id"] == resource_id
        assert rows[0]["kind"] == "sql" and rows[0]["latest_version"] == 1
        assert rows[0]["size_bytes"] == len(b"SELECT 1;")

        everything = client.get(RESOURCES, headers=tokens["dev"], params={"project_id": owned_id})
        assert [row["name"] for row in everything.json()["data"]] == ["etl_job.sql", "helper.py"]
    finally:
        client.__exit__(None, None, None)


def test_not_found_family(tmp_path, monkeypatch):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path))
    client, app, owned_id, other_id, tokens = _client()
    try:
        upload = _upload(client, tokens["dev"], owned_id)
        resource_id = upload.json()["data"]["resource_id"]

        unknown = client.get(f"{RESOURCES}/999/versions", headers=tokens["dev"], params={"project_id": owned_id})
        assert unknown.status_code == 404 and unknown.json()["code"] == "RES_OBJECT_NOT_FOUND"

        missing_version = client.get(
            f"{RESOURCES}/{resource_id}/versions/99", headers=tokens["dev"], params={"project_id": owned_id}
        )
        assert missing_version.status_code == 404 and missing_version.json()["code"] == "RES_VERSION_NOT_FOUND"

        # Same resource queried under a foreign project id is also 404 (project-scoped).
        foreign = client.get(
            f"{RESOURCES}/{resource_id}/versions", headers=tokens["admin"], params={"project_id": other_id}
        )
        assert foreign.status_code == 404 and foreign.json()["code"] == "RES_OBJECT_NOT_FOUND"
    finally:
        client.__exit__(None, None, None)


def test_binding_idempotency_and_conflict(tmp_path, monkeypatch):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path))
    client, app, owned_id, _other_id, tokens = _client()
    try:
        upload = _upload(client, tokens["dev"], owned_id)
        resource_id = upload.json()["data"]["resource_id"]
        _upload(client, tokens["dev"], owned_id, content=b"SELECT 2;")  # creates v2

        slot = {"project_id": owned_id, "workflow_id": 10, "workflow_version": 3, "task_id": "clean"}
        bind = client.post(
            f"{RESOURCES}/bindings",
            headers=tokens["dev"],
            json={**slot, "resource_id": resource_id, "resource_version": 1},
        )
        assert bind.status_code == 200
        assert bind.json()["data"]["bound"] is True
        binding_id = bind.json()["data"]["binding_id"]

        replay = client.post(
            f"{RESOURCES}/bindings",
            headers=tokens["dev"],
            json={**slot, "resource_id": resource_id, "resource_version": 1},
        )
        assert replay.status_code == 200
        assert replay.json()["data"]["binding_id"] == binding_id  # idempotent

        conflict = client.post(
            f"{RESOURCES}/bindings",
            headers=tokens["dev"],
            json={**slot, "resource_id": resource_id, "resource_version": 2},
        )
        assert conflict.status_code == 409 and conflict.json()["code"] == "RES_BINDING_CONFLICT"

        unknown_resource = client.post(
            f"{RESOURCES}/bindings",
            headers=tokens["dev"],
            json={**slot, "resource_id": 999, "resource_version": 1},
        )
        assert unknown_resource.status_code == 404 and unknown_resource.json()["code"] == "RES_OBJECT_NOT_FOUND"

        unknown_version = client.post(
            f"{RESOURCES}/bindings",
            headers=tokens["dev"],
            json={**slot, "resource_id": resource_id, "resource_version": 99},
        )
        assert unknown_version.status_code == 404 and unknown_version.json()["code"] == "RES_VERSION_NOT_FOUND"

        with app.state.session_factory() as session:
            count = len(session.scalars(select(ResourceBindingRecord)).all())
        assert count == 1  # idempotent replay created no second row
    finally:
        client.__exit__(None, None, None)


def test_viewer_and_anonymous_gates(tmp_path, monkeypatch):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path))
    client, app, owned_id, _other_id, tokens = _client()
    try:
        anonymous = _upload(client, {}, owned_id)
        assert anonymous.status_code == 401 and anonymous.json()["code"] == 1001

        viewer_upload = _upload(client, tokens["viewer"], owned_id)
        assert viewer_upload.status_code == 403 and viewer_upload.json()["code"] == 1003

        slot = {"project_id": owned_id, "workflow_id": 10, "workflow_version": 3, "task_id": "clean"}
        viewer_bind = client.post(
            f"{RESOURCES}/bindings",
            headers=tokens["viewer"],
            json={**slot, "resource_id": 1, "resource_version": 1},
        )
        assert viewer_bind.status_code == 403 and viewer_bind.json()["code"] == 1003

        viewer_list = client.get(RESOURCES, headers=tokens["viewer"], params={"project_id": owned_id})
        assert viewer_list.status_code == 200 and viewer_list.json()["data"] == []  # VIEW_ALL is enough to read
    finally:
        client.__exit__(None, None, None)
