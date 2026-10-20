"""17.2-12 A6-12 `GET /api/v1/rebuild/models/{model_id}/versions` 契约测试。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md` A6-12
（旧侧实锚 `datara-backend/api/model.py:355-361` `list_model_versions`）。
错误码：8001/404 模型不存在。排序：`version` 降序 + `id` 降序。
"""

import json

from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.model.models import DwModelRecord, DwModelVersionRecord

VERSION_KEYS = {"id", "version", "changeNote", "createdBy", "createdAt"}


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="model-versions-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    return client, app, {"token": login.json()["data"]["token"]}


def _seed(session, *, version=1, code="dwd_trade_order"):
    model = DwModelRecord(
        code=code, name="订单明细", layer="DWD", biz_domain="交易域",
        engine="MySQL", owner="alice", status="published", version=version,
    )
    session.add(model)
    session.commit()
    return model


def _add_version(session, model_id, *, version, note="n", by="alice"):
    row = DwModelVersionRecord(
        model_id=model_id, version=version,
        snapshot_json=json.dumps({"model": {}, "fields": [], "relations": []}, ensure_ascii=False),
        change_note=note, created_by=by,
    )
    session.add(row)
    session.commit()
    return row


def test_versions_requires_login():
    client, app, _ = _client()
    try:
        response = client.get("/api/v1/rebuild/models/1/versions")
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_versions_returns_rows_shape_and_descending_order():
    """五键行；`version` 降序（旧侧排序 `version desc(), id desc()`）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session)
            model_id = model.id
            # 故意乱序插入，验证排序在 DB 侧而非插入侧
            _add_version(session, model_id, version=2, note="second")
            _add_version(session, model_id, version=4, note="fourth")
            _add_version(session, model_id, version=1, note="first")
            _add_version(session, model_id, version=3, note="third")
        response = client.get(f"/api/v1/rebuild/models/{model_id}/versions", headers=headers)
        assert response.status_code == 200, response.json()
        rows = response.json()["data"]
        assert [r["version"] for r in rows] == [4, 3, 2, 1]
        assert all(set(r) == VERSION_KEYS for r in rows)
        assert rows[0]["changeNote"] == "fourth"
        assert rows[0]["createdBy"] == "alice"
        assert isinstance(rows[0]["createdAt"], str) and rows[0]["createdAt"]
    finally:
        client.__exit__(None, None, None)


def test_versions_unique_constraint_blocks_duplicate_version():
    """旧侧 `UniqueConstraint(model_id, version)` 使同版本双行不可存在。

    因此旧侧排序里的 `id desc` 次级键**在该约束下不可达**（同 version 至多一行）。
    本用例锁定该约束在 rebuild 侧同样生效 —— 重复 (model_id, version) 抛 IntegrityError。
    """
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session)
            model_id = model.id
            _add_version(session, model_id, version=1, note="first")
        with app.state.session_factory() as session:
            try:
                _add_version(session, model_id, version=1, note="dup")
            except IntegrityError:
                session.rollback()
            else:
                raise AssertionError("重复 (model_id, version) 未被唯一约束拒绝")
        rows = client.get(
            f"/api/v1/rebuild/models/{model_id}/versions", headers=headers
        ).json()["data"]
        assert len(rows) == 1
        assert rows[0]["changeNote"] == "first"
    finally:
        client.__exit__(None, None, None)


def test_versions_unknown_model_is_404():
    """8001 判定对象是**模型**：模型不存在 → 404/8001。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed(session)
        response = client.get("/api/v1/rebuild/models/9999/versions", headers=headers)
        assert response.status_code == 404
        assert response.json()["code"] == 8001
    finally:
        client.__exit__(None, None, None)


def test_versions_empty_list_is_not_404():
    """模型存在但无快照 → 200 + 空列表（旧侧不因无版本而报错）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session)
            model_id = model.id
        response = client.get(f"/api/v1/rebuild/models/{model_id}/versions", headers=headers)
        assert response.status_code == 200
        assert response.json()["code"] == 0
        assert response.json()["data"] == []
    finally:
        client.__exit__(None, None, None)


def test_versions_only_returns_own_model_snapshots():
    """快照按 model_id 隔离，不串其他模型。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            mine = _seed(session)
            other = _seed(session, code="ads_trade_sum")
            _add_version(session, mine.id, version=1)
            _add_version(session, mine.id, version=2)
            _add_version(session, other.id, version=99, note="other")
            mine_id = mine.id
        rows = client.get(
            f"/api/v1/rebuild/models/{mine_id}/versions", headers=headers
        ).json()["data"]
        assert [r["version"] for r in rows] == [2, 1]
    finally:
        client.__exit__(None, None, None)


def test_versions_read_allowed_but_write_denied_for_viewer():
    """权限不对称：viewer 持 VIEW_ALL（可读版本）但不持 EDIT_DEFINITION（不可发布）。"""
    client, app, _ = _client()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="viewer", password="pw-123456", role=Role.VIEWER)
            model_id = _seed(session).id
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "viewer", "password": "pw-123456"})
        headers = {"token": login.json()["data"]["token"]}
        read = client.get(f"/api/v1/rebuild/models/{model_id}/versions", headers=headers)
        assert read.status_code == 200
        assert read.json()["data"] == []
        write = client.post(f"/api/v1/rebuild/models/{model_id}/publish", headers=headers)
        assert write.status_code == 403
        assert write.json()["code"] == 1004
    finally:
        client.__exit__(None, None, None)


def _route_pairs(app):
    """展平后的 (method, path) 有序表 —— 与请求匹配同序。"""
    pairs = []
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            pairs.append((method.upper(), path))
    return pairs


def test_versions_route_is_registered_and_reachable():
    """A6-12 三段路由可达性：已注册 + 其前无末段为 `{...}` 的同段数路由 + 语义归 versions 列表。"""
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="versions-order-secret")
    pairs = _route_pairs(app)
    target = [
        i for i, (m, p) in enumerate(pairs)
        if p == "/api/v1/rebuild/models/{model_id}/versions" and m == "GET"
    ]
    assert target, "A6-12 GET /models/{model_id}/versions 未注册"
    rivals = [
        (i, m, p) for i, (m, p) in enumerate(pairs)
        if p.startswith("/api/v1/rebuild/models/{model_id}/")
        and len(p.split("/")) == len("/api/v1/rebuild/models/{model_id}/versions".split("/"))
        and p.split("/")[-1].startswith("{")
    ]
    assert not [r for r in rivals if r[0] < target[0]], f"存在更早的同段数动态路由：{rivals}"
