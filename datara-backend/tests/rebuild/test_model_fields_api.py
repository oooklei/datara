"""17.2-09 A6-9 `PUT /api/v1/rebuild/models/{model_id}/fields` 契约测试。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md` A6-9
（旧侧实锚 `datara-backend/api/model.py:288-305` `save_fields`；`_field_kwargs` 映射 `:267-283`）。
错误码：8001/404 模型不存在；8007/409 非 draft 不可改字段；8006/422 乐观锁冲突（data 带 currentRev）。
"""

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.model.models import DwModelFieldRecord, DwModelRecord


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="model-fields-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    return client, app, {"token": login.json()["data"]["token"]}


def _seed(session, *, status="draft", version=1, fields=(), code="dwd_trade_order"):
    """单模型（可选既有字段，用于验证全量替换）。"""
    model = DwModelRecord(
        code=code, name="订单明细", layer="DWD", biz_domain="交易域",
        engine="MySQL", owner="alice", status=status, version=version,
    )
    session.add(model)
    session.flush()
    for seq, name in enumerate(fields, 1):
        session.add(DwModelFieldRecord(model_id=model.id, seq=seq, name=name, data_type="VARCHAR"))
    session.commit()
    return model


def _field(name, **over):
    """A6-9 契约字段 dict（驼峰键名，与 FE `_field_row` 回读键一致）。"""
    base = {"name": name, "dataType": "varchar", "length": "", "precision": "",
            "nullable": True, "defaultValue": "", "comment": "",
            "isPk": False, "isPartition": False, "dictRef": ""}
    base.update(over)
    return base


def test_save_fields_requires_login():
    client, app, _ = _client()
    try:
        response = client.put("/api/v1/rebuild/models/1/fields", json={"rev": 1, "fields": []})
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_save_fields_replaces_all_and_renumbers_seq():
    """全量替换：旧字段清空、按提交顺序 seq 自 1 重排、返回递增后的 rev。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, fields=("old_a", "old_b"))
            model_id = model.id
        response = client.put(
            f"/api/v1/rebuild/models/{model_id}/fields",
            json={"rev": 1, "fields": [_field("order_id", isPk=True), _field("amt"), _field("ts")]},
            headers=headers,
        )
        assert response.status_code == 200, response.json()
        assert response.json()["code"] == 0
        assert response.json()["data"] == {"rev": 2}

        detail = client.get(f"/api/v1/rebuild/models/{model_id}", headers=headers).json()["data"]
        assert [f["name"] for f in detail["fields"]] == ["order_id", "amt", "ts"]
        assert detail["version"] == 2
        # 旧字段确实被删（全量替换，非合并）
        assert "old_a" not in [f["name"] for f in detail["fields"]]
        assert detail["fields"][0]["isPk"] is True
    finally:
        client.__exit__(None, None, None)


def test_save_fields_unknown_id_is_404():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed(session)
        response = client.put(
            "/api/v1/rebuild/models/9999/fields", json={"rev": 1, "fields": []}, headers=headers
        )
        assert response.status_code == 404
        assert response.json()["code"] == 8001
    finally:
        client.__exit__(None, None, None)


def test_save_fields_rejects_non_draft_status():
    """非 draft（含 published / built / produced）→ 8007/409，且先于乐观锁判定，不改库。"""
    client, app, headers = _client()
    try:
        for status, code in (
            ("published", "dwd_pub_order"),
            ("built", "dwd_built_order"),
            ("produced", "dwd_prod_order"),
        ):
            with app.state.session_factory() as session:
                model = _seed(session, status=status, version=5, code=code)
                model_id = model.id
            response = client.put(
                f"/api/v1/rebuild/models/{model_id}/fields",
                json={"rev": 5, "fields": [_field("x")]},
                headers=headers,
            )
            assert response.status_code == 409, status
            assert response.json()["code"] == 8007, status
            assert "已发布模型不可修改字段" in response.json()["msg"]
            # 状态闸先于乐观锁：rev 即便错也不报 8006
            assert response.json()["data"] is None
            detail = client.get(f"/api/v1/rebuild/models/{model_id}", headers=headers).json()["data"]
            assert detail["version"] == 5
            assert detail["fields"] == []
    finally:
        client.__exit__(None, None, None)


def test_save_fields_optimistic_lock_conflict_returns_current_rev():
    """rev 已被他人推进 → 8006/422，data.currentRev 为回读的真实 version。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, version=3)
            model_id = model.id
        response = client.put(
            f"/api/v1/rebuild/models/{model_id}/fields",
            json={"rev": 1, "fields": [_field("x")]},
            headers=headers,
        )
        assert response.status_code == 422
        assert response.json()["code"] == 8006
        assert response.json()["data"] == {"currentRev": 3}
        # 冲突后库未被改动
        detail = client.get(f"/api/v1/rebuild/models/{model_id}", headers=headers).json()["data"]
        assert detail["version"] == 3
        assert detail["fields"] == []
    finally:
        client.__exit__(None, None, None)


def test_save_fields_rev_advances_and_stale_rev_then_fails():
    """rev 逐次递增：rev=1 成功 → rev=1 再提冲突 → rev=2 成功。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session)
            model_id = model.id
        first = client.put(
            f"/api/v1/rebuild/models/{model_id}/fields",
            json={"rev": 1, "fields": [_field("a")]}, headers=headers,
        )
        assert first.json()["data"] == {"rev": 2}
        stale = client.put(
            f"/api/v1/rebuild/models/{model_id}/fields",
            json={"rev": 1, "fields": [_field("b")]}, headers=headers,
        )
        assert stale.status_code == 422
        assert stale.json()["data"] == {"currentRev": 2}
        second = client.put(
            f"/api/v1/rebuild/models/{model_id}/fields",
            json={"rev": 2, "fields": [_field("b")]}, headers=headers,
        )
        assert second.json()["data"] == {"rev": 3}
        detail = client.get(f"/api/v1/rebuild/models/{model_id}", headers=headers).json()["data"]
        assert [f["name"] for f in detail["fields"]] == ["b"]
        assert detail["version"] == 3
    finally:
        client.__exit__(None, None, None)


def test_save_fields_normalizes_contract_keys():
    """`_field_kwargs` 映射：dataType 大写、nullable/isPk 布尔化、空串归一（回读键驼峰）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session)
            model_id = model.id
        client.put(
            f"/api/v1/rebuild/models/{model_id}/fields",
            json={
                "rev": 1,
                "fields": [
                    {"name": "  order_id  ", "dataType": "bigint", "nullable": False,
                     "isPk": True, "length": 20},
                    {"name": "no_flags"},  # 全缺省 → dataType VARCHAR / nullable True / 标志 False
                ],
            },
            headers=headers,
        )
        fields = client.get(
            f"/api/v1/rebuild/models/{model_id}", headers=headers
        ).json()["data"]["fields"]
        assert fields[0] == {
            "name": "order_id", "dataType": "BIGINT", "length": "20", "precision": "",
            "nullable": False, "defaultValue": "", "comment": "",
            "isPk": True, "isPartition": False, "dictRef": "",
        }
        assert fields[1]["dataType"] == "VARCHAR"
        assert fields[1]["nullable"] is True
        assert fields[1]["isPk"] is False
        assert fields[1]["isPartition"] is False
    finally:
        client.__exit__(None, None, None)


def test_save_fields_forbidden_without_model_write():
    client, app, _ = _client()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="viewer", password="pw-123456", role=Role.VIEWER)
            model_id = _seed(session).id
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "viewer", "password": "pw-123456"})
        headers = {"token": login.json()["data"]["token"]}
        response = client.put(
            f"/api/v1/rebuild/models/{model_id}/fields",
            json={"rev": 1, "fields": []}, headers=headers,
        )
        assert response.status_code == 403
        assert response.json()["code"] == 1004
        # 读端点不受影响
        assert client.get(f"/api/v1/rebuild/models/{model_id}", headers=headers).status_code == 200
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


def test_fields_route_is_registered_and_reachable():
    """A6-9 路由可达性：`/models/{model_id}/fields` 命中 fields 处理器而非 A6-7 更新。

    与 17.2-04/05/07 的静态段吞并风险**不同**：Starlette 按段数匹配，两段的
    `/models/{model_id}` 不可能吞并三段的 `/models/{model_id}/fields`。故此处断言的是
    ① 该三段路由已注册；② 其前**无其他**三段 models 路由（否则才构成吞并）；
    ③ 行为上 fields 请求确由乐观锁语义处理（422/8006），而 `/models/{model_id}`
    仍由 A6-7 更新语义处理（200 + data 为模型行）。
    """
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="fields-order-secret")
    pairs = _route_pairs(app)
    target = [
        i for i, (method, path) in enumerate(pairs)
        if path == "/api/v1/rebuild/models/{model_id}/fields" and method == "PUT"
    ]
    assert target, "A6-9 PUT /models/{model_id}/fields 未注册"
    # 仅**末段为路径参数**的同段数路由才可能吞并（字面尾段不同则永不匹配）
    rivals = [
        (i, method, path) for i, (method, path) in enumerate(pairs)
        if path.startswith("/api/v1/rebuild/models/{model_id}/")
        and len(path.split("/")) == len("/api/v1/rebuild/models/{model_id}/fields".split("/"))
        and path.split("/")[-1].startswith("{")
    ]
    assert not [r for r in rivals if r[0] < target[0]], (
        f"存在更早注册的同段数路由可吞并 A6-9：{rivals}"
    )

    # 行为验证：两路由各自语义独立
    client = TestClient(app)
    client.__enter__()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
        headers = {"token": login.json()["data"]["token"]}
        with app.state.session_factory() as session:
            model = _seed(session, version=9)
            model_id = model.id
        stale = client.put(
            f"/api/v1/rebuild/models/{model_id}/fields", json={"rev": 1, "fields": []}, headers=headers
        )
        assert stale.status_code == 422 and stale.json()["code"] == 8006
        updated = client.put(
            f"/api/v1/rebuild/models/{model_id}", json={"remark": "r1"}, headers=headers
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["remark"] == "r1"
    finally:
        client.__exit__(None, None, None)
