"""Execution domain API — run instance endpoints (WF-23).

- Base path ``/api/v1/rebuild/execution``; envelope ``{code, msg, data}``.
- POST /runs: create a workflow instance (TRIAL/FORMAL/STREAM).
- GET /runs/{id}: instance detail + logs.
- POST /runs/{id}/cancel: cancel a running instance.
- Auth/permission: reuses RUN_INSTANCE (write) and VIEW_ALL (read) gates
  from the host app, with the same 4001/1001/1003 envelope convention.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Iterator

from fastapi import APIRouter, Body, Header
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from rebuild.execution.repository import ExecutionDomainError, ExecutionRepository
from rebuild.execution.models import TaskAttemptRecord, TaskInstanceRecord
from rebuild.identity.contracts import Permission
from rebuild.trial.repository import TrialSnapshotRepository
from rebuild.workflow.models import WorkflowDefinitionRecord, WorkflowNodeRecord, WorkflowVersionRecord
from rebuild.execution.stream_adapter import record_stream_checkpoint


class MalformedRequest(ValueError):
    """Request-frame malformation → 400 {code: 4001}."""


def build_execution_router(
    session_factory: sessionmaker,
    token_service: Any,
    active_tokens: set[str],
    project_permission_error: Callable[..., JSONResponse | None],
) -> APIRouter:
    router = APIRouter()

    def principal(token: str, authorization: str) -> dict[str, object]:
        raw = token or (authorization[7:] if authorization.startswith("Bearer ") else "")
        if not raw:
            raise ValueError("missing token")
        if raw not in active_tokens:
            raise ValueError("token revoked or unknown")
        return token_service.verify(raw)

    def unauthorized() -> JSONResponse:
        return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})

    @contextmanager
    def authorized_session(
        project_id: int, permission: Permission, token: str, authorization: str
    ) -> Iterator[Any]:
        with session_factory() as session:
            try:
                user = principal(token, authorization)
            except ValueError:
                yield unauthorized()
                return
            denial = project_permission_error(session, project_id, user, permission)
            if denial is not None:
                yield denial
                return
            yield session

    def request_error(exc: Exception) -> JSONResponse:
        if isinstance(exc, MalformedRequest):
            return JSONResponse(status_code=400, content={"code": 4001, "msg": str(exc), "data": None})
        if isinstance(exc, ExecutionDomainError):
            return JSONResponse(status_code=400, content={"code": exc.code, "msg": exc.msg, "data": None})
        return JSONResponse(status_code=400, content={"code": 4001, "msg": str(exc), "data": None})

    def frame_int(payload: dict[str, Any], key: str, minimum: int = 1) -> int:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise MalformedRequest(f"{key} must be an integer >= {minimum}")
        return value

    def frame_str(payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise MalformedRequest(f"{key} must be a non-empty string")
        return value

    def frame_optional_str(payload: dict[str, Any], key: str) -> str | None:
        value = payload.get(key)
        if value is None:
            return None
        if not isinstance(value, str):
            raise MalformedRequest(f"{key} must be a string")
        return value

    def _project_for_instance(session: Session, instance_id: int) -> int:
        instance = ExecutionRepository(session)._require_workflow_instance(instance_id)
        definition = session.get(WorkflowDefinitionRecord, instance.workflow_id)
        if definition is None:
            raise ExecutionDomainError(4404, f"workflow definition {instance.workflow_id} not found")
        return definition.project_id

    def _resolve_instance_project(session: Session, instance_id: int, requested: int) -> None:
        if _project_for_instance(session, instance_id) != requested:
            # Deliberately hide cross-project object existence.
            raise ExecutionDomainError(4404, f"workflow_instance {instance_id} not found")

    def _task_payload(task: Any) -> dict[str, Any]:
        return {
            "task_instance_id": task.id,
            "task_id": task.task_id,
            "status": task.status,
            "current_attempt_no": task.current_attempt_no,
        }

    def _attempt_payload(attempt: Any) -> dict[str, Any]:
        return {
            "attempt_id": attempt.id,
            "task_instance_id": attempt.task_instance_id,
            "attempt_no": attempt.attempt_no,
            "status": attempt.status,
        }

    # -- POST /runs ------------------------------------------------------------

    @router.post("/runs")
    def create_run(
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            workflow_id = frame_int(body, "workflow_id")
            instance_type = frame_str(body, "instance_type")
            workflow_version_id = body.get("workflow_version_id")
            if isinstance(workflow_version_id, bool) or not isinstance(workflow_version_id, int):
                raise MalformedRequest("workflow_version_id must be an integer")
            trigger_type = frame_optional_str(body, "trigger_type")
        except MalformedRequest as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.RUN_INSTANCE, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                record = ExecutionRepository(outcome).create_workflow_instance(
                    workflow_id=workflow_id,
                    workflow_version_id=workflow_version_id,
                    instance_type=instance_type,
                    trigger_type=trigger_type,
                )
                outcome.commit()
                data = {
                    "instance_id": record.id,
                    "workflow_id": record.workflow_id,
                    "instance_type": record.instance_type,
                    "status": record.status,
                    "trigger_type": record.trigger_type,
                }
            except ExecutionDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    # -- WBS EXEC-04: canonical workflow-instance endpoints ------------------

    @router.post("/workflow-instances")
    def create_workflow_instance(
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            workflow_id = frame_int(body, "workflow_id")
            instance_type = frame_str(body, "instance_type")
            trigger_type = frame_optional_str(body, "trigger_type")
            if instance_type not in {"TRIAL", "FORMAL", "STREAM"}:
                raise MalformedRequest("instance_type must be TRIAL, FORMAL, or STREAM")
        except MalformedRequest as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.RUN_INSTANCE, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                definition = outcome.get(WorkflowDefinitionRecord, workflow_id)
                if definition is None or definition.project_id != project_id:
                    raise ExecutionDomainError(4404, f"workflow definition {workflow_id} not found")
                snapshot_id = None
                task_codes: list[str] = []
                if instance_type == "TRIAL":
                    user = principal(token, authorization)
                    snapshot = TrialSnapshotRepository(outcome).create_from_draft(
                        workflow_id, created_by=int(user["user_id"])
                    )
                    snapshot_id = int(snapshot["snapshot_id"])
                    task_codes = [str(node["node_code"]) for node in snapshot["node_snapshot_json"]]
                    workflow_version_id = 0  # Draft snapshot is the binding for a trial run.
                elif instance_type == "FORMAL":
                    workflow_version_id = body.get("workflow_version_id", body.get("publish_version"))
                    if isinstance(workflow_version_id, bool) or not isinstance(workflow_version_id, int):
                        raise MalformedRequest("publish_version must be an integer workflow_version_id")
                    version = outcome.get(WorkflowVersionRecord, workflow_version_id)
                    if (
                        version is None
                        or version.definition_id != workflow_id
                        or version.status != "PUBLISHED"
                    ):
                        raise ExecutionDomainError(
                            4108, "FORMAL instance requires a published version of this workflow"
                        )
                    task_codes = list(
                        outcome.scalars(
                            select(WorkflowNodeRecord.node_code).where(
                                WorkflowNodeRecord.definition_id == workflow_id,
                                WorkflowNodeRecord.version_id == workflow_version_id,
                            )
                        )
                    )
                else:
                    workflow_version_id = body.get("workflow_version_id", 0)
                    if isinstance(workflow_version_id, bool) or not isinstance(workflow_version_id, int):
                        raise MalformedRequest("workflow_version_id must be an integer")

                repo = ExecutionRepository(outcome)
                instance = repo.create_workflow_instance(
                    workflow_id=workflow_id,
                    workflow_version_id=workflow_version_id,
                    instance_type=instance_type,
                    trigger_type=trigger_type,
                    trial_snapshot_id=snapshot_id,
                )
                tasks = [
                    repo.create_task_instance(workflow_instance_id=instance.id, task_id=code)
                    for code in task_codes
                ]
                outcome.commit()
                data = {
                    "instance_id": instance.id,
                    "workflow_id": workflow_id,
                    "workflow_version_id": instance.workflow_version_id,
                    "trial_snapshot_id": snapshot_id,
                    "instance_type": instance_type,
                    "status": instance.status,
                    "tasks": [_task_payload(task) for task in tasks],
                }
            except MalformedRequest as exc:
                outcome.rollback()
                return request_error(exc)
            except ExecutionDomainError as exc:
                outcome.rollback()
                return request_error(exc)
            except ValueError as exc:
                outcome.rollback()
                return request_error(MalformedRequest(str(exc)))
        return {"code": 0, "msg": "success", "data": data}

    @router.get("/workflow-instances/{instance_id}")
    def get_workflow_instance(
        instance_id: int,
        project_id: int | None = None,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        if project_id is None:
            return request_error(MalformedRequest("project_id is required"))
        with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                _resolve_instance_project(outcome, instance_id, project_id)
                repo = ExecutionRepository(outcome)
                instance = repo._require_workflow_instance(instance_id)
                tasks = outcome.scalars(
                    select(TaskInstanceRecord)
                    .where(TaskInstanceRecord.workflow_instance_id == instance_id)
                    .order_by(TaskInstanceRecord.id)
                ).all()
                data = {
                    "instance_id": instance.id,
                    "workflow_id": instance.workflow_id,
                    "workflow_version_id": instance.workflow_version_id,
                    "trial_snapshot_id": instance.trial_snapshot_id,
                    "instance_type": instance.instance_type,
                    "status": instance.status,
                    "trigger_type": instance.trigger_type,
                    "tasks": [_task_payload(task) for task in tasks],
                }
            except ExecutionDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    @router.post("/workflow-instances/{instance_id}/transition")
    def transition_workflow_instance(
        instance_id: int,
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            status = frame_str(body, "status")
        except MalformedRequest as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.RUN_INSTANCE, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                _resolve_instance_project(outcome, instance_id, project_id)
                instance = ExecutionRepository(outcome).transition_workflow_instance(instance_id, status)
                outcome.commit()
                data = {"instance_id": instance.id, "instance_type": instance.instance_type, "status": instance.status}
            except ExecutionDomainError as exc:
                outcome.rollback()
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    @router.get("/workflow-instances/{instance_id}/attempts")
    def list_attempts(
        instance_id: int,
        project_id: int | None = None,
        task_instance_id: int | None = None,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        if project_id is None:
            return request_error(MalformedRequest("project_id is required"))
        with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                _resolve_instance_project(outcome, instance_id, project_id)
                task_query = select(TaskInstanceRecord.id).where(TaskInstanceRecord.workflow_instance_id == instance_id)
                if task_instance_id is not None:
                    task_query = task_query.where(TaskInstanceRecord.id == task_instance_id)
                task_ids = list(outcome.scalars(task_query))
                attempts = list(
                    outcome.scalars(
                        select(TaskAttemptRecord)
                        .where(TaskAttemptRecord.task_instance_id.in_(task_ids))
                        .order_by(TaskAttemptRecord.task_instance_id, TaskAttemptRecord.attempt_no)
                    )
                ) if task_ids else []
                data = {"attempts": [_attempt_payload(attempt) for attempt in attempts]}
            except ExecutionDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    def _attempt_context(session: Session, attempt_id: int, project_id: int):
        attempt = session.get(TaskAttemptRecord, attempt_id)
        if attempt is None:
            raise ExecutionDomainError(4404, f"task_instance_attempt {attempt_id} not found")
        task = session.get(TaskInstanceRecord, attempt.task_instance_id)
        if task is None:
            raise ExecutionDomainError(4404, f"task_instance {attempt.task_instance_id} not found")
        _resolve_instance_project(session, task.workflow_instance_id, project_id)
        return attempt, task

    @router.post("/attempts/{attempt_id}/logs")
    def append_attempt_log(
        attempt_id: int,
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            message = frame_str(body, "message")
            level = body.get("level", "INFO")
            if not isinstance(level, str):
                raise MalformedRequest("level must be a string")
        except MalformedRequest as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.RUN_INSTANCE, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                attempt, task = _attempt_context(outcome, attempt_id, project_id)
                log = ExecutionRepository(outcome).append_run_log(
                    task_instance_id=task.id, attempt_no=attempt.attempt_no, message=message, level=level
                )
                outcome.commit()
                data = {"log_id": log.id, "attempt_id": attempt.id, "attempt_no": attempt.attempt_no}
            except ExecutionDomainError as exc:
                outcome.rollback()
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    @router.post("/attempts/{attempt_id}/outputs")
    def append_attempt_output(
        attempt_id: int,
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            output_json = body.get("output_json")
            if not isinstance(output_json, str) or not output_json:
                raise MalformedRequest("output_json must be a non-empty string")
        except MalformedRequest as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.RUN_INSTANCE, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                attempt, task = _attempt_context(outcome, attempt_id, project_id)
                output = ExecutionRepository(outcome).append_run_output(
                    task_instance_id=task.id, attempt_no=attempt.attempt_no, output_json=output_json
                )
                outcome.commit()
                data = {"output_id": output.id, "attempt_id": attempt.id, "attempt_no": attempt.attempt_no}
            except ExecutionDomainError as exc:
                outcome.rollback()
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    @router.post("/result-stat")
    def record_result_stat(
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            workflow_instance_id = frame_int(body, "workflow_instance_id")
            attempt_no = frame_int(body, "attempt_no", minimum=0)
            success_count = frame_int(body, "success_count", minimum=0)
            failed_count = frame_int(body, "failed_count", minimum=0)
            skipped_count = frame_int(body, "skipped_count", minimum=0)
            task_instance_id = body.get("task_instance_id")
            if task_instance_id is not None and (
                isinstance(task_instance_id, bool) or not isinstance(task_instance_id, int)
            ):
                raise MalformedRequest("task_instance_id must be an integer or null")
        except MalformedRequest as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.RUN_INSTANCE, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                _resolve_instance_project(outcome, workflow_instance_id, project_id)
                data = ExecutionRepository(outcome).record_result_stat(
                    workflow_instance_id=workflow_instance_id,
                    task_instance_id=task_instance_id,
                    attempt_no=attempt_no,
                    success_count=success_count,
                    failed_count=failed_count,
                    skipped_count=skipped_count,
                )
                outcome.commit()
            except ExecutionDomainError as exc:
                outcome.rollback()
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    @router.post("/workflow-instances/{instance_id}/checkpoints")
    def write_stream_checkpoint(
        instance_id: int,
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            stream_job_id = frame_int(body, "stream_job_id")
            partition_id = frame_str(body, "partition_id")
            offset_value = frame_int(body, "offset_value", minimum=0)
            event_time_value = frame_str(body, "event_time")
            payload = body.get("payload")
            if payload is not None and not isinstance(payload, (dict, str)):
                raise MalformedRequest("payload must be an object, JSON string, or null")
            try:
                event_time = datetime.fromisoformat(event_time_value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise MalformedRequest("event_time must be an ISO-8601 timestamp") from exc
        except MalformedRequest as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.RUN_INSTANCE, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                _resolve_instance_project(outcome, instance_id, project_id)
                data = record_stream_checkpoint(
                    outcome,
                    workflow_instance_id=instance_id,
                    stream_job_id=stream_job_id,
                    partition_id=partition_id,
                    offset_value=offset_value,
                    payload=payload,
                    event_time=event_time,
                )
                outcome.commit()
            except ExecutionDomainError as exc:
                outcome.rollback()
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    # -- GET /runs/{id} -------------------------------------------------------

    @router.get("/runs/{instance_id}")
    def get_run(
        instance_id: int,
        project_id: int | None = None,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        if project_id is None:
            return JSONResponse(
                status_code=400, content={"code": 4001, "msg": "project_id is required", "data": None}
            )
        with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                repo = ExecutionRepository(outcome)
                record = repo._require_workflow_instance(instance_id)
                logs = outcome.execute(
                    __import__("sqlalchemy").text(
                        "SELECT task_instance_id, attempt_no, level, message FROM task_instance_log "
                        "WHERE task_instance_id IN (SELECT id FROM task_instance WHERE workflow_instance_id = :iid) "
                        "ORDER BY id LIMIT 200"
                    ),
                    {"iid": instance_id},
                ).fetchall()
                data = {
                    "instance_id": record.id,
                    "workflow_id": record.workflow_id,
                    "instance_type": record.instance_type,
                    "status": record.status,
                    "trigger_type": record.trigger_type,
                    "logs": [
                        {
                            "task_instance_id": row[0],
                            "attempt_no": row[1],
                            "level": row[2],
                            "message": row[3],
                        }
                        for row in logs
                    ],
                }
            except ExecutionDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    # -- POST /runs/{id}/cancel ------------------------------------------------

    @router.post("/runs/{instance_id}/cancel")
    def cancel_run(
        instance_id: int,
        body: dict[str, Any] = Body(default={}),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        project_id = body.get("project_id")
        if isinstance(project_id, bool) or not isinstance(project_id, int):
            return JSONResponse(
                status_code=400, content={"code": 4001, "msg": "project_id must be an integer", "data": None}
            )
        with authorized_session(project_id, Permission.RUN_INSTANCE, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                repo = ExecutionRepository(outcome)
                record = repo.transition_workflow_instance(instance_id, "CANCELED")
                outcome.commit()
                data = {
                    "instance_id": record.id,
                    "status": record.status,
                }
            except ExecutionDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    return router
