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

from rebuild.identity.contracts import Permission
from rebuild.trial.repository import TrialSnapshotDomainError, TrialSnapshotRepository


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
        assert isinstance(exc, TrialSnapshotDomainError)
        return JSONResponse(status_code=exc.status, content=exc.payload())

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

    return router
