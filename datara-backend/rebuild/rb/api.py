"""R5-B rb 域 API 路由（P2-3 v3 阶段 A 挂载）。

契约来源：
- docs/increments/2026-10-19-P2-3-R5-B写入闭环实施设计-v3.md §4（wire format）
- docs/increments/2026-10-17-R系列GREEN接线计划.md Task 7（端点草案
  ``/api/v1/rebuild/sql-ide-ddl/*``）

挂载语义：
- #21 getDefinition 复用 R5-A shared read（v3 §1.2 冻结），本 router 不重复挂载。
- #22/#23 由宿主注入真实服务；#24/#25 服务属阶段 D 未交付，facade 返回
  502 CAPABILITY_UNSUPPORTED（fail-closed）。
- envelope：facade 成功返回 ``{code:0,...}``；失败 dict 的 ``code`` 即 HTTP
  状态码，路由层将其转为 ``JSONResponse(status_code=code)``，正文原样透传。
- 鉴权沿用 metrics 模式：``token`` header 优先，Bearer 兜底；401 统一 code 1001。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from rebuild.rb.facade.rb_facade import (
    ListExecutionRecordsRequest,
    PreviewImpactRequest,
    RbFacade,
    SubmitConfirmRequest,
    ValidatePolicyRequest,
)


def build_rb_router(
    facade: RbFacade,
    token_service: Any,
    active_tokens: set[str],
    project_authorize=None,
) -> APIRouter:
    """Build the rb domain router; services are bound by the host via ``facade``."""
    router = APIRouter(prefix="/api/v1/rebuild/sql-ide-ddl", tags=["sql-ide-ddl"])

    def principal(token: str, authorization: str) -> dict[str, object]:
        raw = token or (authorization[7:] if authorization.startswith("Bearer ") else "")
        if not raw:
            raise ValueError("missing token")
        if raw not in active_tokens:
            raise ValueError("token revoked or unknown")
        return token_service.verify(raw)

    def unauthorized() -> JSONResponse:
        return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})

    def guard(token: str, authorization: str, datasource_id: int):
        try:
            user = principal(token, authorization)
        except ValueError:
            return unauthorized()
        if project_authorize is None:
            return JSONResponse(status_code=403, content={"code": 1003, "msg": "project authorization unavailable", "data": None})
        return project_authorize(datasource_id, user)

    def respond(result: dict[str, Any]):
        code = int(result.get("code", 0))
        if code != 0:
            return JSONResponse(status_code=code, content=result)
        return result

    @router.post("/validate-policy")
    def validate_policy(
        body: ValidatePolicyRequest,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        denial = guard(token, authorization, body.datasourceId)
        if denial is not None:
            return denial
        return respond(facade.validate_policy(body))

    @router.post("/preview-impact")
    def preview_impact(
        body: PreviewImpactRequest,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        denial = guard(token, authorization, body.datasourceId)
        if denial is not None:
            return denial
        return respond(facade.preview_impact(body))

    @router.post("/confirm")
    def submit_confirm(
        body: SubmitConfirmRequest,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        denial = guard(token, authorization, body.datasourceId)
        if denial is not None:
            return denial
        return respond(facade.submit_confirm(body))

    @router.post("/execution-records")
    def list_execution_records(
        body: ListExecutionRecordsRequest,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        denial = guard(token, authorization, body.datasourceId)
        if denial is not None:
            return denial
        return respond(facade.list_execution_records(body))

    return router
