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
  A6-16 `/ddl`、A6-17 `/physicalize`、A6-18 `/reverse/scan`、A6-19 `/reverse/import`、
  A6-20 `/reverse/import-ddl`、A6-21 `/lineage`、A6-22 `/impact`）尾段皆**字面量**，与两段的
  `/models/{model_id}`、`/models/er` 段数不同，且彼此尾段互异 —— **互不前缀吞并**
  （Starlette 按段数 + 尾段字面匹配）；各自契约测试以「其前无其他同段数动态尾段路由」+
  行为验证锁定可达性。
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, File, Header, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import sessionmaker

from rebuild.identity.contracts import Permission, authorize
from rebuild.model.dsconn import open_connection
from rebuild.model.errors import PARAM_INVALID, ModelDomainError, fail
from rebuild.model.repository import ErRepository, ModelDictRepository, ModelRepository
from rebuild.model.service import (
    ModelCreateInput,
    ModelService,
    ModelUpdateInput,
    ReverseImportTable as ReverseImportTableInput,
)


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


class PhysicalizeBody(BaseModel):
    """A6-17 物理化入参（旧侧 `PhysicalizeBody` 照抄：`mode` 缺省 `script`）。"""

    engine: str
    dsId: Optional[int] = None
    dbName: Optional[str] = None
    mode: str = "script"  # exec | script
    ddl: Optional[str] = None


class ReverseScanBody(BaseModel):
    """A6-18 逆向扫描入参（旧侧 `ReverseScanBody` 照抄）。"""

    dsId: int
    dbName: Optional[str] = None


class ReverseImportTable(BaseModel):
    """A6-19 逆向导入单表入参（旧侧 `ReverseImportTable` 照抄，`:629-633`）。"""

    tb: str
    layer: str = "ODS"
    bizDomain: str = ""
    name: Optional[str] = None


class ReverseImportBody(BaseModel):
    """A6-19 逆向导入入参（旧侧 `ReverseImportBody` 照抄，`:636-639`）。"""

    dsId: int
    dbName: Optional[str] = None
    tables: list[ReverseImportTable]


# R-33 逐端点权限映射（写端点 `model:write` ↔ rebuild `EDIT_DEFINITION`）。
# 旧侧锚：`api/auth.py:38`（admin 段）/ `:42`（dev 段）——R3 注记校正后的行号。
PERMISSION_MAP = {
    "dicts": Permission.VIEW_ALL,
    "list": Permission.VIEW_ALL,
    "create": Permission.EDIT_DEFINITION,
    # A6-17 物理化会写库（exec 成功置 built + last_ddl）→ 与写端点同权
    "physicalize": Permission.EDIT_DEFINITION,
    # A6-18/19/20 逆向三端点（旧侧均 `require_perm("model:write")`）
    "reverse_scan": Permission.EDIT_DEFINITION,
    "reverse_import": Permission.EDIT_DEFINITION,
    "reverse_import_ddl": Permission.EDIT_DEFINITION,
    # A6-21/22 血缘/影响两图端点（旧侧均 `Depends(get_current_user)` → 读端点登录即可）
    "lineage": Permission.VIEW_ALL,
    "impact": Permission.VIEW_ALL,
}


def build_model_router(
    session_factory: sessionmaker,
    token_service: Any,
    active_tokens: set[str],
    connector: Any = None,
) -> APIRouter:
    """`connector` = A6-17 exec 分支连接工厂注入缝（缺省 `rebuild.model.dsconn.open_connection`）。

    生产由 `create_app` 缺省接线；契约测试经 `create_app(..., model_connector=fake)`
    注入 fake 连接，**使 exec 模式（含真实执行循环）可测且不触网络**
    （域规范：本机只做代码/静态/类型/逻辑稽核，真库联调归 192.168.1.9）。
    """
    router = APIRouter()
    model_connector = connector or open_connection

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

    # -- A6-21. models: GET /models/{model_id}/lineage ------------------------
    # 三段路径，尾段字面 `lineage` 与 A6-9/10/11/12/13/16/22 的尾段互异，
    # 且无同段数动态尾段路由 —— 互不前缀吞并（同 A6-9 口径）。
    # 旧侧实锚 `api/model.py:741-792`（`model_lineage`）；**不落库**，读端点登录即可。
    # runtime 半图依赖新增承载 `LineageEdgeRecord`（`t_lineage_edge`）——★候裁 ①/② 见证据。

    @router.get("/models/{model_id}/lineage")
    def model_lineage(
        model_id: int,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """合并血缘图（declared 声明半 + runtime 运行半；旧侧 `api/model.py:741-792`）。"""
        denial = principal(token, authorization, "lineage")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            try:
                data = ModelService(session, "").lineage(model_id)
            except ModelDomainError as exc:
                return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.message, exc.data))
        return {"code": 0, "msg": "success", "data": data}

    # -- A6-22. models: GET /models/{model_id}/impact ------------------------
    # 三段路径，尾段字面 `impact` 与 A6-9/10/11/12/13/16/21 的尾段互异，
    # 且无同段数动态尾段路由 —— 互不前缀吞并（同 A6-9 口径）。
    # 旧侧实锚 `api/model.py:795-821`（`model_impact`）；**不落库**，读端点登录即可。

    @router.get("/models/{model_id}/impact")
    def model_impact(
        model_id: int,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """下游影响清单（声明血缘 DFS + 环防护；旧侧 `api/model.py:795-821`）。"""
        denial = principal(token, authorization, "impact")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            try:
                data = ModelService(session, "").impact(model_id)
            except ModelDomainError as exc:
                return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.message, exc.data))
        return {"code": 0, "msg": "success", "data": data}

    # -- A6-17. models: POST /models/{model_id}/physicalize ------------------
    # 三段路径，尾段字面 `physicalize` 与 A6-9/10/11/12/13/16 的尾段互异，
    # 且无同段数动态尾段路由 —— 互不前缀吞并（同 A6-9 口径）。
    # 旧侧实锚 `api/model.py:492-546`（`PhysicalizeBody` + `physicalize`）；写端点
    # `model:write` ↔ `EDIT_DEFINITION`（旧侧 `require_perm("model:write")`）。

    @router.post("/models/{model_id}/physicalize")
    def physicalize_model(
        model_id: int,
        body: PhysicalizeBody,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """物理化（script/exec 双模式；exec 白名单仅 CREATE；旧侧 `api/model.py:492-546`）。"""
        denial = principal(token, authorization, "physicalize")
        if isinstance(denial, JSONResponse):
            return denial
        claims = denial
        with session_factory() as session:
            try:
                data = ModelService(
                    session, str(claims["username"]), connector=model_connector
                ).physicalize(
                    model_id,
                    engine=body.engine,
                    ds_id=body.dsId,
                    db_name=body.dbName,
                    mode=body.mode,
                    ddl=body.ddl,
                )
            except ModelDomainError as exc:
                return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.message, exc.data))
        return {"code": 0, "msg": "success", "data": data}

    # -- A6-18. models: POST /models/reverse/scan ---------------------------
    # 三段路径，**两段皆字面**（`reverse`/`scan`）：与 `/models/{model_id}/ddl`（尾段 `ddl`）
    # 及 `/models/{model_id}/physicalize` 等同段数路由尾段互异 → 互不前缀吞并；亦不会吞并
    # 两段的 `/models/{model_id}`。旧侧实锚 `api/model.py:572-594`（`reverse_scan`）。
    # 写端点 `model:write`（旧侧 `require_perm("model:write")`）。

    @router.post("/models/reverse/scan")
    def reverse_scan(
        body: ReverseScanBody,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """逆向内省表清单（表名/注释/行数估算/列数；旧侧 `api/model.py:572-594`）。"""
        denial = principal(token, authorization, "reverse_scan")
        if isinstance(denial, JSONResponse):
            return denial
        with session_factory() as session:
            try:
                data = ModelService(session, "", connector=model_connector).reverse_scan(
                    body.dsId, body.dbName or ""
                )
            except ModelDomainError as exc:
                return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.message, exc.data))
        return {"code": 0, "msg": "success", "data": data}

    # -- A6-19. models: POST /models/reverse/import --------------------------
    # 三段路径，**两段皆字面**（`reverse`/`import`）：与 `/models/reverse/scan` 尾段互异
    # （`scan` vs `import`）→ 互不前缀吞并；亦不会吞并两段的 `/models/{model_id}`。
    # 旧侧实锚 `api/model.py:629-684`（`ReverseImportTable`/`ReverseImportBody` + `reverse_import`）。
    # 写端点 `model:write`（旧侧 `require_perm("model:write")`）。

    @router.post("/models/reverse/import")
    def reverse_import(
        body: ReverseImportBody,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """逆向导入建模（逐表建草稿；旧侧 `api/model.py:642-684`）。"""
        denial = principal(token, authorization, "reverse_import")
        if isinstance(denial, JSONResponse):
            return denial
        claims = denial
        with session_factory() as session:
            try:
                data = ModelService(session, str(claims["username"]), connector=model_connector).reverse_import(
                    body.dsId,
                    body.dbName or "",
                    [
                        ReverseImportTableInput(
                            tb=t.tb, layer=t.layer, biz_domain=t.bizDomain, name=t.name,
                        )
                        for t in body.tables
                    ],
                )
            except ModelDomainError as exc:
                return JSONResponse(status_code=exc.status, content=fail(exc.code, exc.message, exc.data))
        return {"code": 0, "msg": "success", "data": data}

    # -- A6-20. models: POST /models/reverse/import-ddl ---------------------
    # 三段路径，**两段皆字面**（`reverse`/`import-ddl`）：与 `/models/reverse/scan`
    # （尾段 `scan`）、`/models/reverse/import`（尾段 `import`）尾段互异 → 互不前缀吞并。
    # 旧侧实锚 `api/model.py:687-735`（`reverse_import_ddl`）。写端点 `model:write`
    # （旧侧 `require_perm("model:write")`）。
    # 5MB 上限为**双层**（旧侧同）：`file.size` 已知时快速拒绝 + 分块读取二次校验，
    # 避免超大文件整体进内存。分块循环在此层（HTTP IO 关注点），解码/解析/建模特在服务层。

    @router.post("/models/reverse/import-ddl")
    async def reverse_import_ddl(
        file: UploadFile = File(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """DDL 文件导入（.sql ≤5MB → ODS 草稿；旧侧 `api/model.py:687-735`）。"""
        denial = principal(token, authorization, "reverse_import_ddl")
        if isinstance(denial, JSONResponse):
            return denial
        claims = denial
        limit = 5 * 1024 * 1024
        if file.size is not None and file.size > limit:  # size 已知时快速拒绝（size 可能为 None）
            return JSONResponse(
                status_code=400, content=fail(PARAM_INVALID, "DDL 文件超过 5MB 上限")
            )
        chunks: list[bytes] = []
        total = 0
        while True:  # 分块读取兜底：超限立即中断，避免超大文件整体进内存
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                return JSONResponse(
                    status_code=400, content=fail(PARAM_INVALID, "DDL 文件超过 5MB 上限")
                )
            chunks.append(chunk)
        with session_factory() as session:
            try:
                data = ModelService(session, str(claims["username"])).reverse_import_ddl(
                    b"".join(chunks)
                )
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
