"""17.2-17 A6-17 `POST /api/v1/rebuild/models/{model_id}/physicalize` 契约测试。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md` A6-17
（旧侧实锚 `datara-backend/api/model.py:492-546` `PhysicalizeBody` + `physicalize`）。

入参 `{engine, dsId?, dbName?, mode="script", ddl?}`；
- script 出参 `{script, notes}`，**不落库**；
- exec  出参 `{status:"built", executed:N}`；
- 错误码 8001/404、4002/400、8003/400、4001/400、8009/400（data 带 `executed`/`error`）。

exec 分支经 `create_app(..., model_connector=fake)` 注入 fake 连接 —— **不触真实网络**
（域规范：本机只做代码/静态/类型/逻辑稽核，真库联调归 192.168.1.9）。
"""

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.model.models import (
    DataSourceRecord,
    DwModelFieldRecord,
    DwModelRecord,
    EngineTypeRecord,
)

SCRIPT_KEYS = {"script", "notes"}
EXEC_KEYS = {"status", "executed"}


# ---------------------------------------------------------------- fake 连接


class FakeCursor:
    """记录 execute/commit 的最小游标（形状对齐 pymysql 游标，仅本测试用）。"""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql):
        self.conn.statements.append(sql)
        if self.conn.fail_on == len(self.conn.statements):
            raise RuntimeError("boom-on-statement-%d" % len(self.conn.statements))


class FakeConnection:
    """记录 executed 序列 + 可选失败点的假连接（替代 `rebuild.model.dsconn.open_connection`）。"""

    def __init__(self, *, fail_on=None):
        self.statements = []
        self.fail_on = fail_on
        self.committed = False
        self.closed = False
        self.cursor_obj = FakeCursor(self)

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


class FakeConnector:
    """`connector(ds, *, db=...)` 工厂 —— 每次调用新建一个 `FakeConnection` 并留档。"""

    def __init__(self, *, fail_on=None):
        self.connections = []
        self.calls = []
        self.fail_on = fail_on

    def __call__(self, ds, *, db=None, **_kw):
        self.calls.append({"ds_id": ds.id, "type": ds.type, "db": db})
        conn = FakeConnection(fail_on=self.fail_on)
        self.connections.append(conn)
        return conn


# ---------------------------------------------------------------- 夹具


def _client(*, model_connector=None):
    app = create_app(
        "sqlite+pysqlite:///:memory:",
        token_secret="model-phys-secret",
        model_connector=model_connector,
    )
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    return client, app, {"token": login.json()["data"]["token"]}


def _seed_engine(session, *, name="MySQL", ddl="mysql"):
    """引擎字典种子（幂等；应用启动已写入 MySQL/Doris/GreatDB 三行）。"""
    row = session.get(EngineTypeRecord, name)
    if row is None:
        session.add(EngineTypeRecord(name=name, ddl=ddl, xc=False))
    else:
        row.ddl = ddl
    session.commit()


def _seed_ds(session, *, ds_id=None, ds_type="mysql", db_name="trade"):
    """数据源行（`t_data_source`；A6-17 物理化目标）。"""
    ds = DataSourceRecord(
        name="源库", type=ds_type, host="127.0.0.1", port=3306,
        db_name=db_name, user="root", pwd="secret",
    )
    if ds_id is not None:
        ds.id = ds_id
    session.add(ds)
    session.commit()
    return ds


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


def _phys(client, headers, model_id, *, engine="mysql", mode="script", ds_id=None,
          db_name=None, ddl=None):
    body = {"engine": engine, "mode": mode}
    if ds_id is not None:
        body["dsId"] = ds_id
    if db_name is not None:
        body["dbName"] = db_name
    if ddl is not None:
        body["ddl"] = ddl
    return client.post(
        f"/api/v1/rebuild/models/{model_id}/physicalize", json=body, headers=headers
    )


# ---------------------------------------------------------------- 鉴权 / 权限


def test_physicalize_requires_login():
    client, app, _ = _client()
    try:
        response = client.post("/api/v1/rebuild/models/1/physicalize", json={"engine": "mysql"})
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_physicalize_write_permission_required_for_viewer():
    """写端点 `model:write` ↔ `EDIT_DEFINITION`：viewer → 403/1004。"""
    client, app, _ = _client()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="viewer", password="pw-123456", role=Role.VIEWER)
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "viewer", "password": "pw-123456"})
        headers = {"token": login.json()["data"]["token"]}
        response = _phys(client, headers, 1)
        assert response.status_code == 403
        assert response.json()["code"] == 1004
    finally:
        client.__exit__(None, None, None)


def test_physicalize_unknown_model_is_404():
    """模型不存在 → 8001/404（**先于** mode/引擎闸，与旧侧同序）。"""
    client, app, headers = _client()
    try:
        response = _phys(client, headers, 999, mode="bogus")
        assert response.status_code == 404
        assert response.json()["code"] == 8001
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- script 分支（不落库）


def test_physicalize_script_returns_ddl_text_without_persisting():
    """script 模式出 `{script, notes}`；**不改 status/last_ddl/built_at**。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session)
            model = _seed(session, status="draft", version=3, fields=[
                _field("id", isPk=True, nullable=False),
                _field("amt", data_type="DECIMAL", length="18", precision="2", defaultValue="0"),
            ])
            model_id = model.id
        data = _phys(client, headers, model_id, mode="script").json()["data"]
        assert set(data) == SCRIPT_KEYS
        assert "CREATE TABLE `dwd_trade_order`" in data["script"]
        assert data["notes"] == []
        with app.state.session_factory() as session:
            row = session.get(DwModelRecord, model_id)
            assert row.status == "draft"
            assert row.last_ddl is None
            assert row.built_at is None
            assert row.built_by is None
    finally:
        client.__exit__(None, None, None)


def test_physicalize_script_uses_supplied_ddl_verbatim():
    """`ddl` 入参非空 → 直接用它（`body.ddl or gen_ddl(...)`），不重新生成。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, fields=[_field("id")])
            model_id = model.id
        custom = "CREATE TABLE `custom_x` (`id` BIGINT)"
        data = _phys(client, headers, model_id, mode="script", ddl=custom).json()["data"]
        assert data["script"] == custom
    finally:
        client.__exit__(None, None, None)


def test_physicalize_script_empty_ddl_falls_back_to_generated():
    """`ddl` 为空串 → falsy → 回退 `gen_ddl`（旧侧 `body.ddl or ...`）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session)
            model = _seed(session, fields=[_field("id")])
            model_id = model.id
        data = _phys(client, headers, model_id, mode="script", ddl="").json()["data"]
        assert data["script"].startswith("CREATE TABLE `dwd_trade_order`")
    finally:
        client.__exit__(None, None, None)


def test_physicalize_script_doris_engine_allowed():
    """引擎白名单含 `doris`（可生成脚本），script 模式不触连接。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session, name="Apache Doris", ddl="doris")
            model = _seed(session, engine="Apache Doris", fields=[_field("id", isPk=True)])
            model_id = model.id
        data = _phys(client, headers, model_id, engine="doris", mode="script").json()["data"]
        assert "DISTRIBUTED BY HASH(`id`)" in data["script"]
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- 参数闸


def test_physicalize_mode_gate_is_4002():
    """`mode` 非 exec/script → 4002/400「mode 仅支持 exec/script」。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, fields=[_field("id")])
            model_id = model.id
        response = _phys(client, headers, model_id, mode="EXEC")
        assert response.status_code == 400
        assert response.json()["code"] == 4002
        assert "mode" in response.json()["msg"]
    finally:
        client.__exit__(None, None, None)


def test_physicalize_engine_gate_is_4002():
    """引擎方言白名单（mysql/greatdb/doris）→ 4002/400「不支持的引擎方言: …」。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            model = _seed(session, fields=[_field("id")])
            model_id = model.id
        response = _phys(client, headers, model_id, engine="oracle")
        assert response.status_code == 400
        assert response.json()["code"] == 4002
        assert "oracle" in response.json()["msg"]
    finally:
        client.__exit__(None, None, None)


def test_physicalize_ddlgen_value_error_is_8003():
    """`gen_ddl` 的 `ValueError`（非法字段名）→ 8003/400，msg 为异常原文。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session)
            model = _seed(session, fields=[_field("bad name")])
            model_id = model.id
        response = _phys(client, headers, model_id, mode="script")
        assert response.status_code == 400
        assert response.json()["code"] == 8003
        assert "不合法的标识符" in response.json()["msg"]
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- exec 分支


def test_physicalize_exec_success_transitions_to_built():
    """exec 成功：逐条执行 + commit + 状态置 built + last_ddl/built_at/built_by 留痕。"""
    fake = FakeConnector()
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            _seed_engine(session)
            model = _seed(session, status="draft", version=3, fields=[
                _field("id", isPk=True, nullable=False),
            ])
            model_id = model.id
            ds = _seed_ds(session)
            ds_id = ds.id
        response = _phys(client, headers, model_id, engine="mysql", mode="exec", ds_id=ds_id)
        assert response.status_code == 200
        data = response.json()["data"]
        assert set(data) == EXEC_KEYS
        assert data["status"] == "built"
        assert data["executed"] == 1
        # 连接面：factory 被调用一次，db 覆盖为 None（未传 dbName）
        assert len(fake.calls) == 1
        assert fake.calls[0]["ds_id"] == ds_id
        assert fake.calls[0]["db"] is None
        conn = fake.connections[0]
        assert len(conn.statements) == 1
        assert conn.statements[0].startswith("CREATE TABLE `dwd_trade_order`")
        assert conn.committed is True
        assert conn.closed is True
        # 落库
        with app.state.session_factory() as session:
            row = session.get(DwModelRecord, model_id)
            assert row.status == "built"
            assert row.last_ddl is not None and "dwd_trade_order" in row.last_ddl
            assert row.built_at is not None
            assert row.built_by == "admin"
    finally:
        client.__exit__(None, None, None)


def test_physicalize_exec_db_name_overrides_datasource_db():
    """`dbName` 覆盖数据源 `db_name`（旧侧 `db=body.dbName or None`）。"""
    fake = FakeConnector()
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            _seed_engine(session)
            model = _seed(session, fields=[_field("id")])
            model_id = model.id
            ds_id = _seed_ds(session, db_name="trade").id
        _phys(client, headers, model_id, mode="exec", ds_id=ds_id, db_name="other_db")
        assert fake.calls[0]["db"] == "other_db"
    finally:
        client.__exit__(None, None, None)


def test_physicalize_exec_without_datasource_is_4001():
    """exec 未选数据源（`dsId` 缺省）→ 4001/400。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session)
            model = _seed(session, fields=[_field("id")])
            model_id = model.id
        response = _phys(client, headers, model_id, mode="exec")
        assert response.status_code == 400
        assert response.json()["code"] == 4001
    finally:
        client.__exit__(None, None, None)


def test_physicalize_exec_datasource_missing_row_is_4001():
    """`dsId` 指向不存在的行 → 4001/400（旧侧 `ds is None`）。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session)
            model = _seed(session, fields=[_field("id")])
            model_id = model.id
        response = _phys(client, headers, model_id, mode="exec", ds_id=4242)
        assert response.status_code == 400
        assert response.json()["code"] == 4001
    finally:
        client.__exit__(None, None, None)


def test_physicalize_exec_non_connection_datasource_is_4001():
    """数据源 `type` 非 mysql/greatdb（如 file/doris）→ 4001/400。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_engine(session)
            model = _seed(session, fields=[_field("id")])
            model_id = model.id
            ds_id = _seed_ds(session, ds_type="file").id
        response = _phys(client, headers, model_id, mode="exec", ds_id=ds_id)
        assert response.status_code == 400
        assert response.json()["code"] == 4001
    finally:
        client.__exit__(None, None, None)


def test_physicalize_exec_malformed_ddl_is_8009_parse_error():
    """畸形 DDL → 8009/400「DDL 解析失败: …」（不 500）。"""
    client, app, headers = _client(model_connector=FakeConnector())
    try:
        with app.state.session_factory() as session:
            _seed_engine(session)
            model = _seed(session, fields=[_field("id")])
            model_id = model.id
            ds_id = _seed_ds(session).id
        response = _phys(
            client, headers, model_id, mode="exec", ds_id=ds_id,
            ddl="CREATE TABLE `broken` ( ??? ))))",
        )
        assert response.status_code == 400
        assert response.json()["code"] == 8009
        assert "DDL 解析失败" in response.json()["msg"]
    finally:
        client.__exit__(None, None, None)


def test_physicalize_exec_non_create_statement_is_8009():
    """白名单仅 `CREATE`：DROP/INSERT/GRANT 一律 8009/400（排除法会漏 `Command` 兜底节点）。"""
    for ddl in (
        "DROP TABLE `dwd_trade_order`",
        "INSERT INTO `t` VALUES (1)",
        "GRANT ALL ON *.* TO 'x'@'%'",
    ):
        fake = FakeConnector()
        client, app, headers = _client(model_connector=fake)
        try:
            with app.state.session_factory() as session:
                _seed_engine(session)
                model = _seed(session, fields=[_field("id")])
                model_id = model.id
                ds_id = _seed_ds(session).id
            response = _phys(client, headers, model_id, mode="exec", ds_id=ds_id, ddl=ddl)
            assert response.status_code == 400, ddl
            assert response.json()["code"] == 8009, ddl
            assert "仅允许 CREATE" in response.json()["msg"], ddl
            assert fake.connections == [], ddl  # 闸在连接之前，不得触连接
        finally:
            client.__exit__(None, None, None)


def test_physicalize_exec_comment_only_ddl_is_8009():
    """注释内分号不拆语句 → 过滤 `None` 后语句列表为空 → 8009/400。"""
    client, app, headers = _client(model_connector=FakeConnector())
    try:
        with app.state.session_factory() as session:
            _seed_engine(session)
            model = _seed(session, fields=[_field("id")])
            model_id = model.id
            ds_id = _seed_ds(session).id
        response = _phys(
            client, headers, model_id, mode="exec", ds_id=ds_id,
            ddl="-- only a comment; not a statement",
        )
        assert response.status_code == 400
        assert response.json()["code"] == 8009
    finally:
        client.__exit__(None, None, None)


def test_physicalize_exec_failure_keeps_state_and_reports_executed():
    """执行失败：状态**不变**（仍 draft）、8009/400、data 带 `executed`+`error`。"""
    fake = FakeConnector(fail_on=2)
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            _seed_engine(session)
            model = _seed(session, status="published", fields=[_field("id")])
            model_id = model.id
            ds_id = _seed_ds(session).id
        two = (
            "CREATE TABLE `a` (`id` BIGINT);\n"
            "CREATE TABLE `b` (`id` BIGINT)"
        )
        response = _phys(client, headers, model_id, mode="exec", ds_id=ds_id, ddl=two)
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == 8009
        assert body["data"]["executed"] == 1
        assert "boom-on-statement-2" in body["data"]["error"]
        assert "已执行 1 条" in body["msg"]
        conn = fake.connections[0]
        assert conn.committed is False  # 失败路径不 commit
        assert conn.closed is True
        with app.state.session_factory() as session:
            row = session.get(DwModelRecord, model_id)
            assert row.status == "published"
            assert row.last_ddl is None
            assert row.built_at is None
    finally:
        client.__exit__(None, None, None)


def test_physicalize_exec_no_status_gate_for_any_state():
    """**不判状态闸**：旧侧对 draft/published/built/produced 一律放行（照抄，不加闸）。"""
    fake = FakeConnector()
    client, app, headers = _client(model_connector=fake)
    try:
        for index, status in enumerate(("draft", "published", "built", "produced"), 1):
            with app.state.session_factory() as session:
                _seed_engine(session)
                model = _seed(session, code=f"dwd_state_{index}", status=status,
                              fields=[_field("id")])
                model_id = model.id
                ds_id = _seed_ds(session).id
            response = _phys(client, headers, model_id, mode="exec", ds_id=ds_id)
            assert response.status_code == 200, (status, response.text)
            assert response.json()["data"]["status"] == "built"
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- 路由注册


def _route_pairs(app):
    """展平后的 (method, path) 有序表 —— 与请求匹配同序。"""
    pairs = []
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            pairs.append((method.upper(), path))
    return pairs


def test_physicalize_route_is_registered_and_reachable():
    """A6-17 路由可达性：`/models/{model_id}/physicalize` 命中物理化处理器。

    Starlette 按段数匹配，两段的 `/models/{model_id}` 不可能吞并三段路由；
    此处断言 ① 已注册；② 其前无同段数动态尾段路由；③ 行为上物理化语义生效
    （script 返回 `script` 文本），且两段 A6-7 更新语义不受影响。
    """
    app = create_app(
        "sqlite+pysqlite:///:memory:",
        token_secret="phys-order-secret",
        model_connector=FakeConnector(),
    )
    pairs = _route_pairs(app)
    path = "/api/v1/rebuild/models/{model_id}/physicalize"
    target = [i for i, (method, p) in enumerate(pairs) if p == path and method == "POST"]
    assert target, "A6-17 POST /models/{model_id}/physicalize 未注册"
    rivals = [
        (i, method, p) for i, (method, p) in enumerate(pairs)
        if p.startswith("/api/v1/rebuild/models/{model_id}/")
        and len(p.split("/")) == len(path.split("/"))
        and p.split("/")[-1].startswith("{")
    ]
    assert not [r for r in rivals if r[0] < target[0]], (
        f"存在更早注册的同段数路由可吞并 A6-17：{rivals}"
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
            _seed_engine(session)
            model = _seed(session, fields=[_field("id")])
            model_id = model.id
        # 三段物理化语义：返回 script 文本
        assert "script" in _phys(client, headers, model_id).json()["data"]
        # 两段 A6-7 更新语义不受影响：返回模型行（无 script 键）
        updated = client.put(
            f"/api/v1/rebuild/models/{model_id}", json={"remark": "ok"}, headers=headers
        )
        assert updated.status_code == 200
        assert "script" not in updated.json()["data"]
        assert updated.json()["data"]["remark"] == "ok"
    finally:
        client.__exit__(None, None, None)
