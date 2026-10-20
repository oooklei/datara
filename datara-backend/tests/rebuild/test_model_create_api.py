"""17.2-03 A6-3 `POST /api/v1/rebuild/models` 契约测试。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md` A6-3
（旧侧实锚 `datara-backend/api/model.py:165-182` 路由体、`:40` `CODE_RE`、`:76-85` `_check_code`）。
错误码：8002/409 编码已存在；8003/400 编码非法；8004/400 不符合分层命名规范；4002/400 分层/引擎不存在。
鉴权：`model:write` ↔ `Permission.EDIT_DEFINITION`（R-33，旧侧锚 `api/auth.py:38` admin / `:42` dev）。
"""

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository

VALID_BODY = {
    "name": "订单明细",
    "code": "dwd_trade_order",
    "layer": "DWD",
    "engine": "MySQL",
}


def _client(*roles: Role):
    """起应用 + 建号登录；返回 (client, app, headers)。默认单 admin。"""
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="model-create-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        for index, role in enumerate(roles or [Role.ADMIN]):
            UserRepository(session).create(
                username=f"user_{index}", password="pw-123456", role=role
            )
        session.commit()
    username = "user_0"
    login = client.post(
        "/api/v1/rebuild/login", json={"username": username, "password": "pw-123456"}
    )
    token = login.json()["data"]["token"]
    return client, app, {"token": token}


def _create(client, headers, **overrides):
    body = {**VALID_BODY, **overrides}
    return client.post("/api/v1/rebuild/models", json=body, headers=headers)


def test_create_model_requires_login():
    client, app, _ = _client()
    try:
        response = client.post("/api/v1/rebuild/models", json=VALID_BODY)
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_create_model_persists_with_frozen_defaults():
    client, app, headers = _client()
    try:
        response = _create(client, headers)
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0 and body["msg"] == "success"
        assert set(body["data"]) == {"id"}
        assert isinstance(body["data"]["id"], int)

        # 落库默认值逐项照抄旧侧（api/model.py:176-181）
        listed = client.get(
            "/api/v1/rebuild/models", params={"keyword": "dwd_trade_order"}, headers=headers
        ).json()["data"]
        assert listed["total"] == 1
        row = listed["list"][0]
        assert row["code"] == "dwd_trade_order"
        assert row["name"] == "订单明细"
        assert row["layer"] == "DWD"
        assert row["type"] == "明细表"          # body.type 缺省透传
        assert row["bizDomain"] == ""           # body.bizDomain 缺省透传
        assert row["status"] == "draft"
        assert row["version"] == 1
        assert row["securityLevel"] == "内部"
        assert row["owner"] == "user_0"         # 旧侧 owner=user.user_name
    finally:
        client.__exit__(None, None, None)


def test_create_model_accepts_bearer_header():
    """冻结 FE 契约：`token` header 优先，Bearer 回退（两侧均须可用）。"""
    client, app, headers = _client()
    try:
        bearer = {"Authorization": f"Bearer {headers['token']}"}
        assert _create(client, bearer).status_code == 200
    finally:
        client.__exit__(None, None, None)


def test_create_model_rejects_duplicate_code():
    client, app, headers = _client()
    try:
        assert _create(client, headers).status_code == 200
        dup = _create(client, headers, name="订单明细2")
        assert dup.status_code == 409
        assert dup.json()["code"] == 8002
        assert dup.json()["data"] is None
        # 冲突未落库
        assert client.get(
            "/api/v1/rebuild/models", params={"keyword": "dwd_trade_order"}, headers=headers
        ).json()["data"]["total"] == 1
    finally:
        client.__exit__(None, None, None)


def test_create_model_rejects_invalid_code():
    """编码正则 `^[a-z][a-z0-9_]*$`（旧侧 `api/model.py:40`）→ 8003/400。"""
    client, app, headers = _client()
    try:
        for bad in ["DWD_trade", "1dwd_trade", "dwd-trade", "dwd trade", ""]:
            response = _create(client, headers, code=bad)
            assert response.status_code == 400, bad
            assert response.json()["code"] == 8003, bad
    finally:
        client.__exit__(None, None, None)


def test_create_model_rejects_naming_rule_violation():
    """分层命名规范取 `t_dw_layer.rule` 首段前缀（旧侧 `_check_code`）→ 8004/400。"""
    client, app, headers = _client()
    try:
        # DWD 层 rule="dwd_业务_过程，一个过程一张表" → 前缀 dwd
        bad = _create(client, headers, code="ads_trade_sum", layer="DWD")
        assert bad.status_code == 400
        assert bad.json()["code"] == 8004
        assert "dwd_业务_过程" in bad.json()["msg"]
        # 合规编码不受影响
        assert _create(client, headers, code="dwd_trade_refund", layer="DWD").status_code == 200
        # DIM 层前缀 dim
        assert _create(client, headers, code="dim_user", layer="DIM", engine="GreatDB").status_code == 200
        assert _create(client, headers, code="dwd_user", layer="DIM", engine="GreatDB").status_code == 400
    finally:
        client.__exit__(None, None, None)


def test_create_model_rejects_unknown_layer_or_engine():
    """分层/引擎存在性（旧侧 `db.get(DwLayer/EngineType, ...)`）→ 4002/400，且先于编码校验。"""
    client, app, headers = _client()
    try:
        bad_layer = _create(client, headers, layer="NOPE")
        assert bad_layer.status_code == 400
        assert bad_layer.json()["code"] == 4002
        assert "分层不存在" in bad_layer.json()["msg"]

        bad_engine = _create(client, headers, engine="NoEngine")
        assert bad_engine.status_code == 400
        assert bad_engine.json()["code"] == 4002
        assert "引擎不存在" in bad_engine.json()["msg"]

        # 旧侧次序：分层不存在时即便编码非法也先报 4002（非 8003）
        ordered = _create(client, headers, layer="NOPE", code="非法 code")
        assert ordered.json()["code"] == 4002
    finally:
        client.__exit__(None, None, None)


def test_create_model_forbidden_without_model_write():
    """R-33：`model:write` 仅 admin/developer 持有 → viewer 403/1004。"""
    client, app, headers = _client(Role.VIEWER)
    try:
        response = _create(client, headers)
        assert response.status_code == 403
        assert response.json()["code"] == 1004
        # 读端点不受影响（view_all）
        assert client.get("/api/v1/rebuild/models", headers=headers).status_code == 200
    finally:
        client.__exit__(None, None, None)
