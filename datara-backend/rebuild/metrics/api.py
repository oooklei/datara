"""R7 metrics API — six POST endpoints matching the frozen FE contract.

Contract source (frozen): datara-web/src/services/rebuild/metricsApi.ts +
docs/increments/2026-10-17-R系列GREEN接线计划.md Task 5 契约面表.

- Base path ``/api/v1/rebuild/metrics``; envelope ``{code, msg, data}``.
- All six methods are POST with a ``TimeWindowQuery`` body; ``listLineageWritebacks``
  additionally takes ``kind`` (sql|sync|workflow|all).
- Authentication: FE ``token`` header first (frozen FE contract), Bearer fallback.
- MetricValue wrappers are returned verbatim (A7 Step 1: no derivation).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import sessionmaker

from rebuild.metrics.repository import MetricsDomainError, MetricsRepository, parse_window


class TimeWindowRequest(BaseModel):
    project_id: int = Field(ge=1)
    # `from` is a Python keyword — accept it via alias (FE contract key is `from`).
    from_: str = Field(default="", alias="from")
    to: str = ""
    offset: int = 0
    limit: int = 100
    kind: str = "all"

    model_config = {"protected_namespaces": (), "populate_by_name": True}


def build_metrics_router(
    session_factory: sessionmaker,
    token_service: Any,
    active_tokens: set[str],
    project_authorize=None,
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

    def domain_error(exc: MetricsDomainError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"code": exc.code, "msg": exc.msg, "data": None})

    def window_guard(body: TimeWindowRequest, token: str, authorization: str):
        try:
            user = principal(token, authorization)
        except ValueError:
            return unauthorized(), None
        if project_authorize is None:
            return JSONResponse(status_code=403, content={"code": 1003, "msg": "project authorization unavailable", "data": None}), None
        denied = project_authorize(body.project_id, user)
        if denied is not None:
            return denied, None
        try:
            return None, parse_window({"from": body.from_, "to": body.to, "offset": body.offset, "limit": body.limit})
        except MetricsDomainError as exc:
            return domain_error(exc), None

    def respond(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {"code": 0, "msg": "success", "data": rows}

    # -- 1. workflow-result-stats ------------------------------------------

    @router.post("/workflow-result-stats")
    def workflow_result_stats(
        body: TimeWindowRequest, token: str = Header(default=""), authorization: str = Header(default="")
    ):
        denial, window = window_guard(body, token, authorization)
        if denial is not None:
            return denial
        with session_factory() as session:
            rows = MetricsRepository(session).workflow_result_stats(*window, body.project_id)
        return respond(rows)

    # -- 2. task-instance-data-stats ----------------------------------------

    @router.post("/task-instance-data-stats")
    def task_instance_data_stats(
        body: TimeWindowRequest, token: str = Header(default=""), authorization: str = Header(default="")
    ):
        denial, window = window_guard(body, token, authorization)
        if denial is not None:
            return denial
        with session_factory() as session:
            rows = MetricsRepository(session).task_instance_data_stats(*window, body.project_id)
        return respond(rows)

    # -- 3. task-data-stat-segments -----------------------------------------

    @router.post("/task-data-stat-segments")
    def task_data_stat_segments(
        body: TimeWindowRequest, token: str = Header(default=""), authorization: str = Header(default="")
    ):
        denial, window = window_guard(body, token, authorization)
        if denial is not None:
            return denial
        with session_factory() as session:
            rows = MetricsRepository(session).task_data_stat_segments(*window, body.project_id)
        return respond(rows)

    # -- 4. task-data-error-samples -----------------------------------------

    @router.post("/task-data-error-samples")
    def task_data_error_samples(
        body: TimeWindowRequest, token: str = Header(default=""), authorization: str = Header(default="")
    ):
        denial, window = window_guard(body, token, authorization)
        if denial is not None:
            return denial
        with session_factory() as session:
            rows = MetricsRepository(session).task_data_error_samples(*window, body.project_id)
        return respond(rows)

    # -- 5. quality-rule-links ----------------------------------------------

    @router.post("/quality-rule-links")
    def quality_rule_links(
        body: TimeWindowRequest, token: str = Header(default=""), authorization: str = Header(default="")
    ):
        denial, window = window_guard(body, token, authorization)
        if denial is not None:
            return denial
        with session_factory() as session:
            rows = MetricsRepository(session).quality_rule_links(*window, body.project_id)
        return respond(rows)

    # -- 6. lineage-writebacks ----------------------------------------------

    @router.post("/lineage-writebacks")
    def lineage_writebacks(
        body: TimeWindowRequest, token: str = Header(default=""), authorization: str = Header(default="")
    ):
        denial, window = window_guard(body, token, authorization)
        if denial is not None:
            return denial
        try:
            with session_factory() as session:
                rows = MetricsRepository(session).lineage_writebacks(*window, body.kind, body.project_id)
        except MetricsDomainError as exc:
            return domain_error(exc)
        return respond(rows)

    return router
