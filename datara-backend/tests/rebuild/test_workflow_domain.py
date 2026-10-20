"""R2 workflow domain tests — design §3.1/§4 (大盘缺口 #2/#12).

Key assertions: definition CRUD with per-project name uniqueness; draft
node/edge upsert (replace-by-code) + edge endpoint validation + node-delete
edge cascade; publish = immutable version snapshot (monotonic version,
snapshot_digest bound to the copied rows) + publish record + current_version
bump; published version rows reject content mutation (WF_VERSION_IMMUTABLE);
version list/detail; deletion guard (WF_DEFINITION_HAS_PUBLISHED); empty-draft
publish rejection; auth/permission/frame gates.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.models import ProjectMemberRecord
from rebuild.identity.repository import UserRepository
from rebuild.project.models import ProjectRecord
from rebuild.workflow.models import (
    WorkflowDefinitionRecord,
    WorkflowPublishRecord,
    WorkflowVersionRecord,
)
from rebuild.workflow.repository import (
    WorkflowDomainError,
    WorkflowRepository,
    snapshot_digest,
)

WORKFLOWS = "/api/v1/rebuild/workflows"


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="r2-workflow-test-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        admin = UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        dev = UserRepository(session).create(username="dev", password="dev-pass", role=Role.DEVELOPER)
        viewer = UserRepository(session).create(username="viewer", password="viewer-pass", role=Role.VIEWER)
        owned = ProjectRecord(name="wf-owned", description="", owner_id=dev.id)
        other = ProjectRecord(name="wf-other", description="", owner_id=admin.id)
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


def _create(client, headers, project_id, name="etl-daily", description=""):
    return client.post(
        WORKFLOWS,
        headers=headers,
        json={"project_id": project_id, "name": name, "description": description},
    )


def _add_node(client, headers, project_id, definition_id, node_code, node_type="SQL", name=None, params=None, position_x=None, position_y=None):
    body = {"project_id": project_id, "node_code": node_code, "node_type": node_type}
    if name is not None:
        body["name"] = name
    if params is not None:
        body["params"] = params
    if position_x is not None:
        body["position_x"] = position_x
    if position_y is not None:
        body["position_y"] = position_y
    return client.post(f"{WORKFLOWS}/{definition_id}/nodes", headers=headers, json=body)


def _add_edge(client, headers, project_id, definition_id, from_node, to_node, name=None):
    body = {"project_id": project_id, "from_node": from_node, "to_node": to_node}
    if name is not None:
        body["name"] = name
    return client.post(f"{WORKFLOWS}/{definition_id}/edges", headers=headers, json=body)


def _publish(client, headers, project_id, definition_id, remark=None):
    body = {"project_id": project_id}
    if remark is not None:
        body["remark"] = remark
    return client.post(f"{WORKFLOWS}/{definition_id}/publish", headers=headers, json=body)


def test_create_definition_name_uniqueness_and_list():
    client, app, owned_id, other_id, tokens = _client()
    try:
        created = _create(client, tokens["dev"], owned_id, name="etl-daily", description="daily etl")
        assert created.status_code == 200 and created.json()["code"] == 0
        data = created.json()["data"]
        assert data["name"] == "etl-daily"
        assert data["current_version"] is None  # never published

        # Same-name conflict is scoped per project (409 WF_NAME_CONFLICT).
        duplicate = _create(client, tokens["dev"], owned_id, name="etl-daily")
        assert duplicate.status_code == 409 and duplicate.json()["code"] == "WF_NAME_CONFLICT"

        cross = _create(client, tokens["admin"], other_id, name="etl-daily")
        assert cross.status_code == 200

        listing = client.get(WORKFLOWS, headers=tokens["dev"], params={"project_id": owned_id})
        assert listing.status_code == 200
        items = listing.json()["data"]
        assert [row["definition_id"] for row in items] == [data["definition_id"]]
        assert items[0]["name"] == "etl-daily"
    finally:
        client.__exit__(None, None, None)


def test_definition_update_detail_and_404():
    client, app, owned_id, _other_id, tokens = _client()
    try:
        definition_id = _create(client, tokens["dev"], owned_id).json()["data"]["definition_id"]

        updated = client.post(
            f"{WORKFLOWS}/{definition_id}/updates",
            headers=tokens["dev"],
            json={"project_id": owned_id, "name": "etl-renamed", "description": "renamed"},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["name"] == "etl-renamed"

        # Rename onto an existing sibling name is a conflict.
        _create(client, tokens["dev"], owned_id, name="etl-second")
        clash = client.post(
            f"{WORKFLOWS}/{definition_id}/updates",
            headers=tokens["dev"],
            json={"project_id": owned_id, "name": "etl-second"},
        )
        assert clash.status_code == 409 and clash.json()["code"] == "WF_NAME_CONFLICT"

        detail = client.get(f"{WORKFLOWS}/{definition_id}", headers=tokens["dev"], params={"project_id": owned_id})
        assert detail.status_code == 200
        payload = detail.json()["data"]
        assert payload["name"] == "etl-renamed"
        assert payload["draft"] == {"nodes": [], "edges": []}

        missing = client.get(f"{WORKFLOWS}/999999", headers=tokens["dev"], params={"project_id": owned_id})
        assert missing.status_code == 404 and missing.json()["code"] == "WF_DEFINITION_NOT_FOUND"
    finally:
        client.__exit__(None, None, None)


def test_draft_node_upsert_replaces_by_code_and_type_validation():
    client, app, owned_id, _other_id, tokens = _client()
    try:
        definition_id = _create(client, tokens["dev"], owned_id).json()["data"]["definition_id"]

        first = _add_node(client, tokens["dev"], owned_id, definition_id, "task_a", node_type="SQL")
        assert first.status_code == 200
        assert first.json()["data"]["name"] == "task_a"  # name defaults to node_code

        # Re-saving the same node_code replaces the draft row (no duplicate).
        replace = _add_node(
            client,
            tokens["dev"],
            owned_id,
            definition_id,
            "task_a",
            node_type="PYTHON",
            name="clean job",
            params={"script": "clean.py"},
            position_x=120,
            position_y=80,
        )
        assert replace.status_code == 200
        detail = client.get(f"{WORKFLOWS}/{definition_id}", headers=tokens["dev"], params={"project_id": owned_id})
        nodes = detail.json()["data"]["draft"]["nodes"]
        assert len(nodes) == 1
        assert nodes[0]["node_type"] == "PYTHON"
        assert nodes[0]["name"] == "clean job"
        assert nodes[0]["params"] == {"script": "clean.py"}
        assert nodes[0]["position_x"] == 120

        unknown_type = _add_node(client, tokens["dev"], owned_id, definition_id, "task_b", node_type="SPARK")
        assert unknown_type.status_code == 400
        assert unknown_type.json()["code"] == "WF_NODE_TYPE_UNKNOWN"

        missing_code = client.post(
            f"{WORKFLOWS}/{definition_id}/nodes", headers=tokens["dev"], json={"project_id": owned_id, "node_type": "SQL"}
        )
        assert missing_code.status_code == 400 and missing_code.json()["code"] == 4001
    finally:
        client.__exit__(None, None, None)


def test_draft_edge_validation_and_node_delete_cascade():
    client, app, owned_id, _other_id, tokens = _client()
    try:
        definition_id = _create(client, tokens["dev"], owned_id).json()["data"]["definition_id"]
        _add_node(client, tokens["dev"], owned_id, definition_id, "task_a")
        _add_node(client, tokens["dev"], owned_id, definition_id, "task_b")

        invalid = _add_edge(client, tokens["dev"], owned_id, definition_id, "task_a", "ghost")
        assert invalid.status_code == 400 and invalid.json()["code"] == "WF_EDGE_INVALID"

        valid = _add_edge(client, tokens["dev"], owned_id, definition_id, "task_a", "task_b", name="next")
        assert valid.status_code == 200
        detail = client.get(f"{WORKFLOWS}/{definition_id}", headers=tokens["dev"], params={"project_id": owned_id})
        edges = detail.json()["data"]["draft"]["edges"]
        assert len(edges) == 1 and edges[0]["name"] == "next"

        # Deleting a node cascades the touching draft edges.
        removed = client.post(
            f"{WORKFLOWS}/{definition_id}/nodes/delete",
            headers=tokens["dev"],
            json={"project_id": owned_id, "node_code": "task_b"},
        )
        assert removed.status_code == 200
        detail = client.get(f"{WORKFLOWS}/{definition_id}", headers=tokens["dev"], params={"project_id": owned_id})
        assert detail.json()["data"]["draft"]["edges"] == []
        assert [n["node_code"] for n in detail.json()["data"]["draft"]["nodes"]] == ["task_a"]

        missing = client.post(
            f"{WORKFLOWS}/{definition_id}/nodes/delete",
            headers=tokens["dev"],
            json={"project_id": owned_id, "node_code": "task_b"},
        )
        assert missing.status_code == 404 and missing.json()["code"] == "WF_NODE_NOT_FOUND"
    finally:
        client.__exit__(None, None, None)


def test_publish_creates_immutable_snapshot_and_record():
    client, app, owned_id, _other_id, tokens = _client()
    try:
        definition_id = _create(client, tokens["dev"], owned_id).json()["data"]["definition_id"]
        _add_node(
            client, tokens["dev"], owned_id, definition_id, "task_a", name="extract", params={"sql": "SELECT 1"}
        )
        _add_node(client, tokens["dev"], owned_id, definition_id, "task_b", node_type="PYTHON", name="load")
        _add_edge(client, tokens["dev"], owned_id, definition_id, "task_a", "task_b")

        published = _publish(client, tokens["dev"], owned_id, definition_id, remark="first release")
        assert published.status_code == 200
        data = published.json()["data"]
        assert data["version"] == 1
        assert data["status"] == "PUBLISHED"
        assert data["node_count"] == 2 and data["edge_count"] == 1
        assert data["published_at"].endswith("Z")
        assert data["published_by"] is not None

        # Snapshot digest binds the copied rows (recomputed from version detail).
        detail = client.get(
            f"{WORKFLOWS}/{definition_id}/versions/1", headers=tokens["dev"], params={"project_id": owned_id}
        )
        assert detail.status_code == 200
        version_data = detail.json()["data"]
        assert [n["node_code"] for n in version_data["nodes"]] == ["task_a", "task_b"]
        assert version_data["nodes"][0]["params"] == {"sql": "SELECT 1"}
        assert version_data["snapshot_digest"] == snapshot_digest(version_data["nodes"], version_data["edges"])
        assert version_data["publish_record"]["remark"] == "first release"

        with app.state.session_factory() as session:
            definition = session.get(WorkflowDefinitionRecord, definition_id)
            assert definition.current_version == 1
            assert session.scalar(select(WorkflowPublishRecord)) is not None

        # Edit the draft and publish again: v2 gets the new shape, v1 stays frozen.
        _add_node(client, tokens["dev"], owned_id, definition_id, "task_a", node_type="SQL", name="extract v2")
        _add_node(client, tokens["dev"], owned_id, definition_id, "task_c", node_type="SHELL")
        second = _publish(client, tokens["dev"], owned_id, definition_id, remark="second release")
        assert second.json()["data"]["version"] == 2
        assert second.json()["data"]["node_count"] == 3

        v1 = client.get(
            f"{WORKFLOWS}/{definition_id}/versions/1", headers=tokens["dev"], params={"project_id": owned_id}
        ).json()["data"]
        assert [n["name"] for n in v1["nodes"]] == ["extract", "load"]  # v1 rows untouched
        assert len(v1["nodes"]) == 2
        assert v1["snapshot_digest"] == version_data["snapshot_digest"]
    finally:
        client.__exit__(None, None, None)


def test_published_version_rows_reject_mutation():
    client, app, owned_id, _other_id, tokens = _client()
    try:
        definition_id = _create(client, tokens["dev"], owned_id).json()["data"]["definition_id"]
        _add_node(client, tokens["dev"], owned_id, definition_id, "task_a")
        _publish(client, tokens["dev"], owned_id, definition_id, remark="release")

        with app.state.session_factory() as session:
            repo = WorkflowRepository(session)
            with pytest.raises(WorkflowDomainError) as excinfo:
                repo.update_version_content(owned_id, definition_id, 1, remark="tampered")
            assert excinfo.value.code == "WF_VERSION_IMMUTABLE"
            session.rollback()

            row = session.scalar(
                select(WorkflowVersionRecord).where(WorkflowVersionRecord.definition_id == definition_id)
            )
            assert row.status == "PUBLISHED" and row.remark == "release"

            with pytest.raises(WorkflowDomainError) as excinfo:
                repo.update_version_content(owned_id, definition_id, 99, remark="x")
            assert excinfo.value.code == "WF_VERSION_NOT_FOUND"
    finally:
        client.__exit__(None, None, None)


def test_version_list_and_detail_404():
    client, app, owned_id, _other_id, tokens = _client()
    try:
        definition_id = _create(client, tokens["dev"], owned_id).json()["data"]["definition_id"]
        _add_node(client, tokens["dev"], owned_id, definition_id, "task_a")
        _publish(client, tokens["dev"], owned_id, definition_id)
        _add_node(client, tokens["dev"], owned_id, definition_id, "task_b", node_type="SHELL")
        _publish(client, tokens["dev"], owned_id, definition_id)

        versions = client.get(
            f"{WORKFLOWS}/{definition_id}/versions", headers=tokens["dev"], params={"project_id": owned_id}
        )
        assert versions.status_code == 200
        items = versions.json()["data"]
        assert [row["version"] for row in items] == [1, 2]
        assert all(row["status"] == "PUBLISHED" for row in items)

        detail = client.get(
            f"{WORKFLOWS}/{definition_id}/versions/2", headers=tokens["dev"], params={"project_id": owned_id}
        )
        assert detail.status_code == 200
        payload = detail.json()["data"]
        assert [n["node_code"] for n in payload["nodes"]] == ["task_a", "task_b"]
        assert payload["publish_record"]["version"] == 2

        missing = client.get(
            f"{WORKFLOWS}/{definition_id}/versions/9", headers=tokens["dev"], params={"project_id": owned_id}
        )
        assert missing.status_code == 404 and missing.json()["code"] == "WF_VERSION_NOT_FOUND"
    finally:
        client.__exit__(None, None, None)


def test_publish_empty_draft_rejected():
    client, app, owned_id, _other_id, tokens = _client()
    try:
        definition_id = _create(client, tokens["dev"], owned_id).json()["data"]["definition_id"]
        rejected = _publish(client, tokens["dev"], owned_id, definition_id)
        assert rejected.status_code == 400 and rejected.json()["code"] == "WF_DRAFT_EMPTY"

        with app.state.session_factory() as session:
            assert session.scalar(select(WorkflowVersionRecord)) is None
            assert session.get(WorkflowDefinitionRecord, definition_id).current_version is None
    finally:
        client.__exit__(None, None, None)


def test_delete_definition_guard():
    client, app, owned_id, _other_id, tokens = _client()
    try:
        # Draft-only definition: deletable.
        draft_only = _create(client, tokens["dev"], owned_id, name="wip-flow").json()["data"]["definition_id"]
        _add_node(client, tokens["dev"], owned_id, draft_only, "task_a")
        deleted = client.post(
            f"{WORKFLOWS}/{draft_only}/delete", headers=tokens["dev"], json={"project_id": owned_id}
        )
        assert deleted.status_code == 200 and deleted.json()["data"]["deleted"] is True
        gone = client.get(f"{WORKFLOWS}/{draft_only}", headers=tokens["dev"], params={"project_id": owned_id})
        assert gone.status_code == 404

        # Published definition: deletion is rejected so formal-run bindings stay resolvable.
        published_id = _create(client, tokens["dev"], owned_id, name="prod-flow").json()["data"]["definition_id"]
        _add_node(client, tokens["dev"], owned_id, published_id, "task_a")
        _publish(client, tokens["dev"], owned_id, published_id)
        rejected = client.post(
            f"{WORKFLOWS}/{published_id}/delete", headers=tokens["dev"], json={"project_id": owned_id}
        )
        assert rejected.status_code == 409 and rejected.json()["code"] == "WF_DEFINITION_HAS_PUBLISHED"
        still_there = client.get(f"{WORKFLOWS}/{published_id}", headers=tokens["dev"], params={"project_id": owned_id})
        assert still_there.status_code == 200
    finally:
        client.__exit__(None, None, None)


def test_auth_permission_and_frame_gates():
    client, app, owned_id, other_id, tokens = _client()
    try:
        definition_id = _create(client, tokens["dev"], owned_id).json()["data"]["definition_id"]
        _add_node(client, tokens["dev"], owned_id, definition_id, "task_a")

        anonymous = _publish(client, {}, owned_id, definition_id)
        assert anonymous.status_code == 401 and anonymous.json()["code"] == 1001

        # Viewer has VIEW_ALL only: reads pass, edits are denied.
        viewer_read = client.get(
            f"{WORKFLOWS}/{definition_id}", headers=tokens["viewer"], params={"project_id": owned_id}
        )
        assert viewer_read.status_code == 200
        viewer_write = _publish(client, tokens["viewer"], owned_id, definition_id)
        assert viewer_write.status_code == 403 and viewer_write.json()["code"] == 1003

        # Non-member dev on a foreign project is denied too.
        foreign = _create(client, tokens["dev"], other_id, name="foreign-flow")
        assert foreign.status_code == 403 and foreign.json()["code"] == 1003

        missing_name = client.post(WORKFLOWS, headers=tokens["dev"], json={"project_id": owned_id})
        assert missing_name.status_code == 400 and missing_name.json()["code"] == 4001

        missing_project = client.get(WORKFLOWS, headers=tokens["dev"])
        assert missing_project.status_code == 400 and missing_project.json()["code"] == 4001
    finally:
        client.__exit__(None, None, None)
