"""Trial output aggregation — logs / variables / data-stats (WF-22).

Design source: docs/increments/2026-10-14-datara-platform-rebuild-design.md §4.1.

GET /trial/runs/{run_id} aggregates:
  - logs: task_instance_log grouped by task_instance (ordered by task + attempt)
  - variables: terminal variable snapshot (task_instance_variable_runtime last values)
  - stats: record_result_stat rollup for this instance
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.execution.models import (
    RunLogRecord,
    RunOutputRecord,
    TaskInstanceRecord,
    WorkflowInstanceRecord,
)
from rebuild.variables.models import TaskInstanceVariableRuntimeRecord


class TrialOutputAggregator:
    """Aggregates trial run output for the GET /trial/runs/{run_id} endpoint."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def aggregate(self, instance_id: int) -> dict[str, Any]:
        """Return {logs, variables, stats} for a trial run.

        Empty run returns empty arrays (not 404).
        """
        instance = self._session.get(WorkflowInstanceRecord, instance_id)
        if instance is None:
            return {"logs": [], "variables": [], "stats": {}, "found": False}

        logs = self._collect_logs(instance_id)
        variables = self._collect_variables(instance_id)
        stats = self._collect_stats(instance_id)

        return {
            "logs": logs,
            "variables": variables,
            "stats": stats,
            "found": True,
            "instance_type": instance.instance_type,
            "status": instance.status,
        }

    def _collect_logs(self, instance_id: int) -> list[dict[str, Any]]:
        """Collect task_instance_log rows grouped by task."""
        task_ids = self._instance_task_ids(instance_id)
        if not task_ids:
            return []

        rows = self._session.scalars(
            select(RunLogRecord)
            .where(RunLogRecord.task_instance_id.in_(task_ids))
            .order_by(RunLogRecord.task_instance_id, RunLogRecord.attempt_no, RunLogRecord.id)
        ).all()

        # Group by task_instance_id.
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            grouped.setdefault(row.task_instance_id, []).append(
                {
                    "attempt_no": row.attempt_no,
                    "level": row.level,
                    "message": row.message,
                }
            )

        # Map to task codes.
        task_map = self._task_map(instance_id)
        result = []
        for task_id, log_entries in grouped.items():
            result.append(
                {
                    "task_id": task_id,
                    "task_code": task_map.get(task_id, task_id),
                    "logs": log_entries,
                }
            )
        return result

    def _collect_variables(self, instance_id: int) -> list[dict[str, Any]]:
        """Collect terminal variable runtime snapshots (last value per name)."""
        rows = self._session.scalars(
            select(TaskInstanceVariableRuntimeRecord)
            .where(TaskInstanceVariableRuntimeRecord.instance_id == instance_id)
            .order_by(TaskInstanceVariableRuntimeRecord.attempt_no, TaskInstanceVariableRuntimeRecord.id)
        ).all()

        # Keep the last value per (name, attempt_no) — simplified: last per name.
        terminal: dict[str, dict[str, Any]] = {}
        for row in rows:
            terminal[row.name] = {
                "name": row.name,
                "expression": row.expression,
                "scope": row.scope,
                "resolved_value": row.resolved_value,
                "value_type": row.value_type,
                "source": row.source,
                "attempt_no": row.attempt_no,
            }
        return list(terminal.values())

    def _collect_stats(self, instance_id: int) -> dict[str, Any]:
        """Collect result-stat rollup for this instance."""
        # The stats are stored in execution_event with event_kind=RESULT_STAT
        # and in the metrics workflow_result_stat table. For trial runs, we
        # aggregate from the execution_event receipts.
        from rebuild.execution.models import ExecutionEventRecord
        from rebuild.execution.repository import RESULT_STAT_EVENT_KIND

        events = self._session.scalars(
            select(ExecutionEventRecord).where(
                ExecutionEventRecord.workflow_instance_id == instance_id,
                ExecutionEventRecord.event_kind == RESULT_STAT_EVENT_KIND,
            )
        ).all()

        total_success = 0
        total_failed = 0
        total_skipped = 0
        for event in events:
            if event.payload_json:
                payload = json.loads(event.payload_json)
                total_success += payload.get("success_count", 0)
                total_failed += payload.get("failed_count", 0)
                total_skipped += payload.get("skipped_count", 0)

        return {
            "success_count": total_success,
            "failed_count": total_failed,
            "skipped_count": total_skipped,
        }

    def _instance_task_ids(self, instance_id: int) -> list[int]:
        return list(
            self._session.scalars(
                select(TaskInstanceRecord.id).where(
                    TaskInstanceRecord.workflow_instance_id == instance_id
                )
            ).all()
        )

    def _task_map(self, instance_id: int) -> dict[int, str]:
        rows = self._session.scalars(
            select(TaskInstanceRecord).where(
                TaskInstanceRecord.workflow_instance_id == instance_id
            )
        ).all()
        return {row.id: row.task_id for row in rows}
