"""17.2-10 / 17.2-11 — A6-10 `POST /models/{model_id}/publish` 与
A6-11 `POST /models/{model_id}/redraft` 契约测试（状态迁移对）。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md`
A6-10 / A6-11（旧侧实锚 `datara-backend/api/model.py:311-321` `publish_model`、
`:342-352` `redraft_model`）。
错误码：8001/404 模型不存在；8005/409 状态冲突（A6-10 仅草稿可发布 / A6-11 当前已是草稿）。
"""

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.model.models import DwModelFieldRecord, DwModelRecord


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="model-publish-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    return client, app, {"token": login.json()["data"]["token"]}


def _seed(session, *, status="draft", version=1, code="dwd_trade_order"):
    model = DwModelRecord(
        code=code, name="订单明细", layer="DWD", biz_domain="交易域",
        engine="MySQL", owner="alice", status=status, version=version,
    )
    session.add(model)
    session.flush()
    session.add(DwModelFieldRecord(model_id=model.id, seq=1, name="order_id", data_type="BIGINT"))
    session.commit()
    return model


# ---------- A6-10 publish ----------


def test_publish_requires_login():
    client, app, _ = _client()
    try:
        response = client.post("/api/v1/rebuild/models/1/publish")
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_publish_draft_returns_published_status():
    """draft → published；出参恰为 `{status: "published"}`（非 ModelRow）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session)
            model_id = model.id
        response = client.post(f"/api/v1/rebuild/models/{model_id}/publish", headers=headers)
        assert response.status_code == 200, response.json()
        assert response.json()["code"] == 0
        assert response.json()["data"] == {"status": "published"}
        detail = client.get(f"/api/v1/rebuild/models/{model_id}", headers=headers).json()["data"]
        assert detail["status"] == "published"
    finally:
        client.__exit__(None, None, None)


def test_publish_unknown_id_is_404():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed(session)
        response = client.post("/api/v1/rebuild/models/9999/publish", headers=headers)
        assert response.status_code == 404
        assert response.json()["code"] == 8001
    finally:
        client.__exit__(None, None, None)


def test_publish_rejects_non_draft_status():
    """published/built/produced 三态 → 8005/409「仅草稿可发布」，状态不变。"""
    client, app, headers = _client()
    try:
        for status, code in (
            ("published", "dwd_pub_order"),
            ("built", "dwd_built_order"),
            ("produced", "dwd_prod_order"),
        ):
            with app.state.session_factory() as session:
                model = _seed(session, status=status, version=4, code=code)
                model_id = model.id
            response = client.post(f"/api/v1/rebuild/models/{model_id}/publish", headers=headers)
            assert response.status_code == 409, status
            assert response.json()["code"] == 8005, status
            assert response.json()["msg"] == "仅草稿可发布"
            assert response.json()["data"] is None
            detail = client.get(
                f"/api/v1/rebuild/models/{model_id}", headers=headers
            ).json()["data"]
            assert detail["status"] == status
            assert detail["version"] == 4  # 发布不改 version
    finally:
        client.__exit__(None, None, None)


def test_publish_forbidden_without_model_write():
    client, app, _ = _client()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="viewer", password="pw-123456", role=Role.VIEWER)
            model_id = _seed(session).id
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "viewer", "password": "pw-123456"})
        headers = {"token": login.json()["data"]["token"]}
        response = client.post(f"/api/v1/rebuild/models/{model_id}/publish", headers=headers)
        assert response.status_code == 403
        assert response.json()["code"] == 1004
        assert client.get(f"/api/v1/rebuild/models/{model_id}", headers=headers).status_code == 200
    finally:
        client.__exit__(None, None, None)


# ---------- A6-11 redraft ----------


def test_redraft_requires_login():
    client, app, _ = _client()
    try:
        response = client.post("/api/v1/rebuild/models/1/redraft")
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_redraft_published_returns_model_row_and_bumps_version():
    """published → draft，version 递增；出参为 **ModelRow**（非 `{status}`）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, status="published", version=7)
            model_id = model.id
        response = client.post(f"/api/v1/rebuild/models/{model_id}/redraft", headers=headers)
        assert response.status_code == 200, response.json()
        assert response.json()["code"] == 0
        data = response.json()["data"]
        assert data["status"] == "draft"
        assert data["version"] == 8
        # 出参形状 = ModelRow（含列表行键），非 A6-10 的 {"status": ...}
        assert set(data) == {
            "id", "code", "name", "layer", "type", "bizDomain", "engine", "engineXc",
            "dsId", "dbName", "securityLevel", "status", "version", "owner",
            "builtAt", "updatedAt", "remark",
        }
        assert data["code"] == "dwd_trade_order"
        detail = client.get(f"/api/v1/rebuild/models/{model_id}", headers=headers).json()["data"]
        assert detail["status"] == "draft"
        assert detail["version"] == 8
    finally:
        client.__exit__(None, None, None)


def test_redraft_unknown_id_is_404():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed(session)
        response = client.post("/api/v1/rebuild/models/9999/redraft", headers=headers)
        assert response.status_code == 404
        assert response.json()["code"] == 8001
    finally:
        client.__exit__(None, None, None)


def test_redraft_rejects_when_already_draft():
    """已是 draft → 8005/409「当前已是草稿」；注意状态闸方向与 publish **相反**。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, status="draft", version=2)
            model_id = model.id
        response = client.post(f"/api/v1/rebuild/models/{model_id}/redraft", headers=headers)
        assert response.status_code == 409
        assert response.json()["code"] == 8005
        assert response.json()["msg"] == "当前已是草稿"
        detail = client.get(f"/api/v1/rebuild/models/{model_id}", headers=headers).json()["data"]
        assert detail["version"] == 2  # 冲突时不递增
    finally:
        client.__exit__(None, None, None)


def test_publish_then_redraft_roundtrip():
    """往返：draft --publish--> published --redraft--> draft，version 1 → 1 → 2。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session)
            model_id = model.id
        assert client.post(
            f"/api/v1/rebuild/models/{model_id}/publish", headers=headers
        ).json()["data"] == {"status": "published"}
        redraft = client.post(f"/api/v1/rebuild/models/{model_id}/redraft", headers=headers)
        assert redraft.json()["data"]["status"] == "draft"
        assert redraft.json()["data"]["version"] == 2
        # 再次发布成功（回 draft 后闸门重开）
        assert client.post(
            f"/api/v1/rebuild/models/{model_id}/publish", headers=headers
        ).json()["data"] == {"status": "published"}
    finally:
        client.__exit__(None, None, None)


def _route_pairs(app):
    """展平后的 (method, path) 有序表 —— 与请求匹配同序。"""
    pairs = []
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            pairs.append((method.upper(), path))
    return pairs


def test_three_segment_sub_routes_are_registered_and_reachable():
    """A6-9/10/11 三条三段子路由可达性：已注册 + 其前无同段数路由 + 语义各归其主。

    Starlette 按段数匹配，三段路由不可能被两段的 `/models/{model_id}` 吞并
    （17.2-07 那类同段数吞并不适用于此）。故断言重点为「无前导同段数路由」+ 行为验证。
    """
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="sub-route-secret")
    pairs = _route_pairs(app)
    seg = len("/api/v1/rebuild/models/{model_id}/publish".split("/"))
    for suffix, method in (("fields", "PUT"), ("publish", "POST"), ("redraft", "POST")):
        target = [
            i for i, (m, p) in enumerate(pairs)
            if p == f"/api/v1/rebuild/models/{{model_id}}/{suffix}" and m == method
        ]
        assert target, f"A6 子路由 {method} /models/{{model_id}}/{suffix} 未注册"
        # 仅**末段为路径参数**的同段数路由才可能吞并（字面尾段不同则永不匹配）
        rivals = [
            (i, m, p) for i, (m, p) in enumerate(pairs)
            if p.startswith("/api/v1/rebuild/models/{model_id}/")
            and len(p.split("/")) == seg
            and p.split("/")[-1].startswith("{")
        ]
        assert not [r for r in rivals if r[0] < target[0]], (
            f"存在更早注册的同段数路由可吞并 {suffix}：{rivals}"
        )

    # 行为：publish/redraft 互不串味
    client = TestClient(app)
    client.__enter__()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
        headers = {"token": login.json()["data"]["token"]}
        with app.state.session_factory() as session:
            published = _seed(session, status="published", version=5, code="dwd_pub_x")
            drafted = _seed(session, status="draft", version=1, code="dwd_drf_x")
            published_id, drafted_id = published.id, drafted.id
        assert client.post(
            f"/api/v1/rebuild/models/{published_id}/redraft", headers=headers
        ).json()["data"]["status"] == "draft"
        conflict = client.post(
            f"/api/v1/rebuild/models/{drafted_id}/redraft", headers=headers
        )
        assert conflict.status_code == 409 and conflict.json()["code"] == 8005
        assert client.post(
            f"/api/v1/rebuild/models/{drafted_id}/publish", headers=headers
        ).json()["data"] == {"status": "published"}
    finally:
        client.__exit__(None, None, None)
