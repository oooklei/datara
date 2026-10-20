"""17.2-05 A6-5 `PUT /api/v1/rebuild/models/er` 契约测试。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md` A6-5
（旧侧实锚 `datara-backend/api/model.py:435-453` `put_er`；`ErBody` 见 `:185-188`）。
positions 全量覆盖；relations 增量 diff（removed 按 id 删、added/updated 按有无 id 新建或改四字段）。
错误码：8001/404 模型不存在。
"""

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.model.models import DwModelRecord, DwModelRelationRecord


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="model-er-save-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    return client, app, {"token": login.json()["data"]["token"]}


def _seed(session):
    order = DwModelRecord(code="dwd_trade_order", name="订单明细", layer="DWD", biz_domain="交易域",
                          engine="MySQL", owner="alice", status="published")
    summary = DwModelRecord(code="ads_trade_sum", name="交易汇总", layer="ADS", biz_domain="交易域",
                            engine="Apache Doris", owner="bob", status="draft")
    session.add_all([order, summary])
    session.flush()
    relation = DwModelRelationRecord(src_model_id=order.id, tgt_model_id=summary.id, rel_type="1:N",
                                     src_fields='["order_id"]', tgt_fields='["order_id"]',
                                     join_desc="订单汇总", created_by="alice")
    session.add(relation)
    session.commit()
    return order, summary, relation


def _graph(client, headers):
    return client.get("/api/v1/rebuild/models/er", headers=headers).json()["data"]


def test_put_er_requires_login():
    client, app, _ = _client()
    try:
        response = client.put("/api/v1/rebuild/models/er", json={"positions": {}, "relations": {}})
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_put_er_positions_full_overwrite_and_saved_flag():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            order, summary, _ = _seed(session)
            order_id, summary_id = str(order.id), str(summary.id)
        response = client.put(
            "/api/v1/rebuild/models/er",
            json={"positions": {order_id: {"x": 1.5, "y": 2.5}}, "relations": {}},
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0 and body["msg"] == "success"
        assert body["data"] == {"saved": True}

        # positions 全量覆盖：仅提交的模型被写入，未提交的保持原值（旧侧不落默认值）
        er_pos = {n["id"]: n["erPos"] for n in _graph(client, headers)["nodes"]}
        assert er_pos[order_id] == {"x": 1.5, "y": 2.5}
        assert er_pos[summary_id] == {}
    finally:
        client.__exit__(None, None, None)


def test_put_er_position_defaults_zero_and_coerces_float():
    """旧侧 `float(pos.get("x", 0))`：缺键 → 0.0，字符串数字 → 强转 float。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            order, _, _ = _seed(session)
            order_id = str(order.id)
        client.put(
            "/api/v1/rebuild/models/er",
            json={"positions": {order_id: {"x": "7"}}, "relations": {}},
            headers=headers,
        )
        er_pos = {n["id"]: n["erPos"] for n in _graph(client, headers)["nodes"]}
        assert er_pos[order_id] == {"x": 7.0, "y": 0.0}
    finally:
        client.__exit__(None, None, None)


def test_put_er_unknown_model_position_is_404():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed(session)
        response = client.put(
            "/api/v1/rebuild/models/er",
            json={"positions": {"9999": {"x": 1, "y": 1}}, "relations": {}},
            headers=headers,
        )
        assert response.status_code == 404
        assert response.json()["code"] == 8001
        # 失败不改库
        assert all(n["erPos"] == {} for n in _graph(client, headers)["nodes"])
    finally:
        client.__exit__(None, None, None)


def test_put_er_relations_added_updated_removed():
    """relations 增量 diff 三向（旧侧 `api/model.py:444-452`）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            order, summary, relation = _seed(session)
            order_id, summary_id = order.id, summary.id
            relation_id = relation.id

        # added：无 id → 新建（第二维度边）
        client.put(
            "/api/v1/rebuild/models/er",
            json={
                "positions": {},
                "relations": {"added": [{
                    "source": summary_id, "target": order_id, "relType": "N:1",
                    "srcFields": '["sum_id"]', "tgtFields": '["order_id"]', "joinDesc": "反向",
                }]},
            },
            headers=headers,
        )
        edges = _graph(client, headers)["edges"]
        assert len(edges) == 2
        assert {e["relType"] for e in edges} == {"1:N", "N:1"}

        # updated：带 id → 改四字段（不新建）
        client.put(
            "/api/v1/rebuild/models/er",
            json={
                "positions": {},
                "relations": {"updated": [{
                    "id": relation_id, "relType": "1:1",
                    "srcFields": '["order_id","dt"]', "tgtFields": '["order_id"]',
                    "joinDesc": "改后",
                }]},
            },
            headers=headers,
        )
        edges = _graph(client, headers)["edges"]
        assert len(edges) == 2
        updated = [e for e in edges if e["id"] == relation_id][0]
        assert updated["relType"] == "1:1"
        assert updated["srcFields"] == '["order_id","dt"]'
        assert updated["joinDesc"] == "改后"

        # removed：按 id 删
        client.put(
            "/api/v1/rebuild/models/er",
            json={"positions": {}, "relations": {"removed": [{"id": relation_id}]}},
            headers=headers,
        )
        edges = _graph(client, headers)["edges"]
        assert len(edges) == 1
        assert all(e["id"] != relation_id for e in edges)
    finally:
        client.__exit__(None, None, None)


def test_put_er_forbidden_without_model_write():
    client, app, _ = _client()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="viewer", password="pw-123456", role=Role.VIEWER)
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "viewer", "password": "pw-123456"})
        headers = {"token": login.json()["data"]["token"]}
        response = client.put(
            "/api/v1/rebuild/models/er", json={"positions": {}, "relations": {}}, headers=headers
        )
        assert response.status_code == 403
        assert response.json()["code"] == 1004
        # 读端点不受影响
        assert client.get("/api/v1/rebuild/models/er", headers=headers).status_code == 200
    finally:
        client.__exit__(None, None, None)
