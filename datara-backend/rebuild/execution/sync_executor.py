"""Execution-domain bridge for running a saved rebuild SYNC snapshot.

The SYNC domain owns plan validation and row orchestration. This bridge owns
the execution attempt lifecycle and persists the executor's result using the
existing execution/metrics models. Datasource I/O is still supplied by the
caller through ``SyncRuntimeAdapter``; this module does not implement or claim
to provide concrete database drivers.

The caller owns the SQLAlchemy transaction and must commit on success or roll
back on failure. Driver writes may already have happened when a DB writeback
fails, so production callers need a retry/reconciliation policy around that
boundary.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from time import perf_counter
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from rebuild.execution.models import (
    TaskAttemptRecord,
    TaskInstanceRecord,
    WorkflowInstanceRecord,
)
from rebuild.execution.repository import ExecutionDomainError, ExecutionRepository
from rebuild.metrics.models import (
    LineageWritebackRecord,
    TaskDataStatSegmentRecord,
    TaskInstanceDataStatRecord,
)
from rebuild.workflow.models import WorkflowDefinitionRecord
from rebuild.sync.executor import (
    SyncBatchWriteResult,
    SyncExecutionMetrics,
    SyncExecutionSpec,
    SyncLineageEdge,
    SyncRuntimeAdapter,
    execute_sync,
)


_COUNT_NAMES = (
    "read_rows",
    "write_rows",
    "inserted",
    "updated",
    "success",
    "failed",
    "skipped",
    "filtered",
)


def _metric_value(value: int | float) -> str:
    return json.dumps({"value": value, "known": True, "estimated": False}, sort_keys=True)


class _PersistingAdapter:
    """Delegate datasource operations and persist result/stat/lineage callbacks."""

    def __init__(
        self,
        *,
        session: Session,
        repository: ExecutionRepository,
        driver: SyncRuntimeAdapter,
        workflow_instance: WorkflowInstanceRecord,
        task_instance: TaskInstanceRecord,
        attempt: TaskAttemptRecord,
        started_at: float,
    ) -> None:
        self._session = session
        self._repository = repository
        self._driver = driver
        self._workflow_instance = workflow_instance
        self._task_instance = task_instance
        self._attempt = attempt
        self._started_at = started_at
        self._task_code = task_instance.task_id
        self._lineage_written = False
        self._metrics: dict[str, int] | None = None

    def read_rows(self, spec: SyncExecutionSpec, *, batch_size: int) -> Iterable[Mapping[str, Any]]:
        return self._driver.read_rows(spec, batch_size=batch_size)

    def include_row(self, condition: str, row: Mapping[str, Any]) -> bool:
        return self._driver.include_row(condition, row)

    def transform_value(self, expression: str, row: Mapping[str, Any]) -> Any:
        return self._driver.transform_value(expression, row)

    def write_batch(self, spec: SyncExecutionSpec, rows: Sequence[Mapping[str, Any]]) -> SyncBatchWriteResult:
        return self._driver.write_batch(spec, rows)

    def write_statistics(self, context: Mapping[str, Any], metrics: Mapping[str, int]) -> None:
        if self._metrics is not None:
            raise ExecutionDomainError(4106, "SYNC statistics callback was invoked more than once")
        self._metrics = {name: metrics[name] for name in _COUNT_NAMES}

    def write_lineage(self, context: Mapping[str, Any], edges: Sequence[SyncLineageEdge]) -> None:
        if self._lineage_written:
            raise ExecutionDomainError(4106, "SYNC lineage callback was invoked more than once")
        if self._metrics is None:
            raise ExecutionDomainError(4106, "SYNC lineage callback preceded statistics")
        self._lineage_written = True
        run_id = f"{self._workflow_instance.id}:{self._task_instance.id}:{self._attempt.attempt_no}"
        workflow = self._session.get(WorkflowDefinitionRecord, self._workflow_instance.workflow_id)
        if workflow is None:
            raise ExecutionDomainError(4106, "workflow project cannot be resolved for metrics writeback")
        # Keep the metric and governance writes atomic with one another. The
        # execution attempt itself remains outside the savepoint so the caller
        # can persist a FAILED status if writeback fails.
        with self._session.begin_nested():
            for name in _COUNT_NAMES:
                self._session.add(
                    TaskDataStatSegmentRecord(
                        instance_id=self._workflow_instance.id,
                        task_id=self._task_code,
                        segment_key=f"sync.attempt.{self._attempt.attempt_no}.{name}",
                        row_count=_metric_value(self._metrics[name]),
                    )
                )
            self._session.add(
                TaskInstanceDataStatRecord(
                    instance_id=self._workflow_instance.id,
                    task_id=self._task_code,
                    rows_in=_metric_value(self._metrics["read_rows"]),
                    rows_out=_metric_value(self._metrics["write_rows"]),
                    error_rows=_metric_value(self._metrics["failed"]),
                    elapsed_ms=_metric_value(round((perf_counter() - self._started_at) * 1000, 3)),
                ),
            )
            self._repository.record_result_stat(
                workflow_instance_id=self._workflow_instance.id,
                task_instance_id=self._task_instance.id,
                attempt_no=self._attempt.attempt_no,
                success_count=self._metrics["success"],
                failed_count=self._metrics["failed"],
                skipped_count=self._metrics["skipped"],
            )
            for edge in edges:
                self._session.add(
                    LineageWritebackRecord(
                        project_id=workflow.project_id,
                        run_id=run_id,
                        run_kind="sync",
                        source_entity=edge.source_entity,
                        target_entity=edge.target_entity,
                        writeback_at=func.current_timestamp(),
                    )
                )
                # The R7 governance table/API carries table edges only. Preserve
                # field-level mappings in the existing attempt-scoped event stream.
                self._repository.append_execution_event(
                    workflow_instance_id=self._workflow_instance.id,
                    task_instance_id=self._task_instance.id,
                    attempt_no=self._attempt.attempt_no,
                    event_kind="SYNC_FIELD_LINEAGE",
                    payload_json=json.dumps(
                        {
                            "run_id": run_id,
                            "source_entity": edge.source_entity,
                            "target_entity": edge.target_entity,
                            "field_mappings": [list(pair) for pair in edge.field_mappings],
                        },
                        sort_keys=True,
                    ),
                )


def execute_sync_attempt(
    session: Session,
    snapshot: Mapping[str, Any],
    *,
    workflow_instance_id: int,
    task_instance_id: int,
    driver: SyncRuntimeAdapter,
) -> SyncExecutionMetrics:
    """Run one SYNC snapshot as a persisted execution attempt.

    The workflow instance must already be RUNNING and the task must be PENDING.
    This method creates/starts one attempt, delegates row I/O, persists all
    eight counters plus task/workflow result stats and table/field lineage, then
    closes the task and attempt. Failed driver execution marks both failed and
    re-raises the original error.
    """
    # Validate the snapshot before any datasource operation. This yields the
    # task code and prevents attaching a plan to a different task instance.
    from rebuild.sync.executor import prepare_sync_execution

    spec = prepare_sync_execution(snapshot)
    repository = ExecutionRepository(session)
    workflow_instance = session.get(WorkflowInstanceRecord, workflow_instance_id)
    task_instance = session.get(TaskInstanceRecord, task_instance_id)
    if workflow_instance is None:
        raise ExecutionDomainError(4404, f"workflow_instance {workflow_instance_id} not found")
    if task_instance is None:
        raise ExecutionDomainError(4404, f"task_instance {task_instance_id} not found")
    if workflow_instance.status != "RUNNING":
        raise ExecutionDomainError(4103, "SYNC requires a RUNNING workflow_instance")
    if task_instance.workflow_instance_id != workflow_instance.id:
        raise ExecutionDomainError(4107, "task_instance does not belong to workflow_instance")
    if task_instance.task_id != spec.task_id:
        raise ExecutionDomainError(4107, "snapshot task_id does not match task_instance")
    if workflow_instance.workflow_id != spec.workflow_id:
        raise ExecutionDomainError(4107, "snapshot workflow_id does not match workflow_instance")
    if task_instance.status != "PENDING":
        raise ExecutionDomainError(4103, "SYNC requires a PENDING task_instance")

    repository.transition_task_instance(task_instance.id, "RUNNING")
    attempt = repository.append_attempt(task_instance.id)
    repository.transition_attempt(attempt.id, "RUNNING")
    started_at = perf_counter()
    adapter = _PersistingAdapter(
        session=session,
        repository=repository,
        driver=driver,
        workflow_instance=workflow_instance,
        task_instance=task_instance,
        attempt=attempt,
        started_at=started_at,
    )
    run_context = {
        "workflow_instance_id": workflow_instance.id,
        "task_instance_id": task_instance.id,
        "attempt_no": attempt.attempt_no,
    }

    try:
        metrics = execute_sync(snapshot, adapter=adapter, run_context=run_context)
        if not adapter._lineage_written:
            raise ExecutionDomainError(4106, "SYNC executor did not persist lineage")
        repository.append_run_output(
            task_instance_id=task_instance.id,
            attempt_no=attempt.attempt_no,
            output_json=json.dumps(metrics.as_dict(), sort_keys=True),
        )
        repository.transition_attempt(attempt.id, "SUCCEEDED")
        repository.transition_task_instance(task_instance.id, "SUCCEEDED")
        return metrics
    except Exception as exc:
        # A callback/database failure may leave the Session requiring rollback;
        # preserve the original exception rather than masking it with cleanup.
        try:
            repository.append_run_log(
                task_instance_id=task_instance.id,
                attempt_no=attempt.attempt_no,
                message=str(exc) or type(exc).__name__,
                level="ERROR",
            )
            if attempt.status == "RUNNING":
                repository.transition_attempt(attempt.id, "FAILED")
            if task_instance.status == "RUNNING":
                repository.transition_task_instance(task_instance.id, "FAILED")
        except Exception:
            pass
        raise

