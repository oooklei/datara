"""17.2-16 A6-16 `GET /api/v1/rebuild/models/{model_id}/ddl` 契约测试。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md` A6-16
（旧侧实锚 `datara-backend/api/model.py:466-481` `preview_ddl`）。
出参 `{engine, ddl, notes}`；`engine` 缺省按模型 `engine` 查 `t_engine_type.ddl`，
取不到回退 `"mysql"`；`gen_ddl` 的 `ValueError` → 8003/400（msg 为异常原文）；**不落库**。
"""

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.model.models import (
    DwModelFieldRecord,
    DwModelRecord,
    DwModelVersionRecord,
    EngineTypeRecord,
)

DDL_KEYS = {"engine", "ddl", "notes"}


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="model-ddl-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    return client, app, {"token": login.json()["data"]["token"]}


def _seed_engine(session, *, name="MySQL", ddl="mysql"):
    """引擎字典种子（幂等）。

    应用启动已写入 MySQL/Apache Doris/GreatDB 三行（`rebuild/model/dicts.py:37-42`），
    故存在即改 `ddl`、不存在才插入 —— 否则撞 `t_engine_type.name` 主键。
    """
    row = session.get(EngineTypeRecord, name)
    if row is None:
        session.add(EngineTypeRecord(name=name, ddl=ddl, xc=False))
    else:
        row.ddl = ddl
    session.commit()


def _seed(
    session,
    *,
    code="dwd_trade_order",
    name="订单明细",
    engine="MySQL",
    status="draft",
    version=1,
    fields=(),
):
    model = DwModelRecord(
        code=code, name=name, layer="DWD", biz_domain="交易域",
        engine=engine, owner="alice", status=status, version=version,
    )
    session.add(model)
    session.commit()
    for seq, field in enumerate(fields, 1):
        session.add(DwModelFieldRecord(
            model_id=model.id, seq=seq, name=field["name"], data_type=field.get("dataType", "VARCHAR"),
            length=field.get("length", ""), precision=field.get("precision", ""),
            nullable=field.get("nullable", True), default_value=field.get("defaultValue", ""),
            comment=field.get("comment", ""), is_pk=field.get("isPk", False),
            is_partition=field.get("isPartition", False), dict_ref="",
        ))
    session.commit()
    return model


def _field(name, data_type="BIGINT", **over):
    base = {"name": name, "dataType": data_type, "length": "", "precision": "",
            "nullable": True, "defaultValue": "", "comment": "",
            "isPk": False, "isPartition": False}
    base.update(over)
    return base


def _ddl(client, headers, model_id, engine=None):
    params = {"engine": engine} if engine is not None else None
    return client.get(
        f"/api/v1/rebuild/models/{model_id}/ddl", params=params, headers=headers
    )


# ---------------------------------------------------------------- 鉴权 / 权限


def test_ddl_requires_login():
    client, app, _ = _client()
    try:
        response = client.get("/api/v1/rebuild/models/1/ddl")
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_ddl_read_allowed_for_viewer():
    """读端点登录即可（VIEW_ALL）；viewer 可访问。"""
    client, app, _ = _client()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="viewer", password="pw-123456", role=Role.VIEWER)
            _seed_engine(session)
            model = _seed(session, fields=[_field("id")])
            model_id = model.id
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "viewer", "password": "pw-123456"})
        headers = {"token": login.json()["data"]["token"]}
        response = _ddl(client, headers, model_id)
        assert response.status_code == 200
        assert set(response.json()["data"]) == DDL_KEYS
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- engine 解析


def test_ddl_default_engine_resolves_from_model_engine():
    """`engine` 缺省 → 按模型 `engine` 查 `t_engine_type.ddl`（旧侧 `row.ddl`）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session, name="Apache Doris", ddl="doris")
            model = _seed(session, engine="Apache Doris", fields=[_field("id")])
            model_id = model.id
        data = _ddl(client, headers, model_id).json()["data"]
        assert data["engine"] == "doris"
        assert "DISTRIBUTED BY HASH(`id`) BUCKETS 10" in data["ddl"]
        assert data["notes"] == []
    finally:
        client.__exit__(None, None, None)


def test_ddl_default_engine_falls_back_to_mysql_when_model_engine_blank():
    """模型 `engine` 为空串 → 旧侧 `if m.engine` 为假，直接回退 `"mysql"`（不查字典）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, engine="", fields=[_field("id")])
            model_id = model.id
        data = _ddl(client, headers, model_id).json()["data"]
        assert data["engine"] == "mysql"
        assert data["ddl"].endswith("ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单明细'")
    finally:
        client.__exit__(None, None, None)


def test_ddl_default_engine_falls_back_to_mysql_when_engine_row_missing():
    """模型 `engine` 指向不存在的字典行 → `db.get` 返回 None → 回退 `"mysql"`。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, engine="Nonexistent", fields=[_field("id")])
            model_id = model.id
        assert _ddl(client, headers, model_id).json()["data"]["engine"] == "mysql"
    finally:
        client.__exit__(None, None, None)


def test_ddl_default_engine_falls_back_to_mysql_when_ddl_column_blank():
    """字典行存在但 `ddl` 列为空 → `row and row.ddl` 为假 → 回退 `"mysql"`。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session, name="OddEngine", ddl="")
            model = _seed(session, engine="OddEngine", fields=[_field("id")])
            model_id = model.id
        assert _ddl(client, headers, model_id).json()["data"]["engine"] == "mysql"
    finally:
        client.__exit__(None, None, None)


def test_ddl_explicit_engine_overrides_model_engine():
    """显式 `engine` query 覆盖模型引擎映射（旧侧 `else: ddl_id = engine`）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session, name="MySQL", ddl="mysql")
            model = _seed(session, engine="MySQL", fields=[_field("id")])
            model_id = model.id
        data = _ddl(client, headers, model_id, engine="greatdb").json()["data"]
        assert data["engine"] == "greatdb"
        # greatdb 与 mysql 同语系（dsconn 裁定②）
        assert "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4" in data["ddl"]
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- DDL 渲染


def test_ddl_renders_column_lines_exactly():
    """列渲染逐字断言：NOT NULL / DEFAULT / COMMENT / 主键 / DECIMAL 精度。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session, name="MySQL", ddl="mysql")
            model = _seed(session, fields=[
                _field("id", data_type="BIGINT", isPk=True, nullable=False),
                _field("amt", data_type="DECIMAL", length="18", precision="2",
                       defaultValue="0", comment="金额"),
                _field("remark", data_type="VARCHAR", length="255"),
            ])
            model_id = model.id
        data = _ddl(client, headers, model_id).json()["data"]
        assert data["ddl"] == (
            "CREATE TABLE `dwd_trade_order` (\n"
            "  `id` BIGINT NOT NULL COMMENT 'id',\n"
            "  `amt` DECIMAL(18,2) DEFAULT '0' COMMENT '金额',\n"
            "  `remark` VARCHAR(255) COMMENT 'remark',\n"
            "  PRIMARY KEY (`id`)\n"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单明细'"
        )
    finally:
        client.__exit__(None, None, None)


def test_ddl_mysql_partition_note_present():
    """`is_partition` 仅 doris 生效；mysql/greatdb 由 `dialect_notes` 提示不支持。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session, name="MySQL", ddl="mysql")
            model = _seed(session, fields=[_field("dt", data_type="DATE", isPartition=True)])
            model_id = model.id
        data = _ddl(client, headers, model_id).json()["data"]
        assert data["notes"] == ["该引擎不支持分区声明"]
        assert "PARTITION BY RANGE" not in data["ddl"]
    finally:
        client.__exit__(None, None, None)


def test_ddl_doris_partition_and_distribution():
    """doris 方言：分区声明 + HASH 分布 + PROPERTIES，且**不**出分区不支持提示。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, fields=[
                _field("id", data_type="BIGINT", isPk=True, nullable=False),
                _field("dt", data_type="DATE", isPartition=True),
            ])
            model_id = model.id
        data = _ddl(client, headers, model_id, engine="doris").json()["data"]
        assert data["notes"] == []
        assert "PARTITION BY RANGE(`dt`) ()" in data["ddl"]
        assert "DISTRIBUTED BY HASH(`id`) BUCKETS 10" in data["ddl"]
        assert "'dynamic_partition.enable' = 'true'" in data["ddl"]
        assert "ENGINE=InnoDB" not in data["ddl"]
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- 400 边界


def test_ddl_empty_fields_is_400():
    """空字段列表 → 8003/400，msg 为 ddlgen 异常原文「字段列表为空」。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session, name="MySQL", ddl="mysql")
            model = _seed(session, fields=[])
            model_id = model.id
        response = _ddl(client, headers, model_id)
        assert response.status_code == 400
        assert response.json()["code"] == 8003
        assert response.json()["msg"] == "字段列表为空"
    finally:
        client.__exit__(None, None, None)


def test_ddl_illegal_identifier_is_400():
    """非法标识符（含空格）→ 8003/400「不合法的标识符: 'bad name'」。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session, name="MySQL", ddl="mysql")
            model = _seed(session, fields=[_field("bad name")])
            model_id = model.id
        response = _ddl(client, headers, model_id)
        assert response.status_code == 400
        assert response.json()["code"] == 8003
        assert response.json()["msg"] == "不合法的标识符: 'bad name'"
    finally:
        client.__exit__(None, None, None)


def test_ddl_empty_field_name_is_400():
    """空字段名 → `str(f.get('name') or '')` 得空串 → 同样 ValueError（标识符分支）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session, name="MySQL", ddl="mysql")
            model = _seed(session, fields=[_field("")])
            model_id = model.id
        response = _ddl(client, headers, model_id)
        assert response.status_code == 400
        assert response.json()["msg"] == "不合法的标识符: ''"
    finally:
        client.__exit__(None, None, None)


def test_ddl_illegal_type_is_400():
    """类型不在白名单 → 8003/400「不合法的数据类型: 'FOO'」。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session, name="MySQL", ddl="mysql")
            model = _seed(session, fields=[_field("a", data_type="FOO")])
            model_id = model.id
        response = _ddl(client, headers, model_id)
        assert response.status_code == 400
        assert response.json()["msg"] == "不合法的数据类型: 'FOO'"
    finally:
        client.__exit__(None, None, None)


def test_ddl_illegal_length_is_400():
    """`length` 非纯数字 → 8003/400「不合法的长度: 'abc'」（防裸拼接注入）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session, name="MySQL", ddl="mysql")
            model = _seed(session, fields=[_field("a", data_type="VARCHAR", length="abc")])
            model_id = model.id
        response = _ddl(client, headers, model_id)
        assert response.status_code == 400
        assert response.json()["msg"] == "不合法的长度: 'abc'"
    finally:
        client.__exit__(None, None, None)


def test_ddl_oversized_length_is_400():
    """`length` 超 9 位（`_ARG_RE` 上限）→ 同样 8003/400。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session, name="MySQL", ddl="mysql")
            model = _seed(session, fields=[_field("a", data_type="VARCHAR", length="1234567890")])
            model_id = model.id
        response = _ddl(client, headers, model_id)
        assert response.status_code == 400
        assert response.json()["msg"] == "不合法的长度: '1234567890'"
    finally:
        client.__exit__(None, None, None)


def test_ddl_precision_without_length_is_400():
    """有精度无长度 → 8003/400「精度需与长度同时填写」。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session, name="MySQL", ddl="mysql")
            model = _seed(session, fields=[_field("a", data_type="DECIMAL", precision="2")])
            model_id = model.id
        response = _ddl(client, headers, model_id)
        assert response.status_code == 400
        assert response.json()["msg"] == "精度需与长度同时填写"
    finally:
        client.__exit__(None, None, None)


def test_ddl_unknown_engine_is_400():
    """`gen_ddl` 方言白名单外的 `engine` → 8003/400「不支持的引擎: 'oracle'」。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, fields=[_field("id")])
            model_id = model.id
        response = _ddl(client, headers, model_id, engine="oracle")
        assert response.status_code == 400
        assert response.json()["code"] == 8003
        assert response.json()["msg"] == "不支持的引擎: 'oracle'"
    finally:
        client.__exit__(None, None, None)


def test_ddl_illegal_table_code_is_400():
    """模型 `code` 亦经 `quote_ident` —— 非法表名 → 8003/400（标识符分支）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session, name="MySQL", ddl="mysql")
            model = _seed(session, code="bad code", fields=[_field("id")])
            model_id = model.id
        response = _ddl(client, headers, model_id)
        assert response.status_code == 400
        assert response.json()["msg"] == "不合法的标识符: 'bad code'"
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- 404 / 不落库


def test_ddl_unknown_model_is_404():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed(session)
        response = _ddl(client, headers, 9999)
        assert response.status_code == 404
        assert response.json()["code"] == 8001
    finally:
        client.__exit__(None, None, None)


def test_ddl_does_not_persist_any_state():
    """**不落库**：预览后 `status`/`version`/`last_ddl` 不变，且不新增版本快照行。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session, name="MySQL", ddl="mysql")
            model = _seed(session, status="published", version=3,
                          fields=[_field("id"), _field("gone")])
            model_id = model.id
        before = _ddl(client, headers, model_id).json()["data"]
        assert before["engine"] == "mysql"
        with app.state.session_factory() as session:
            record = session.get(DwModelRecord, model_id)
            assert record.status == "published"
            assert record.version == 3
            assert record.last_ddl is None
            assert record.built_at is None
            snapshots = (
                session.query(DwModelVersionRecord)
                .filter(DwModelVersionRecord.model_id == model_id)
                .count()
            )
            assert snapshots == 0
            fields = (
                session.query(DwModelFieldRecord)
                .filter(DwModelFieldRecord.model_id == model_id)
                .order_by(DwModelFieldRecord.seq)
                .all()
            )
            assert [f.name for f in fields] == ["id", "gone"]
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- 路由注册


def _route_pairs(app):
    """展平后的 (method, path) 有序表 —— 与请求匹配同序。

    本版 FastAPI 下 `app.routes` 为惰性 `_IncludedRouter` 包装，须取 openapi 展平结果。
    """
    pairs = []
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            pairs.append((method.upper(), path))
    return pairs


def test_ddl_route_is_registered_and_reachable():
    """A6-16 路由可达性：`/models/{model_id}/ddl` 命中 DDL 预览处理器。

    与 17.2-04/05/07 的静态段吞并风险**不同**：Starlette 按段数匹配，两段的
    `/models/{model_id}` 不可能吞并三段的 `/models/{model_id}/ddl`。故此处断言的是
    ① 该三段路由已注册；② 其前**无其他末段为路径参数的同段数路由**（字面尾段互异则永不匹配）；
    ③ 行为上 ddl 请求确由 DDL 语义处理（200 + `ddl` 文本），且两段的 A6-7 更新
    （`PUT /models/{model_id}`）语义不受影响（200 + data 为模型行，无 `ddl` 键）。
    """
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="ddl-order-secret")
    pairs = _route_pairs(app)
    path = "/api/v1/rebuild/models/{model_id}/ddl"
    target = [i for i, (method, p) in enumerate(pairs) if p == path and method == "GET"]
    assert target, "A6-16 GET /models/{model_id}/ddl 未注册"
    rivals = [
        (i, method, p) for i, (method, p) in enumerate(pairs)
        if p.startswith("/api/v1/rebuild/models/{model_id}/")
        and len(p.split("/")) == len(path.split("/"))
        and p.split("/")[-1].startswith("{")
    ]
    assert not [r for r in rivals if r[0] < target[0]], (
        f"存在更早注册的同段数路由可吞并 A6-16：{rivals}"
    )

    client = TestClient(app)
    client.__enter__()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
        headers = {"token": login.json()["data"]["token"]}
        with app.state.session_factory() as session:
            _seed_engine(session, name="MySQL", ddl="mysql")
            model = _seed(session, fields=[_field("id")])
            model_id = model.id
        ddl_resp = _ddl(client, headers, model_id)
        assert ddl_resp.status_code == 200
        assert "CREATE TABLE `dwd_trade_order`" in ddl_resp.json()["data"]["ddl"]
        # 两段的另一处理器（A6-7 更新）语义不受影响
        upd = client.put(
            f"/api/v1/rebuild/models/{model_id}", headers=headers, json={"remark": "r"}
        )
        assert upd.status_code == 200
        assert upd.json()["data"]["remark"] == "r"
        assert "ddl" not in upd.json()["data"]
    finally:
        client.__exit__(None, None, None)
