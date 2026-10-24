"""Authoritative per-workflow-instance statistics snapshots."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from rebuild.execution.models import (
    ExecutionEventRecord,
    TaskAttemptRecord,
    TaskInstanceRecord,
    WorkflowInstanceRecord,
    WorkflowRunReconcileDetailRecord,
    WorkflowRunStatRecord,
)
from rebuild.execution.repository import ExecutionDomainError, RESULT_STAT_EVENT_KIND
from rebuild.workflow.models import WorkflowDefinitionRecord

TERMINAL = ("SUCCEEDED", "FAILED", "CANCELLED", "CANCEL_FAILED", "STOPPED", "SKIPPED")
SECRETS = ("password", "passwd", "secret", "token", "private_key", "connection_string", "credential")


def _count(value: Any, name: str, optional: bool = False) -> int | None:
    if optional and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ExecutionDomainError(4107, f"{name} must be a non-negative integer")
    return value


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): ("***" if any(p in str(k).lower() for p in SECRETS) else _scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def _payload(event: ExecutionEventRecord) -> dict[str, Any]:
    try:
        value = json.loads(event.payload_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def normalize_datetime(value: Any, name: str, optional: bool = True) -> datetime | None:
    """Normalize API/executor timestamps to the database's UTC-naive contract."""
    if value is None and optional:
        return None
    if isinstance(value, bool):
        raise ExecutionDomainError(4107, f"{name} must be a datetime or ISO-8601 timestamp")
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ExecutionDomainError(4107, f"{name} must be a datetime or ISO-8601 timestamp") from exc
    if not isinstance(value, datetime):
        raise ExecutionDomainError(4107, f"{name} must be a datetime or ISO-8601 timestamp")
    if value.tzinfo is not None:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value


class RunStatisticsService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _context(self, instance: WorkflowInstanceRecord) -> WorkflowDefinitionRecord:
        definition = self._session.get(WorkflowDefinitionRecord, instance.workflow_id)
        if definition is None:
            raise ExecutionDomainError(4404, f"workflow definition {instance.workflow_id} not found")
        return definition

    def _record(self, instance: WorkflowInstanceRecord, definition: WorkflowDefinitionRecord) -> WorkflowRunStatRecord:
        row = self._session.scalar(
            select(WorkflowRunStatRecord).where(WorkflowRunStatRecord.workflow_instance_id == instance.id)
        )
        if row is not None:
            return row
        row = WorkflowRunStatRecord(
            project_id=definition.project_id,
            workflow_id=instance.workflow_id,
            workflow_version_id=instance.workflow_version_id,
            workflow_instance_id=instance.id,
            instance_type=instance.instance_type,
            status=instance.status,
            dag_name=definition.name,
            success_count=0,
            failure_count=0,
            skipped_count=0,
            total_count=0,
            started_at=instance.started_at or instance.created_at,
        )
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
            return row
        except IntegrityError:
            existing = self._session.scalar(
                select(WorkflowRunStatRecord).where(WorkflowRunStatRecord.workflow_instance_id == instance.id)
            )
            if existing is None:
                raise
            return existing

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
        data_param: dict[str, Any] | None = None,
    ) -> WorkflowRunStatRecord:
        del task_instance_id, attempt_no
        source_count = _count(source_count, "source_count", True)
        target_count = _count(target_count, "target_count", True)
        success_count = _count(success_count, "success_count")
        failure_count = _count(failure_count, "failure_count")
        skipped_count = _count(skipped_count, "skipped_count")
        row = self._record(instance, self._context(instance))
        values = dict(
            source_count=source_count,
            target_count=target_count,
            success_count=success_count,
            failure_count=failure_count,
            skipped_count=skipped_count,
            total_count=success_count + failure_count,
            status=instance.status,
            started_at=instance.started_at or instance.created_at,
            finished_at=instance.finished_at,
            data_param_json=(
                json.dumps(_scrub(data_param), ensure_ascii=False, sort_keys=True)
                if data_param is not None
                else row.data_param_json
            ),
            updated_at=func.current_timestamp(),
        )
        predicates = [WorkflowRunStatRecord.id == row.id]
        if stream_checkpoint:
            predicates += [
                WorkflowRunStatRecord.success_count <= success_count,
                WorkflowRunStatRecord.failure_count <= failure_count,
                WorkflowRunStatRecord.skipped_count <= skipped_count,
            ]
            if source_count is not None:
                predicates.append(
                    or_(
                        WorkflowRunStatRecord.source_count.is_(None), WorkflowRunStatRecord.source_count <= source_count
                    )
                )
            if target_count is not None:
                predicates.append(
                    or_(
                        WorkflowRunStatRecord.target_count.is_(None), WorkflowRunStatRecord.target_count <= target_count
                    )
                )
        if self._session.execute(update(WorkflowRunStatRecord).where(*predicates).values(**values)).rowcount != 1:
            raise ExecutionDomainError(4109, "stream checkpoint counts must not decrease")
        self._session.flush()
        self._session.refresh(row)
        if reconcile_details is not None:
            self._replace_details(row.id, reconcile_details)
        return row

    def _contributions(self, instance_id: int) -> list[dict[str, Any]]:
        workflow_event = self._session.scalar(
            select(ExecutionEventRecord)
            .where(
                ExecutionEventRecord.workflow_instance_id == instance_id,
                ExecutionEventRecord.task_instance_id.is_(None),
                ExecutionEventRecord.event_kind == RESULT_STAT_EVENT_KIND,
            )
            .order_by(ExecutionEventRecord.attempt_no.desc(), ExecutionEventRecord.id.desc())
        )
        # A workflow-level RESULT_STAT is the executor's authoritative rollup.
        # Task-level receipts remain trace evidence but must not be counted again.
        if workflow_event is not None:
            return [_payload(workflow_event)]
        output = []
        for task in self._session.scalars(
            select(TaskInstanceRecord).where(TaskInstanceRecord.workflow_instance_id == instance_id)
        ):
            number = self._session.scalar(
                select(func.max(TaskAttemptRecord.attempt_no)).where(
                    TaskAttemptRecord.task_instance_id == task.id, TaskAttemptRecord.status.in_(TERMINAL)
                )
            )
            if number is None:
                continue
            event = self._session.scalar(
                select(ExecutionEventRecord).where(
                    ExecutionEventRecord.workflow_instance_id == instance_id,
                    ExecutionEventRecord.task_instance_id == task.id,
                    ExecutionEventRecord.attempt_no == number,
                    ExecutionEventRecord.event_kind == RESULT_STAT_EVENT_KIND,
                )
            )
            if event is not None:
                output.append(_payload(event))
        return output

    def finalize(self, workflow_instance_id: int) -> WorkflowRunStatRecord:
        instance = self._session.get(WorkflowInstanceRecord, workflow_instance_id)
        if instance is None:
            raise ExecutionDomainError(4404, f"workflow_instance {workflow_instance_id} not found")
        if instance.status not in TERMINAL:
            raise ExecutionDomainError(4108, "run statistics can only be finalized for a terminal instance")
        parts = self._contributions(instance.id)
        details = []
        params = {}
        for part in parts:
            if isinstance(part.get("reconcile_details"), list):
                details += part["reconcile_details"]
            if isinstance(part.get("data_param"), dict):
                params.update(part["data_param"])
        def optsum(key: str) -> int | None:
            if not any(part.get(key) is not None for part in parts):
                return None
            return sum(
                value
                for part in parts
                if isinstance((value := part.get(key)), int) and not isinstance(value, bool)
            )
        return self.upsert(
            instance,
            task_instance_id=None,
            attempt_no=0,
            source_count=optsum("source_count"),
            target_count=optsum("target_count"),
            success_count=sum(int(p.get("success_count", 0)) for p in parts),
            failure_count=sum(int(p.get("failed_count", 0)) for p in parts),
            skipped_count=sum(int(p.get("skipped_count", 0)) for p in parts),
            reconcile_details=details,
            data_param=params or None,
        )

    def _replace_details(self, stat_id: int, details: list[dict[str, Any]]) -> None:
        seen = set()
        for item in details:
            if not isinstance(item, dict):
                raise ExecutionDomainError(4107, "reconcile_details items must be objects")
            source, target = item.get("source_object"), item.get("target_object")
            if not isinstance(source, str) or not source or not isinstance(target, str) or not target:
                raise ExecutionDomainError(4107, "reconcile detail objects must be non-empty strings")
            sc = _count(item.get("source_count"), "source_count", True)
            tc = _count(item.get("target_count"), "target_count", True)
            values = dict(
                source_count=sc,
                target_count=tc,
                success_count=_count(item.get("success_count", 0), "success_count"),
                failure_count=_count(item.get("failure_count", 0), "failure_count"),
                skipped_count=_count(item.get("skipped_count", 0), "skipped_count"),
                difference_count=tc - sc if sc is not None and tc is not None else None,
                data_param_json=json.dumps(_scrub(item.get("data_param")), ensure_ascii=False, sort_keys=True)
                if item.get("data_param") is not None
                else None,
                started_at=normalize_datetime(item.get("started_at"), "started_at"),
                finished_at=normalize_datetime(item.get("finished_at"), "finished_at"),
            )
            row = self._session.scalar(
                select(WorkflowRunReconcileDetailRecord).where(
                    WorkflowRunReconcileDetailRecord.run_stat_id == stat_id,
                    WorkflowRunReconcileDetailRecord.source_object == source,
                    WorkflowRunReconcileDetailRecord.target_object == target,
                )
            )
            if row is None:
                self._session.add(
                    WorkflowRunReconcileDetailRecord(
                        run_stat_id=stat_id, source_object=source, target_object=target, **values
                    )
                )
            else:
                self._session.execute(
                    update(WorkflowRunReconcileDetailRecord)
                    .where(WorkflowRunReconcileDetailRecord.id == row.id)
                    .values(**values)
                )
            seen.add((source, target))
        for row in self._session.scalars(
            select(WorkflowRunReconcileDetailRecord).where(WorkflowRunReconcileDetailRecord.run_stat_id == stat_id)
        ):
            if (row.source_object, row.target_object) not in seen:
                self._session.delete(row)
        self._session.flush()

    def get(self, stat_id: int, project_id: int, *, detail_offset: int = 0, detail_limit: int = 100):
        row = self._session.scalar(
            select(WorkflowRunStatRecord).where(
                WorkflowRunStatRecord.id == stat_id, WorkflowRunStatRecord.project_id == project_id
            )
        )
        if row is None:
            raise ExecutionDomainError(4404, f"run statistics {stat_id} not found")
        query = select(WorkflowRunReconcileDetailRecord).where(WorkflowRunReconcileDetailRecord.run_stat_id == stat_id)
        total = int(
            self._session.scalar(
                select(func.count())
                .select_from(WorkflowRunReconcileDetailRecord)
                .where(WorkflowRunReconcileDetailRecord.run_stat_id == stat_id)
            )
            or 0
        )
        return (
            row,
            list(
                self._session.scalars(
                    query.order_by(WorkflowRunReconcileDetailRecord.id).offset(detail_offset).limit(detail_limit)
                )
            ),
            total,
        )

    def list(
        self,
        project_id: int,
        *,
        workflow_id=None,
        workflow_instance_id=None,
        instance_type=None,
        status=None,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
        offset=0,
        limit=50,
    ):
        filters = [WorkflowRunStatRecord.project_id == project_id]
        for value, column in (
            (workflow_id, WorkflowRunStatRecord.workflow_id),
            (workflow_instance_id, WorkflowRunStatRecord.workflow_instance_id),
            (instance_type, WorkflowRunStatRecord.instance_type),
            (status, WorkflowRunStatRecord.status),
        ):
            if value is not None:
                filters.append(column == value)
        started_from = normalize_datetime(started_from, "started_from")
        started_to = normalize_datetime(started_to, "started_to")
        if started_from is not None:
            filters.append(WorkflowRunStatRecord.started_at >= started_from)
        if started_to is not None:
            filters.append(WorkflowRunStatRecord.started_at < started_to)
        total = int(self._session.scalar(select(func.count()).select_from(WorkflowRunStatRecord).where(*filters)) or 0)
        rows = list(
            self._session.scalars(
                select(WorkflowRunStatRecord)
                .where(*filters)
                .order_by(WorkflowRunStatRecord.started_at.desc(), WorkflowRunStatRecord.id.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        return rows, total
