"""Trial-run domain API — draft snapshot endpoints (WF-12).

- Base path ``/api/v1/rebuild/trial``; envelope ``{code, msg, data}``.
- POST /definitions/{id}/snapshot: generate or refresh the draft snapshot.
- GET /snapshots/{snapshot_id}: fetch a snapshot by id.
- Auth/permission: reuses EDIT_DEFINITION (write) and VIEW_ALL (read) gates
  from the host app, with the same 4001/1001/1003 envelope convention.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator

from fastapi import APIRouter, Body, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from rebuild.execution.repository import ExecutionDomainError, ExecutionRepository
from rebuild.execution.models import WorkflowInstanceRecord
from rebuild.identity.contracts import Permission
from rebuild.trial.repository import TrialSnapshotDomainError, TrialSnapshotRepository
from rebuild.trial.runner import TrialRunner, TrialRunnerError, TrialRunOptions
from rebuild.trial.promote import PromoteError, TrialPromoter
from rebuild.trial.output import TrialOutputAggregator
from rebuild.workflow.models import WorkflowDefinitionRecord


class MalformedRequest(ValueError):
    """Request-frame malformation → 400 {code: 4001}."""


def build_trial_router(
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
        if isinstance(exc, TrialSnapshotDomainError):
            return JSONResponse(status_code=exc.status, content=exc.payload())
        if isinstance(exc, TrialRunnerError):
            return JSONResponse(status_code=exc.status, content={"code": exc.code, "msg": exc.msg, "data": None})
        if isinstance(exc, PromoteError):
            return JSONResponse(status_code=exc.status, content={"code": exc.code, "msg": exc.msg, "data": None})
        if isinstance(exc, ExecutionDomainError):
            return JSONResponse(status_code=400, content={"code": exc.code, "msg": exc.msg, "data": None})
        return JSONResponse(status_code=400, content={"code": 4001, "msg": str(exc), "data": None})

    def frame_int(payload: dict[str, Any], key: str, minimum: int = 1) -> int:
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise MalformedRequest(f"{key} must be an integer >= {minimum}")
        return value

    # -- POST /definitions/{definition_id}/snapshot --------------------------

    @router.post("/definitions/{definition_id}/snapshot")
    def create_snapshot(
        definition_id: int,
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
        except MalformedRequest as exc:
            return request_error(exc)
        with authorized_session(project_id, Permission.EDIT_DEFINITION, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                user = principal(token, authorization)
                user_id = int(user["user_id"])  # type: ignore[arg-type]
            except (ValueError, KeyError):
                user_id = None
            try:
                data = TrialSnapshotRepository(outcome).create_from_draft(
                    definition_id, created_by=user_id
                )
                outcome.commit()
            except TrialSnapshotDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    # -- GET /snapshots/{snapshot_id} ----------------------------------------

    @router.get("/snapshots/{snapshot_id}")
    def get_snapshot(
        snapshot_id: int,
        project_id: int | None = None,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        # For GET, we need project_id for permission check; require it as query param.
        if project_id is None:
            return JSONResponse(
                status_code=400, content={"code": 4001, "msg": "project_id is required", "data": None}
            )
        with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                data = TrialSnapshotRepository(outcome).get(snapshot_id)
            except TrialSnapshotDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    # -- POST /definitions/{definition_id}/run -------------------------------

    @router.post("/definitions/{definition_id}/run")
    def run_trial(
        definition_id: int,
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            snapshot_id = frame_int(body, "snapshot_id")
        except MalformedRequest as exc:
            return request_error(exc)

        options_raw = body.get("options")
        if options_raw is not None and not isinstance(options_raw, dict):
            return request_error(MalformedRequest("options must be an object"))

        options = TrialRunOptions(
            node_codes=options_raw.get("node_codes") if options_raw else None,
            start_node=options_raw.get("start_node") if options_raw else None,
            test_variables=options_raw.get("test_variables") if options_raw else None,
            dependency_mock=options_raw.get("dependency_mock") if options_raw else None,
            dry_run=bool(options_raw.get("dry_run", False)) if options_raw else False,
            sql_precheck=bool(options_raw.get("sql_precheck", False)) if options_raw else False,
        )

        with authorized_session(project_id, Permission.EDIT_DEFINITION, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                user = principal(token, authorization)
                user_id = int(user["user_id"])  # type: ignore[arg-type]
            except (ValueError, KeyError):
                user_id = None
            try:
                runner = TrialRunner(outcome)
                result = runner.run(
                    definition_id=definition_id,
                    snapshot_id=snapshot_id,
                    project_id=project_id,
                    created_by=user_id,
                    options=options,
                )
                outcome.commit()
            except TrialRunnerError as exc:
                return request_error(exc)
            except TrialSnapshotDomainError as exc:
                return request_error(exc)
        return {
            "code": 0,
            "msg": "success",
            "data": {
                "instance_id": result.instance_id,
                "status": result.status,
                "task_count": result.task_count,
                "tasks": result.tasks,
                "plan": result.plan,
            },
        }

    # -- POST /definitions/{definition_id}/promote ----------------------------

    @router.post("/definitions/{definition_id}/promote")
    def promote_trial(
        definition_id: int,
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            project_id = frame_int(body, "project_id")
            instance_id = frame_int(body, "instance_id")
        except MalformedRequest as exc:
            return request_error(exc)

        remark = body.get("remark", "")
        if remark is not None and not isinstance(remark, str):
            return request_error(MalformedRequest("remark must be a string"))

        with authorized_session(project_id, Permission.EDIT_DEFINITION, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                user = principal(token, authorization)
                user_id = int(user["user_id"])  # type: ignore[arg-type]
            except (ValueError, KeyError):
                user_id = None
            try:
                promoter = TrialPromoter(outcome)
                data = promoter.promote(
                    definition_id=definition_id,
                    instance_id=instance_id,
                    project_id=project_id,
                    remark=remark or "",
                    promoted_by=user_id,
                )
                outcome.commit()
            except PromoteError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    # -- WF-26: POST /runs ----------------------------------------------------

    @router.post("/runs")
    def create_run(
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """Create and execute a TRIAL run from a draft snapshot."""
        try:
            project_id = frame_int(body, "project_id")
            definition_id = frame_int(body, "definition_id")
            snapshot_id = frame_int(body, "snapshot_id")
        except MalformedRequest as exc:
            return request_error(exc)

        options_raw = body.get("options")
        if options_raw is not None and not isinstance(options_raw, dict):
            return request_error(MalformedRequest("options must be an object"))

        options = TrialRunOptions(
            node_codes=options_raw.get("node_codes") if options_raw else None,
            start_node=options_raw.get("start_node") if options_raw else None,
            test_variables=options_raw.get("test_variables") if options_raw else None,
            dependency_mock=options_raw.get("dependency_mock") if options_raw else None,
            dry_run=bool(options_raw.get("dry_run", False)) if options_raw else False,
            sql_precheck=bool(options_raw.get("sql_precheck", False)) if options_raw else False,
        )

        with authorized_session(project_id, Permission.EDIT_DEFINITION, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                user = principal(token, authorization)
                user_id = int(user["user_id"])  # type: ignore[arg-type]
            except (ValueError, KeyError):
                user_id = None
            try:
                runner = TrialRunner(outcome)
                result = runner.run(
                    definition_id=definition_id,
                    snapshot_id=snapshot_id,
                    project_id=project_id,
                    created_by=user_id,
                    options=options,
                )
                outcome.commit()
            except TrialRunnerError as exc:
                return request_error(exc)
            except TrialSnapshotDomainError as exc:
                return request_error(exc)
        return {
            "code": 0,
            "msg": "success",
            "data": {
                "instance_id": result.instance_id,
                "status": result.status,
                "task_count": result.task_count,
                "tasks": result.tasks,
                "plan": result.plan,
            },
        }

    # -- WF-26: GET /runs/{run_id} --------------------------------------------

    @router.get("/runs/{run_id}")
    def get_run(
        run_id: int,
        project_id: int | None = None,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """Get TRIAL run output (logs/variables/stats)."""
        if project_id is None:
            return JSONResponse(
                status_code=400, content={"code": 4001, "msg": "project_id is required", "data": None}
            )
        with authorized_session(project_id, Permission.VIEW_ALL, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                # Verify the instance exists and belongs to this project.
                instance = outcome.get(WorkflowInstanceRecord, run_id)
                if instance is None:
                    return JSONResponse(
                        status_code=404, content={"code": 4404, "msg": f"workflow instance {run_id} not found", "data": None}
                    )
                definition = outcome.get(WorkflowDefinitionRecord, instance.workflow_id)
                if definition is None or definition.project_id != project_id:
                    return JSONResponse(
                        status_code=404, content={"code": 4404, "msg": f"workflow instance {run_id} not found", "data": None}
                    )
                aggregator = TrialOutputAggregator(outcome)
                data = aggregator.aggregate(run_id)
            except ExecutionDomainError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    # -- WF-26: POST /runs/{run_id}/promote -----------------------------------

    @router.post("/runs/{run_id}/promote")
    def promote_run(
        run_id: int,
        body: dict[str, Any] = Body(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """Promote a TRIAL run to a formal workflow version."""
        try:
            project_id = frame_int(body, "project_id")
        except MalformedRequest as exc:
            return request_error(exc)

        remark = body.get("remark", "")
        if remark is not None and not isinstance(remark, str):
            return request_error(MalformedRequest("remark must be a string"))

        with authorized_session(project_id, Permission.EDIT_DEFINITION, token, authorization) as outcome:
            if isinstance(outcome, JSONResponse):
                return outcome
            try:
                # Resolve definition_id from the instance.
                instance = outcome.get(WorkflowInstanceRecord, run_id)
                if instance is None:
                    return JSONResponse(
                        status_code=404, content={"code": 4404, "msg": f"workflow instance {run_id} not found", "data": None}
                    )
                definition = outcome.get(WorkflowDefinitionRecord, instance.workflow_id)
                if definition is None or definition.project_id != project_id:
                    return JSONResponse(
                        status_code=404, content={"code": 4404, "msg": f"workflow instance {run_id} not found", "data": None}
                    )
                user = principal(token, authorization)
                user_id = int(user["user_id"])  # type: ignore[arg-type]
            except (ValueError, KeyError):
                user_id = None
            try:
                promoter = TrialPromoter(outcome)
                data = promoter.promote(
                    definition_id=definition.id,
                    instance_id=run_id,
                    project_id=project_id,
                    remark=remark or "",
                    promoted_by=user_id,
                )
                outcome.commit()
            except PromoteError as exc:
                return request_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    return router
