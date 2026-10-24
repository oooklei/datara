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
                    "project_id": project_id,
                    "environment_group_id": 9,
                    "workflow_id": None,
                    "task_id": None,
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


def test_snapshot_repository_never_persists_a_sensitive_resolved_value() -> None:
    client, app, project_id, headers = _client()
    try:
        from sqlalchemy import select

        from rebuild.variables.models import TaskInstanceVariableRuntimeRecord
        from rebuild.variables.repository import VariableRepository

        with app.state.session_factory() as session:
            VariableRepository(session).write_snapshot_rows([{
                "instance_id": 91,
                "project_id": project_id,
                "attempt_no": 1,
                "expression": "${workflow.password}",
                "scope": "workflow",
                "name": "password",
                "resolved_value": "must-not-persist",
                "value_type": "string",
                "source": "workflow.password",
                "sensitive": True,
            }])
            session.commit()
            row = session.scalar(select(TaskInstanceVariableRuntimeRecord))
            assert row is not None and row.resolved_value == "******"

        response = client.get(
            f"/api/v1/rebuild/variables/run-snapshot?instance_id=91&project_id={project_id}", headers=headers
        )
        assert response.status_code == 200
        assert response.json()["data"][0]["resolved_value"] == "******"
        assert "must-not-persist" not in response.text
    finally:
        client.__exit__(None, None, None)


def test_execution_parameter_bridge_resolves_and_persists_attempt_snapshot() -> None:
    client, app, project_id, _headers = _client()
    try:
        from sqlalchemy import select

        from rebuild.execution.parameter_resolver import resolve_execution_parameters
        from rebuild.variables.models import TaskInstanceVariableRuntimeRecord
        from rebuild.variables.repository import VariableRepository

        with app.state.session_factory() as session:
            VariableRepository(session).upsert(
                scope="workflow",
                project_id=project_id,
                workflow_id=21,
                name="table_name",
                value="orders",
                value_type="string",
                sensitive=False,
                description="",
            )
            payload = resolve_execution_parameters(
                session,
                instance_id=101,
                attempt_no=2,
                context=VariableContext(project_id=project_id, workflow_id=21, task_id="sql-1"),
                parameters={"sql": "select * from ${workflow.table_name}"},
            )
            session.commit()
            assert payload == {"sql": "select * from orders"}
            row = session.scalar(select(TaskInstanceVariableRuntimeRecord))
            assert row is not None
            assert (row.instance_id, row.attempt_no, row.project_id, row.resolved_value) == (101, 2, project_id, "orders")
    finally:
        client.__exit__(None, None, None)
