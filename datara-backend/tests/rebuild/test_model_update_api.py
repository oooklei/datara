"""17.2-07 A6-7 `PUT /api/v1/rebuild/models/{model_id}` 契约测试。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md` A6-7
（旧侧实锚 `datara-backend/api/model.py:216-233` `update_model`；`ModelUpdateBody` 见 `:210-216`）。
入参六字段皆可选（None = 不修改）；出参 ModelRow；错误码 8001/404、8005/409。
"""

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.model.models import DwModelRecord

MODEL_KEYS = {
    "id", "code", "name", "layer", "type", "bizDomain", "engine", "engineXc",
    "dsId", "dbName", "securityLevel", "status", "version", "owner",
    "builtAt", "updatedAt", "remark",
}


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="model-update-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    return client, app, {"token": login.json()["data"]["token"]}


def _seed(session, *, status="draft"):
    model = DwModelRecord(code="dwd_trade_order", name="订单明细", layer="DWD", biz_domain="交易域",
                          engine="MySQL", owner="alice", status=status, version=3,
                          security_level="内部", remark="旧备注", ds_id=None, db_name=None)
    session.add(model)
    session.commit()
    return model


def _route_pairs(app):
    """展平后的 (method, path) 有序表 —— 与请求匹配同序。

    本版 FastAPI 下 `app.routes` 为惰性 `_IncludedRouter` 包装，须取 openapi 展平结果。
    """
    pairs = []
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            pairs.append((method.upper(), path))
    return pairs


def test_er_static_routes_precede_model_id_routes_per_method():
    """静态段 `/models/er` 的**每个方法**都须先于 `/models/{model_id}` 注册。

    旧侧注记 `api/model.py:184`。本用例按 (method, path) 逐方法断言 ——
    仅比路径键（openapi 同路径多方法合并为一键）不足以发现同前缀异方法的吞并：
    17.2-07 落地时 `PUT /models/{model_id}` 曾先于 `PUT /models/er` 注册，
    致 `PUT /models/er` 被吞为 model_id 并返回 422（由本用例发现并修正）。
    """
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="order-per-method")
    pairs = _route_pairs(app)
    static = [i for i, (m, p) in enumerate(pairs) if p == "/api/v1/rebuild/models/er"]
    dynamic = [i for i, (m, p) in enumerate(pairs) if p == "/api/v1/rebuild/models/{model_id}"]
    assert static and dynamic
    # 逐方法配对：每个静态方法的注册序须先于同方法（或任意方法）的动态路由
    for index in static:
        assert index < min(dynamic), f"静态路由 {pairs[index]} 被 {{model_id}} 抢前"


def test_update_model_requires_login():
    client, app, _ = _client()
    try:
        response = client.put("/api/v1/rebuild/models/1", json={"remark": "x"})
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_update_model_returns_full_model_row():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session)
            model_id = model.id
        body = client.put(
            f"/api/v1/rebuild/models/{model_id}",
            json={"remark": "新备注", "owner": "carol"},
            headers=headers,
        ).json()
        assert body["code"] == 0 and body["msg"] == "success"
        # 出参 = ModelRow 16 键（不含 fields，区别于 A6-6 详情）
        assert set(body["data"]) == MODEL_KEYS
        assert body["data"]["remark"] == "新备注"
        assert body["data"]["owner"] == "carol"
        assert body["data"]["name"] == "订单明细"      # 未提交的字段不动
        assert body["data"]["version"] == 3           # 更新不改 version
    finally:
        client.__exit__(None, None, None)


def test_update_model_partial_fields_only_touch_submitted():
    """六字段皆可选：未提交的字段保持原值（旧侧逐个 `if body.X is not None`）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session)
            model_id = model.id
        client.put(f"/api/v1/rebuild/models/{model_id}", json={"dsId": 7, "dbName": "dw"},
                   headers=headers)
        data = client.get(f"/api/v1/rebuild/models/{model_id}", headers=headers).json()["data"]
        assert data["dsId"] == 7 and data["dbName"] == "dw"
        assert data["remark"] == "旧备注" and data["owner"] == "alice"
        assert data["securityLevel"] == "内部"
    finally:
        client.__exit__(None, None, None)


def test_update_model_name_is_stripped():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model_id = _seed(session).id
        client.put(f"/api/v1/rebuild/models/{model_id}", json={"name": "  订单明细改  "},
                   headers=headers)
        data = client.get(f"/api/v1/rebuild/models/{model_id}", headers=headers).json()["data"]
        assert data["name"] == "订单明细改"
    finally:
        client.__exit__(None, None, None)


def test_update_model_unknown_id_is_404():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed(session)
        response = client.put("/api/v1/rebuild/models/9999", json={"remark": "x"}, headers=headers)
        assert response.status_code == 404
        assert response.json()["code"] == 8001
    finally:
        client.__exit__(None, None, None)


def test_update_model_published_rejects_name_change():
    """已发布（非 draft）模型改名 → 8005/409，且先于任何字段写入。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, status="published")
            model_id = model.id
        response = client.put(
            f"/api/v1/rebuild/models/{model_id}",
            json={"name": "改名尝试", "remark": "顺带改备注"},
            headers=headers,
        )
        assert response.status_code == 409
        assert response.json()["code"] == 8005
        assert "已发布模型仅可修改备注" in response.json()["msg"]
        # 失败不改库：remark 也未写入
        data = client.get(f"/api/v1/rebuild/models/{model_id}", headers=headers).json()["data"]
        assert data["name"] == "订单明细" and data["remark"] == "旧备注"
    finally:
        client.__exit__(None, None, None)


def test_update_model_published_allows_four_field_subset():
    """已发布模型仅可改 备注/负责人/密级/目标数据源（旧侧四字段白名单）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model_id = _seed(session, status="published").id
        response = client.put(
            f"/api/v1/rebuild/models/{model_id}",
            json={"remark": "r", "owner": "carol", "securityLevel": "秘密", "dsId": 9, "dbName": "dw2"},
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["remark"] == "r" and data["owner"] == "carol"
        assert data["securityLevel"] == "秘密" and data["dsId"] == 9 and data["dbName"] == "dw2"
    finally:
        client.__exit__(None, None, None)


def test_update_model_published_same_name_is_not_a_conflict():
    """旧侧判定含 `body.name != m.name`：提交同名不构成冲突（仅改备注）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model_id = _seed(session, status="published").id
        response = client.put(
            f"/api/v1/rebuild/models/{model_id}",
            json={"name": "订单明细", "remark": "同名+改备注"},
            headers=headers,
        )
        assert response.status_code == 200
        assert response.json()["data"]["remark"] == "同名+改备注"
    finally:
        client.__exit__(None, None, None)


def test_update_model_forbidden_without_model_write():
    client, app, _ = _client()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="viewer", password="pw-123456", role=Role.VIEWER)
            model_id = _seed(session).id
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "viewer", "password": "pw-123456"})
        headers = {"token": login.json()["data"]["token"]}
        response = client.put(
            f"/api/v1/rebuild/models/{model_id}", json={"remark": "x"}, headers=headers
        )
        assert response.status_code == 403
        assert response.json()["code"] == 1004
        # 读端点不受影响
        assert client.get(f"/api/v1/rebuild/models/{model_id}", headers=headers).status_code == 200
    finally:
        client.__exit__(None, None, None)
