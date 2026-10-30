"""WF-23 execution API tests — design §4.1/§4.2/§13.4.

Covers: execution API compatibility routes and WBS EXEC-04 canonical routes.
"""

import json
from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from common import queue
from common.models import Base as LegacyBase
from rebuild.api.app import create_app
from rebuild.common.db import Base
from rebuild.execution.models import EXECUTION_TABLES
from rebuild.execution.repository import ExecutionRepository
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.project.models import ProjectRecord
from rebuild.stream.models import StreamCheckpointRecord, StreamJobRecord
from rebuild.workflow.models import (
    WorkflowDefinitionRecord,
    WorkflowEdgeRecord,
    WorkflowNodeRecord,
    WorkflowVersionRecord,
)


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
        with app.state.session_factory() as session:
            workflow_id = _add_definition(session, project_id).id
            session.commit()
        created = client.post(
            f"{EXEC}/runs",
            headers=tokens["dev"],
            json={
                "project_id": project_id,
                "workflow_id": workflow_id,
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


def test_cancel_run_hides_cross_project_instance():
    """Cancellation must never mutate an instance outside the requested project."""
    client, app, project_id, tokens = _client()
    try:
        with app.state.session_factory() as session:
            definition = _add_definition(session, project_id)
            instance = ExecutionRepository(session).create_workflow_instance(
                workflow_id=definition.id, workflow_version_id=1, instance_type="FORMAL"
            )
            instance_id = instance.id
            # A distinct project is enough to exercise the object-scope guard;
            # the admin principal is authorized for both project permissions.
            other = ProjectRecord(name="other-exec-proj", description="", owner_id=1)
            session.add(other)
            session.flush()
            other_id = other.id
            session.commit()
        response = client.post(
            f"{EXEC}/runs/{instance_id}/cancel",
            headers=tokens["admin"],
            json={"project_id": other_id},
        )
        assert response.status_code == 400
        assert response.json()["code"] == 4404
        with app.state.session_factory() as session:
            assert ExecutionRepository(session)._require_workflow_instance(instance_id).status == "PENDING"
    finally:
        client.__exit__(None, None, None)


def test_auth_and_permission_gates():
    client, app, project_id, tokens = _client()
    try:
        # No token → 401.(先清 cookie：中间件会把 datara_session 回退为会话凭证)
        client.cookies.clear()
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


def _stream_channel(tmp_path, monkeypatch):
    """STREAM 实例创建现走真实执行链（2026-10-28 裁决项 3，fail-closed）：
    测试配齐 legacy 通道桩（legacy 表 + 广播 + 日志目录）。"""
    legacy_url = f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}"
    LegacyBase.metadata.create_all(create_engine(legacy_url))
    monkeypatch.setenv("REBUILD_LEGACY_DB_URL", legacy_url)
    stub = SimpleNamespace(publishes=[])

    def _publish(channel_name: str, payload: str) -> None:
        stub.publishes.append((channel_name, json.loads(payload)))

    stub.publish = _publish
    monkeypatch.setattr(queue, "get_client", lambda: stub)
    monkeypatch.setattr(
        "api.streamjob.get_settings", lambda: SimpleNamespace(log_dir=str(tmp_path / "logs"))
    )
    return stub


def _add_stream_definition(session, project_id):
    definition = WorkflowDefinitionRecord(
        project_id=project_id, name="execution-stream-workflow", description="", workflow_type="STREAM"
    )
    session.add(definition)
    session.flush()
    for code, node_type, params in (
        ("si1", "stream_input", {"srcType": "simulate"}),
        ("so1", "stream_output", {}),
    ):
        session.add(
            WorkflowNodeRecord(
                definition_id=definition.id,
                version_id=None,
                node_code=code,
                node_type=node_type,
                name=code,
                params_json=json.dumps(params),
            )
        )
    session.add(
        WorkflowEdgeRecord(definition_id=definition.id, version_id=None, from_node="si1", to_node="so1")
    )
    session.flush()
    return definition


def test_run_statistics_list_and_detail_are_project_scoped():
    client, app, project_id, tokens = _client()
    try:
        with app.state.session_factory() as session:
            definition = _add_definition(session, project_id)
            instance = ExecutionRepository(session).create_workflow_instance(
                workflow_id=definition.id, workflow_version_id=3, instance_type="FORMAL"
            )
            ExecutionRepository(session).record_result_stat(
                workflow_instance_id=instance.id, attempt_no=0,
                source_count=5, target_count=4, success_count=4, failed_count=1, skipped_count=0,
                data_param={"batch": "nightly"},
                reconcile_details=[{
                    "source_object": "ods.orders", "target_object": "dwd.orders",
                    "source_count": 5, "target_count": 4, "success_count": 4,
                    "failure_count": 1, "skipped_count": 0,
                    "data_param": {"partition": "2026-10-24"},
                    "started_at": "2026-10-24T01:00:00Z",
                    "finished_at": "2026-10-24T01:02:00Z",
                }],
            )
            ExecutionRepository(session).transition_workflow_instance(instance.id, "RUNNING")
            ExecutionRepository(session).transition_workflow_instance(instance.id, "FAILED")
            from rebuild.execution.run_stats import RunStatisticsService
            RunStatisticsService(session).finalize(instance.id)
            session.commit()
        listing = client.get(f"{EXEC}/run-stats", headers=tokens["dev"], params={"project_id": project_id})
        assert listing.status_code == 200
        assert listing.json()["data"]["total"] == 1
        item = listing.json()["data"]["items"][0]
        assert (item["source_count"], item["failure_count"]) == (5, 1)
        detail = client.get(
            f"{EXEC}/run-stats/{item['id']}", headers=tokens["dev"], params={"project_id": project_id}
        )
        assert detail.status_code == 200 and detail.json()["data"]["workflow_version_id"] == 3
        payload = detail.json()["data"]["details"][0]
        assert payload["id"] > 0
        assert payload["data_param"] == {"partition": "2026-10-24"}
        assert payload["started_at"] == "2026-10-24T01:00:00"
        assert payload["finished_at"] == "2026-10-24T01:02:00"
        assert payload["created_at"] and payload["updated_at"] and payload["generated_at"]

        invalid_time = client.get(
            f"{EXEC}/run-stats", headers=tokens["dev"],
            params={"project_id": project_id, "started_from": "yesterday"},
        )
        assert invalid_time.status_code == 400
        assert invalid_time.json()["code"] == 4107
    finally:
        client.__exit__(None, None, None)


def test_terminal_stat_failure_is_observable_and_repair_is_scoped_and_idempotent(monkeypatch):
    client, app, project_id, tokens = _client()
    try:
        with app.state.session_factory() as session:
            definition = _add_definition(session, project_id)
            instance = ExecutionRepository(session).create_workflow_instance(
                workflow_id=definition.id, workflow_version_id=3, instance_type="FORMAL"
            )
            instance_id = instance.id
            session.commit()

        running = client.post(
            f"{EXEC}/workflow-instances/{instance_id}/transition",
            headers=tokens["dev"], json={"project_id": project_id, "status": "RUNNING"},
        )
        assert running.status_code == 200

        from rebuild.execution.run_stats import RunStatisticsService

        original_finalize = RunStatisticsService.finalize

        def fail_finalize(self, workflow_instance_id):
            raise RuntimeError("simulated stat storage outage")

        monkeypatch.setattr(RunStatisticsService, "finalize", fail_finalize)
        failed = client.post(
            f"{EXEC}/workflow-instances/{instance_id}/transition",
            headers=tokens["dev"], json={"project_id": project_id, "status": "FAILED"},
        )
        assert failed.status_code == 500
        assert failed.json()["code"] == 5101
        assert failed.json()["data"] == {
            "instance_id": instance_id,
            "status": "FAILED",
            "run_stat_finalized": False,
            "repairable": True,
        }
        with app.state.session_factory() as session:
            assert ExecutionRepository(session)._require_workflow_instance(instance_id).status == "FAILED"

        monkeypatch.setattr(RunStatisticsService, "finalize", original_finalize)
        viewer = client.post(
            f"{EXEC}/workflow-instances/{instance_id}/run-stat/finalize",
            headers=tokens["viewer"], json={"project_id": project_id},
        )
        assert viewer.status_code == 403
        wrong_project = client.post(
            f"{EXEC}/workflow-instances/{instance_id}/run-stat/finalize",
            headers=tokens["admin"], json={"project_id": project_id + 1},
        )
        assert wrong_project.status_code in {403, 404}

        first = client.post(
            f"{EXEC}/workflow-instances/{instance_id}/run-stat/finalize",
            headers=tokens["dev"], json={"project_id": project_id},
        )
        second = client.post(
            f"{EXEC}/workflow-instances/{instance_id}/run-stat/finalize",
            headers=tokens["dev"], json={"project_id": project_id},
        )
        assert first.status_code == second.status_code == 200
        assert first.json()["data"]["id"] == second.json()["data"]["id"]
        assert second.json()["data"]["status"] == "FAILED"
    finally:
        client.__exit__(None, None, None)


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


def test_stream_cannot_succeed_and_malformed_transition_is_4001(tmp_path, monkeypatch):
    _stream_channel(tmp_path, monkeypatch)
    client, app, project_id, tokens = _client()
    try:
        with app.state.session_factory() as session:
            definition = _add_stream_definition(session, project_id)
            workflow_id = definition.id
            session.commit()
        created = client.post(
            f"{EXEC}/workflow-instances",
            headers=tokens["dev"],
            json={"project_id": project_id, "workflow_id": workflow_id, "instance_type": "STREAM"},
        )
        assert created.status_code == 200, created.text
        # 裁决项 3：创建即走执行链——返回面携带流任务关联信息
        assert created.json()["data"]["stream"]["mq_topic"] == f"datara.stream.{workflow_id}"
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


def test_stream_checkpoint_delegates_to_stream_domain_protocol(tmp_path, monkeypatch):
    _stream_channel(tmp_path, monkeypatch)
    client, app, project_id, tokens = _client()
    try:
        with app.state.session_factory() as session:
            definition = _add_stream_definition(session, project_id)
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
