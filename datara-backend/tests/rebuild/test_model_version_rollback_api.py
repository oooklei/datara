"""17.2-15 A6-15 `POST /api/v1/rebuild/models/{model_id}/versions/{version_id}/rollback` 契约测试。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md` A6-15
（旧侧实锚 `datara-backend/api/model.py:396-415` `rollback_model_version`）。
出参 `{status:"draft", version:int, sourceVersion:int}`；回滚后状态 draft、version 递增、保存新快照。
"""

import json

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.model.models import DwModelRecord, DwModelVersionRecord


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="model-rollback-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    return client, app, {"token": login.json()["data"]["token"]}


def _seed(session, *, status="published", version=5, code="dwd_trade_order"):
    model = DwModelRecord(
        code=code, name="订单明细", layer="DWD", biz_domain="交易域",
        engine="MySQL", owner="alice", status=status, version=version,
    )
    session.add(model)
    session.commit()
    return model


def _field(name, data_type="BIGINT", **over):
    base = {"name": name, "dataType": data_type, "length": "", "precision": "",
            "nullable": True, "defaultValue": "", "comment": "",
            "isPk": False, "isPartition": False, "dictRef": ""}
    base.update(over)
    return base


def _add_snapshot(session, model_id, *, version, fields, note="n"):
    row = DwModelVersionRecord(
        model_id=model_id, version=version,
        snapshot_json=json.dumps({"model": {}, "fields": fields, "relations": []},
                                ensure_ascii=False),
        change_note=note, created_by="alice",
    )
    session.add(row)
    session.commit()
    return row


def _fields_of(client, headers, model_id):
    return client.get(f"/api/v1/rebuild/models/{model_id}", headers=headers).json()["data"]["fields"]


def test_rollback_requires_login():
    client, app, _ = _client()
    try:
        response = client.post("/api/v1/rebuild/models/1/versions/1/rollback")
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_rollback_restores_fields_and_returns_triple():
    """字段还原为快照内容；出参 `{status:"draft", version, sourceVersion}`。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, status="published", version=5)
            model_id = model.id
            snap = _add_snapshot(session, model_id, version=3, fields=[
                _field("old_id", data_type="INT"), _field("old_name", data_type="VARCHAR"),
            ])
            snap_id = snap.id
        response = client.post(
            f"/api/v1/rebuild/models/{model_id}/versions/{snap_id}/rollback", headers=headers
        )
        assert response.status_code == 200, response.json()
        data = response.json()["data"]
        assert set(data) == {"status", "version", "sourceVersion"}
        assert data["status"] == "draft"
        assert data["version"] == 6      # 5 + 1
        assert data["sourceVersion"] == 3  # 快照行的 version 值（非入参 snap_id）
        detail = client.get(f"/api/v1/rebuild/models/{model_id}", headers=headers).json()["data"]
        assert detail["status"] == "draft"
        assert detail["version"] == 6
        assert [f["name"] for f in detail["fields"]] == ["old_id", "old_name"]
    finally:
        client.__exit__(None, None, None)


def test_rollback_replaces_existing_fields_not_merges():
    """回滚是**全量替换**：快照外字段被删除，seq 自 1 重排。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, status="draft", version=2)
            model_id = model.id
            # 当前模型有两字段；快照只有一字段
            from rebuild.model.models import DwModelFieldRecord
            session.add_all([
                DwModelFieldRecord(model_id=model_id, seq=1, name="now_a", data_type="INT"),
                DwModelFieldRecord(model_id=model_id, seq=2, name="now_b", data_type="INT"),
            ])
            snap = _add_snapshot(session, model_id, version=1, fields=[_field("only_old")])
            model_id, snap_id = model.id, snap.id
            session.commit()
        client.post(f"/api/v1/rebuild/models/{model_id}/versions/{snap_id}/rollback", headers=headers)
        fields = _fields_of(client, headers, model_id)
        assert [f["name"] for f in fields] == ["only_old"]
        assert "now_a" not in [f["name"] for f in fields]
    finally:
        client.__exit__(None, None, None)


def test_rollback_saves_new_snapshot_with_rollback_note():
    """回滚后存**新快照**（version 递增后的新值），`change_note` = `rollback from {src.version}`。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, status="published", version=5)
            model_id = model.id
            snap = _add_snapshot(session, model_id, version=3, fields=[_field("x")])
            snap_id = snap.id
        client.post(f"/api/v1/rebuild/models/{model_id}/versions/{snap_id}/rollback", headers=headers)
        rows = client.get(
            f"/api/v1/rebuild/models/{model_id}/versions", headers=headers
        ).json()["data"]
        assert [r["version"] for r in rows] == [6, 3]
        newest = rows[0]
        assert newest["changeNote"] == "rollback from 3"
        assert newest["createdBy"] == "admin"
        with app.state.session_factory() as session:
            raw = (
                session.query(DwModelVersionRecord)
                .filter(DwModelVersionRecord.id == newest["id"])
                .first()
                .snapshot_json
            )
        assert json.loads(raw)["fields"] == [_field("x")]
    finally:
        client.__exit__(None, None, None)


def test_rollback_does_not_require_non_draft_status():
    """**无状态闸**：模型已是 draft 时旧侧同样执行回滚（不报 8005）—— 照抄。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, status="draft", version=1)
            model_id = model.id
            snap = _add_snapshot(session, model_id, version=1, fields=[_field("x")])
            snap_id = snap.id
        response = client.post(
            f"/api/v1/rebuild/models/{model_id}/versions/{snap_id}/rollback", headers=headers
        )
        assert response.status_code == 200, response.json()
        assert response.json()["data"]["status"] == "draft"
        assert response.json()["data"]["version"] == 2
    finally:
        client.__exit__(None, None, None)


def test_rollback_unknown_model_is_404():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed(session)
        response = client.post("/api/v1/rebuild/models/9999/versions/1/rollback", headers=headers)
        assert response.status_code == 404
        assert response.json()["code"] == 8001
    finally:
        client.__exit__(None, None, None)


def test_rollback_unknown_version_is_404_with_explicit_message():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session)
            model_id = model.id
        response = client.post(
            f"/api/v1/rebuild/models/{model_id}/versions/424242/rollback", headers=headers
        )
        assert response.status_code == 404
        assert response.json()["code"] == 8001
        assert response.json()["msg"] == "版本不存在"
        # 未改库
        detail = client.get(f"/api/v1/rebuild/models/{model_id}", headers=headers).json()["data"]
        assert detail["status"] == "published"
    finally:
        client.__exit__(None, None, None)


def test_rollback_version_of_other_model_is_404():
    """版本按 (model_id, id) 双重限定。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            mine = _seed(session)
            other = _seed(session, code="ads_trade_sum")
            row = _add_snapshot(session, other.id, version=1, fields=[_field("x")])
            mine_id, other_version_id = mine.id, row.id
        response = client.post(
            f"/api/v1/rebuild/models/{mine_id}/versions/{other_version_id}/rollback",
            headers=headers,
        )
        assert response.status_code == 404
        assert response.json()["msg"] == "版本不存在"
    finally:
        client.__exit__(None, None, None)


def test_rollback_forbidden_without_model_write():
    client, app, _ = _client()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="viewer", password="pw-123456", role=Role.VIEWER)
            model = _seed(session)
            row = _add_snapshot(session, model.id, version=1, fields=[_field("x")])
            model_id, version_id = model.id, row.id
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "viewer", "password": "pw-123456"})
        headers = {"token": login.json()["data"]["token"]}
        response = client.post(
            f"/api/v1/rebuild/models/{model_id}/versions/{version_id}/rollback", headers=headers
        )
        assert response.status_code == 403
        assert response.json()["code"] == 1004
        # 读端点（A6-14 diff）不受影响
        assert client.get(
            f"/api/v1/rebuild/models/{model_id}/versions/{version_id}/diff", headers=headers
        ).status_code == 200
    finally:
        client.__exit__(None, None, None)


def _route_pairs(app):
    """展平后的 (method, path) 有序表 —— 与请求匹配同序。"""
    pairs = []
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            pairs.append((method.upper(), path))
    return pairs


def test_rollback_route_is_registered():
    """A6-15 五段路由已注册，且与 A6-14 `GET .../diff` 同段数但尾段字面不同（不吞并）。"""
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="rollback-order-secret")
    pairs = _route_pairs(app)
    rollback = [
        (m, p) for m, p in pairs
        if p == "/api/v1/rebuild/models/{model_id}/versions/{version_id}/rollback" and m == "POST"
    ]
    assert rollback, "A6-15 POST .../rollback 未注册"
    diff = [
        (m, p) for m, p in pairs
        if p == "/api/v1/rebuild/models/{model_id}/versions/{version_id}/diff" and m == "GET"
    ]
    assert diff, "A6-14 GET .../diff 未注册"
