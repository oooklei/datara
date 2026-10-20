"""17.2-14 A6-14 `GET /api/v1/rebuild/models/{model_id}/versions/{version_id}/diff` 契约测试。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md` A6-14
（旧侧实锚 `datara-backend/api/model.py:377-394` `diff_model_version`）。
出参 `{added, removed, changed:[{name,before,after}], relationsChanged:bool}`；diff **仅比较 fields**。
`base` 为可选基准版本 **id**（非版本号）。
"""

import json

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.model.models import DwModelRecord, DwModelVersionRecord

DIFF_KEYS = {"added", "removed", "changed", "relationsChanged"}


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="model-diff-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    return client, app, {"token": login.json()["data"]["token"]}


def _seed(session, *, code="dwd_trade_order"):
    model = DwModelRecord(
        code=code, name="订单明细", layer="DWD", biz_domain="交易域",
        engine="MySQL", owner="alice", status="published", version=2,
    )
    session.add(model)
    session.commit()
    return model


def _snapshot(fields, relations=None):
    return {"model": {"code": "dwd_trade_order"}, "fields": fields, "relations": relations or []}


def _field(name, data_type="BIGINT", **over):
    base = {"name": name, "dataType": data_type, "length": "", "precision": "",
            "nullable": True, "defaultValue": "", "comment": "",
            "isPk": False, "isPartition": False, "dictRef": ""}
    base.update(over)
    return base


def _add_snapshot(session, model_id, *, version, fields, relations=None, note="n"):
    row = DwModelVersionRecord(
        model_id=model_id, version=version,
        snapshot_json=json.dumps(_snapshot(fields, relations), ensure_ascii=False),
        change_note=note, created_by="alice",
    )
    session.add(row)
    session.commit()
    return row


def _diff(client, headers, model_id, version_id, base=None):
    params = {"base": base} if base is not None else None
    return client.get(
        f"/api/v1/rebuild/models/{model_id}/versions/{version_id}/diff",
        params=params, headers=headers,
    )


def test_diff_requires_login():
    client, app, _ = _client()
    try:
        response = client.get("/api/v1/rebuild/models/1/versions/1/diff")
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_diff_added_removed_changed_and_relations_flag():
    """三类字段差异 + `relationsChanged` 布尔；出参四键。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session)
            model_id = model.id
            old = _add_snapshot(session, model_id, version=1, fields=[
                _field("keep", data_type="BIGINT"),
                _field("gone", data_type="VARCHAR"),
                _field("typed", data_type="VARCHAR"),
            ], relations=[{"id": 1, "srcModelId": 1, "tgtModelId": 2}])
            new = _add_snapshot(session, model_id, version=2, fields=[
                _field("keep", data_type="BIGINT"),
                _field("fresh", data_type="DECIMAL"),
                _field("typed", data_type="BIGINT"),
            ], relations=[{"id": 1, "srcModelId": 1, "tgtModelId": 2}])
            old_id, new_id = old.id, new.id
        response = _diff(client, headers, model_id, new_id, base=old_id)
        assert response.status_code == 200, response.json()
        data = response.json()["data"]
        assert set(data) == DIFF_KEYS
        assert [f["name"] for f in data["added"]] == ["fresh"]
        assert [f["name"] for f in data["removed"]] == ["gone"]
        assert data["changed"] == [{
            "name": "typed", "before": _field("typed", data_type="VARCHAR"),
            "after": _field("typed", data_type="BIGINT"),
        }]
        assert data["relationsChanged"] is False
    finally:
        client.__exit__(None, None, None)


def test_diff_without_base_treats_everything_as_added():
    """`base` 缺省 → 基准为空快照 → 全量字段计入 `added`，`relationsChanged` 由关系非空决定。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session)
            model_id = model.id
            new = _add_snapshot(session, model_id, version=1, fields=[
                _field("a"), _field("b"),
            ], relations=[{"id": 1}])
            new_id = new.id
        data = _diff(client, headers, model_id, new_id).json()["data"]
        assert sorted(f["name"] for f in data["added"]) == ["a", "b"]
        assert data["removed"] == [] and data["changed"] == []
        assert data["relationsChanged"] is True  # 基准 relations 为 []，快照非空
    finally:
        client.__exit__(None, None, None)


def test_diff_unknown_base_id_silently_treated_as_empty():
    """`base` 指向不存在的版本 id → 静默按空基准处理（旧侧 `.first()` 返回 None），**不**报错。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session)
            model_id = model.id
            new = _add_snapshot(session, model_id, version=1, fields=[_field("only")])
            new_id = new.id
        data = _diff(client, headers, model_id, new_id, base=424242).json()["data"]
        assert [f["name"] for f in data["added"]] == ["only"]
        assert data["removed"] == [] and data["changed"] == []
    finally:
        client.__exit__(None, None, None)


def test_diff_relations_changed_flag_detects_any_relation_difference():
    """`relationsChanged` 为全量关系列表相等性（任一处不同即为 True）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session)
            model_id = model.id
            old = _add_snapshot(session, model_id, version=1, fields=[_field("x")],
                                relations=[{"id": 1, "joinDesc": "a"}])
            new = _add_snapshot(session, model_id, version=2, fields=[_field("x")],
                                relations=[{"id": 1, "joinDesc": "b"}])
            old_id, new_id = old.id, new.id
        data = _diff(client, headers, model_id, new_id, base=old_id).json()["data"]
        assert data["added"] == [] and data["removed"] == [] and data["changed"] == []
        assert data["relationsChanged"] is True
    finally:
        client.__exit__(None, None, None)


def test_diff_only_compares_fields_not_model_block():
    """快照 `model` 块不同**不**体现在 diff 出参（旧侧仅比较 fields + relations 布尔）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session)
            model_id = model.id
            snap_a = _snapshot([_field("x")])
            snap_a["model"]["remark"] = "旧备注"
            snap_b = _snapshot([_field("x")])
            snap_b["model"]["remark"] = "新备注"
            for ver, snap in ((1, snap_a), (2, snap_b)):
                session.add(DwModelVersionRecord(
                    model_id=model_id, version=ver,
                    snapshot_json=json.dumps(snap, ensure_ascii=False),
                    change_note="n", created_by="alice",
                ))
            session.commit()
            rows = (
                session.query(DwModelVersionRecord)
                .filter(DwModelVersionRecord.model_id == model_id)
                .order_by(DwModelVersionRecord.version)
                .all()
            )
            old_id, new_id = rows[0].id, rows[1].id
        data = _diff(client, headers, model_id, new_id, base=old_id).json()["data"]
        assert data["added"] == [] and data["removed"] == [] and data["changed"] == []
        assert data["relationsChanged"] is False  # relations 相同（皆空）
    finally:
        client.__exit__(None, None, None)


def test_diff_unknown_model_is_404():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed(session)
        response = _diff(client, headers, 9999, 1)
        assert response.status_code == 404
        assert response.json()["code"] == 8001
    finally:
        client.__exit__(None, None, None)


def test_diff_unknown_version_is_404_with_explicit_message():
    """模型存在但版本行不存在 → 8001 + 显式 msg「版本不存在」（与模型缺失的内置 msg 区分）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session)
            model_id = model.id
        response = _diff(client, headers, model_id, 424242)
        assert response.status_code == 404
        assert response.json()["code"] == 8001
        assert response.json()["msg"] == "版本不存在"
    finally:
        client.__exit__(None, None, None)


def test_diff_version_belongs_to_other_model_is_404():
    """版本按 (model_id, id) 双重限定：他模型的版本 id 对本模型不可见。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            mine = _seed(session)
            other = _seed(session, code="ads_trade_sum")
            row = _add_snapshot(session, other.id, version=1, fields=[_field("x")])
            mine_id, other_version_id = mine.id, row.id
        response = _diff(client, headers, mine_id, other_version_id)
        assert response.status_code == 404
        assert response.json()["msg"] == "版本不存在"
    finally:
        client.__exit__(None, None, None)


def test_diff_read_allowed_for_viewer():
    """读端点登录即可（VIEW_ALL）；viewer 可访问。"""
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
        response = _diff(client, headers, model_id, version_id)
        assert response.status_code == 200
        assert response.json()["data"]["added"] != []
    finally:
        client.__exit__(None, None, None)


def _route_pairs(app):
    """展平后的 (method, path) 有序表 —— 与请求匹配同序。"""
    pairs = []
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            pairs.append((method.upper(), path))
    return pairs


def test_diff_route_is_registered():
    """A6-14 五段路由已注册（段数与既有三/四段皆不同，无前缀吞并）。"""
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="diff-order-secret")
    pairs = _route_pairs(app)
    target = [
        (m, p) for m, p in pairs
        if p == "/api/v1/rebuild/models/{model_id}/versions/{version_id}/diff" and m == "GET"
    ]
    assert target, "A6-14 GET .../versions/{version_id}/diff 未注册"
