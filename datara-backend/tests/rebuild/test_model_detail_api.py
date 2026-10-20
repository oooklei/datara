"""17.2-06 A6-6 `GET /api/v1/rebuild/models/{model_id}` 契约测试。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md` A6-6
（旧侧实锚 `datara-backend/api/model.py:198-206` `get_model`；`_field_row` 见 `:72-79`）。
出参 = ModelRow（16 键）+ `fields: ModelFieldRow[]`；错误码 8001/404。
路由次序：`/models/er` 必须先于 `/models/{model_id}`（旧侧注记 `api/model.py:184`）。
"""

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.model.models import DwModelRecord, DwModelFieldRecord

MODEL_KEYS = {
    "id", "code", "name", "layer", "type", "bizDomain", "engine", "engineXc",
    "dsId", "dbName", "securityLevel", "status", "version", "owner",
    "builtAt", "updatedAt", "remark",
}
FIELD_KEYS = {
    "name", "dataType", "length", "precision", "nullable",
    "defaultValue", "comment", "isPk", "isPartition", "dictRef",
}


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="model-detail-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    return client, app, {"token": login.json()["data"]["token"]}


def _seed(session):
    model = DwModelRecord(code="dwd_trade_order", name="订单明细", layer="DWD", biz_domain="交易域",
                          engine="MySQL", owner="alice", status="published", version=2,
                          security_level="内部", er_pos={"x": 1, "y": 2})
    session.add(model)
    session.flush()
    # 故意乱序插入，验证读侧 order_by(seq)
    session.add_all([
        DwModelFieldRecord(model_id=model.id, seq=2, name="amount", data_type="DECIMAL",
                           length="18", precision="2", nullable=False, comment="金额"),
        DwModelFieldRecord(model_id=model.id, seq=1, name="order_id", data_type="BIGINT",
                           nullable=False, is_pk=True, dict_ref="dim_order"),
        DwModelFieldRecord(model_id=model.id, seq=3, name="dt", data_type="DATE",
                           is_partition=True, default_value=""),
    ])
    # 另一模型的字段：不得串入
    other = DwModelRecord(code="ads_trade_sum", name="交易汇总", layer="ADS", biz_domain="交易域",
                          engine="Apache Doris", owner="bob", status="draft")
    session.add(other)
    session.flush()
    session.add(DwModelFieldRecord(model_id=other.id, seq=1, name="other_field", data_type="INT"))
    session.commit()
    return model, other


def test_get_model_requires_login():
    client, app, _ = _client()
    try:
        response = client.get("/api/v1/rebuild/models/1")
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_get_model_returns_row_plus_fields_in_seq_order():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model, other = _seed(session)
        body = client.get(f"/api/v1/rebuild/models/{model.id}", headers=headers).json()
        assert body["code"] == 0 and body["msg"] == "success"
        data = body["data"]

        # ModelRow 16 键 + fields，共 17 键
        assert set(data) == MODEL_KEYS | {"fields"}
        assert data["id"] == model.id and data["code"] == "dwd_trade_order"
        assert data["version"] == 2 and data["status"] == "published"
        assert data["engineXc"] is False            # MySQL 非信创

        # fields 按 seq 升序（种子故意按 2/1/3 插入）
        assert [f["name"] for f in data["fields"]] == ["order_id", "amount", "dt"]
        assert all(set(f) == FIELD_KEYS for f in data["fields"])
        first, second, third = data["fields"]
        assert first["dataType"] == "BIGINT" and first["isPk"] is True
        assert first["dictRef"] == "dim_order"
        assert first["length"] == "" and first["precision"] == ""      # 缺省透传 ""
        assert first["nullable"] is False
        assert second["dataType"] == "DECIMAL"
        assert second["length"] == "18" and second["precision"] == "2"  # 字符串保真
        assert second["comment"] == "金额"
        assert third["isPartition"] is True
        assert third["defaultValue"] == ""

        # 不串入他模型字段
        assert "other_field" not in [f["name"] for f in data["fields"]]
    finally:
        client.__exit__(None, None, None)


def test_get_model_without_fields_returns_empty_list():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model, _ = _seed(session)
        session = app.state.session_factory()
        with session as s:
            s.query(DwModelFieldRecord).filter(
                DwModelFieldRecord.model_id == model.id
            ).delete()
            s.commit()
        data = client.get(f"/api/v1/rebuild/models/{model.id}", headers=headers).json()["data"]
        assert data["fields"] == []
    finally:
        client.__exit__(None, None, None)


def test_get_model_unknown_id_is_404():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed(session)
        response = client.get("/api/v1/rebuild/models/9999", headers=headers)
        assert response.status_code == 404
        assert response.json()["code"] == 8001
    finally:
        client.__exit__(None, None, None)


def test_er_static_route_still_precedes_model_id_route():
    """17.2-06 落地后转生效：`/models/er` 必须仍先于 `/models/{model_id}` 匹配。

    旧侧注记 `api/model.py:184`；若 `{model_id}` 抢前，GET /models/er 会因 int 转换失败返回 422。
    """
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model, _ = _seed(session)
        paths = list(app.openapi()["paths"])
        er_index = paths.index("/api/v1/rebuild/models/er")
        id_index = paths.index("/api/v1/rebuild/models/{model_id}")
        assert er_index < id_index

        # 行为验证：静态段不被 {model_id} 吞并（若被吞并会 422/404，而非 200）
        assert client.get("/api/v1/rebuild/models/er", headers=headers).status_code == 200
        assert client.get(
            f"/api/v1/rebuild/models/{model.id}", headers=headers
        ).status_code == 200
    finally:
        client.__exit__(None, None, None)
