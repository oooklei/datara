"""I18 数仓建模 API（WBS 17.2 · 五步迁移第②③④步）。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md`
A6 分片 22 端点（A6-1~A6-22）；迁移源 `datara-backend/api/model.py`（只读，下线留 17.6 第⑤步）。

- 路由前缀 `/api/v1/rebuild`（R-30 四分片承载域 models=17.2）；域内保留旧相对路径，
  故 A6-1 落 `/api/v1/rebuild/model-dicts`、A6-2 落 `/api/v1/rebuild/models`（与冻结清单
  映射表「旧 `/api/v1/models` → 新 `/api/v1/rebuild/models`」逐字一致）。
- 信封 `{code, msg, data}`（R-31）；错误码旧 4xxx/8xxx 原样保留（R-32，R2 注记：禁从
  `common/resp.py` 导入常量，须在域内显式定义并保留语义映射）。
- 鉴权 `TokenService` + 逐端点权限映射（R-33，`PERMISSION_MAP`）：读端点 `view_all`
  （旧侧 `get_current_user`），写端点 `model:write` ↔ `Permission.EDIT_DEFINITION`
  （旧侧锚 `api/auth.py:38` admin / `:42` dev —— R3 注记校正后行号；admin+developer 两角色同权）。
- 静态路由（`/models/er`）须先于 `/models/{model_id}` 注册，否则 `er` 被吞为 `model_id`
  （旧侧约束，实锚 `api/model.py:185-197`）。
- 三段子路由（A6-9 `/fields`、A6-10 `/publish`、A6-11 `/redraft`、A6-12/13 `/versions`、
  A6-16 `/ddl`）尾段皆**字面量**，与两段的 `/models/{model_id}`、`/models/er` 段数不同，
  且彼此尾段互异 —— **互不前缀吞并**（Starlette 按段数 + 尾段字面匹配）；
  各自契约测试以「其前无其他同段数动态尾段路由」+ 行为验证锁定可达性。
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from rebuild.identity.contracts import Permission, authorize
from rebuild.model.errors import ModelDomainError, fail
from rebuild.model.repository import ErRepository, ModelDictRepository, ModelRepository
from rebuild.model.service import ModelCreateInput, ModelService, ModelUpdateInput


def _update_input(body: ModelUpdateBody) -> ModelUpdateInput:
    return ModelUpdateInput(
        name=body.name,
        remark=body.remark,
        owner=body.owner,
        security_level=body.securityLevel,
        ds_id=body.dsId,
        db_name=body.dbName,
    )


class ModelCreateBody(BaseModel):
    """A6-3 新建模型入参（旧侧 `ModelCreateBody` 六字段，字段名/缺省值照抄）。"""

    name: str
    code: str
    layer: str
    engine: str
    type: str = "明细表"
    bizDomain: str = ""


class ModelUpdateBody(BaseModel):
    """A6-7 模型更新入参（旧侧 `ModelUpdateBody`：六字段皆可选，`None` = 不修改）。"""

    name: Optional[str] = None
    remark: Optional[str] = None
    owner: Optional[str] = None
    securityLevel: Optional[str] = None
    dsId: Optional[int] = None
    dbName: Optional[str] = None


class ErBody(BaseModel):
    """A6-5 ER 保存入参（旧侧 `ErBody` 照抄：`relations` 三键 removed/added/updated 皆 list[dict]）。"""

    positions: dict[str, dict[str, float]] = {}
    relations: dict[str, list[dict]] = {}


class FieldsBody(BaseModel):
    """A6-9 字段全量保存入参（旧侧 `FieldsBody` 照抄：`rev` 乐观锁 + `fields` 全量）。"""

    rev: int
    fields: list[dict] = []


class VersionBody(BaseModel):
    """A6-13 版本快照创建入参（旧侧 `VersionBody` 照抄：`changeNote` 缺省空串）。"""

    changeNote: str = ""


# R-33 逐端点权限映射（写端点 `model:write` ↔ rebuild `EDIT_DEFINITION`）。
# 旧侧锚：`api/auth.py:38`（admin 段）/ `:42`（dev 段）——R3 注记校正后的行号。
PERMISSION_MAP = {
    "dicts": Permission.VIEW_ALL,
    "list": Permission.VIEW_ALL,
    "create": Permission.EDIT_DEFINITION,
}


def build_model_router(
    session_factory: sessionmaker,
    token_service: Any,
    active_tokens: set[str],
) -> APIRouter:
    router = APIRouter()

    def principal(token: str, authorization: str, operation: str):
        """FE `token` header 优先（冻结 FE 契约），Bearer 回退 + 权限校验（R-33）。"""
        raw = token or (authorization[7:] if authorization.startswith("Bearer ") else "")
        if not raw:
            return unauthorized()
        if raw not in active_tokens:
            return unauthorized()
        try:
            claims = token_service.verify(raw)
        except ValueError:
            return unauthorized()
        if not authorize(str(claims["role"]), PERMISSION_MAP[operation]):
            return JSONResponse(status_code=403, content=fail(1004, "无操作权限"))
        return claims

    def unauthorized() -> JSONResponse:
        return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})

    # -- A6-1. model-dicts: GET /model-dicts --------------------------------

    @router.get("/model-dicts")
    def model_dicts(
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """分层/业务域/引擎字典一次取齐（列表与设计器共用；读端点登录即可）。"""
        denial = principal(token, authorization, "dicts")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            data = ModelDictRepository(session).dicts()
        return {"code": 0, "msg": "success", "data": data}

    # -- A6-2. models: GET /models ------------------------------------------

    @router.get("/models")
    def list_models(
        layer: str = "",
        status: str = "",
        domain: str = "",
        keyword: str = "",
        page: int = Query(default=1, ge=1),
        size: int = Query(default=50, ge=1, le=200),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """列表 + 双维统计（交叉过滤，I18 §4.1：分层计数叠 domain，域计数叠 layer）。"""
        denial = principal(token, authorization, "list")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            data = ModelRepository(session).list_models(
                layer=layer, status=status, domain=domain, keyword=keyword, page=page, size=size
            )
        return {"code": 0, "msg": "success", "data": data}

    # -- A6-4. models: GET /models/er（静态路由，须先于 /models/{model_id}）--

    @router.get("/models/er")
    def get_er(
        layer: str = "",
        domain: str = "",
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """ER 图读取（nodes + edges；迁移源实锚 `api/model.py:421-431`）。"""
        denial = principal(token, authorization, "list")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            data = ErRepository(session).graph(layer=layer, domain=domain)
        return {"code": 0, "msg": "success", "data": data}

    # -- A6-5. models: PUT /models/er（静态路由，须先于 /models/{model_id}）--

    @router.put("/models/er")
    def put_er(
        body: ErBody,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """ER 图保存（positions 全量覆盖 + relations 增量 diff；旧侧 `api/model.py:435-453`）。"""
        denial = principal(token, authorization, "create")
        if isinstance(denial, JSONResponse):
            return denial
        claims = denial
        with session_factory() as session:
            try:
                saved = ModelService(session, str(claims["username"])).save_er(
                    body.positions, body.relations
                )
            except ModelDomainError as exc:
                return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.message, exc.data))
        return {"code": 0, "msg": "success", "data": {"saved": saved}}

    # -- A6-6. models: GET /models/{model_id} -------------------------------
    # 静态段（/models/er 两法）必须先注册，否则 `er` 被吞为 model_id 并 422
    # （旧侧注记 `api/model.py:184`；次序由 test_model_detail_api /
    #  test_model_er_read_api 的 per-method 路由表断言锁定）

    @router.get("/models/{model_id}")
    def get_model(
        model_id: int,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """模型详情（ModelRow + fields，seq 升序；旧侧 `api/model.py:198-206`）。"""
        denial = principal(token, authorization, "list")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            try:
                data = ModelService(session, "").detail(model_id)
            except ModelDomainError as exc:
                return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.message, exc.data))
        return {"code": 0, "msg": "success", "data": data}

    # -- A6-7. models: PUT /models/{model_id} -------------------------------

    @router.put("/models/{model_id}")
    def update_model(
        model_id: int,
        body: ModelUpdateBody,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """模型更新（六可选字段；旧侧 `api/model.py:216-233`）。"""
        denial = principal(token, authorization, "create")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            try:
                data = ModelService(session, "").update(model_id, _update_input(body))
            except ModelDomainError as exc:
                return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.message, exc.data))
        return {"code": 0, "msg": "success", "data": data}

    # -- A6-8. models: DELETE /models/{model_id} ----------------------------

    @router.delete("/models/{model_id}")
    def delete_model(
        model_id: int,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """模型删除（已物理化拒删 + 血缘引用防护 + 级联；旧侧 `api/model.py:239-258`）。"""
        denial = principal(token, authorization, "create")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            try:
                result = ModelService(session, "").delete(model_id)
            except ModelDomainError as exc:
                return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.message, exc.data))
        return {"code": 0, "msg": "success", "data": result}

    # -- A6-9. models: PUT /models/{model_id}/fields -------------------------
    # 三段路径，与 `/models/{model_id}`（两段）不构成前缀吞并；静态段 `/models/er`
    # 仍为两段故亦不冲突。次序由 test_model_fields_api 的 per-method 路由表断言锁定。

    @router.put("/models/{model_id}/fields")
    def save_fields(
        model_id: int,
        body: FieldsBody,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """字段全量保存（乐观锁 rev；仅 draft 可保存；旧侧 `api/model.py:288-305`）。"""
        denial = principal(token, authorization, "create")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            try:
                rev = ModelService(session, "").save_fields(model_id, body.rev, body.fields)
            except ModelDomainError as exc:
                return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.message, exc.data))
        return {"code": 0, "msg": "success", "data": {"rev": rev}}

    # -- A6-10. models: POST /models/{model_id}/publish ----------------------
    # 三段路径，与两段 `/models/{model_id}` 及 `/models/er` 互不前缀吞并（同 A6-9）。

    @router.post("/models/{model_id}/publish")
    def publish_model(
        model_id: int,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """模型发布（draft → published；无审批流，旧侧 `api/model.py:311-321`）。"""
        denial = principal(token, authorization, "create")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            try:
                data = ModelService(session, "").publish(model_id)
            except ModelDomainError as exc:
                return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.message, exc.data))
        return {"code": 0, "msg": "success", "data": data}

    # -- A6-11. models: POST /models/{model_id}/redraft ----------------------

    @router.post("/models/{model_id}/redraft")
    def redraft_model(
        model_id: int,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """模型回草稿（→ draft 且 version 递增；旧侧 `api/model.py:342-352`）。"""
        denial = principal(token, authorization, "create")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            try:
                data = ModelService(session, "").redraft(model_id)
            except ModelDomainError as exc:
                return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.message, exc.data))
        return {"code": 0, "msg": "success", "data": data}

    # -- A6-12. models: GET /models/{model_id}/versions ----------------------
    # 三段路径，与两段 `/models/{model_id}` 及 `/models/er` 互不前缀吞并（同 A6-9/10/11）。

    @router.get("/models/{model_id}/versions")
    def list_versions(
        model_id: int,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """版本列表（version 降序 + id 降序；旧侧 `api/model.py:355-361`）。"""
        denial = principal(token, authorization, "list")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            try:
                data = ModelService(session, "").versions(model_id)
            except ModelDomainError as exc:
                return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.message, exc.data))
        return {"code": 0, "msg": "success", "data": data}

    # -- A6-13. models: POST /models/{model_id}/versions ---------------------
    # 三段路径，与 A6-12 `GET /models/{model_id}/versions` 同前缀异方法（openapi 合并为一键，
    # per-method 次序由 test_model_version_snapshot_api 锁定）。

    @router.post("/models/{model_id}/versions")
    def save_version(
        model_id: int,
        body: VersionBody,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """版本快照创建（全量 JSON 快照；旧侧 `api/model.py:362-374`）。"""
        denial = principal(token, authorization, "create")
        if isinstance(denial, JSONResponse):
            return denial
        claims = denial
        with session_factory() as session:
            try:
                data = ModelService(session, str(claims["username"])).save_version(
                    model_id, body.changeNote, str(claims["username"])
                )
            except ModelDomainError as exc:
                return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.message, exc.data))
        return {"code": 0, "msg": "success", "data": data}

    # -- A6-14. models: GET /models/{model_id}/versions/{version_id}/diff ---
    # 五段路径，与三/四段路由段数不同，互不前缀吞并。

    @router.get("/models/{model_id}/versions/{version_id}/diff")
    def diff_version(
        model_id: int,
        version_id: int,
        base: Optional[int] = None,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """版本 diff（仅比较 fields；旧侧 `api/model.py:377-394`）。"""
        denial = principal(token, authorization, "list")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            try:
                data = ModelService(session, "").diff_version(model_id, version_id, base)
            except ModelDomainError as exc:
                return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.message, exc.data))
        return {"code": 0, "msg": "success", "data": data}

    # -- A6-15. models: POST /models/{model_id}/versions/{version_id}/rollback
    # 五段路径，与既有三/四段路由段数不同，互不前缀吞并。

    @router.post("/models/{model_id}/versions/{version_id}/rollback")
    def rollback_version(
        model_id: int,
        version_id: int,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """版本回滚（字段还原 + 回 draft + version 递增 + 存新快照；旧侧 `api/model.py:396-415`）。"""
        denial = principal(token, authorization, "create")
        if isinstance(denial, JSONResponse):
            return denial
        claims = denial
        with session_factory() as session:
            try:
                data = ModelService(session, str(claims["username"])).rollback_version(
                    model_id, version_id, str(claims["username"])
                )
            except ModelDomainError as exc:
                return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.message, exc.data))
        return {"code": 0, "msg": "success", "data": data}

    # -- A6-16. models: GET /models/{model_id}/ddl ---------------------------
    # 三段路径，尾段字面 `ddl` 与 A6-9/10/11/12/13 的 `fields`/`publish`/`redraft`/`versions`
    # 互异，且无同段数动态尾段路由 —— 互不前缀吞并（同 A6-9 口径）。
    # 旧侧实锚 `api/model.py:466-481`（`preview_ddl`）；**不落库**，读端点登录即可。

    @router.get("/models/{model_id}/ddl")
    def preview_ddl(
        model_id: int,
        engine: str = "",
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """DDL 方言预览（不落库，供前端可编辑框；旧侧 `api/model.py:466-481`）。"""
        denial = principal(token, authorization, "list")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            try:
                data = ModelService(session, "").preview_ddl(model_id, engine)
            except ModelDomainError as exc:
                return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.message, exc.data))
        return {"code": 0, "msg": "success", "data": data}

    # -- A6-3. models: POST /models -----------------------------------------

    @router.post("/models")
    def create_model(
        body: ModelCreateBody,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """新建模型（编码正则 + 唯一 + 分层命名规范；旧侧 `api/model.py:165-182`）。"""
        denial = principal(token, authorization, "create")
        if isinstance(denial, JSONResponse):
            return denial
        claims = denial
        with session_factory() as session:
            try:
                record = ModelService(session, str(claims["username"])).create(
                    ModelCreateInput(
                        name=body.name,
                        code=body.code,
                        layer=body.layer,
                        engine=body.engine,
                        type=body.type,
                        biz_domain=body.bizDomain,
                    )
                )
            except ModelDomainError as exc:
                return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.message, exc.data))
        return {"code": 0, "msg": "success", "data": {"id": record.id}}

    return router
