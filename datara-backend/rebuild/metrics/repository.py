"""Time-window queries over the R7 metric tables.

All six contract methods are POST with a ``TimeWindowQuery`` body
({from, to, offset, limit}; B2 gap #4: formats pass through unprocessed —
ISO-8601 strings compared lexicographically). MetricValue JSON columns are
returned verbatim (A7 Step 1: no derivation on either side).
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.metrics.models import (
    LineageWritebackRecord,
    QualityRuleResultLinkRecord,
    TaskDataErrorSampleRecord,
    TaskDataStatSegmentRecord,
    TaskInstanceDataStatRecord,
    WorkflowResultStatRecord,
)
from rebuild.execution.models import WorkflowInstanceRecord
from rebuild.workflow.models import WorkflowDefinitionRecord


class MetricsDomainError(ValueError):
    def __init__(self, code: int, msg: str) -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg


VALID_RUN_KINDS = ("sql", "sync", "workflow", "all")


def parse_window(payload: dict[str, Any]) -> tuple[str, str, int, int]:
    """Validate the TimeWindowQuery body; return (from, to, offset, limit)."""
    window_from = payload.get("from")
    window_to = payload.get("to")
    offset = payload.get("offset", 0)
    limit = payload.get("limit", 100)
    if not isinstance(window_from, str) or not isinstance(window_to, str) or not window_from or not window_to:
        raise MetricsDomainError(4001, "from/to are required ISO strings")
    if window_from > window_to:
        raise MetricsDomainError(4001, "from must not be after to")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise MetricsDomainError(4001, "offset must be a non-negative integer")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0 or limit > 1000:
        raise MetricsDomainError(4001, "limit must be an integer within (0, 1000]")
    return window_from, window_to, offset, limit


def _metric_json(raw: str) -> dict[str, Any]:
    """Parse a MetricValue column; malformed storage rows surface as-is."""
    return json.loads(raw)


class MetricsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def workflow_result_stats(self, window_from: str, window_to: str, offset: int, limit: int, project_id: int) -> list[dict[str, Any]]:
        rows = self._session.scalars(
            select(WorkflowResultStatRecord)
            .join(WorkflowDefinitionRecord, WorkflowDefinitionRecord.id == WorkflowResultStatRecord.workflow_id)
            .where(WorkflowResultStatRecord.run_date >= window_from[:10], WorkflowResultStatRecord.run_date <= window_to[:10])
            .where(WorkflowDefinitionRecord.project_id == project_id)
            .order_by(WorkflowResultStatRecord.run_date, WorkflowResultStatRecord.workflow_id, WorkflowResultStatRecord.id)
            .offset(offset)
            .limit(limit)
        )
        return [
            {
                "workflow_id": row.workflow_id,
                "run_date": row.run_date.isoformat(),
                "success_count": row.success_count,
                "failure_count": row.failure_count,
                "skipped_count": row.skipped_count,
                "retry_count": row.retry_count,
            }
            for row in rows
        ]

    def task_instance_data_stats(self, window_from: str, window_to: str, offset: int, limit: int, project_id: int) -> list[dict[str, Any]]:
        rows = self._session.scalars(
            select(TaskInstanceDataStatRecord)
            .join(WorkflowInstanceRecord, WorkflowInstanceRecord.id == TaskInstanceDataStatRecord.instance_id)
            .join(WorkflowDefinitionRecord, WorkflowDefinitionRecord.id == WorkflowInstanceRecord.workflow_id)
            .where(TaskInstanceDataStatRecord.created_at >= window_from, TaskInstanceDataStatRecord.created_at <= window_to)
            .where(WorkflowDefinitionRecord.project_id == project_id)
            .order_by(TaskInstanceDataStatRecord.instance_id, TaskInstanceDataStatRecord.id)
            .offset(offset)
            .limit(limit)
        )
        return [
            {
                "instance_id": row.instance_id,
                "task_id": row.task_id,
                "rows_in": _metric_json(row.rows_in),
                "rows_out": _metric_json(row.rows_out),
                "error_rows": _metric_json(row.error_rows),
                "elapsed_ms": _metric_json(row.elapsed_ms),
            }
            for row in rows
        ]

    def task_data_stat_segments(self, window_from: str, window_to: str, offset: int, limit: int, project_id: int) -> list[dict[str, Any]]:
        rows = self._session.scalars(
            select(TaskDataStatSegmentRecord)
            .join(WorkflowInstanceRecord, WorkflowInstanceRecord.id == TaskDataStatSegmentRecord.instance_id)
            .join(WorkflowDefinitionRecord, WorkflowDefinitionRecord.id == WorkflowInstanceRecord.workflow_id)
            .where(TaskDataStatSegmentRecord.created_at >= window_from, TaskDataStatSegmentRecord.created_at <= window_to)
            .where(WorkflowDefinitionRecord.project_id == project_id)
            .order_by(TaskDataStatSegmentRecord.instance_id, TaskDataStatSegmentRecord.segment_key, TaskDataStatSegmentRecord.id)
            .offset(offset)
            .limit(limit)
        )
        return [
            {
                "instance_id": row.instance_id,
                "task_id": row.task_id,
                "segment_key": row.segment_key,
                "row_count": _metric_json(row.row_count),
            }
            for row in rows
        ]

    def task_data_error_samples(self, window_from: str, window_to: str, offset: int, limit: int, project_id: int) -> list[dict[str, Any]]:
        rows = self._session.scalars(
            select(TaskDataErrorSampleRecord)
            .join(WorkflowInstanceRecord, WorkflowInstanceRecord.id == TaskDataErrorSampleRecord.instance_id)
            .join(WorkflowDefinitionRecord, WorkflowDefinitionRecord.id == WorkflowInstanceRecord.workflow_id)
            .where(TaskDataErrorSampleRecord.captured_at >= window_from, TaskDataErrorSampleRecord.captured_at <= window_to)
            .where(WorkflowDefinitionRecord.project_id == project_id)
            .order_by(TaskDataErrorSampleRecord.captured_at, TaskDataErrorSampleRecord.id)
            .offset(offset)
            .limit(limit)
        )
        return [
            {
                "instance_id": row.instance_id,
                "task_id": row.task_id,
                "error_type": row.error_type,
                "sample_data": row.sample_data,
                "captured_at": row.captured_at.isoformat(),
            }
            for row in rows
        ]

    def quality_rule_links(self, window_from: str, window_to: str, offset: int, limit: int, project_id: int) -> list[dict[str, Any]]:
        rows = self._session.scalars(
            select(QualityRuleResultLinkRecord)
            .where(QualityRuleResultLinkRecord.result_at >= window_from, QualityRuleResultLinkRecord.result_at <= window_to)
            .where(QualityRuleResultLinkRecord.project_id == project_id)
            .order_by(QualityRuleResultLinkRecord.result_at, QualityRuleResultLinkRecord.id)
            .offset(offset)
            .limit(limit)
        )
        return [
            {
                "rule_id": row.rule_id,
                "rule_name": row.rule_name,
                "stat_ref": row.stat_ref,
                "alert_sent": row.alert_sent,
                "result_at": row.result_at.isoformat(),
            }
            for row in rows
        ]

    def lineage_writebacks(
        self, window_from: str, window_to: str, offset: int, limit: int, kind: str, project_id: int
    ) -> list[dict[str, Any]]:
        if kind not in VALID_RUN_KINDS:
            raise MetricsDomainError(4001, f"kind must be one of {list(VALID_RUN_KINDS)}")
        query = select(LineageWritebackRecord).where(
            LineageWritebackRecord.writeback_at >= window_from,
            LineageWritebackRecord.writeback_at <= window_to,
            LineageWritebackRecord.project_id == project_id,
        )
        if kind != "all":
            query = query.where(LineageWritebackRecord.run_kind == kind)
        rows = self._session.scalars(
            query.order_by(LineageWritebackRecord.writeback_at, LineageWritebackRecord.id).offset(offset).limit(limit)
        )
        return [
            {
                "run_id": row.run_id,
                "run_kind": row.run_kind,
                "source_entity": row.source_entity,
                "target_entity": row.target_entity,
                "writeback_at": row.writeback_at.isoformat(),
            }
            for row in rows
        ]
