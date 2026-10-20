"""HTTP adapter for the frozen component specification contract."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import sessionmaker

from rebuild.component_spec.service import ComponentSpecError, ComponentSpecService


def build_component_spec_router(
    session_factory: sessionmaker,
    token_service: Any,
    active_tokens: Any,
) -> APIRouter:
    router = APIRouter()

    def authenticate(token: str, authorization: str) -> None:
        raw = token or (authorization[7:] if authorization.startswith("Bearer ") else "")
        if not raw or raw not in active_tokens:
            raise ValueError("token revoked or unknown")
        claims = token_service.verify(raw)
        if claims.get("capability") is not None:
            raise ValueError("scoped capability is not valid for component specifications")

    @router.get("/spec")
    def get_component_spec(
        if_none_match: str = Header(default="", alias="If-None-Match"),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        try:
            authenticate(token, authorization)
        except ValueError:
            return JSONResponse(
                status_code=401,
                content={"code": 1001, "msg": "invalid token", "data": None},
            )
        try:
            with session_factory() as session:
                document = ComponentSpecService(session).published_document()
        except ComponentSpecError:
            return JSONResponse(
                status_code=500,
                content={"code": 5001, "msg": "published component specification is invalid", "data": None},
            )
        if if_none_match == document.etag:
            return Response(status_code=304, headers={"ETag": document.etag})
        return Response(
            content=document.body,
            media_type="application/json",
            headers={"ETag": document.etag},
        )

    return router
