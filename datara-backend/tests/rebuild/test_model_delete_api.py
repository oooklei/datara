"""17.2-08 A6-8 `DELETE /api/v1/rebuild/models/{model_id}` 契约测试。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md` A6-8
（旧侧实锚 `datara-backend/api/model.py:239-258` `delete_model`）。
错误码：8001/404 模型不存在；8005/409 已物理化不可删除；8008/409 被下游血缘引用（data 带 refs）。
"""

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.model.models import (
    DwModelFieldRecord,
    DwModelRecord,
    DwModelRelationRecord,
)


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="model-delete-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    return client, app, {"token": login.json()["data"]["token"]}


def _seed(session, *, status="draft", with_field=True, downstream=None, code="dwd_trade_order"):
    """单模型（可选字段 + 可选下游血缘）。downstream 为下游模型的 code。"""
    model = DwModelRecord(code=code, name="订单明细", layer="DWD", biz_domain="交易域",
                          engine="MySQL", owner="alice", status=status, version=1)
    session.add(model)
    session.flush()
    if with_field:
        session.add(DwModelFieldRecord(model_id=model.id, seq=1, name="order_id", data_type="BIGINT"))
    if downstream:
        target = DwModelRecord(code=downstream, name="下游汇总", layer="ADS", biz_domain="交易域",
                               engine="Apache Doris", owner="bob", status="draft")
        session.add(target)
        session.flush()
        session.add(DwModelRelationRecord(src_model_id=model.id, tgt_model_id=target.id,
                                          rel_type="1:N", created_by="alice"))
    session.commit()
    return model


def test_delete_model_requires_login():
    client, app, _ = _client()
    try:
        response = client.delete("/api/v1/rebuild/models/1")
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_delete_model_returns_true_and_cascades():
    """出参 true；字段与双向关系级联删除（旧侧 `api/model.py:252-256`）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session)
            model_id = model.id
        response = client.delete(f"/api/v1/rebuild/models/{model_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["code"] == 0
        assert response.json()["data"] is True

        # 模型本体已删
        assert client.get(f"/api/v1/rebuild/models/{model_id}", headers=headers).status_code == 404
        # 级联：字段清空、关系列表不再含该模型
        remaining = client.get(
            "/api/v1/rebuild/models", params={"keyword": "dwd_trade_order"}, headers=headers
        ).json()["data"]
        assert remaining["total"] == 0
    finally:
        client.__exit__(None, None, None)


def test_delete_model_unknown_id_is_404():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed(session)
        response = client.delete("/api/v1/rebuild/models/9999", headers=headers)
        assert response.status_code == 404
        assert response.json()["code"] == 8001
    finally:
        client.__exit__(None, None, None)


def test_delete_model_rejects_physicalized_status():
    """built/produced 态拒删 → 8005/409，不改库。"""
    client, app, headers = _client()
    try:
        # 同一 DB 内两轮，须用不同 code（t_dw_model.code 唯一）
        for status, code in (("built", "dwd_built_order"), ("produced", "dwd_produced_order")):
            with app.state.session_factory() as session:
                model = _seed(session, status=status, code=code)
                model_id = model.id
            response = client.delete(f"/api/v1/rebuild/models/{model_id}", headers=headers)
            assert response.status_code == 409, status
            assert response.json()["code"] == 8005, status
            assert "已物理化模型不可删除" in response.json()["msg"]
            # 未删
            assert client.get(
                f"/api/v1/rebuild/models/{model_id}", headers=headers
            ).status_code == 200
    finally:
        client.__exit__(None, None, None)


def test_delete_model_rejects_when_referenced_downstream():
    """存在以本模型为**上游**的血缘边 → 8008/409，data 带 refs 三元组。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, downstream="ads_trade_sum")
            model_id = model.id
        response = client.delete(f"/api/v1/rebuild/models/{model_id}", headers=headers)
        assert response.status_code == 409
        assert response.json()["code"] == 8008
        refs = response.json()["data"]["refs"]
        assert refs == [{"id": refs[0]["id"], "code": "ads_trade_sum", "name": "下游汇总"}]
        # 未删
        assert client.get(
            f"/api/v1/rebuild/models/{model_id}", headers=headers
        ).status_code == 200
    finally:
        client.__exit__(None, None, None)


def test_delete_model_allows_when_only_downstream_side():
    """旧侧仅查 src 侧：本模型作**下游**（tgt）时被引用**不**阻断删除。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            upstream = _seed(session, downstream=None)
            target = DwModelRecord(code="dim_user", name="用户维表", layer="DIM", biz_domain="用户域",
                                   engine="GreatDB", owner="bob", status="draft")
            session.add(target)
            session.flush()
            session.add(DwModelRelationRecord(src_model_id=upstream.id, tgt_model_id=target.id,
                                              rel_type="N:1", created_by="bob"))
            session.commit()
            target_id = target.id
        response = client.delete(f"/api/v1/rebuild/models/{target_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"] is True
    finally:
        client.__exit__(None, None, None)


def test_delete_model_dangling_downstream_target_is_not_a_ref():
    """旧侧 `if t:` 守卫：下游模型已不存在则不计入 refs（可删）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session)
            model_id = model.id
            session.add(DwModelRelationRecord(src_model_id=model_id, tgt_model_id=424242,
                                              rel_type="1:N", created_by="ghost"))
            session.commit()
        response = client.delete(f"/api/v1/rebuild/models/{model_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"] is True
    finally:
        client.__exit__(None, None, None)


def test_delete_model_forbidden_without_model_write():
    client, app, _ = _client()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="viewer", password="pw-123456", role=Role.VIEWER)
            model_id = _seed(session).id
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "viewer", "password": "pw-123456"})
        headers = {"token": login.json()["data"]["token"]}
        response = client.delete(f"/api/v1/rebuild/models/{model_id}", headers=headers)
        assert response.status_code == 403
        assert response.json()["code"] == 1004
        assert client.get(f"/api/v1/rebuild/models/{model_id}", headers=headers).status_code == 200
    finally:
        client.__exit__(None, None, None)
