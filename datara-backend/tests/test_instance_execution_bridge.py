"""Compatibility coverage for the legacy /api/instances execution-domain bridge."""

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import api.instance as legacy_instances
from common.resp import PageQuery
from rebuild.execution.legacy_bridge import _session_factory
from rebuild.execution.models import EXECUTION_TABLES, TaskInstanceRecord, WorkflowInstanceRecord
from rebuild.execution.repository import ExecutionRepository
from rebuild.common.db import Base as RebuildBase


USER = SimpleNamespace(id=1, user_name="bridge-test", user_role="dev")


@pytest.fixture
def execution_store(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'execution.sqlite'}"
    monkeypatch.setenv("REBUILD_DB_URL", database_url)
    _session_factory.cache_clear()
    engine = create_engine(database_url)
    RebuildBase.metadata.create_all(engine, tables=list(EXECUTION_TABLES))
    with Session(engine) as session:
        repo = ExecutionRepository(session)
        instance = repo.create_workflow_instance(
            workflow_id=17, workflow_version_id=3, instance_type="FORMAL", trigger_type="MANUAL"
        )
        task = repo.create_task_instance(workflow_instance_id=instance.id, task_id="node-1")
        repo.transition_workflow_instance(instance.id, "RUNNING")
        repo.append_execution_event(
            workflow_instance_id=instance.id,
            task_instance_id=task.id,
            event_kind="TASK_STARTED",
            payload_json='{"node":"node-1"}',
        )
        session.commit()
        instance_id = instance.id
        task_id = task.id
    yield engine, instance_id, task_id
    engine.dispose()
    _session_factory.cache_clear()


def test_legacy_list_detail_and_events_include_execution_records(execution_store, db_session):
    _engine, numeric_id, _task_id = execution_store
    external_id = f"r9-{numeric_id}"

    listing = legacy_instances.list_instances(
        page=PageQuery(page_no=1, page_size=20),
        run_mode=None,
        state=None,
        wf_code=None,
        sync_logs=None,
        user=USER,
        db=db_session,
    )
    item = next(row for row in listing["data"]["list"] if row["instanceId"] == external_id)
    assert item["source"] == "execution"
    assert item["instanceType"] == "FORMAL"
    assert item["state"] == "running"

    detail = legacy_instances.get_instance(instance_id=external_id, user=USER, db=db_session)
    assert detail["data"]["taskInstances"][0]["nodeId"] == "node-1"
    events = legacy_instances.list_run_events(
        instance_id=external_id,
        page=PageQuery(page_no=1, page_size=20),
        after_id=None,
        user=USER,
        db=db_session,
    )
    assert events["data"]["list"][0]["type"] == "TASK_STARTED"
    assert events["data"]["list"][0]["source"] == "execution"


def test_legacy_stop_and_rerun_commands_map_to_execution_transitions_and_attempts(execution_store, db_session):
    _engine, numeric_id, task_id = execution_store
    external_id = f"r9-{numeric_id}"

    stopped = legacy_instances.stop_instance(instance_id=external_id, user=USER, db=db_session)
    assert stopped["data"]["state"] == "kill"
    with Session(_engine) as session:
        instance = session.get(WorkflowInstanceRecord, numeric_id)
        assert instance is not None and instance.status == "CANCELED"
        instance.status = "SUCCEEDED"
        task = session.get(TaskInstanceRecord, task_id)
        assert task is not None
        task.status = "FAILED"
        session.commit()

    rerun = legacy_instances.rerun_instance(
        instance_id=external_id,
        body=legacy_instances.RerunBody(priority=3),
        user=USER,
        db=db_session,
    )
    assert rerun["data"]["attempts"][0]["attempt_no"] == 1
    failed = legacy_instances.rerun_failed(
        instance_id=external_id,
        body=legacy_instances.RerunBody(priority=3),
        user=USER,
        db=db_session,
    )
    assert failed["data"]["attempts"][0]["attempt_no"] == 2


def test_legacy_sse_replays_execution_events_and_terminal_state(execution_store, client):
    engine, numeric_id, _task_id = execution_store
    with Session(engine) as session:
        row = session.get(WorkflowInstanceRecord, numeric_id)
        assert row is not None
        row.status = "SUCCEEDED"
        session.commit()

    response = client.get(f"/api/v1/instances/r9-{numeric_id}/stream")
    assert response.status_code == 200
    assert "event: node_event" in response.text
    assert '"source": "execution"' in response.text
    assert "event: instance_finished" in response.text
