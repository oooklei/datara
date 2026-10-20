"""Read/command adapter for the legacy ``/api/instances`` surface.

The old API process can use the same configured rebuild database without
coupling its ORM Base to rebuild's Base. IDs exposed by the adapter are
``r9-<workflow_instance.id>`` so they cannot collide with legacy instance IDs.
If the rebuild URL or execution schema is not configured, read adapters return
an empty result and command adapters report unavailable to the caller.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from rebuild.common.db import configure_engine
from rebuild.execution.models import (
    EXECUTION_TABLES,
    ExecutionEventRecord,
    RunOutputRecord,
    TaskInstanceRecord,
    WorkflowInstanceRecord,
)
from rebuild.execution.repository import ExecutionRepository

LEGACY_EXECUTION_PREFIX = "r9-"


def parse_execution_id(value: str) -> int | None:
    if not value.startswith(LEGACY_EXECUTION_PREFIX):
        return None
    raw = value[len(LEGACY_EXECUTION_PREFIX) :]
    return int(raw) if raw.isdigit() and int(raw) > 0 else None


def execution_instance_id(value: int) -> str:
    return f"{LEGACY_EXECUTION_PREFIX}{value}"


def _status(status: str) -> str:
    return {
        "PENDING": "submitted",
        "RUNNING": "running",
        "SUCCEEDED": "success",
        "FAILED": "failure",
        "CANCELLED": "kill",
        "STOPPED": "stopped",
    }.get(status, status.lower())


def _legacy_run_mode(trigger_type: str | None) -> str:
    return {"MANUAL": "manual", "CRON": "schedule", "TRIAL": "complement"}.get(
        trigger_type or "MANUAL", (trigger_type or "MANUAL").lower()
    )


@lru_cache(maxsize=2)
def _session_factory(url: str) -> sessionmaker:
    engine: Engine = configure_engine(url)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _factory() -> sessionmaker | None:
    url = os.environ.get("REBUILD_DB_URL", "").strip()
    if not url:
        return None
    return _session_factory(url)


def _ready(session: Session) -> bool:
    inspector = inspect(session.get_bind())
    return all(inspector.has_table(table.name) for table in EXECUTION_TABLES)


def _instance_payload(row: WorkflowInstanceRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "instanceId": execution_instance_id(row.id),
        "wfCode": row.workflow_id,
        "wfVersion": row.workflow_version_id,
        "state": _status(row.status),
        "runMode": _legacy_run_mode(row.trigger_type),
        "scheduleTime": None,
        "startTime": row.started_at.isoformat() if row.started_at else None,
        "endTime": row.finished_at.isoformat() if row.finished_at else None,
        "host": None,
        "commandType": row.instance_type,
        "createdAt": row.created_at.isoformat() if row.created_at else None,
        "source": "execution",
        "instanceType": row.instance_type,
        "trialSnapshotId": row.trial_snapshot_id,
    }


def list_instances(*, wf_code: int | None = None, state: str | None = None, run_mode: str | None = None):
    factory = _factory()
    if factory is None:
        return []
    with factory() as session:
        if not _ready(session):
            return []
        query = select(WorkflowInstanceRecord).order_by(WorkflowInstanceRecord.id.desc())
        if wf_code is not None:
            query = query.where(WorkflowInstanceRecord.workflow_id == wf_code)
        if state:
            normalized = {
                "SUBMITTED": "PENDING",
                "SUCCESS": "SUCCEEDED",
                "FAILURE": "FAILED",
                "KILL": "CANCELLED",
            }.get(state.upper(), state.upper())
            query = query.where(WorkflowInstanceRecord.status == normalized)
        if run_mode:
            normalized_mode = {"MANUAL": "MANUAL", "SCHEDULE": "CRON", "COMPLEMENT": "TRIAL"}.get(
                run_mode.upper()
            )
            if normalized_mode is None:
                return []
            query = query.where(WorkflowInstanceRecord.trigger_type == normalized_mode)
        return [_instance_payload(row) for row in session.scalars(query)]


def get_instance(instance_id: str) -> dict[str, Any] | None:
    numeric_id = parse_execution_id(instance_id)
    factory = _factory()
    if numeric_id is None or factory is None:
        return None
    with factory() as session:
        if not _ready(session):
            return None
        row = session.get(WorkflowInstanceRecord, numeric_id)
        if row is None:
            return None
        tasks = session.scalars(
            select(TaskInstanceRecord)
            .where(TaskInstanceRecord.workflow_instance_id == row.id)
            .order_by(TaskInstanceRecord.id)
        ).all()
        payload = _instance_payload(row)
        payload.update(
            {
                "variables": None,
                "recovery": 0,
                "taskInstances": [
                    {
                        "id": task.id,
                        "instanceId": instance_id,
                        "nodeId": task.task_id,
                        "nodeType": "execution",
                        "name": task.task_id,
                        "state": _status(task.status),
                        "attempt": task.current_attempt_no,
                        "loopIter": 0,
                        "delayUntil": None,
                        "startTime": task.started_at.isoformat() if task.started_at else None,
                        "endTime": task.finished_at.isoformat() if task.finished_at else None,
                        "host": None,
                        "logPath": None,
                        "outputs": _latest_outputs(session, task.id, task.current_attempt_no),
                    }
                    for task in tasks
                ],
            }
        )
        return payload


def _latest_outputs(session: Session, task_id: int, attempt_no: int):
    if attempt_no <= 0:
        return None
    row = session.scalar(
        select(RunOutputRecord)
        .where(RunOutputRecord.task_instance_id == task_id, RunOutputRecord.attempt_no == attempt_no)
        .order_by(RunOutputRecord.id.desc())
    )
    if row is None:
        return None
    try:
        return json.loads(row.output_json)
    except (TypeError, ValueError):
        return row.output_json


def list_events(instance_id: str, after_id: int | None = None) -> list[dict[str, Any]] | None:
    numeric_id = parse_execution_id(instance_id)
    factory = _factory()
    if numeric_id is None or factory is None:
        return None
    with factory() as session:
        if not _ready(session):
            return None
        if session.get(WorkflowInstanceRecord, numeric_id) is None:
            return None
        query = select(ExecutionEventRecord).where(ExecutionEventRecord.workflow_instance_id == numeric_id)
        if after_id is not None:
            query = query.where(ExecutionEventRecord.id > after_id).order_by(ExecutionEventRecord.id)
        else:
            query = query.order_by(ExecutionEventRecord.id.desc())
        rows = session.scalars(query.limit(500)).all()
        return [
            {
                "id": f"r9:{row.id}",
                "runId": instance_id,
                "nodeId": str(row.task_instance_id or ""),
                "type": row.event_kind,
                "payload": json.loads(row.payload_json) if row.payload_json else {},
                "ts": row.event_time.isoformat() if row.event_time else None,
                "source": "execution",
            }
            for row in rows
        ]


def transition(instance_id: str, new_status: str) -> dict[str, Any] | None:
    numeric_id = parse_execution_id(instance_id)
    factory = _factory()
    if numeric_id is None or factory is None:
        return None
    with factory() as session:
        if not _ready(session):
            return None
        repo = ExecutionRepository(session)
        row = repo._require_workflow_instance(numeric_id)
        if row.instance_type == "STREAM" and new_status == "CANCELLED":
            new_status = "STOPPED"
        row = repo.transition_workflow_instance(numeric_id, new_status)
        session.commit()
        return {"instanceId": instance_id, "state": _status(row.status)}


def append_retry_attempts(instance_id: str, *, failed_only: bool) -> list[dict[str, int]] | None:
    numeric_id = parse_execution_id(instance_id)
    factory = _factory()
    if numeric_id is None or factory is None:
        return None
    with factory() as session:
        if not _ready(session):
            return None
        repo = ExecutionRepository(session)
        repo._require_workflow_instance(numeric_id)
        query = select(TaskInstanceRecord).where(TaskInstanceRecord.workflow_instance_id == numeric_id)
        if failed_only:
            query = query.where(TaskInstanceRecord.status == "FAILED")
        tasks = session.scalars(query.order_by(TaskInstanceRecord.id)).all()
        attempts = []
        for task in tasks:
            attempt = repo.append_attempt(task.id)
            attempts.append({"task_instance_id": task.id, "attempt_id": attempt.id, "attempt_no": attempt.attempt_no})
        repo.append_execution_event(
            workflow_instance_id=numeric_id,
            event_kind="LEGACY_RERUN_FAILED_REQUESTED" if failed_only else "LEGACY_RERUN_REQUESTED",
            payload_json=json.dumps({"attempts": attempts}, sort_keys=True),
        )
        session.commit()
        return attempts
