"""Target-completion contract for variable management and runtime resolution."""

from __future__ import annotations

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.project.models import ProjectRecord
from rebuild.variables.service import ResolvedVariable, VariableContext, VariableResolver


def _client() -> tuple[TestClient, object, int, dict[str, str]]:
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="variables-completion-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        user = UserRepository(session).create(username="owner", password="owner-pass", role=Role.DEVELOPER)
        project = ProjectRecord(name="variables-project", description="", owner_id=user.id)
        session.add(project)
        session.commit()
        project_id = project.id
    login = client.post("/api/v1/rebuild/login", json={"username": "owner", "password": "owner-pass"})
    return client, app, project_id, {"token": login.json()["data"]["token"]}


def test_effective_resolution_uses_node_workflow_environment_global_priority() -> None:
    definitions = {
        "global": [ResolvedVariable("region", "global", "global", "string")],
        "env:7:3": [ResolvedVariable("region", "env", "environment", "string")],
        "workflow:7:11": [ResolvedVariable("region", "workflow", "workflow", "string")],
        "task:7:node-a": [ResolvedVariable("region", "task", "node", "string")],
    }
    resolver = VariableResolver(lambda owner: definitions.get(owner, []))
    context = VariableContext(project_id=7, environment_group_id=3, workflow_id=11, task_id="node-a")

    assert resolver.resolve_effective_name("region", context).value == "node"
    assert resolver.catalog(context)[0].scope == "task"

    context_without_node = VariableContext(project_id=7, environment_group_id=3, workflow_id=11)
    assert resolver.resolve_effective_name("region", context_without_node).value == "workflow"
    context_without_workflow = VariableContext(project_id=7, environment_group_id=3)
    assert resolver.resolve_effective_name("region", context_without_workflow).value == "environment"


def test_environment_group_crud_masks_secret_and_supports_delete() -> None:
    client, _app, project_id, headers = _client()
    try:
        saved = client.post(
            f"/api/v1/rebuild/variables?project_id={project_id}",
            headers=headers,
            json={
                "scope": "env",
                "environment_group_id": 9,
                "name": "db_password",
                "value_type": "string",
                "value": "do-not-leak",
                "sensitive": True,
            },
        )
        assert saved.status_code == 200, saved.text

        listed = client.get(
            f"/api/v1/rebuild/variables?project_id={project_id}&scopes=env&environment_group_id=9",
            headers=headers,
        )
        assert listed.status_code == 200
        assert listed.json()["data"] == [
            {
                "scope": "env",
                "name": "db_password",
                "value_type": "string",
                "value": "******",
                "description": "",
                "sensitive": True,
                "default_value": None,
                "nullable": True,
                "format": None,
                "timezone": None,
                "business_calendar": None,
            }
        ]
        assert "do-not-leak" not in listed.text

        deleted = client.delete(
            f"/api/v1/rebuild/variables/db_password?project_id={project_id}&scope=env&environment_group_id=9",
            headers=headers,
        )
        assert deleted.status_code == 200
        assert deleted.json()["data"] == {"deleted": True, "scope": "env", "name": "db_password"}
        assert client.get(
            f"/api/v1/rebuild/variables?project_id={project_id}&scopes=env&environment_group_id=9",
            headers=headers,
        ).json()["data"] == []
    finally:
        client.__exit__(None, None, None)


def test_runtime_parameter_resolution_returns_snapshot_without_resolved_secret() -> None:
    definitions = {
        "workflow:7:11": [
            ResolvedVariable("table", "workflow", "orders", "string"),
            ResolvedVariable("password", "workflow", "secret-value", "string", sensitive=True),
        ]
    }
    resolver = VariableResolver(lambda owner: definitions.get(owner, []))
    context = VariableContext(project_id=7, workflow_id=11, task_id="node-a")

    resolved, snapshot = resolver.resolve_parameters(
        {"sql": "select * from ${workflow.table}", "password": "${workflow.password}"}, context
    )

    assert resolved == {"sql": "select * from orders", "password": "secret-value"}
    assert snapshot[0]["resolved_value"] == "orders"
    secret_row = next(row for row in snapshot if row["name"] == "password")
    assert secret_row["resolved_value"] == "******"
    assert "secret-value" not in repr(snapshot)
