"""T69 DEP-07~12 six-node-type end-to-end tests (host-testable subset).

DEP-07/10/11/12 local coverage through the real FastAPI app:
- SQL node: FORMAL lifecycle wired to the real ProductionSqlExecutionPort
  (DEP-08/DEP-09 blockers: no docker / target datasource unreachable on this
  host, so the engine registry is a seam mock while the port, read-only
  preflight and result snapshot are real).
- PYTHON/SHELL nodes: FORMAL state machine over a 5-node pipeline (per-node
  executors land in a later increment; the lifecycle contract is what T69
  verifies here).
- SYNC node: real execute_sync_attempt bridge persisting metrics, result stat,
  stat segments and field lineage.
- DEPENDENCY node: evaluate verdict without metrics history → pending.
- STREAM: instance + job eight-state machine + checkpoint roundtrip.
- DEP-12: cancel guard, failure isolation, redispatch via a fresh task
  instance, and monotonic attempt numbering.

DEP-07 real Sync/Stream runtime drivers and DEP-12 crash-point / duplicate /
out-of-order MQ scenarios require a docker+MQ host (disclosed in the T69
evidence report).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.api.app import create_app
from rebuild.datasource.models import ProjectDatasourceRecord
from rebuild.execution.models import ExecutionEventRecord, TaskAttemptRecord
from rebuild.execution.repository import ExecutionDomainError, ExecutionRepository
from rebuild.execution.sync_executor import execute_sync_attempt
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.metrics.models import (
    LineageWritebackRecord,
    TaskDataStatSegmentRecord,
    TaskInstanceDataStatRecord,
    WorkflowResultStatRecord,
)
from rebuild.project.models import ProjectRecord
from rebuild.sql_ide.execution import build_execution_port
from rebuild.sync.executor import SyncBatchWriteResult, SyncExecutionSpec
from rebuild.variables.models import VariableDefinitionRecord
from rebuild.workflow.models import WorkflowVersionRecord

EXECUTION = "/api/v1/rebuild/execution"
WORKFLOWS = "/api/v1/rebuild/workflows"
STREAM = "/api/v1/rebuild/stream"
DEPENDENCY = "/api/v1/rebuild/dependency"
VARIABLES = "/api/v1/rebuild/variables"


# ---------------------------------------------------------------------------
# shared fixtures / helpers
# ---------------------------------------------------------------------------


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="e2e-test-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        dev = UserRepository(session).create(username="dev", password="dev-pass", role=Role.DEVELOPER)
        project = ProjectRecord(name="t69-proj", description="", owner_id=dev.id)
        session.add(project)
        session.commit()
        project_id = project.id
    response = client.post("/api/v1/rebuild/login", json={"username": "dev", "password": "dev-pass"})
    headers = {"Authorization": f"Bearer {response.json()['data']['token']}"}
    return client, app, project_id, headers


def _create_definition(client, headers, project_id, name):
    response = client.post(WORKFLOWS, headers=headers, json={"project_id": project_id, "name": name})
    assert response.status_code == 200, response.text
    return response.json()["data"]["definition_id"]


def _add_node(client, headers, project_id, definition_id, node_code, node_type="SQL", params=None):
    body = {"project_id": project_id, "node_code": node_code, "node_type": node_type}
    if params is not None:
        body["params"] = params
    response = client.post(f"{WORKFLOWS}/{definition_id}/nodes", headers=headers, json=body)
    assert response.status_code == 200, response.text


def _publish(client, headers, project_id, definition_id):
    response = client.post(
        f"{WORKFLOWS}/{definition_id}/publish", headers=headers, json={"project_id": project_id}
    )
    assert response.status_code == 200, response.text


def _published_version_id(app, definition_id):
    with app.state.session_factory() as session:
        row = session.scalar(
            select(WorkflowVersionRecord).where(
                WorkflowVersionRecord.definition_id == definition_id,
                WorkflowVersionRecord.status == "PUBLISHED",
            )
        )
        assert row is not None
        return row.id


def _create_formal_instance(client, headers, project_id, definition_id, version_id):
    response = client.post(
        f"{EXECUTION}/workflow-instances",
        headers=headers,
        json={
            "project_id": project_id,
            "workflow_id": definition_id,
            "instance_type": "FORMAL",
            "workflow_version_id": version_id,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _transition(client, headers, project_id, instance_id, status):
    response = client.post(
        f"{EXECUTION}/workflow-instances/{instance_id}/transition",
        headers=headers,
        json={"project_id": project_id, "status": status},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _instance_detail(client, headers, project_id, instance_id):
    response = client.get(
        f"{EXECUTION}/workflow-instances/{instance_id}", headers=headers, params={"project_id": project_id}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


class FakeDriver:
    """SYNC driver seam (mirrors test_execution_sync_bridge.py)."""

    def __init__(self, *, fail_write: bool = False):
        self.fail_write = fail_write
        self.written: list[dict[str, object]] = []

    def read_rows(self, spec: SyncExecutionSpec, *, batch_size: int):
        assert batch_size == 2
        yield {"id": 1, "name": "Ada", "active": True}
        yield {"id": 2, "name": "Lin", "active": False}

    def include_row(self, condition: str, row: dict[str, object]) -> bool:
        return bool(row["active"])

    def transform_value(self, expression: str, row: dict[str, object]) -> object:
        assert expression == "upper(name)"
        return str(row["name"]).upper()

    def write_batch(self, spec: SyncExecutionSpec, rows) -> SyncBatchWriteResult:
        if self.fail_write:
            raise RuntimeError("simulated datasource write failure")
        self.written.extend(rows)
        return SyncBatchWriteResult(inserted=len(rows), success=len(rows))


def _sync_snapshot(project_id, workflow_id, workflow_version, task_id="sync_users"):
    return {
        "project_id": project_id,
        "workflow_id": workflow_id,
        "workflow_version": workflow_version,
        "task_id": task_id,
        "source": {"datasource_id": 4, "schema": "src", "object": "users"},
        "target": {"datasource_id": 5, "schema": "dw", "object": "users"},
        "mappings": [
            {
                "source_column": "id", "target_column": "user_id", "source_type": "int", "target_type": "int",
                "transform_expression": "", "nullable": False, "default_value": None, "mapping_status": "AUTO",
            },
            {
                "source_column": "name", "target_column": "display_name", "source_type": "text",
                "target_type": "text",
                "transform_expression": "upper(name)", "nullable": True,
                "default_value": None, "mapping_status": "ADJUSTED",
            },
        ],
        "transform_config": {"filter_condition": "active = true"},
        "target_properties": {"batch_concurrency": {"batch_size": 2, "concurrency": 1}},
    }


def _readonly_connection(columns, rows):
    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value = cursor
    cursor.description = [(column,) for column in columns]
    cursor.fetchall.return_value = [tuple(row) for row in rows]
    return connection


class FakeEngineRegistry:
    def __init__(self, connection):
        self._connection = connection
        self.calls: list[tuple[int, int, object]] = []

    def connect(self, project_id, datasource_id, draft):
        self.calls.append((project_id, datasource_id, draft))
        return self._connection


# ---------------------------------------------------------------------------
# test 1 — SQL node: FORMAL lifecycle + real execution port (DEP-08/09 seam)
# ---------------------------------------------------------------------------


def test_sql_node_formal_lifecycle_with_real_execution_port():
    client, app, project_id, headers = _client()
    try:
        definition_id = _create_definition(client, headers, project_id, "sql-e2e")
        _add_node(client, headers, project_id, definition_id, "start", node_type="START")
        _add_node(
            client, headers, project_id, definition_id, "sql_extract",
            params={"sql": "SELECT id, name FROM users"},
        )
        _add_node(client, headers, project_id, definition_id, "end", node_type="END")
        _publish(client, headers, project_id, definition_id)
        version_id = _published_version_id(app, definition_id)

        data = _create_formal_instance(client, headers, project_id, definition_id, version_id)
        instance_id = data["instance_id"]
        assert data["status"] == "PENDING"
        assert {task["task_id"] for task in data["tasks"]} == {"start", "sql_extract", "end"}
        assert all(task["status"] == "PENDING" for task in data["tasks"])
        assert all(task["current_attempt_no"] == 0 for task in data["tasks"])

        # Real port over the app session_factory; only the engine registry is a
        # seam (docker + reachable target datasource are DEP-08/09 blockers).
        with app.state.session_factory() as session:
            ds = ProjectDatasourceRecord(
                project_id=project_id, name="dw-mirror", kind="postgresql",
                host="127.0.0.1", port=5432, database_name="dw",
                username="etl", password="",
            )
            session.add(ds)
            session.commit()
            datasource_id = ds.id

        connection = _readonly_connection(["id", "name"], [[1, "Ada"], [2, "Lin"]])
        registry = FakeEngineRegistry(connection)
        port = build_execution_port(session_factory=app.state.session_factory, engine_registry=registry)
        result = port.execute(
            project_id=project_id,
            datasource_id=datasource_id,
            sql="SELECT id, name FROM users",
            row_limit=200,
            timeout_ms=30000,
        )
        assert result["columns"] == ["id", "name"]
        assert result["rows"] == [[1, "Ada"], [2, "Lin"]]
        assert result["row_count"] == 2
        assert result["truncated"] is False
        assert isinstance(result["execution_id"], str) and result["execution_id"]
        # The port opened exactly one connection carrying the real draft.
        assert len(registry.calls) == 1
        assert registry.calls[0][0] == project_id and registry.calls[0][1] == datasource_id

        _transition(client, headers, project_id, instance_id, "RUNNING")
        detail = _instance_detail(client, headers, project_id, instance_id)
        assert detail["status"] == "RUNNING"
        _transition(client, headers, project_id, instance_id, "SUCCEEDED")
        detail = _instance_detail(client, headers, project_id, instance_id)
        assert detail["status"] == "SUCCEEDED"
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# test 2 — PYTHON + SHELL nodes: 5-node FORMAL state machine
# ---------------------------------------------------------------------------


def test_python_shell_pipeline_formal_state_machine():
    client, app, project_id, headers = _client()
    try:
        definition_id = _create_definition(client, headers, project_id, "py-sh-e2e")
        _add_node(client, headers, project_id, definition_id, "start", node_type="START")
        _add_node(client, headers, project_id, definition_id, "extract", params={"sql": "SELECT * FROM orders"})
        _add_node(
            client, headers, project_id, definition_id, "transform",
            node_type="PYTHON", params={"script": "etl.py"},
        )
        _add_node(
            client, headers, project_id, definition_id, "load",
            node_type="SHELL", params={"command": "sh load.sh"},
        )
        _add_node(client, headers, project_id, definition_id, "end", node_type="END")
        _publish(client, headers, project_id, definition_id)
        version_id = _published_version_id(app, definition_id)

        data = _create_formal_instance(client, headers, project_id, definition_id, version_id)
        instance_id = data["instance_id"]
        # FORMAL task set spans every node of the published version (5 nodes).
        assert len(data["tasks"]) == 5
        assert {task["task_id"] for task in data["tasks"]} == {
            "start", "extract", "transform", "load", "end",
        }
        assert all(task["status"] == "PENDING" for task in data["tasks"])

        # PENDING → RUNNING → SUCCEEDED across the full node set. Per-node
        # PYTHON/SHELL executors are not landed yet (pre-study risk §5.3); the
        # lifecycle contract is what this test freezes.
        _transition(client, headers, project_id, instance_id, "RUNNING")
        detail = _instance_detail(client, headers, project_id, instance_id)
        assert detail["status"] == "RUNNING"
        assert all(task["status"] == "PENDING" for task in detail["tasks"])

        _transition(client, headers, project_id, instance_id, "SUCCEEDED")
        detail = _instance_detail(client, headers, project_id, instance_id)
        assert detail["status"] == "SUCCEEDED"
        assert len(detail["tasks"]) == 5
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# test 3 — SYNC node: real bridge persists metrics / stat / lineage
# ---------------------------------------------------------------------------


def test_sync_node_bridge_persists_metrics_stats_and_lineage():
    client, app, project_id, headers = _client()
    try:
        definition_id = _create_definition(client, headers, project_id, "sync-e2e")
        _add_node(client, headers, project_id, definition_id, "start", node_type="START")
        _add_node(client, headers, project_id, definition_id, "sync_users", node_type="SYNC")
        _add_node(client, headers, project_id, definition_id, "end", node_type="END")
        _publish(client, headers, project_id, definition_id)
        version_id = _published_version_id(app, definition_id)

        data = _create_formal_instance(client, headers, project_id, definition_id, version_id)
        instance_id = data["instance_id"]
        sync_task = next(task for task in data["tasks"] if task["task_id"] == "sync_users")

        _transition(client, headers, project_id, instance_id, "RUNNING")

        driver = FakeDriver()
        with app.state.session_factory() as session:
            metrics = execute_sync_attempt(
                session,
                _sync_snapshot(project_id, definition_id, version_id),
                workflow_instance_id=instance_id,
                task_instance_id=sync_task["task_instance_id"],
                driver=driver,
            )
            session.commit()  # caller owns the transaction

        assert metrics.as_dict() == {
            "read_rows": 2, "write_rows": 1, "inserted": 1, "updated": 0,
            "success": 1, "failed": 0, "skipped": 0, "filtered": 1,
        }
        assert driver.written == [{"user_id": 1, "display_name": "ADA"}]

        with app.state.session_factory() as session:
            attempt = session.scalar(
                select(TaskAttemptRecord).where(
                    TaskAttemptRecord.task_instance_id == sync_task["task_instance_id"]
                )
            )
            assert attempt is not None and attempt.attempt_no == 1 and attempt.status == "SUCCEEDED"

            result_stat = session.scalar(select(WorkflowResultStatRecord))
            assert result_stat is not None
            assert (result_stat.success_count, result_stat.failure_count, result_stat.skipped_count) == (1, 0, 0)

            task_stat = session.scalar(select(TaskInstanceDataStatRecord))
            assert task_stat is not None and task_stat.rows_in == '{"estimated": false, "known": true, "value": 2}'
            segments = list(session.scalars(select(TaskDataStatSegmentRecord)).all())
            assert len(segments) == 8
            assert {row.segment_key.rsplit(".", 1)[-1] for row in segments} == {
                "read_rows", "write_rows", "inserted", "updated",
                "success", "failed", "skipped", "filtered",
            }

            (lineage,) = session.scalars(select(LineageWritebackRecord)).all()
            assert (lineage.run_kind, lineage.source_entity, lineage.target_entity) == (
                "sync", "4:src.users", "5:dw.users"
            )
            detail_event = session.scalar(
                select(ExecutionEventRecord).where(ExecutionEventRecord.event_kind == "SYNC_FIELD_LINEAGE")
            )
            assert detail_event is not None
            assert '[["id", "user_id"], ["name", "display_name"]]' in detail_event.payload_json

        # The API view confirms the task landed SUCCEEDED.
        detail = _instance_detail(client, headers, project_id, instance_id)
        statuses = {task["task_id"]: task["status"] for task in detail["tasks"]}
        assert statuses["sync_users"] == "SUCCEEDED"
        # Instance itself stays RUNNING until the orchestrator closes it.
        assert detail["status"] == "RUNNING"
        _transition(client, headers, project_id, instance_id, "SUCCEEDED")
        assert _instance_detail(client, headers, project_id, instance_id)["status"] == "SUCCEEDED"
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# test 4 — DEPENDENCY node: evaluate without history → pending
# ---------------------------------------------------------------------------


def test_dependency_node_evaluate_reports_pending_without_history():
    client, app, project_id, headers = _client()
    try:
        definition_id = _create_definition(client, headers, project_id, "dep-e2e")
        _add_node(client, headers, project_id, definition_id, "start", node_type="START")
        _add_node(client, headers, project_id, definition_id, "check_upstream", node_type="DEPENDENCY")
        _add_node(client, headers, project_id, definition_id, "end", node_type="END")
        _publish(client, headers, project_id, definition_id)
        version_id = _published_version_id(app, definition_id)

        response = client.post(
            f"{DEPENDENCY}/evaluate",
            headers=headers,
            json={
                "project_id": project_id,
                "workflow_id": definition_id,
                "workflow_version": version_id,
                "task_id": "check_upstream",
                "groups": [
                    {
                        "conditions": [
                            {
                                "upstream_workflow_id": definition_id,
                                "cycle": "day",
                                "date_value": "today",
                            }
                        ]
                    }
                ],
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        # No metrics history + as_of inside the window → honest pending verdict.
        assert data["verdict"] == "pending"
        # resolved is a per-condition list, one entry per evaluated condition.
        assert data["resolved"] == [
            {
                "upstream_workflow_id": definition_id,
                "verdict": "pending",
                "window_start": data["resolved"][0]["window_start"],
                "window_end": data["resolved"][0]["window_end"],
            }
        ]
        assert data["expression"]
        assert data["evaluated_at"]
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# test 5 — STREAM instance + job lifecycle + checkpoint roundtrip
# ---------------------------------------------------------------------------


def test_stream_instance_job_lifecycle_and_checkpoint_roundtrip():
    client, app, project_id, headers = _client()
    try:
        definition_id = _create_definition(client, headers, project_id, "stream-e2e")
        _add_node(client, headers, project_id, definition_id, "start", node_type="START")
        _add_node(client, headers, project_id, definition_id, "end", node_type="END")
        _publish(client, headers, project_id, definition_id)

        # STREAM instance: no published version binding, no tasks.
        response = client.post(
            f"{EXECUTION}/workflow-instances",
            headers=headers,
            json={"project_id": project_id, "workflow_id": definition_id, "instance_type": "STREAM"},
        )
        assert response.status_code == 200, response.text
        instance = response.json()["data"]
        instance_id = instance["instance_id"]
        assert instance["workflow_version_id"] == 0
        assert instance["tasks"] == []

        _transition(client, headers, project_id, instance_id, "RUNNING")

        # Job registration → eight-state machine walk.
        response = client.post(
            f"{STREAM}/jobs",
            headers=headers,
            json={
                "name": "stream-e2e",
                "workflow_id": definition_id,
                "mq_topic": "topic.e2e",
                "runtime_config": {"mode": "fixed_rate", "rows_per_sec": 10, "columns": ["id", "name"]},
            },
        )
        assert response.status_code == 200, response.text
        job = response.json()["data"]
        job_id = job["id"]
        assert job["state"] == "CREATED"

        for action, expected in [
            ("start", "STARTING"),
            ("activate", "RUNNING"),
            ("pause", "PAUSED"),
            ("resume", "RUNNING"),
            ("stop", "STOPPING"),
            ("complete_stop", "STOPPED"),
        ]:
            response = client.post(
                f"{STREAM}/jobs/{job_id}/transitions", headers=headers, json={"action": action}
            )
            assert response.status_code == 200, response.text
            assert response.json()["data"]["state"] == expected

        # Checkpoint write through the execution API, read back through stream.
        response = client.post(
            f"{EXECUTION}/workflow-instances/{instance_id}/checkpoints",
            headers=headers,
            json={
                "project_id": project_id,
                "stream_job_id": job_id,
                "partition_id": "p-0",
                "offset_value": 42,
                "event_time": "2026-10-20T08:00:00Z",
                "payload": {"rows": 42},
            },
        )
        assert response.status_code == 200, response.text
        response = client.get(f"{STREAM}/jobs/{job_id}/checkpoints", headers=headers)
        assert response.status_code == 200, response.text
        checkpoints = response.json()["data"]
        assert len(checkpoints) == 1
        assert checkpoints[0]["job_id"] == job_id
        assert checkpoints[0]["partition_id"] == "p-0"
        assert checkpoints[0]["offset_value"] == 42
        assert checkpoints[0]["payload"] == {"rows": 42}
        assert checkpoints[0]["event_time"]

        # Close the stream instance.
        _transition(client, headers, project_id, instance_id, "STOPPED")
        assert _instance_detail(client, headers, project_id, instance_id)["status"] == "STOPPED"
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# test 6 — DEP-12: cancel guard, failure isolation, redispatch, attempt isolation
# ---------------------------------------------------------------------------


def test_dep12_cancel_failure_guard_redispatch_and_attempt_isolation():
    client, app, project_id, headers = _client()

    # (a) cancel guard: PENDING FORMAL instance → CANCELLED via /runs/{id}/cancel.
    definition_id = _create_definition(client, headers, project_id, "cancel-e2e")
    _add_node(client, headers, project_id, definition_id, "start", node_type="START")
    _add_node(client, headers, project_id, definition_id, "end", node_type="END")
    _publish(client, headers, project_id, definition_id)
    version_id = _published_version_id(app, definition_id)
    cancel_data = _create_formal_instance(client, headers, project_id, definition_id, version_id)
    response = client.post(
        f"{EXECUTION}/runs/{cancel_data['instance_id']}/cancel", headers=headers, json={"project_id": project_id}
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "instance_id": cancel_data["instance_id"], "status": "CANCELLED",
    }

    # (b) sync failure → FAILED attempt/task, then guard + redispatch.
    sync_definition = _create_definition(client, headers, project_id, "retry-e2e")
    _add_node(client, headers, project_id, sync_definition, "start", node_type="START")
    _add_node(client, headers, project_id, sync_definition, "sync_users", node_type="SYNC")
    _add_node(client, headers, project_id, sync_definition, "end", node_type="END")
    _publish(client, headers, project_id, sync_definition)
    sync_version = _published_version_id(app, sync_definition)
    sync_data = _create_formal_instance(client, headers, project_id, sync_definition, sync_version)
    sync_instance = sync_data["instance_id"]
    sync_task = next(task for task in sync_data["tasks"] if task["task_id"] == "sync_users")
    _transition(client, headers, project_id, sync_instance, "RUNNING")

    with app.state.session_factory() as session:
        with pytest.raises(RuntimeError, match="simulated datasource write failure"):
            execute_sync_attempt(
                session,
                _sync_snapshot(project_id, sync_definition, sync_version),
                workflow_instance_id=sync_instance,
                task_instance_id=sync_task["task_instance_id"],
                driver=FakeDriver(fail_write=True),
            )
        session.commit()

        attempt = session.scalar(
            select(TaskAttemptRecord).where(
                TaskAttemptRecord.task_instance_id == sync_task["task_instance_id"]
            )
        )
        assert attempt is not None and attempt.status == "FAILED"
        assert session.scalar(select(WorkflowResultStatRecord)) is None

        # Guard: a FAILED task cannot rerun in place (4103).
        with pytest.raises(ExecutionDomainError) as guard:
            execute_sync_attempt(
                session,
                _sync_snapshot(project_id, sync_definition, sync_version),
                workflow_instance_id=sync_instance,
                task_instance_id=sync_task["task_instance_id"],
                driver=FakeDriver(),
            )
        assert guard.value.code == 4103

        # Orchestrator redispatch: a fresh PENDING task on the same instance.
        # The (workflow_instance_id, task_id) UNIQUE constraint forces a new
        # task_id for the redispatched node run.
        repo = ExecutionRepository(session)
        retry_task = repo.create_task_instance(
            workflow_instance_id=sync_instance, task_id="sync_users_r2"
        )
        metrics = execute_sync_attempt(
            session,
            _sync_snapshot(project_id, sync_definition, sync_version, task_id="sync_users_r2"),
            workflow_instance_id=sync_instance,
            task_instance_id=retry_task.id,
            driver=FakeDriver(),
        )
        assert metrics.as_dict()["write_rows"] == 1
        # Attempt numbering stays monotonic per task (retry task now at 1).
        manual = repo.append_attempt(retry_task.id)
        assert manual.attempt_no == 2
        session.commit()

        retry_task_id = retry_task.id

    response = client.get(
        f"{EXECUTION}/workflow-instances/{sync_instance}/attempts",
        headers=headers,
        params={"project_id": project_id, "task_instance_id": retry_task_id},
    )
    assert response.status_code == 200, response.text
    attempts = response.json()["data"]["attempts"]
    assert [item["attempt_no"] for item in attempts] == [1, 2]
    assert attempts[0]["status"] == "SUCCEEDED"

    # Failed first task keeps its isolated FAILED attempt.
    response = client.get(
        f"{EXECUTION}/workflow-instances/{sync_instance}/attempts",
        headers=headers,
        params={"project_id": project_id, "task_instance_id": sync_task["task_instance_id"]},
    )
    assert response.status_code == 200, response.text
    failed_attempts = response.json()["data"]["attempts"]
    assert [item["attempt_no"] for item in failed_attempts] == [1]
    assert failed_attempts[0]["status"] == "FAILED"
    client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# test 7 — DEP-11: variable reference five diagnostic codes end-to-end
# ---------------------------------------------------------------------------


def _save_variable(client, headers, project_id, name, value, value_type="string"):
    response = client.post(
        VARIABLES,
        headers=headers,
        params={"project_id": project_id},
        json={"scope": "project", "name": name, "value_type": value_type, "value": value},
    )
    assert response.status_code == 200, response.text


def _check_reference(client, headers, project_id, expression):
    response = client.post(
        f"{VARIABLES}/check-reference",
        headers=headers,
        json={"expression": expression, "context": {"project_id": project_id}},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_dep11_variable_reference_five_diagnostic_codes():
    client, app, project_id, headers = _client()
    try:
        _save_variable(client, headers, project_id, "alpha", "hello")
        _save_variable(client, headers, project_id, "loop_a", "${project.loop_b}")
        _save_variable(client, headers, project_id, "loop_b", "${project.loop_a}")
        # TYPE_MISMATCH fixture cannot go through the API: upsert runs
        # validate_definition (type check) and would 400 the value. Insert the
        # inconsistent row directly, matching the repository owner_key rule.
        with app.state.session_factory() as session:
            session.add(
                VariableDefinitionRecord(
                    scope="project", project_id=project_id, owner_key=f"project:{project_id}",
                    name="bad_int", value_type="integer", value_json="abc",
                    sensitive=False, description="",
                )
            )
            session.commit()

        # A braced fragment that is not a well-formed ${scope.name} ref.
        syntax = _check_reference(client, headers, project_id, "${bad syntax}")
        assert syntax["valid"] is False
        assert [d["code"] for d in syntax["diagnostics"]] == ["SYNTAX"]

        invisible = _check_reference(client, headers, project_id, "${tmp.ghost}")
        assert invisible["valid"] is False
        assert [d["code"] for d in invisible["diagnostics"]] == ["SCOPE_INVISIBLE"]

        undefined = _check_reference(client, headers, project_id, "${project.missing_var}")
        assert undefined["valid"] is False
        assert [d["code"] for d in undefined["diagnostics"]] == ["UNDEFINED"]

        mismatch = _check_reference(client, headers, project_id, "${project.bad_int}")
        assert mismatch["valid"] is False
        assert [d["code"] for d in mismatch["diagnostics"]] == ["TYPE_MISMATCH"]

        cycle = _check_reference(client, headers, project_id, "${project.loop_a}")
        assert cycle["valid"] is False
        assert [d["code"] for d in cycle["diagnostics"]] == ["CYCLE"]

        healthy = _check_reference(client, headers, project_id, "${project.alpha}")
        assert healthy["valid"] is True
        assert healthy["diagnostics"] == []
    finally:
        client.__exit__(None, None, None)
