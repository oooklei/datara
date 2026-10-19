from collections.abc import Mapping, Sequence

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.execution.models import EXECUTION_TABLES, ExecutionEventRecord, TaskAttemptRecord
from rebuild.execution.repository import ExecutionRepository
from rebuild.execution.sync_executor import execute_sync_attempt
from rebuild.metrics.models import (
    LineageWritebackRecord,
    TaskDataStatSegmentRecord,
    TaskInstanceDataStatRecord,
    WorkflowResultStatRecord,
)
from rebuild.sync.executor import SyncBatchWriteResult, SyncExecutionSpec
from rebuild.workflow.models import WorkflowDefinitionRecord


class FakeDriver:
    def __init__(self, *, fail_write: bool = False):
        self.fail_write = fail_write
        self.written: list[Mapping[str, object]] = []

    def read_rows(self, spec: SyncExecutionSpec, *, batch_size: int):
        assert batch_size == 2
        yield {"id": 1, "name": "Ada", "active": True}
        yield {"id": 2, "name": "Lin", "active": False}

    def include_row(self, condition: str, row: Mapping[str, object]) -> bool:
        return bool(row["active"])

    def transform_value(self, expression: str, row: Mapping[str, object]) -> object:
        assert expression == "upper(name)"
        return str(row["name"]).upper()

    def write_batch(self, spec: SyncExecutionSpec, rows: Sequence[Mapping[str, object]]) -> SyncBatchWriteResult:
        if self.fail_write:
            raise RuntimeError("simulated datasource write failure")
        self.written.extend(rows)
        return SyncBatchWriteResult(inserted=len(rows), success=len(rows))


def _snapshot():
    return {
        "project_id": 1,
        "workflow_id": 2,
        "workflow_version": 3,
        "task_id": "sync-users",
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


def _prepared_run():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            *EXECUTION_TABLES,
            WorkflowResultStatRecord.__table__,
            TaskInstanceDataStatRecord.__table__,
            TaskDataStatSegmentRecord.__table__,
            LineageWritebackRecord.__table__,
            WorkflowDefinitionRecord.__table__,
        ],
    )
    session = Session(engine)
    session.add(WorkflowDefinitionRecord(id=2, project_id=1, name="sync-test", description=""))
    session.flush()
    repository = ExecutionRepository(session)
    instance = repository.create_workflow_instance(
        workflow_id=2, workflow_version_id=3, instance_type="FORMAL"
    )
    repository.transition_workflow_instance(instance.id, "RUNNING")
    task = repository.create_task_instance(workflow_instance_id=instance.id, task_id="sync-users")
    return session, instance, task


def test_sync_bridge_runs_driver_and_writes_attempt_metrics_and_lineage():
    session, instance, task = _prepared_run()
    driver = FakeDriver()

    metrics = execute_sync_attempt(
        session,
        _snapshot(),
        workflow_instance_id=instance.id,
        task_instance_id=task.id,
        driver=driver,
    )

    assert metrics.as_dict() == {
        "read_rows": 2,
        "write_rows": 1,
        "inserted": 1,
        "updated": 0,
        "success": 1,
        "failed": 0,
        "skipped": 0,
        "filtered": 1,
    }
    assert driver.written == [{"user_id": 1, "display_name": "ADA"}]
    attempt = session.scalar(select(TaskAttemptRecord).where(TaskAttemptRecord.task_instance_id == task.id))
    assert attempt is not None and attempt.attempt_no == 1 and attempt.status == "SUCCEEDED"
    assert task.status == "SUCCEEDED"

    result_stat = session.scalar(select(WorkflowResultStatRecord))
    assert result_stat is not None
    assert (result_stat.success_count, result_stat.failure_count, result_stat.skipped_count) == (1, 0, 0)

    task_stat = session.scalar(select(TaskInstanceDataStatRecord))
    assert task_stat is not None and task_stat.rows_in == '{"estimated": false, "known": true, "value": 2}'
    segments = list(session.scalars(select(TaskDataStatSegmentRecord)).all())
    assert len(segments) == 8
    assert {row.segment_key.rsplit(".", 1)[-1] for row in segments} == {
        "read_rows", "write_rows", "inserted", "updated", "success", "failed", "skipped", "filtered"
    }

    (lineage,) = session.scalars(select(LineageWritebackRecord)).all()
    assert (lineage.run_kind, lineage.source_entity, lineage.target_entity) == (
        "sync", "4:src.users", "5:dw.users"
    )
    detail = session.scalar(
        select(ExecutionEventRecord).where(ExecutionEventRecord.event_kind == "SYNC_FIELD_LINEAGE")
    )
    assert detail is not None
    assert '[["id", "user_id"], ["name", "display_name"]]' in detail.payload_json


def test_sync_bridge_marks_failed_attempt_when_driver_write_fails():
    session, instance, task = _prepared_run()

    with pytest.raises(RuntimeError, match="simulated datasource write failure"):
        execute_sync_attempt(
            session,
            _snapshot(),
            workflow_instance_id=instance.id,
            task_instance_id=task.id,
            driver=FakeDriver(fail_write=True),
        )

    attempt = session.scalar(select(TaskAttemptRecord).where(TaskAttemptRecord.task_instance_id == task.id))
    assert attempt is not None and attempt.status == "FAILED"
    assert task.status == "FAILED"
    assert session.scalar(select(WorkflowResultStatRecord)) is None


def test_sync_bridge_rejects_snapshot_task_mismatch_before_driver_io():
    session, instance, task = _prepared_run()
    snapshot = _snapshot()
    snapshot["task_id"] = "different-task"
    driver = FakeDriver()

    with pytest.raises(ValueError, match="snapshot task_id does not match"):
        execute_sync_attempt(
            session,
            snapshot,
            workflow_instance_id=instance.id,
            task_instance_id=task.id,
            driver=driver,
        )

    assert task.status == "PENDING"
    assert session.scalar(select(TaskAttemptRecord)) is None
    assert driver.written == []
