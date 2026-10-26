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

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import sessionmaker

from rebuild.stream.repository import StreamDomainError, StreamRepository
from rebuild.stream.alert import evaluate_failure_alert
from rebuild.stream.processor import StreamProcessingError, aggregate_window, fuse_streams
from rebuild.identity.contracts import Permission


class StreamJobCreateRequest(BaseModel):
    project_id: int = Field(default=0, ge=0)
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
    # Keep observation/failure queries bounded at the API boundary.  The
    # repository also caps reads, but accepting zero/negative values here
    # produces an ambiguous empty observation and lets clients bypass the
    # documented 500-row ceiling.
    limit: int = Field(default=100, ge=1, le=500)

    model_config = {"protected_namespaces": (), "populate_by_name": True}


class StreamCheckpointRequest(BaseModel):
    partition_id: str = ""
    offset: int = Field(ge=0)
    payload: dict[str, Any] | str | None = None
    event_time: str = ""

    model_config = {"protected_namespaces": ()}


class StreamProduceRequest(BaseModel):
    count: int = Field(default=1, ge=1, le=10000)
    partition_id: str = "p0"
    start_offset: int = Field(default=0, ge=0)
    event_time: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    schema_: dict[str, str] = Field(default_factory=dict, alias="schema")
    aggregate: dict[str, Any] | None = None

    model_config = {"protected_namespaces": (), "populate_by_name": True}


class StreamFuseRequest(BaseModel):
    key_field: str = "id"
    streams: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    event_time: str = ""

    model_config = {"protected_namespaces": ()}


def build_stream_router(
    session_factory: sessionmaker,
    token_service: Any,
    active_tokens: set[str],
    project_permission_error: Any | None = None,
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

    def auth_guard(
        token: str,
        authorization: str,
        *,
        project_id: int | None = None,
        job_id: int | None = None,
        permission: Permission = Permission.VIEW_ALL,
    ) -> JSONResponse | None:
        try:
            claims = principal(token, authorization)
        except ValueError:
            return unauthorized()
        if project_permission_error is None:
            return None
        if project_id is not None and project_id <= 0:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "project_id is required", "data": None})
        with session_factory() as session:
            try:
                scoped_project_id = project_id if project_id is not None else StreamRepository(session).job_project_id(int(job_id))
            except StreamDomainError as exc:
                return domain_error(exc)
            denial = project_permission_error(session, scoped_project_id, claims, permission)
            if denial is not None:
                return denial
        return None

    def respond(data: Any) -> dict[str, Any]:
        return {"code": 0, "msg": "success", "data": data}

    def require_running(job: Any) -> JSONResponse | None:
        """Gate data-plane writes on the RUNNING lifecycle state.

        Producer/fusion endpoints represent live stream processing, so accepting
        events while a job is CREATED/PAUSED/STOPPED would create observations
        outside the declared runtime state machine.
        """
        if job.state != "RUNNING":
            return JSONResponse(
                status_code=400,
                content={"code": 4002, "msg": "stream job must be RUNNING for data-plane processing", "data": None},
            )
        return None

    # -- 1. register job ------------------------------------------------------

    @router.post("/jobs")
    def register_job(body: StreamJobCreateRequest, token: str = Header(default=""), authorization: str = Header(default="")):
        denial = auth_guard(token, authorization, project_id=body.project_id, permission=Permission.EDIT_DEFINITION)
        if denial is not None:
            return denial
        with session_factory() as session:
            try:
                record = StreamRepository(session).register(
                    name=body.name, workflow_id=body.workflow_id, mq_topic=body.mq_topic,
                    runtime_config=body.runtime_config, legacy_job_id=body.legacy_job_id,
                    project_id=body.project_id if project_permission_error is not None else None,
                )
                session.commit()
            except StreamDomainError as exc:
                return domain_error(exc)
            return respond(StreamRepository.job_payload(record))

    # -- 2. list jobs ----------------------------------------------------------

    @router.get("/jobs")
    def list_jobs(project_id: int = Query(default=0, ge=0), token: str = Header(default=""), authorization: str = Header(default="")):
        denial = auth_guard(token, authorization, project_id=project_id)
        if denial is not None:
            return denial
        with session_factory() as session:
            return respond(StreamRepository(session).list_jobs(project_id if project_permission_error is not None else None))

    @router.get("/jobs/{job_id}/attempts")
    def list_attempts(job_id: int, token: str = Header(default=""), authorization: str = Header(default="")):
        denial = auth_guard(token, authorization, job_id=job_id)
        if denial is not None:
            return denial
        with session_factory() as session:
            try:
                return respond(StreamRepository(session).list_attempts(job_id))
            except StreamDomainError as exc:
                return domain_error(exc)

    @router.get("/jobs/{job_id}/checkpoints")
    def list_checkpoints(job_id: int, token: str = Header(default=""), authorization: str = Header(default="")):
        denial = auth_guard(token, authorization, job_id=job_id)
        if denial is not None:
            return denial
        with session_factory() as session:
            try:
                return respond(StreamRepository(session).latest_checkpoints(job_id))
            except StreamDomainError as exc:
                return domain_error(exc)

    @router.post("/jobs/{job_id}/checkpoints")
    def write_checkpoint(job_id: int, body: StreamCheckpointRequest, token: str = Header(default=""), authorization: str = Header(default="")):
        denial = auth_guard(token, authorization, job_id=job_id)
        if denial is not None:
            return denial
        if not body.partition_id.strip() or not body.event_time.strip():
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "partition_id and event_time are required", "data": None})
        from datetime import datetime
        try:
            event_time = datetime.fromisoformat(body.event_time.replace("Z", "+00:00"))
        except ValueError:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "event_time must be ISO-8601", "data": None})
        with session_factory() as session:
            try:
                repository = StreamRepository(session)
                repository.write_checkpoint(job_id, body.partition_id, body.offset, body.payload, event_time)
                session.commit()
                return respond(repository.latest_checkpoint(job_id, body.partition_id))
            except StreamDomainError as exc:
                return domain_error(exc)

    @router.post("/jobs/{job_id}/produce")
    def produce_events(job_id: int, body: StreamProduceRequest, token: str = Header(default=""), authorization: str = Header(default="")):
        """Generate deterministic events for live observation and acceptance runs.

        This endpoint is intentionally bounded and authenticated. It is a test
        producer, not a broker replacement: every generated event is persisted
        as a checkpoint and one cumulative metric snapshot is recorded.
        """
        denial = auth_guard(token, authorization, job_id=job_id)
        if denial is not None:
            return denial
        if not body.partition_id.strip():
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "partition_id is required", "data": None})
        try:
            event_time = datetime.fromisoformat(body.event_time.replace("Z", "+00:00")) if body.event_time else datetime.now(timezone.utc)
        except ValueError:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "event_time must be ISO-8601", "data": None})
        for field, expected in body.schema_.items():
            if field not in body.payload or not isinstance(expected, str):
                return JSONResponse(status_code=400, content={"code": 4001, "msg": f"payload does not satisfy schema field {field}", "data": None})
            value = body.payload[field]
            actual = type(value).__name__
            # The stream form uses JSON-schema-ish names while Python's
            # runtime type names are ``int``/``float``.  Accept the common
            # aliases so a valid integer/number payload is not rejected by
            # the API adapter (the persisted payload remains unchanged).
            aliases = {
                "integer": {"int"},
                "number": {"int", "float"},
                "boolean": {"bool"},
                "object": {"dict"},
                "array": {"list"},
                "string": {"str"},
            }
            accepted = aliases.get(expected, {expected})
            if actual not in accepted:
                return JSONResponse(status_code=400, content={"code": 4001, "msg": f"payload field {field} has type {actual}, expected {expected}", "data": None})
        with session_factory() as session:
            try:
                repository = StreamRepository(session)
                job = repository.get_job(job_id)
                denial = require_running(job)
                if denial is not None:
                    return denial
                offset = body.start_offset
                if "start_offset" not in body.model_fields_set:
                    checkpoint = repository.latest_checkpoint(job_id, body.partition_id)
                    if checkpoint is not None:
                        offset = int(checkpoint["offset_value"]) + 1
                events: list[dict[str, Any]] = []
                for index in range(body.count):
                    payload = {**body.payload, "sequence": index, "partition": body.partition_id}
                    events.append(payload)
                    repository.write_checkpoint(job_id, body.partition_id, offset + index, payload, event_time)
                window_result: dict[str, Any] = {"producer": "deterministic", "records": body.count}
                if body.aggregate is not None:
                    key_field = body.aggregate.get("key_field")
                    value_field = body.aggregate.get("value_field")
                    window_size = body.aggregate.get("window_size", body.count)
                    if not isinstance(key_field, str) or not isinstance(value_field, str) or not isinstance(window_size, int):
                        raise StreamProcessingError("aggregate requires key_field, value_field, window_size")
                    window_result["aggregate"] = aggregate_window(events, key_field=key_field, value_field=value_field, window_size=window_size)
                metric = repository.append_metric_snapshot(
                    job_id,
                    {
                        "attempt_no": job.attempt_no,
                        "produce_rate": body.count,
                        "consume_rate": body.count,
                        "process_rate": body.count,
                        "input_count": body.count,
                        "output_count": body.count,
                        "success_count": body.count,
                        "failure_count": 0,
                        "offset_value": offset + body.count - 1,
                        "window_result": window_result,
                    },
                    event_time,
                )
                session.commit()
                return respond({"job_id": job_id, "partition_id": body.partition_id, "produced": body.count, "last_offset": offset + body.count - 1, "metric": metric})
            except StreamProcessingError as exc:
                return JSONResponse(status_code=400, content={"code": 4001, "msg": str(exc), "data": None})
            except StreamDomainError as exc:
                return domain_error(exc)

    @router.post("/jobs/{job_id}/fuse")
    def fuse_events(job_id: int, body: StreamFuseRequest, token: str = Header(default=""), authorization: str = Header(default="")):
        """Fuse two or more named event streams and persist the observation result."""
        denial = auth_guard(token, authorization, job_id=job_id)
        if denial is not None:
            return denial
        try:
            event_time = datetime.fromisoformat(body.event_time.replace("Z", "+00:00")) if body.event_time else datetime.now(timezone.utc)
            fused = fuse_streams(body.streams, key_field=body.key_field)
        except (ValueError, StreamProcessingError) as exc:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": str(exc), "data": None})
        with session_factory() as session:
            try:
                repository = StreamRepository(session)
                job = repository.get_job(job_id)
                denial = require_running(job)
                if denial is not None:
                    return denial
                metric = repository.append_metric_snapshot(
                    job_id,
                    {"attempt_no": job.attempt_no, "input_count": sum(len(items) for items in body.streams.values()),
                     "output_count": len(fused), "success_count": len(fused), "failure_count": 0,
                     "process_rate": len(fused), "window_result": {"fusion": fused}},
                    event_time,
                )
                session.commit()
                return respond({"job_id": job_id, "fused": len(fused), "metric": metric, "result": fused})
            except StreamDomainError as exc:
                return domain_error(exc)

    @router.get("/jobs/{job_id}/metrics")
    def list_metrics(
        job_id: int, from_: str = Query(alias="from"), to: str = Query(), limit: int = Query(default=100),
        token: str = Header(default=""), authorization: str = Header(default=""),
    ):
        denial = auth_guard(token, authorization, job_id=job_id)
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
        denial = auth_guard(token, authorization, job_id=job_id)
        if denial is not None:
            return denial
        with session_factory() as session:
            try:
                return respond(StreamRepository(session).list_recovery_events(job_id, from_, to, limit))
            except StreamDomainError as exc:
                return domain_error(exc)

    @router.get("/jobs/{job_id}/failure-alert")
    def get_failure_alert(job_id: int, token: str = Header(default=""), authorization: str = Header(default="")):
        denial = auth_guard(token, authorization, job_id=job_id)
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
        denial = auth_guard(token, authorization, job_id=job_id)
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
        denial = auth_guard(token, authorization, job_id=job_id)
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
        denial = auth_guard(token, authorization, job_id=job_id)
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
        denial = auth_guard(token, authorization, job_id=job_id)
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
