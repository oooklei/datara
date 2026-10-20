from contextlib import contextmanager

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.resources.models import ResourceRecord
from rebuild.workflow.models import WorkflowDefinitionRecord


@contextmanager
def owner_client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="project-crud-secret")
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="owner", password="password", role=Role.DEVELOPER)
            session.commit()
        token = client.post("/api/v1/rebuild/login", json={"username": "owner", "password": "password"}).json()["data"]["token"]
        yield client, {"Authorization": f"Bearer {token}"}


def create_project(client, headers, name="project"):
    return client.post("/api/v1/rebuild/projects", headers=headers, json={"name": name, "description": "before"}).json()["data"]["id"]


def test_owner_can_update_project_name_and_description():
    with owner_client() as (client, headers):
        project_id = create_project(client, headers)
        response = client.put(f"/api/v1/rebuild/projects/{project_id}", headers=headers, json={"name": "renamed", "description": "after"})
    assert response.status_code == 200
    assert response.json()["data"] == {"id": project_id, "name": "renamed", "description": "after"}


def test_empty_project_can_be_deleted():
    with owner_client() as (client, headers):
        project_id = create_project(client, headers)
        response = client.delete(f"/api/v1/rebuild/projects/{project_id}", headers=headers)
        missing = client.put(f"/api/v1/rebuild/projects/{project_id}", headers=headers, json={"name": "x"})
    assert response.status_code == 200
    assert response.json()["data"] == {"deleted": True, "id": project_id}
    assert missing.status_code == 404


def test_non_empty_project_delete_returns_frozen_409_counts():
    with owner_client() as (client, headers):
        project_id = create_project(client, headers)
        created = client.post(f"/api/v1/rebuild/projects/{project_id}/datasources", headers=headers, json={"name": "source", "kind": "mysql", "host": "localhost", "port": 3306, "database": "db", "username": "user"})
        assert created.status_code == 201
        response = client.delete(f"/api/v1/rebuild/projects/{project_id}", headers=headers)
    assert response.status_code == 409
    assert response.json() == {"code": 4091, "msg": "project not empty", "data": {"workflows": 0, "datasources": 1, "resources": 0}}


def test_delete_reports_all_three_dependency_counts():
    with owner_client() as (client, headers):
        project_id = create_project(client, headers)
        client.post(f"/api/v1/rebuild/projects/{project_id}/datasources", headers=headers, json={"name": "source", "kind": "mysql", "host": "localhost", "port": 3306, "database": "db", "username": "user"})
        with client.app.state.session_factory() as session:
            session.add(WorkflowDefinitionRecord(project_id=project_id, name="workflow"))
            session.add(ResourceRecord(project_id=project_id, name="script.py", kind="python"))
            session.commit()
        response = client.delete(f"/api/v1/rebuild/projects/{project_id}", headers=headers)
    assert response.status_code == 409
    assert response.json()["data"] == {"workflows": 1, "datasources": 1, "resources": 1}


def test_project_mutations_require_authentication():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="project-crud-secret")
    with TestClient(app) as client:
        assert client.put("/api/v1/rebuild/projects/1", json={"name": "x"}).status_code == 401
        assert client.delete("/api/v1/rebuild/projects/1").status_code == 401
