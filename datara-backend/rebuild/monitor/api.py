"""Frozen B3 HTTP adapter: GET /api/v1/rebuild/monitor/nodes."""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import sessionmaker

from common.monitor import read_known_nodes, read_metrics
from common.registry import list_live_nodes
from rebuild.identity.contracts import Permission, authorize
from rebuild.monitor.service import MonitorService


def build_monitor_router(
    session_factory: sessionmaker,
    token_service: Any,
    active_tokens: Any,
    *,
    zk_provider: Callable[[], object | None] = lambda: None,
    known_nodes_reader=read_known_nodes,
    metrics_reader=read_metrics,
) -> APIRouter:
    router = APIRouter()

    def authenticate(token: str, authorization: str) -> JSONResponse | None:
        raw = token or (authorization[7:] if authorization.startswith("Bearer ") else "")
        if not raw or raw not in active_tokens:
            return _error(401, 1001, "invalid token")
        try:
            claims = token_service.verify(raw)
        except ValueError:
            return _error(401, 1001, "invalid token")
        if claims.get("capability") is not None:
            return _error(401, 1001, "invalid token")
        if not authorize(str(claims["role"]), Permission.VIEW_ALL):
            return _error(403, 1003, "permission denied")
        return None

    @router.get("/nodes")
    def monitor_nodes(token: str = Header(default=""), authorization: str = Header(default="")):
        denial = authenticate(token, authorization)
        if denial is not None:
            return denial
        with session_factory() as session:
            data = MonitorService(
                session,
                lambda: list_live_nodes(zk_provider()),
                known_nodes_reader,
                metrics_reader,
            ).nodes()
        return {"code": 0, "msg": "success", "data": data}

    return router


def _error(status: int, code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "msg": message, "data": None})
