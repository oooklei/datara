"""R8-STREAM API — job lifecycle + observation metrics + failure sample queries.

Design source: docs/increments/2026-10-14-datara-platform-rebuild-design.md §8
(realtime observation chain) + §13.7 (stream runtime tables, eight states).

- Base path ``/api/v1/rebuild/stream`` (router is mounted by the app assembly;
  this module only builds the router — mounting stays with the supervisor).
- Envelope ``{code, msg, data}``; authentication: FE ``token`` header first,
  Bearer fallback (same contract as the R7 metrics router).
- Endpoints: register/list/get jobs, state transitions (eight-state machine,
  illegal transitions → 4002), observation aggregation (POST window body),
  failure sample queries (POST window body).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import sessionmaker

from rebuild.stream.repository import StreamDomainError, StreamRepository
from rebuild.stream.alert import evaluate_failure_alert


class StreamJobCreateRequest(BaseModel):
    name: str = ""
    workflow_id: int = 0
    legacy_job_id: int | None = Field(default=None, gt=0)
    mq_topic: str = ""
    runtime_config: dict[str, Any] = Field(default_factory=dict)

    model_config = {"protected_namespaces": ()}


class StreamTransitionRequest(BaseModel):
    action: str = ""

    model_config = {"protected_namespaces": ()}


class StreamWindowRequest(BaseModel):
    # `from` is a Python keyword — accept it via alias (FE contract key is `from`).
    from_: str = Field(default="", alias="from")
    to: str = ""
    limit: int = 100

    model_config = {"protected_namespaces": (), "populate_by_name": True}


def build_stream_router(
    session_factory: sessionmaker,
    token_service: Any,
    active_tokens: set[str],
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

    def domain_error(exc: StreamDomainError) -> JSONResponse:
        status = 404 if exc.code == 4041 else 400
        return JSONResponse(status_code=status, content={"code": exc.code, "msg": exc.msg, "data": None})

    def auth_guard(token: str, authorization: str) -> JSONResponse | None:
        try:
            principal(token, authorization)
        except ValueError:
            return unauthorized()
        return None

    def respond(data: Any) -> dict[str, Any]:
        return {"code": 0, "msg": "success", "data": data}

    # -- 1. register job ------------------------------------------------------

    @router.post("/jobs")
    def register_job(body: StreamJobCreateRequest, token: str = Header(default=""), authorization: str = Header(default="")):
        denial = auth_guard(token, authorization)
        if denial is not None:
            return denial
        with session_factory() as session:
            try:
                record = StreamRepository(session).register(
                    name=body.name, workflow_id=body.workflow_id, mq_topic=body.mq_topic,
                    runtime_config=body.runtime_config, legacy_job_id=body.legacy_job_id,
                )
                session.commit()
            except StreamDomainError as exc:
                return domain_error(exc)
            return respond(StreamRepository.job_payload(record))

    # -- 2. list jobs ----------------------------------------------------------

    @router.get("/jobs")
    def list_jobs(token: str = Header(default=""), authorization: str = Header(default="")):
        denial = auth_guard(token, authorization)
        if denial is not None:
            return denial
        with session_factory() as session:
            return respond(StreamRepository(session).list_jobs())

    @router.get("/jobs/{job_id}/attempts")
    def list_attempts(job_id: int, token: str = Header(default=""), authorization: str = Header(default="")):
        denial = auth_guard(token, authorization)
        if denial is not None:
            return denial
        with session_factory() as session:
            try:
                return respond(StreamRepository(session).list_attempts(job_id))
            except StreamDomainError as exc:
                return domain_error(exc)

    @router.get("/jobs/{job_id}/checkpoints")
    def list_checkpoints(job_id: int, token: str = Header(default=""), authorization: str = Header(default="")):
        denial = auth_guard(token, authorization)
        if denial is not None:
            return denial
        with session_factory() as session:
            try:
                return respond(StreamRepository(session).latest_checkpoints(job_id))
            except StreamDomainError as exc:
                return domain_error(exc)

    @router.get("/jobs/{job_id}/metrics")
    def list_metrics(
        job_id: int, from_: str = Query(alias="from"), to: str = Query(), limit: int = Query(default=100),
        token: str = Header(default=""), authorization: str = Header(default=""),
    ):
        denial = auth_guard(token, authorization)
        if denial is not None:
            return denial
        with session_factory() as session:
            try:
                return respond(StreamRepository(session).list_metric_points(job_id, from_, to, limit))
            except StreamDomainError as exc:
                return domain_error(exc)

    @router.get("/jobs/{job_id}/recovery-events")
    def list_recovery_events(
        job_id: int, from_: str = Query(alias="from"), to: str = Query(), limit: int = Query(default=100),
        token: str = Header(default=""), authorization: str = Header(default=""),
    ):
        denial = auth_guard(token, authorization)
        if denial is not None:
            return denial
        with session_factory() as session:
            try:
                return respond(StreamRepository(session).list_recovery_events(job_id, from_, to, limit))
            except StreamDomainError as exc:
                return domain_error(exc)

    @router.get("/jobs/{job_id}/failure-alert")
    def get_failure_alert(job_id: int, token: str = Header(default=""), authorization: str = Header(default="")):
        denial = auth_guard(token, authorization)
        if denial is not None:
            return denial
        with session_factory() as session:
            try:
                result = evaluate_failure_alert(session, job_id)
                return respond(result)
            except StreamDomainError as exc:
                return domain_error(exc)

    # -- 3. job detail ---------------------------------------------------------

    @router.get("/jobs/{job_id}")
    def get_job(job_id: int, token: str = Header(default=""), authorization: str = Header(default="")):
        denial = auth_guard(token, authorization)
        if denial is not None:
            return denial
        with session_factory() as session:
            try:
                record = StreamRepository(session).get_job(job_id)
            except StreamDomainError as exc:
                return domain_error(exc)
            return respond(StreamRepository.job_payload(record))

    # -- 4. state transition (start/stop lifecycle + eight-state machine) ------

    @router.post("/jobs/{job_id}/transitions")
    def transition_job(
        job_id: int, body: StreamTransitionRequest, token: str = Header(default=""), authorization: str = Header(default="")
    ):
        denial = auth_guard(token, authorization)
        if denial is not None:
            return denial
        with session_factory() as session:
            try:
                record = StreamRepository(session).transition(job_id, body.action)
                session.commit()
            except StreamDomainError as exc:
                return domain_error(exc)
            return respond(StreamRepository.job_payload(record))

    # -- 5. observation aggregation (design §8 metric set) ----------------------

    @router.post("/jobs/{job_id}/observe")
    def observe_job(
        job_id: int, body: StreamWindowRequest, token: str = Header(default=""), authorization: str = Header(default="")
    ):
        denial = auth_guard(token, authorization)
        if denial is not None:
            return denial
        if not body.from_ or not body.to or body.from_ > body.to:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "from/to are required ISO strings", "data": None})
        with session_factory() as session:
            try:
                return respond(StreamRepository(session).observe(job_id, body.from_, body.to))
            except StreamDomainError as exc:
                return domain_error(exc)

    # -- 6. failure sample query -------------------------------------------------

    @router.post("/jobs/{job_id}/failures")
    def list_failures(
        job_id: int, body: StreamWindowRequest, token: str = Header(default=""), authorization: str = Header(default="")
    ):
        denial = auth_guard(token, authorization)
        if denial is not None:
            return denial
        if not body.from_ or not body.to or body.from_ > body.to:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "from/to are required ISO strings", "data": None})
        with session_factory() as session:
            try:
                rows = StreamRepository(session).list_failures(job_id, body.from_, body.to, body.limit)
            except StreamDomainError as exc:
                return domain_error(exc)
            return respond(rows)

    return router
