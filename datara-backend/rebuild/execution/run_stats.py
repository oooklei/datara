"""Execution-owned run-result persistence, independent from diagnostic logs."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from rebuild.execution.models import (
    WorkflowInstanceRecord,
    WorkflowRunReconcileDetailRecord,
    WorkflowRunStatRecord,
)
from rebuild.execution.repository import ExecutionDomainError
from rebuild.workflow.models import WorkflowDefinitionRecord


def _count(value: Any, name: str, *, optional: bool = False) -> int | None:
    if optional and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ExecutionDomainError(4107, f"{name} must be a non-negative integer")
    return value


class RunStatisticsService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
        self,
        instance: WorkflowInstanceRecord,
        *,
        task_instance_id: int | None,
        attempt_no: int,
        source_count: int | None,
        target_count: int | None,
        success_count: int,
        failure_count: int,
        skipped_count: int,
        reconcile_details: list[dict[str, Any]] | None = None,
        stream_checkpoint: bool = False,
    ) -> WorkflowRunStatRecord:
        attempt_no = _count(attempt_no, "attempt_no")  # type: ignore[assignment]
        source_count = _count(source_count, "source_count", optional=True)
        target_count = _count(target_count, "target_count", optional=True)
        success_count = _count(success_count, "success_count")  # type: ignore[assignment]
        failure_count = _count(failure_count, "failure_count")  # type: ignore[assignment]
        skipped_count = _count(skipped_count, "skipped_count")  # type: ignore[assignment]
        definition = self._session.get(WorkflowDefinitionRecord, instance.workflow_id)
        if definition is None:
            raise ExecutionDomainError(4404, f"workflow definition {instance.workflow_id} not found")
        identity = str(task_instance_id) if task_instance_id is not None else "workflow"
        record = self._session.scalar(
            select(WorkflowRunStatRecord).where(
                WorkflowRunStatRecord.workflow_instance_id == instance.id,
                WorkflowRunStatRecord.task_identity == identity,
                WorkflowRunStatRecord.attempt_no == attempt_no,
            )
        )
        if stream_checkpoint and record is not None:
            old = (record.source_count, record.target_count, record.success_count,
                   record.failure_count, record.skipped_count)
            new = (source_count, target_count, success_count, failure_count, skipped_count)
            if any(before is not None and after is not None and after < before
                   for before, after in zip(old, new)):
                raise ExecutionDomainError(4109, "stream checkpoint counts must not decrease")
        values = dict(
            project_id=definition.project_id,
            workflow_id=instance.workflow_id,
            workflow_version_id=instance.workflow_version_id,
            task_instance_id=task_instance_id,
            instance_type=instance.instance_type,
            status=instance.status,
            source_count=source_count,
            target_count=target_count,
            success_count=success_count,
            failure_count=failure_count,
            skipped_count=skipped_count,
            started_at=instance.started_at,
            finished_at=instance.finished_at,
        )
        if record is None:
            record = WorkflowRunStatRecord(
                workflow_instance_id=instance.id, task_identity=identity, attempt_no=attempt_no, **values
            )
            self._session.add(record)
            self._session.flush()
        else:
            self._session.execute(
                update(WorkflowRunStatRecord).where(WorkflowRunStatRecord.id == record.id).values(
                    **values, updated_at=func.current_timestamp()
                )
            )
            self._session.flush()
            self._session.refresh(record)
        self._replace_details(record.id, reconcile_details or [])
        return record

    def _replace_details(self, run_stat_id: int, details: list[dict[str, Any]]) -> None:
        seen: set[tuple[str, str]] = set()
        for detail in details:
            if not isinstance(detail, dict):
                raise ExecutionDomainError(4107, "reconcile_details items must be objects")
            source = detail.get("source_object")
            target = detail.get("target_object")
            if not isinstance(source, str) or not source or not isinstance(target, str) or not target:
                raise ExecutionDomainError(4107, "reconcile detail objects must be non-empty strings")
            source_value = _count(detail.get("source_count"), "source_count", optional=True)
            target_value = _count(detail.get("target_count"), "target_count", optional=True)
            values = dict(
                source_count=source_value,
                target_count=target_value,
                success_count=_count(detail.get("success_count", 0), "success_count"),
                failure_count=_count(detail.get("failure_count", 0), "failure_count"),
                skipped_count=_count(detail.get("skipped_count", 0), "skipped_count"),
                difference_count=(target_value - source_value
                                  if source_value is not None and target_value is not None else None),
            )
            row = self._session.scalar(select(WorkflowRunReconcileDetailRecord).where(
                WorkflowRunReconcileDetailRecord.run_stat_id == run_stat_id,
                WorkflowRunReconcileDetailRecord.source_object == source,
                WorkflowRunReconcileDetailRecord.target_object == target,
            ))
            if row is None:
                self._session.add(WorkflowRunReconcileDetailRecord(
                    run_stat_id=run_stat_id, source_object=source, target_object=target, **values
                ))
            else:
                self._session.execute(update(WorkflowRunReconcileDetailRecord).where(
                    WorkflowRunReconcileDetailRecord.id == row.id
                ).values(**values, updated_at=func.current_timestamp()))
            seen.add((source, target))
        for row in self._session.scalars(select(WorkflowRunReconcileDetailRecord).where(
            WorkflowRunReconcileDetailRecord.run_stat_id == run_stat_id
        )):
            if (row.source_object, row.target_object) not in seen:
                self._session.delete(row)
        self._session.flush()

    def finalize(self, workflow_instance_id: int) -> None:
        instance = self._session.get(WorkflowInstanceRecord, workflow_instance_id)
        if instance is None:
            raise ExecutionDomainError(4404, f"workflow_instance {workflow_instance_id} not found")
        self._session.execute(update(WorkflowRunStatRecord).where(
            WorkflowRunStatRecord.workflow_instance_id == workflow_instance_id
        ).values(status=instance.status, started_at=instance.started_at,
                 finished_at=instance.finished_at, updated_at=func.current_timestamp()))

    def get(self, stat_id: int, project_id: int):
        record = self._session.scalar(select(WorkflowRunStatRecord).where(
            WorkflowRunStatRecord.id == stat_id, WorkflowRunStatRecord.project_id == project_id
        ))
        if record is None:
            raise ExecutionDomainError(4404, f"run statistics {stat_id} not found")
        details = list(self._session.scalars(select(WorkflowRunReconcileDetailRecord).where(
            WorkflowRunReconcileDetailRecord.run_stat_id == stat_id
        ).order_by(WorkflowRunReconcileDetailRecord.id)))
        return record, details

    def list(self, project_id: int, *, workflow_id: int | None = None,
             workflow_instance_id: int | None = None, offset: int = 0,
             limit: int = 50) -> tuple[list[WorkflowRunStatRecord], int]:
        filters = [WorkflowRunStatRecord.project_id == project_id]
        if workflow_id is not None:
            filters.append(WorkflowRunStatRecord.workflow_id == workflow_id)
        if workflow_instance_id is not None:
            filters.append(WorkflowRunStatRecord.workflow_instance_id == workflow_instance_id)
        total = int(self._session.scalar(select(func.count()).select_from(
            WorkflowRunStatRecord).where(*filters)) or 0)
        rows = list(self._session.scalars(select(WorkflowRunStatRecord).where(*filters).order_by(
            WorkflowRunStatRecord.created_at.desc(), WorkflowRunStatRecord.id.desc()
        ).offset(offset).limit(limit)))
        return rows, total
