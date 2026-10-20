"""17.2-13 A6-13 `POST /api/v1/rebuild/models/{model_id}/versions` 契约测试。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md` A6-13
（旧侧实锚 `datara-backend/api/model.py:362-374` `save_model_version` +
`:325-335` `_model_snapshot` + `:460-463` `_fields_of`）。
错误码：8001/404 模型不存在。
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.model.models import (
    DwModelFieldRecord,
    DwModelRecord,
    DwModelRelationRecord,
    DwModelVersionRecord,
)


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="model-snapshot-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    return client, app, {"token": login.json()["data"]["token"]}


def _seed(session, *, status="published", version=3, code="dwd_trade_order", fields=(), relations=()):
    model = DwModelRecord(
        code=code, name="订单明细", layer="DWD", biz_domain="交易域",
        engine="MySQL", owner="alice", status=status, version=version,
        remark="备注原文",
    )
    session.add(model)
    session.flush()
    for seq, name in enumerate(fields, 1):
        session.add(DwModelFieldRecord(model_id=model.id, seq=seq, name=name, data_type="BIGINT"))
    for tgt_code in relations:
        target = DwModelRecord(code=tgt_code, name="下游汇总", layer="ADS", biz_domain="交易域",
                               engine="Apache Doris", owner="bob", status="draft")
        session.add(target)
        session.flush()
        session.add(DwModelRelationRecord(
            src_model_id=model.id, tgt_model_id=target.id, rel_type="1:N",
            src_fields='["order_id"]', tgt_fields='["order_id"]', join_desc="订单汇总",
            created_by="alice",
        ))
    session.commit()
    return model


def _snapshot_rows(session, model_id):
    return (
        session.query(DwModelVersionRecord)
        .filter(DwModelVersionRecord.model_id == model_id)
        .all()
    )


def test_save_version_requires_login():
    client, app, _ = _client()
    try:
        response = client.post("/api/v1/rebuild/models/1/versions", json={"changeNote": "n"})
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_save_version_returns_triple_and_persists_snapshot():
    """出参 `{id, version, changeNote}`；快照落库且 version 取模型**当前** version。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, version=3, fields=("order_id", "amt"))
            model_id = model.id
        response = client.post(
            f"/api/v1/rebuild/models/{model_id}/versions",
            json={"changeNote": "首次快照"},
            headers=headers,
        )
        assert response.status_code == 200, response.json()
        assert response.json()["code"] == 0
        data = response.json()["data"]
        assert set(data) == {"id", "version", "changeNote"}
        assert data["version"] == 3
        assert data["changeNote"] == "首次快照"
        with app.state.session_factory() as session:
            rows = _snapshot_rows(session, model_id)
            assert len(rows) == 1
            assert rows[0].id == data["id"]
            assert rows[0].version == 3
            assert rows[0].created_by == "admin"
            snap = json.loads(rows[0].snapshot_json)
            assert [f["name"] for f in snap["fields"]] == ["order_id", "amt"]
    finally:
        client.__exit__(None, None, None)


def test_save_version_snapshot_is_full_and_keeps_chinese_verbatim():
    """快照 = 主数据 + fields + relations **全量**；中文不转义（ensure_ascii=False）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, fields=("order_id",), relations=("ads_trade_sum",))
            model_id = model.id
        client.post(
            f"/api/v1/rebuild/models/{model_id}/versions",
            json={"changeNote": "中文说明"},
            headers=headers,
        )
        with app.state.session_factory() as session:
            raw = _snapshot_rows(session, model_id)[0].snapshot_json
        # 中文原样保留（旧侧 ensure_ascii=False）；若被转义则含 "\\u"
        assert "\\u" not in raw
        assert "订单明细" in raw and "备注原文" in raw and "中文说明" not in raw  # 说明不入快照
        snap = json.loads(raw)
        assert set(snap) == {"model", "fields", "relations"}
        assert snap["model"]["code"] == "dwd_trade_order"
        assert snap["model"]["remark"] == "备注原文"
        assert snap["relations"] == [{
            "id": snap["relations"][0]["id"],
            "srcModelId": model_id,
            "tgtModelId": snap["relations"][0]["tgtModelId"],
            "relType": "1:N",
            "srcFields": '["order_id"]',
            "tgtFields": '["order_id"]',
            "joinDesc": "订单汇总",
        }]
    finally:
        client.__exit__(None, None, None)


def test_save_version_strips_change_note():
    """`changeNote.strip()`（旧侧照抄）；缺省空串合法。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            m1 = _seed(session, code="dwd_a")
            m2 = _seed(session, code="dwd_b")
            id1, id2 = m1.id, m2.id
        r1 = client.post(
            f"/api/v1/rebuild/models/{id1}/versions",
            json={"changeNote": "  带空格  "}, headers=headers,
        )
        assert r1.json()["data"]["changeNote"] == "带空格"
        r2 = client.post(f"/api/v1/rebuild/models/{id2}/versions", json={}, headers=headers)
        assert r2.status_code == 200
        assert r2.json()["data"]["changeNote"] == ""
    finally:
        client.__exit__(None, None, None)


def test_save_version_unknown_id_is_404():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed(session)
        response = client.post(
            "/api/v1/rebuild/models/9999/versions", json={"changeNote": "n"}, headers=headers
        )
        assert response.status_code == 404
        assert response.json()["code"] == 8001
    finally:
        client.__exit__(None, None, None)


def test_save_version_duplicate_version_rejected_by_constraint():
    """同 (model_id, version) 二次快照 → 唯一约束拒绝，且**不**被转成友好错误码。

    旧侧仅注册 `ApiError` 处理器（`api/main.py:48`），无 `IntegrityError` 分支，
    故该冲突在旧侧同样**冒泡为原始 DB 错误**（500）。rebuild 侧**照抄**该行为：
    不新增 409/8xxx 分支，由 `IntegrityError` 穿透到传输层。
    本用例据此断言「约束生效 + 未吞未转」—— 这是迁移忠实性的一部分，而非缺陷。
    """
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, version=3)
            model_id = model.id
        first = client.post(
            f"/api/v1/rebuild/models/{model_id}/versions",
            json={"changeNote": "v1"}, headers=headers,
        )
        assert first.status_code == 200
        # 约束冲突穿透到传输层（TestClient 默认 raise_server_exceptions=True）
        with pytest.raises(IntegrityError):
            client.post(
                f"/api/v1/rebuild/models/{model_id}/versions",
                json={"changeNote": "v2"}, headers=headers,
            )
        with app.state.session_factory() as session:
            assert len(_snapshot_rows(session, model_id)) == 1
    finally:
        client.__exit__(None, None, None)


def test_save_version_conflict_is_500_not_a_friendly_code():
    """同一冲突在 `raise_server_exceptions=False` 下表现为 500，非 `{code:8xxx}` 信封。

    锁定「旧侧无 IntegrityError 处理器」这一迁移忠实点：若后续 rebuild 增补了该处理器，
    本用例会失败 —— 届时属**有意的行为变更**，需变更单。
    """
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="snapshot-500-secret")
    client = TestClient(app, raise_server_exceptions=False)
    client.__enter__()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
            model_id = _seed(session, version=3).id
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
        headers = {"token": login.json()["data"]["token"]}
        client.post(f"/api/v1/rebuild/models/{model_id}/versions", json={"changeNote": "v1"}, headers=headers)
        second = client.post(
            f"/api/v1/rebuild/models/{model_id}/versions", json={"changeNote": "v2"}, headers=headers
        )
        assert second.status_code == 500
        # 500 体为 Starlette 默认纯文本，**不是** `{code,msg,data}` 信封
        assert second.text == "Internal Server Error"
        with pytest.raises(json.JSONDecodeError):
            second.json()
    finally:
        client.__exit__(None, None, None)


def test_save_version_after_version_bump_allows_new_snapshot():
    """模型 version 递增后（redraft）可再存同版本号快照 —— 唯一约束按 version 值而非行数。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, status="published", version=3)
            model_id = model.id
        assert client.post(
            f"/api/v1/rebuild/models/{model_id}/versions",
            json={"changeNote": "at v3"}, headers=headers,
        ).json()["data"]["version"] == 3
        # redraft → status=draft, version=4
        assert client.post(
            f"/api/v1/rebuild/models/{model_id}/redraft", headers=headers
        ).json()["data"]["version"] == 4
        again = client.post(
            f"/api/v1/rebuild/models/{model_id}/versions",
            json={"changeNote": "at v4"}, headers=headers,
        )
        assert again.status_code == 200
        assert again.json()["data"]["version"] == 4
        rows = client.get(
            f"/api/v1/rebuild/models/{model_id}/versions", headers=headers
        ).json()["data"]
        assert [r["version"] for r in rows] == [4, 3]
    finally:
        client.__exit__(None, None, None)


def test_save_version_forbidden_without_model_write():
    client, app, _ = _client()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="viewer", password="pw-123456", role=Role.VIEWER)
            model_id = _seed(session).id
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "viewer", "password": "pw-123456"})
        headers = {"token": login.json()["data"]["token"]}
        write = client.post(
            f"/api/v1/rebuild/models/{model_id}/versions",
            json={"changeNote": "n"}, headers=headers,
        )
        assert write.status_code == 403
        assert write.json()["code"] == 1004
        # 读端点（A6-12）不受影响
        assert client.get(f"/api/v1/rebuild/models/{model_id}/versions", headers=headers).status_code == 200
    finally:
        client.__exit__(None, None, None)


def _route_pairs(app):
    """展平后的 (method, path) 有序表 —— 与请求匹配同序。"""
    pairs = []
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            pairs.append((method.upper(), path))
    return pairs


def test_snapshot_route_is_registered_alongside_list():
    """A6-13 与 A6-12 同前缀异方法：两法均已注册，openapi 合并同路径键。"""
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="snapshot-order-secret")
    pairs = _route_pairs(app)
    methods = sorted(m for m, p in pairs if p == "/api/v1/rebuild/models/{model_id}/versions")
    assert methods == ["GET", "POST"], methods
