"""Execution-domain persistence services (R9 run-instance slice).

Scope (governance line task #26/#39): instance creation, legal state
transitions (batch vs stream machines — models.py), attempt append with
attempt_no isolation, log/output writes, execution_event append, and the
result-stat write-back contract.

Contract sources: design §9 (run tables, DB-generated timestamps, attempt_no
isolation, 汇总不得重复计算) + 纠偏方案 §5.4 (workflow_result_stat idempotency)
+ design §4.1/§4.2 (TRIAL/FORMAL/STREAM). All timestamp writes go through the
database (server_default on insert, SQL-side CURRENT_TIMESTAMP on transition
updates) — no application-side datetime ever reaches a run table.

record_result_stat: the executor result contract reports success/failed/skipped
counts (never parsed from logs). Idempotency per (workflow_instance_id,
task_instance_id, attempt_no) is enforced by a RESULT_STAT receipt stored as an
execution_event row; a repeated report for the same tuple is a no-op. The
aggregate accumulates into the metrics-domain workflow_result_stat row (fields
aligned: success_count / failure_count / skipped_count); distinct attempts
accumulate separately so retries stay traceable without double counting.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from rebuild.execution.models import (
    BATCH_TRANSITIONS,
    STREAM_TRANSITIONS,
    TERMINAL_STATUSES,
    INSTANCE_TYPES,
    TRIGGER_TYPES,
    ExecutionEventRecord,
    RunLogRecord,
    RunOutputRecord,
    TaskAttemptRecord,
    TaskInstanceRecord,
    WorkflowInstanceRecord,
)
from rebuild.metrics.models import WorkflowResultStatRecord

RESULT_STAT_EVENT_KIND = "RESULT_STAT"
LOG_LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")


class ExecutionDomainError(ValueError):
    def __init__(self, code: int, msg: str) -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg


class ExecutionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # ---- instance creation -------------------------------------------------

    def create_workflow_instance(
        self,
        *,
        workflow_id: int,
        workflow_version_id: int,
        instance_type: str,
        trigger_type: str | None = None,
        trial_snapshot_id: int | None = None,
    ) -> WorkflowInstanceRecord:
        if instance_type not in INSTANCE_TYPES:
            raise ExecutionDomainError(4101, f"instance_type must be one of {list(INSTANCE_TYPES)}")
        if trigger_type is not None and trigger_type not in TRIGGER_TYPES:
            raise ExecutionDomainError(4102, f"trigger_type must be one of {list(TRIGGER_TYPES)}")
        record = WorkflowInstanceRecord(
            workflow_id=workflow_id,
            workflow_version_id=workflow_version_id,
            instance_type=instance_type,
            status="PENDING",
            trigger_type=trigger_type,
            trial_snapshot_id=trial_snapshot_id,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def create_task_instance(self, *, workflow_instance_id: int, task_id: str) -> TaskInstanceRecord:
        self._require_workflow_instance(workflow_instance_id)
        if not isinstance(task_id, str) or not task_id:
            raise ExecutionDomainError(4102, "task_id must be a non-empty string")
        record = TaskInstanceRecord(
            workflow_instance_id=workflow_instance_id, task_id=task_id, status="PENDING", current_attempt_no=0
        )
        self._session.add(record)
        self._session.flush()
        return record

    # ---- state transitions ---------------------------------------------------

    def transition_workflow_instance(self, instance_id: int, new_status: str) -> WorkflowInstanceRecord:
        record = self._require_workflow_instance(instance_id)
        allowed = STREAM_TRANSITIONS if record.instance_type == "STREAM" else BATCH_TRANSITIONS
        self._apply_transition(WorkflowInstanceRecord, record, new_status, allowed)
        return record

    def transition_task_instance(self, task_instance_id: int, new_status: str) -> TaskInstanceRecord:
        record = self._require_task_instance(task_instance_id)
        self._apply_transition(TaskInstanceRecord, record, new_status, BATCH_TRANSITIONS)
        return record

    def transition_attempt(self, attempt_id: int, new_status: str) -> TaskAttemptRecord:
        record = self._session.get(TaskAttemptRecord, attempt_id)
        if record is None:
            raise ExecutionDomainError(4404, f"task_instance_attempt {attempt_id} not found")
        self._apply_transition(TaskAttemptRecord, record, new_status, BATCH_TRANSITIONS)
        return record

    def _apply_transition(
        self, model: type, record: Any, new_status: str, allowed: dict[str, set[str]]
    ) -> None:
        current = record.status
        if new_status not in allowed.get(current, set()):
            raise ExecutionDomainError(4103, f"illegal status transition {current} -> {new_status}")
        values: dict[str, Any] = {"status": new_status, "updated_at": func.current_timestamp()}
        if new_status == "RUNNING":
            values["started_at"] = func.current_timestamp()
        if new_status in TERMINAL_STATUSES:
            values["finished_at"] = func.current_timestamp()
        result = self._session.execute(
            update(model).where(model.id == record.id, model.status == current).values(**values)
        )
        if result.rowcount != 1:
            raise ExecutionDomainError(4104, "concurrent status change detected")
        self._session.flush()
        self._session.refresh(record)

    # ---- attempts ------------------------------------------------------------

    def append_attempt(self, task_instance_id: int) -> TaskAttemptRecord:
        """Append the next retry attempt; attempt_no is isolated and monotonic per task."""
        task = self._require_task_instance(task_instance_id)
        expected_no = task.current_attempt_no
        max_no = self._session.scalar(
            select(func.max(TaskAttemptRecord.attempt_no)).where(
                TaskAttemptRecord.task_instance_id == task_instance_id
            )
        )
        next_no = (max_no or 0) + 1
        if next_no != expected_no + 1:
            raise ExecutionDomainError(4104, "current_attempt_no is inconsistent with persisted attempts")
        result = self._session.execute(
            update(TaskInstanceRecord)
            .where(TaskInstanceRecord.id == task_instance_id, TaskInstanceRecord.current_attempt_no == expected_no)
            .values(current_attempt_no=next_no, updated_at=func.current_timestamp())
        )
        if result.rowcount != 1:
            raise ExecutionDomainError(4104, "concurrent attempt append detected")
        attempt = TaskAttemptRecord(task_instance_id=task_instance_id, attempt_no=next_no, status="PENDING")
        self._session.add(attempt)
        self._session.flush()
        self._session.refresh(task)
        return attempt

    # ---- logs / outputs / events ---------------------------------------------

    def append_run_log(
        self, *, task_instance_id: int, attempt_no: int, message: str, level: str = "INFO"
    ) -> RunLogRecord:
        self._require_attempt(task_instance_id, attempt_no)
        if level not in LOG_LEVELS:
            raise ExecutionDomainError(4105, f"level must be one of {list(LOG_LEVELS)}")
        if not isinstance(message, str) or not message:
            raise ExecutionDomainError(4106, "message must be a non-empty string")
        record = RunLogRecord(task_instance_id=task_instance_id, attempt_no=attempt_no, level=level, message=message)
        self._session.add(record)
        self._session.flush()
        return record

    def append_run_output(self, *, task_instance_id: int, attempt_no: int, output_json: str) -> RunOutputRecord:
        self._require_attempt(task_instance_id, attempt_no)
        if not isinstance(output_json, str) or not output_json:
            raise ExecutionDomainError(4106, "output_json must be a non-empty string (verbatim passthrough)")
        record = RunOutputRecord(task_instance_id=task_instance_id, attempt_no=attempt_no, output_json=output_json)
        self._session.add(record)
        self._session.flush()
        return record

    def append_execution_event(
        self,
        *,
        workflow_instance_id: int,
        event_kind: str,
        task_instance_id: int | None = None,
        attempt_no: int | None = None,
        payload_json: str | None = None,
    ) -> ExecutionEventRecord:
        self._require_workflow_instance(workflow_instance_id)
        if not isinstance(event_kind, str) or not event_kind:
            raise ExecutionDomainError(4106, "event_kind must be a non-empty string")
        record = ExecutionEventRecord(
            workflow_instance_id=workflow_instance_id,
            task_instance_id=task_instance_id,
            attempt_no=attempt_no,
            event_kind=event_kind,
            payload_json=payload_json,
        )
        self._session.add(record)
        self._session.flush()
        return record

    # ---- result-stat write-back contract (纠偏方案 §5.4) ----------------------

    def record_result_stat(
        self,
        *,
        workflow_instance_id: int,
        attempt_no: int,
        success_count: int,
        failed_count: int,
        skipped_count: int,
        task_instance_id: int | None = None,
    ) -> dict[str, Any]:
        """Idempotent result-stat write-back aligned with the metrics workflow_result_stat fields.

        Counts come from the executor result contract (never derived from logs).
        Exactly one accumulation per (instance, task, attempt): a repeated report
        is detected via the RESULT_STAT receipt event and returns without
        touching the aggregate. Workflow-level rollups pass task_instance_id=None
        (NULL-aware dedup). run_date derives from the instance's DB-generated
        created_at.
        """
        instance = self._require_workflow_instance(workflow_instance_id)
        reported = {"success_count": success_count, "failed_count": failed_count, "skipped_count": skipped_count}
        for name, value in reported.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ExecutionDomainError(4107, f"{name} must be a non-negative integer")
        if isinstance(attempt_no, bool) or not isinstance(attempt_no, int) or attempt_no < 0:
            raise ExecutionDomainError(4107, "attempt_no must be a non-negative integer")
        if task_instance_id is not None:
            task = self._require_task_instance(task_instance_id)
            if task.workflow_instance_id != workflow_instance_id:
                raise ExecutionDomainError(4107, "task_instance does not belong to workflow_instance")
            self._require_attempt(task_instance_id, attempt_no)

        receipt_filter = [
            ExecutionEventRecord.event_kind == RESULT_STAT_EVENT_KIND,
            ExecutionEventRecord.workflow_instance_id == workflow_instance_id,
            ExecutionEventRecord.attempt_no == attempt_no,
        ]
        if task_instance_id is None:
            receipt_filter.append(ExecutionEventRecord.task_instance_id.is_(None))
        else:
            receipt_filter.append(ExecutionEventRecord.task_instance_id == task_instance_id)
        if self._session.scalar(select(ExecutionEventRecord.id).where(*receipt_filter)) is not None:
            return {
                "recorded": False,
                "duplicate": True,
                "workflow_id": instance.workflow_id,
                "attempt_no": attempt_no,
            }

        run_date = instance.created_at.date()
        if instance.instance_type != "TRIAL":
            aggregate = self._session.scalar(
                select(WorkflowResultStatRecord).where(
                    WorkflowResultStatRecord.workflow_id == instance.workflow_id,
                    WorkflowResultStatRecord.run_date == run_date,
                )
            )
            if aggregate is None:
                self._session.add(
                    WorkflowResultStatRecord(
                        workflow_id=instance.workflow_id,
                        run_date=run_date,
                        success_count=success_count,
                        failure_count=failed_count,
                        skipped_count=skipped_count,
                    )
                )
            else:
                self._session.execute(
                    update(WorkflowResultStatRecord)
                    .where(WorkflowResultStatRecord.id == aggregate.id)
                    .values(
                        success_count=WorkflowResultStatRecord.success_count + success_count,
                        failure_count=WorkflowResultStatRecord.failure_count + failed_count,
                        skipped_count=WorkflowResultStatRecord.skipped_count + skipped_count,
                        updated_at=func.current_timestamp(),
                    )
                )
        self._session.add(
            ExecutionEventRecord(
                workflow_instance_id=workflow_instance_id,
                task_instance_id=task_instance_id,
                attempt_no=attempt_no,
                event_kind=RESULT_STAT_EVENT_KIND,
                payload_json=json.dumps(reported, sort_keys=True),
            )
        )
        self._session.flush()
        return {
            "recorded": True,
            "duplicate": False,
            "isolated": instance.instance_type == "TRIAL",
            "workflow_id": instance.workflow_id,
            "run_date": run_date.isoformat(),
            "attempt_no": attempt_no,
        }

    # ---- lookups ---------------------------------------------------------------

    def _require_workflow_instance(self, instance_id: int) -> WorkflowInstanceRecord:
        record = self._session.get(WorkflowInstanceRecord, instance_id)
        if record is None:
            raise ExecutionDomainError(4404, f"workflow_instance {instance_id} not found")
        return record

    def _require_task_instance(self, task_instance_id: int) -> TaskInstanceRecord:
        record = self._session.get(TaskInstanceRecord, task_instance_id)
        if record is None:
            raise ExecutionDomainError(4404, f"task_instance {task_instance_id} not found")
        return record

    def _require_attempt(self, task_instance_id: int, attempt_no: int) -> TaskAttemptRecord:
        self._require_task_instance(task_instance_id)
        record = self._session.scalar(
            select(TaskAttemptRecord).where(
                TaskAttemptRecord.task_instance_id == task_instance_id,
                TaskAttemptRecord.attempt_no == attempt_no,
            )
        )
        if record is None:
            raise ExecutionDomainError(4404, f"attempt {attempt_no} of task_instance {task_instance_id} not found")
        return record
