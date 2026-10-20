"""WF-23 execution API tests — design §4.1/§4.2/§13.4.

Covers: execution API compatibility routes and WBS EXEC-04 canonical routes.
"""

from datetime import datetime

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.common.db import Base
from rebuild.execution.models import EXECUTION_TABLES
from rebuild.execution.repository import ExecutionRepository
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.project.models import ProjectRecord
from rebuild.stream.models import StreamCheckpointRecord, StreamJobRecord
from rebuild.workflow.models import WorkflowDefinitionRecord, WorkflowNodeRecord, WorkflowVersionRecord


EXEC = "/api/v1/rebuild/execution"


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="exec-api-test-secret")
    client = TestClient(app)
    client.__enter__()
    # Keep this domain test independent of host-app assembly; EXEC-05 owns the
    # lifespan registration and the integrator verifies that separately.
    Base.metadata.create_all(
        bind=app.state.session_factory.kw["bind"],
        tables=[*EXECUTION_TABLES, StreamJobRecord.__table__, StreamCheckpointRecord.__table__],
    )
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        dev = UserRepository(session).create(username="dev", password="dev-pass", role=Role.DEVELOPER)
        UserRepository(session).create(username="viewer", password="viewer-pass", role=Role.VIEWER)
        project = ProjectRecord(name="exec-proj", description="", owner_id=dev.id)
        session.add(project)
        session.commit()
        project_id = project.id
    tokens = {}
    for username, password in (("admin", "admin-pass"), ("dev", "dev-pass"), ("viewer", "viewer-pass")):
        response = client.post("/api/v1/rebuild/login", json={"username": username, "password": password})
        tokens[username] = {"Authorization": f"Bearer {response.json()['data']['token']}"}
    return client, app, project_id, tokens


def test_create_run_success():
    client, app, project_id, tokens = _client()
    try:
        resp = client.post(
            f"{EXEC}/runs",
            headers=tokens["dev"],
            json={
                "project_id": project_id,
                "workflow_id": 1,
                "workflow_version_id": 1,
                "instance_type": "TRIAL",
                "trigger_type": "TRIAL",
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["instance_type"] == "TRIAL"
        assert data["status"] == "PENDING"
        assert data["trigger_type"] == "TRIAL"
    finally:
        client.__exit__(None, None, None)


def test_get_run_detail():
    client, app, project_id, tokens = _client()
    try:
        created = client.post(
            f"{EXEC}/runs",
            headers=tokens["dev"],
            json={
                "project_id": project_id,
                "workflow_id": 1,
                "workflow_version_id": 1,
                "instance_type": "FORMAL",
            },
        ).json()["data"]

        resp = client.get(
            f"{EXEC}/runs/{created['instance_id']}",
            headers=tokens["dev"],
            params={"project_id": project_id},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["instance_id"] == created["instance_id"]
        assert data["instance_type"] == "FORMAL"
        assert "logs" in data
    finally:
        client.__exit__(None, None, None)


def test_cancel_run():
    client, app, project_id, tokens = _client()
    try:
        created = client.post(
            f"{EXEC}/runs",
            headers=tokens["dev"],
            json={
                "project_id": project_id,
                "workflow_id": 1,
                "workflow_version_id": 1,
                "instance_type": "TRIAL",
            },
        ).json()["data"]

        resp = client.post(
            f"{EXEC}/runs/{created['instance_id']}/cancel",
            headers=tokens["dev"],
            json={"project_id": project_id},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "CANCELLED"
    finally:
        client.__exit__(None, None, None)


def test_auth_and_permission_gates():
    client, app, project_id, tokens = _client()
    try:
        # No token → 401.
        anon = client.post(
            f"{EXEC}/runs",
            json={
                "project_id": project_id,
                "workflow_id": 1,
                "workflow_version_id": 1,
                "instance_type": "TRIAL",
            },
        )
        assert anon.status_code == 401 and anon.json()["code"] == 1001

        # Viewer → 403 on write.
        viewer = client.post(
            f"{EXEC}/runs",
            headers=tokens["viewer"],
            json={
                "project_id": project_id,
                "workflow_id": 1,
                "workflow_version_id": 1,
                "instance_type": "TRIAL",
            },
        )
        assert viewer.status_code == 403 and viewer.json()["code"] == 1003

        # Missing project_id → 400/4001.
        missing = client.post(
            f"{EXEC}/runs",
            headers=tokens["dev"],
            json={"workflow_id": 1, "workflow_version_id": 1, "instance_type": "TRIAL"},
        )
        assert missing.status_code == 400 and missing.json()["code"] == 4001
    finally:
        client.__exit__(None, None, None)


def _add_definition(session, project_id):
    definition = WorkflowDefinitionRecord(project_id=project_id, name="execution-domain-workflow", description="")
    session.add(definition)
    session.flush()
    session.add(
        WorkflowNodeRecord(
            definition_id=definition.id,
            version_id=None,
            node_code="task-1",
            node_type="SQL",
            name="Task 1",
            params_json="{}",
        )
    )
    session.flush()
    return definition


def test_trial_instance_creation_binds_draft_snapshot_and_tasks():
    client, app, project_id, tokens = _client()
    try:
        with app.state.session_factory() as session:
            definition = _add_definition(session, project_id)
            workflow_id = definition.id
            session.commit()

        response = client.post(
            f"{EXEC}/workflow-instances",
            headers=tokens["dev"],
            json={"project_id": project_id, "workflow_id": workflow_id, "instance_type": "TRIAL"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["instance_type"] == "TRIAL"
        assert data["trial_snapshot_id"] > 0
        assert data["workflow_version_id"] == 0
        assert [task["task_id"] for task in data["tasks"]] == ["task-1"]
        assert data["tasks"][0]["current_attempt_no"] == 0
    finally:
        client.__exit__(None, None, None)


def test_formal_instance_requires_published_version_and_lists_attempts():
    client, app, project_id, tokens = _client()
    try:
        with app.state.session_factory() as session:
            definition = _add_definition(session, project_id)
            version = WorkflowVersionRecord(
                definition_id=definition.id,
                version=1,
                status="PUBLISHED",
                remark="",
                snapshot_digest="a" * 64,
                published_at=datetime(2026, 1, 1),
            )
            session.add(version)
            session.flush()
            session.add(
                WorkflowNodeRecord(
                    definition_id=definition.id,
                    version_id=version.id,
                    node_code="task-1",
                    node_type="SQL",
                    name="Task 1",
                    params_json="{}",
                )
            )
            session.flush()
            version_id = version.id
            workflow_id = definition.id
            session.commit()

        rejected = client.post(
            f"{EXEC}/workflow-instances",
            headers=tokens["dev"],
            json={"project_id": project_id, "workflow_id": workflow_id, "instance_type": "FORMAL"},
        )
        assert rejected.status_code == 400 and rejected.json()["code"] == 4001

        created = client.post(
            f"{EXEC}/workflow-instances",
            headers=tokens["dev"],
            json={
                "project_id": project_id,
                "workflow_id": workflow_id,
                "instance_type": "FORMAL",
                "publish_version": version_id,
            },
        )
        assert created.status_code == 200
        data = created.json()["data"]
        assert data["workflow_version_id"] == version_id
        assert len(data["tasks"]) == 1
        instance_id = data["instance_id"]
        task_id = data["tasks"][0]["task_instance_id"]
        with app.state.session_factory() as session:
            attempt = ExecutionRepository(session).append_attempt(task_id)
            attempt_id = attempt.id
            session.commit()

        attempts = client.get(
            f"{EXEC}/workflow-instances/{instance_id}/attempts",
            headers=tokens["dev"],
            params={"project_id": project_id},
        )
        assert attempts.status_code == 200
        assert attempts.json()["data"]["attempts"][0]["attempt_no"] == 1
        log = client.post(
            f"{EXEC}/attempts/{attempt_id}/logs",
            headers=tokens["dev"],
            json={"project_id": project_id, "message": "started", "level": "INFO"},
        )
        output = client.post(
            f"{EXEC}/attempts/{attempt_id}/outputs",
            headers=tokens["dev"],
            json={"project_id": project_id, "output_json": '{"rows":1}'},
        )
        assert log.status_code == 200 and log.json()["data"]["attempt_no"] == 1
        assert output.status_code == 200 and output.json()["data"]["attempt_no"] == 1

        stat_payload = {
            "project_id": project_id,
            "workflow_instance_id": instance_id,
            "task_instance_id": task_id,
            "attempt_no": 1,
            "success_count": 3,
            "failed_count": 1,
            "skipped_count": 0,
        }
        first_stat = client.post(f"{EXEC}/result-stat", headers=tokens["dev"], json=stat_payload)
        duplicate_stat = client.post(f"{EXEC}/result-stat", headers=tokens["dev"], json=stat_payload)
        assert first_stat.status_code == 200 and first_stat.json()["data"]["recorded"] is True
        assert duplicate_stat.status_code == 200 and duplicate_stat.json()["data"]["duplicate"] is True

        detail = client.get(
            f"{EXEC}/workflow-instances/{instance_id}",
            headers=tokens["dev"],
            params={"project_id": project_id},
        )
        assert detail.status_code == 200 and len(detail.json()["data"]["tasks"]) == 1
    finally:
        client.__exit__(None, None, None)


def test_stream_cannot_succeed_and_malformed_transition_is_4001():
    client, app, project_id, tokens = _client()
    try:
        with app.state.session_factory() as session:
            definition = _add_definition(session, project_id)
            workflow_id = definition.id
            session.commit()
        created = client.post(
            f"{EXEC}/workflow-instances",
            headers=tokens["dev"],
            json={"project_id": project_id, "workflow_id": workflow_id, "instance_type": "STREAM"},
        )
        instance_id = created.json()["data"]["instance_id"]
        malformed = client.post(
            f"{EXEC}/workflow-instances/{instance_id}/transition",
            headers=tokens["dev"],
            json={"project_id": project_id, "status": 42},
        )
        assert malformed.status_code == 400 and malformed.json()["code"] == 4001
        client.post(
            f"{EXEC}/workflow-instances/{instance_id}/transition",
            headers=tokens["dev"],
            json={"project_id": project_id, "status": "RUNNING"},
        )
        illegal = client.post(
            f"{EXEC}/workflow-instances/{instance_id}/transition",
            headers=tokens["dev"],
            json={"project_id": project_id, "status": "SUCCEEDED"},
        )
        assert illegal.status_code == 400 and illegal.json()["code"] == 4103
    finally:
        client.__exit__(None, None, None)


def test_stream_checkpoint_delegates_to_stream_domain_protocol():
    client, app, project_id, tokens = _client()
    try:
        with app.state.session_factory() as session:
            definition = _add_definition(session, project_id)
            job = StreamJobRecord(
                name="execution-stream",
                workflow_id=definition.id,
                mq_topic="topic.execution",
                runtime_config="{}",
                state="CREATED",
                attempt_no=0,
            )
            session.add(job)
            session.flush()
            workflow_id = definition.id
            stream_job_id = job.id
            session.commit()

        created = client.post(
            f"{EXEC}/workflow-instances",
            headers=tokens["dev"],
            json={"project_id": project_id, "workflow_id": workflow_id, "instance_type": "STREAM"},
        )
        instance_id = created.json()["data"]["instance_id"]
        response = client.post(
            f"{EXEC}/workflow-instances/{instance_id}/checkpoints",
            headers=tokens["dev"],
            json={
                "project_id": project_id,
                "stream_job_id": stream_job_id,
                "partition_id": "p0",
                "offset_value": 81,
                "payload": {"consumer_group": "cg1"},
                "event_time": "2026-10-19T12:00:00Z",
            },
        )
        assert response.status_code == 200
        assert response.json()["data"]["offset_value"] == 81
        with app.state.session_factory() as session:
            checkpoint = session.query(StreamCheckpointRecord).one()
            assert checkpoint.job_id == stream_job_id and checkpoint.partition_id == "p0"
    finally:
        client.__exit__(None, None, None)
