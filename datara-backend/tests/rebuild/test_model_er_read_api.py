"""17.2-04 A6-4 `GET /api/v1/rebuild/models/er` 契约测试。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md` A6-4
（旧侧实锚 `datara-backend/api/model.py:421-431`；`_model_row` 序列化 `:61-70`）。
静态路由约束：`/models/er` 必须先于 `/models/{model_id}` 注册（旧侧注记 `api/model.py:184`）。
"""

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.model.models import DwModelRecord, DwModelRelationRecord

NODE_KEYS = {"id", "model", "erPos"}
EDGE_KEYS = {"id", "source", "target", "relType", "srcFields", "tgtFields", "joinDesc"}
MODEL_KEYS = {
    "id", "code", "name", "layer", "type", "bizDomain", "engine", "engineXc",
    "dsId", "dbName", "securityLevel", "status", "version", "owner",
    "builtAt", "updatedAt", "remark",
}


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="model-er-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    return client, app, {"token": login.json()["data"]["token"]}


def _seed(session, *, with_relation=True):
    """两模型一关系：dwd_trade_order → ads_trade_sum；dim_user 孤立（跨层）。"""
    order = DwModelRecord(
        code="dwd_trade_order", name="订单明细", layer="DWD", biz_domain="交易域",
        engine="MySQL", owner="alice", status="published", version=1,
        security_level="内部", er_pos={"x": 12.5, "y": 34.0},
    )
    summary = DwModelRecord(
        code="ads_trade_sum", name="交易汇总", layer="ADS", biz_domain="交易域",
        engine="Apache Doris", owner="bob", status="draft",
    )
    dim = DwModelRecord(
        code="dim_user", name="用户维表", layer="DIM", biz_domain="用户域",
        engine="GreatDB", owner="alice", status="built",
    )
    session.add_all([order, summary, dim])
    session.flush()
    if with_relation:
        session.add(DwModelRelationRecord(
            src_model_id=order.id, tgt_model_id=summary.id, rel_type="1:N",
            src_fields='["order_id"]', tgt_fields='["order_id"]', join_desc="订单汇总",
            created_by="alice",
        ))
        # 跨域边：src 在交易域、tgt 在用户域 —— 用于验证「双边须在过滤集内」
        session.add(DwModelRelationRecord(
            src_model_id=order.id, tgt_model_id=dim.id, rel_type="N:1",
            src_fields='["user_id"]', tgt_fields='["user_id"]', created_by="bob",
        ))
    session.commit()
    return order, summary, dim


def test_get_er_requires_login():
    client, app, _ = _client()
    try:
        response = client.get("/api/v1/rebuild/models/er")
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_get_er_returns_nodes_and_edges_shape():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            order, summary, dim = _seed(session)
        data = client.get("/api/v1/rebuild/models/er", headers=headers).json()["data"]
        assert set(data) == {"nodes", "edges"}

        # nodes：id 为 str，model 为 16 键 ModelRow，erPos 缺省 {}
        assert len(data["nodes"]) == 3
        assert all(set(n) == NODE_KEYS for n in data["nodes"])
        assert all(isinstance(n["id"], str) for n in data["nodes"])
        assert all(set(n["model"]) == MODEL_KEYS for n in data["nodes"])
        # 旧侧 order_by(DwModel.id) → 种子插入序
        assert [n["model"]["code"] for n in data["nodes"]] == [
            "dwd_trade_order", "ads_trade_sum", "dim_user",
        ]
        er_pos = {n["model"]["code"]: n["erPos"] for n in data["nodes"]}
        assert er_pos["dwd_trade_order"] == {"x": 12.5, "y": 34.0}
        assert er_pos["ads_trade_sum"] == {}          # er_pos 为空 → {}
        assert er_pos["dim_user"] == {}

        # edges：键集合精确，source/target 为 str，字段名照抄旧侧驼峰
        # 按 (source, target) 定位——两条边同源于 order，单键会互相覆盖
        assert len(data["edges"]) == 2
        assert all(set(e) == EDGE_KEYS for e in data["edges"])
        edge = {(e["source"], e["target"]): e for e in data["edges"]}
        first = edge[(str(order.id), str(summary.id))]
        assert first["id"] == 1
        assert first["relType"] == "1:N"
        assert first["srcFields"] == '["order_id"]'
        assert first["tgtFields"] == '["order_id"]'
        assert first["joinDesc"] == "订单汇总"
        second = edge[(str(order.id), str(dim.id))]
        assert second["id"] == 2
        assert second["relType"] == "N:1"
        assert second["joinDesc"] == ""
    finally:
        client.__exit__(None, None, None)


def test_get_er_filters_by_layer_and_domain():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed(session)
        # layer=DWD → 仅 order
        only_dwd = client.get(
            "/api/v1/rebuild/models/er", params={"layer": "DWD"}, headers=headers
        ).json()["data"]
        assert [n["model"]["code"] for n in only_dwd["nodes"]] == ["dwd_trade_order"]
        assert only_dwd["edges"] == []          # 双边须同在过滤集内 → 跨层边被丢弃

        # domain=交易域 → order + summary（DIM 被排除）
        trade = client.get(
            "/api/v1/rebuild/models/er", params={"domain": "交易域"}, headers=headers
        ).json()["data"]
        assert [n["model"]["code"] for n in trade["nodes"]] == ["dwd_trade_order", "ads_trade_sum"]
        assert len(trade["edges"]) == 1         # 仅 order→summary 双边在集内
        assert trade["edges"][0]["relType"] == "1:N"

        # 交叉：layer=DWD + domain=用户域 → 空集（不报错，返回空列表）
        cross = client.get(
            "/api/v1/rebuild/models/er",
            params={"layer": "DWD", "domain": "用户域"},
            headers=headers,
        ).json()["data"]
        assert cross == {"nodes": [], "edges": []}
    finally:
        client.__exit__(None, None, None)


def test_get_er_no_match_returns_empty_lists():
    """无匹配 → 空 nodes/edges（旧侧 ids 为空时不查关系，不抛 `IN ()`）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed(session)
        data = client.get(
            "/api/v1/rebuild/models/er", params={"layer": "NOPE"}, headers=headers
        ).json()
        assert data["code"] == 0
        assert data["data"] == {"nodes": [], "edges": []}
    finally:
        client.__exit__(None, None, None)


def _route_pairs(app):
    """展平后的 (method, path) 有序表 —— 与请求匹配同序。

    本版 FastAPI 下 `app.routes` 为惰性 `_IncludedRouter` 包装，须取 openapi 展平结果。
    """
    pairs = []
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            pairs.append((method.upper(), path))
    return pairs


def test_er_static_route_is_registered_before_model_id_route():
    """静态路由次序约束：`/models/er` 的每个方法都须先于 `/models/{model_id}` 注册。

    旧侧注记 `api/model.py:184`；若 `{model_id}` 在前，`er` 会被吞为模型 id 并 422。
    按 (method, path) 逐方法断言 —— 仅比路径键不足以发现同前缀异方法的吞并
    （openapi 把同路径的 GET/PUT 合并为一键）。17.2-07 的 PUT 吞并事故后由本用例形态锁定。
    """
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="order-secret")
    pairs = _route_pairs(app)
    static = [i for i, (_, path) in enumerate(pairs) if path == "/api/v1/rebuild/models/er"]
    dynamic = [
        i for i, (_, path) in enumerate(pairs)
        if path.startswith("/api/v1/rebuild/models/{")
    ]
    assert static, "/models/er 未注册"
    if dynamic:
        assert max(static) < min(dynamic), (
            f"/models/er 须整体先于 {{model_id}}（er={static}, first_id={min(dynamic)}）"
        )
