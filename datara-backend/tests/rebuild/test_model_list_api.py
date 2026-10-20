"""17.2-02 A6-2 `GET /api/v1/rebuild/models` 契约测试。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md` A6-2
（旧侧实锚 `datara-backend/api/model.py:114-155`；ModelRow 序列化 `:61-70`）。
双维统计 = 分层计数叠 domain、域计数叠 layer（交叉过滤，I18 §4.1）；`size` 上限 200。
"""

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.model.models import DwModelRecord


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="model-list-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    return client, app, {"Authorization": f"Bearer {login.json()['data']['token']}"}


def _seed(session, rows):
    """rows: (code, name, layer, biz_domain, engine, owner, status)"""
    for code, name, layer, domain, engine, owner, status in rows:
        session.add(DwModelRecord(
            code=code, name=name, layer=layer, biz_domain=domain, engine=engine,
            owner=owner, status=status, version=1, security_level="内部",
        ))
    session.commit()


def test_list_models_requires_login():
    client, app, _ = _client()
    try:
        response = client.get("/api/v1/rebuild/models")
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_list_models_returns_rows_stats_and_shape():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed(session, [
                ("dwd_trade_order", "订单明细", "DWD", "交易域", "MySQL", "alice", "published"),
                ("ads_trade_sum", "交易汇总", "ADS", "交易域", "Apache Doris", "bob", "draft"),
                ("dim_user", "用户维表", "DIM", "用户域", "GreatDB", "alice", "built"),
            ])
        body = client.get("/api/v1/rebuild/models", headers=headers).json()
        assert body["code"] == 0
        data = body["data"]
        assert set(data) == {"list", "total", "layers", "domains"}
        assert data["total"] == 3
        assert len(data["list"]) == 3

        row = data["list"][0]
        assert set(row) == {
            "id", "code", "name", "layer", "type", "bizDomain", "engine", "engineXc",
            "dsId", "dbName", "securityLevel", "status", "version", "owner",
            "builtAt", "updatedAt", "remark",
        }
        # 默认值透传：type 缺省「明细表」、securityLevel 缺省「内部」
        assert row["type"] == "明细表"
        assert row["securityLevel"] == "内部"
        # engineXc 由引擎字典解析（GreatDB 信创）
        assert {r["code"]: r["engineXc"] for r in data["list"]}["dim_user"] is True
        assert {r["code"]: r["engineXc"] for r in data["list"]}["ads_trade_sum"] is False

        # 双维统计：五层 + 四域全量计数（无过滤时）
        assert [l["code"] for l in data["layers"]] == ["ODS", "DWD", "DWS", "ADS", "DIM"]
        assert {l["code"]: l["count"] for l in data["layers"]} == {
            "ODS": 0, "DWD": 1, "DWS": 0, "ADS": 1, "DIM": 1,
        }
        assert {d["name"]: d["count"] for d in data["domains"]} == {
            "交易域": 2, "用户域": 1, "商品域": 0, "流量域": 0,
        }
    finally:
        client.__exit__(None, None, None)


def test_list_models_cross_filtered_stats():
    """分层计数叠 domain、域计数叠 layer（交叉过滤，I18 §4.1）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed(session, [
                ("dwd_trade_order", "订单明细", "DWD", "交易域", "MySQL", "alice", "published"),
                ("ads_trade_sum", "交易汇总", "ADS", "交易域", "Apache Doris", "bob", "draft"),
                ("dim_user", "用户维表", "DIM", "用户域", "GreatDB", "alice", "built"),
            ])
        # domain=交易域：分层计数只统计交易域；域计数叠 layer=ADS
        data = client.get(
            "/api/v1/rebuild/models", params={"domain": "交易域", "layer": "ADS"}, headers=headers
        ).json()["data"]
        assert data["total"] == 1
        assert [r["code"] for r in data["list"]] == ["ads_trade_sum"]
        # 分层计数叠 domain=交易域 → DWD 仍计 1（交易域下的 DWD）
        assert {l["code"]: l["count"] for l in data["layers"]} == {
            "ODS": 0, "DWD": 1, "DWS": 0, "ADS": 1, "DIM": 0,
        }
        # 域计数叠 layer=ADS → 只有 ADS 层各域计数
        assert {d["name"]: d["count"] for d in data["domains"]} == {
            "交易域": 1, "用户域": 0, "商品域": 0, "流量域": 0,
        }
    finally:
        client.__exit__(None, None, None)


def test_list_models_keyword_status_filters_and_pagination():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed(session, [
                ("dwd_trade_order", "订单明细", "DWD", "交易域", "MySQL", "alice", "published"),
                ("dwd_trade_refund", "退款明细", "DWD", "交易域", "MySQL", "bob", "draft"),
                ("dim_user", "用户维表", "DIM", "用户域", "GreatDB", "alice", "built"),
            ])
        # keyword 命中 code/name/owner 三字段
        assert client.get(
            "/api/v1/rebuild/models", params={"keyword": "refund"}, headers=headers
        ).json()["data"]["total"] == 1
        assert client.get(
            "/api/v1/rebuild/models", params={"keyword": "alice"}, headers=headers
        ).json()["data"]["total"] == 2
        assert client.get(
            "/api/v1/rebuild/models", params={"keyword": "明细"}, headers=headers
        ).json()["data"]["total"] == 2
        # keyword 首尾空白剥离
        assert client.get(
            "/api/v1/rebuild/models", params={"keyword": "  refund  "}, headers=headers
        ).json()["data"]["total"] == 1
        # status 精确过滤
        assert client.get(
            "/api/v1/rebuild/models", params={"status": "draft"}, headers=headers
        ).json()["data"]["total"] == 1
        # 分页：size=1 两页各 1 条，total 恒为过滤后总数
        page1 = client.get(
            "/api/v1/rebuild/models", params={"page": 1, "size": 1}, headers=headers
        ).json()["data"]
        page2 = client.get(
            "/api/v1/rebuild/models", params={"page": 2, "size": 1}, headers=headers
        ).json()["data"]
        assert page1["total"] == 3 and len(page1["list"]) == 1
        assert page2["total"] == 3 and len(page2["list"]) == 1
        assert page1["list"][0]["id"] != page2["list"][0]["id"]
    finally:
        client.__exit__(None, None, None)


def test_list_models_size_bounds_are_enforced():
    client, app, headers = _client()
    try:
        # size 上限 200（契约卡兼容性注记）
        too_large = client.get(
            "/api/v1/rebuild/models", params={"size": 201}, headers=headers
        )
        assert too_large.status_code == 422
        too_small = client.get(
            "/api/v1/rebuild/models", params={"size": 0}, headers=headers
        )
        assert too_small.status_code == 422
        bad_page = client.get(
            "/api/v1/rebuild/models", params={"page": 0}, headers=headers
        )
        assert bad_page.status_code == 422
        # 边界值 200 合法
        assert client.get(
            "/api/v1/rebuild/models", params={"size": 200}, headers=headers
        ).status_code == 200
    finally:
        client.__exit__(None, None, None)
