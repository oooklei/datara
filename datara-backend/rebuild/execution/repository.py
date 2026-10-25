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
from sqlalchemy.exc import IntegrityError
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
WORKFLOW_RECEIPT_IDENTITY = "__workflow__"


def _receipt_identity(task_instance_id: int | None) -> str:
    return WORKFLOW_RECEIPT_IDENTITY if task_instance_id is None else f"task:{task_instance_id}"


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
            receipt_identity=_receipt_identity(task_instance_id),
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
        source_count: int | None = None,
        target_count: int | None = None,
        reconcile_details: list[dict[str, Any]] | None = None,
        data_param: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Idempotent result-stat write-back aligned with the metrics workflow_result_stat fields.

        Counts come from the executor result contract (never derived from logs).
        Exactly one accumulation per (instance, task, attempt): a repeated report
        is detected via the RESULT_STAT receipt event and returns without
        touching the aggregate. Workflow-level rollups pass task_instance_id=None
        (NULL-aware dedup). run_date derives from the instance's DB-generated
        created_at.
        """
        instance = self._session.scalar(
            select(WorkflowInstanceRecord)
            .where(WorkflowInstanceRecord.id == workflow_instance_id)
            .with_for_update()
        )
        if instance is None:
            raise ExecutionDomainError(4404, f"workflow_instance {workflow_instance_id} not found")
        reported = {"success_count": success_count, "failed_count": failed_count, "skipped_count": skipped_count}
        for name, value in reported.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ExecutionDomainError(4107, f"{name} must be a non-negative integer")
        for name, value in (("source_count", source_count), ("target_count", target_count)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ExecutionDomainError(4107, f"{name} must be a non-negative integer")
        if reconcile_details is not None and not isinstance(reconcile_details, list):
            raise ExecutionDomainError(4107, "reconcile_details must be a list")
        if isinstance(attempt_no, bool) or not isinstance(attempt_no, int) or attempt_no < 0:
            raise ExecutionDomainError(4107, "attempt_no must be a non-negative integer")
        if task_instance_id is not None:
            task = self._require_task_instance(task_instance_id)
            if task.workflow_instance_id != workflow_instance_id:
                raise ExecutionDomainError(4107, "task_instance does not belong to workflow_instance")
            self._require_attempt(task_instance_id, attempt_no)

        identity = _receipt_identity(task_instance_id)
        receipt_filter = [
            ExecutionEventRecord.event_kind == RESULT_STAT_EVENT_KIND,
            ExecutionEventRecord.workflow_instance_id == workflow_instance_id,
            ExecutionEventRecord.receipt_identity == identity,
            ExecutionEventRecord.attempt_no == attempt_no,
        ]
        receipt = self._session.scalar(select(ExecutionEventRecord).where(*receipt_filter).with_for_update())
        if receipt is not None and instance.instance_type != "STREAM":
            return {
                "recorded": False,
                "duplicate": True,
                "workflow_id": instance.workflow_id,
                "attempt_no": attempt_no,
            }

        before = self.result_totals(workflow_instance_id)

        event_payload = {
            **reported,
            "source_count": source_count,
            "target_count": target_count,
            "reconcile_details": reconcile_details,
            "data_param": data_param,
        }
        if receipt is None:
            receipt = ExecutionEventRecord(
                workflow_instance_id=workflow_instance_id,
                task_instance_id=task_instance_id,
                receipt_identity=identity,
                attempt_no=attempt_no,
                event_kind=RESULT_STAT_EVENT_KIND,
                payload_json=json.dumps(event_payload, ensure_ascii=False, sort_keys=True),
            )
            try:
                with self._session.begin_nested():
                    self._session.add(receipt)
                    self._session.flush()
            except IntegrityError:
                receipt = self._session.scalar(
                    select(ExecutionEventRecord).where(*receipt_filter).with_for_update()
                )
                if receipt is None:
                    raise
                if instance.instance_type != "STREAM":
                    return {
                        "recorded": False,
                        "duplicate": True,
                        "workflow_id": instance.workflow_id,
                        "attempt_no": attempt_no,
                    }
                receipt.payload_json = json.dumps(event_payload, ensure_ascii=False, sort_keys=True)
        else:
            receipt.payload_json = json.dumps(event_payload, ensure_ascii=False, sort_keys=True)
        self._session.flush()
        after = self.result_totals(workflow_instance_id)
        if instance.instance_type != "TRIAL":
            deltas = tuple(current - previous for current, previous in zip(after, before, strict=True))
            self._apply_metrics_delta(instance, deltas)
        # Definitions are mandatory in API/runtime flows. A conditional keeps
        # the lower-level historical repository tests (which use detached IDs)
        # backwards compatible while all real workflow reports are persisted.
        from rebuild.workflow.models import WorkflowDefinitionRecord
        bind = self._session.get_bind()
        has_definitions = bind is not None and bind.dialect.has_table(
            self._session.connection(), WorkflowDefinitionRecord.__tablename__
        )
        if (instance.instance_type == "STREAM" and has_definitions
                and self._session.get(WorkflowDefinitionRecord, instance.workflow_id) is not None):
            from rebuild.execution.run_stats import RunStatisticsService
            RunStatisticsService(self._session).upsert(
                instance,
                task_instance_id=task_instance_id,
                attempt_no=attempt_no,
                source_count=source_count,
                target_count=target_count,
                success_count=success_count,
                failure_count=failed_count,
                skipped_count=skipped_count,
                reconcile_details=reconcile_details,
                stream_checkpoint=instance.instance_type == "STREAM",
                data_param=data_param,
            )
        return {
            "recorded": True,
            "duplicate": False,
            "isolated": instance.instance_type == "TRIAL",
            "workflow_id": instance.workflow_id,
            "run_date": instance.created_at.date().isoformat(),
            "attempt_no": attempt_no,
        }

    def result_totals(self, workflow_instance_id: int) -> tuple[int, int, int]:
        """Return authoritative success/failure/skipped totals without log parsing."""
        events = list(
            self._session.scalars(
                select(ExecutionEventRecord)
                .where(
                    ExecutionEventRecord.workflow_instance_id == workflow_instance_id,
                    ExecutionEventRecord.event_kind == RESULT_STAT_EVENT_KIND,
                )
                .order_by(ExecutionEventRecord.attempt_no.desc(), ExecutionEventRecord.id.desc())
            )
        )
        workflow = next(
            (event for event in events if event.receipt_identity == WORKFLOW_RECEIPT_IDENTITY), None
        )
        effective = [workflow] if workflow is not None else []
        if workflow is None:
            latest_by_task: dict[str, ExecutionEventRecord] = {}
            for event in events:
                latest_by_task.setdefault(event.receipt_identity, event)
            effective = list(latest_by_task.values())
        totals = [0, 0, 0]
        for event in effective:
            try:
                payload = json.loads(event.payload_json or "{}")
            except (TypeError, json.JSONDecodeError):
                payload = {}
            for index, name in enumerate(("success_count", "failed_count", "skipped_count")):
                value = payload.get(name, 0) if isinstance(payload, dict) else 0
                if isinstance(value, int) and not isinstance(value, bool):
                    totals[index] += value
        return totals[0], totals[1], totals[2]

    def _apply_metrics_delta(
        self, instance: WorkflowInstanceRecord, deltas: tuple[int, int, int]
    ) -> None:
        if deltas == (0, 0, 0):
            return
        key = (
            WorkflowResultStatRecord.workflow_id == instance.workflow_id,
            WorkflowResultStatRecord.run_date == instance.created_at.date(),
        )
        values = {
            "success_count": WorkflowResultStatRecord.success_count + deltas[0],
            "failure_count": WorkflowResultStatRecord.failure_count + deltas[1],
            "skipped_count": WorkflowResultStatRecord.skipped_count + deltas[2],
            "updated_at": func.current_timestamp(),
        }
        if self._session.execute(update(WorkflowResultStatRecord).where(*key).values(**values)).rowcount == 1:
            return
        try:
            with self._session.begin_nested():
                self._session.add(
                    WorkflowResultStatRecord(
                        workflow_id=instance.workflow_id,
                        run_date=instance.created_at.date(),
                        success_count=deltas[0],
                        failure_count=deltas[1],
                        skipped_count=deltas[2],
                    )
                )
                self._session.flush()
        except IntegrityError:
            result = self._session.execute(update(WorkflowResultStatRecord).where(*key).values(**values))
            if result.rowcount != 1:
                raise

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
