"""17.2-19 A6-19 `POST /api/v1/rebuild/models/reverse/import` 契约测试。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md` A6-19
（旧侧实锚 `datara-backend/api/model.py:629-684` `ReverseImportTable`/`ReverseImportBody`/`reverse_import`）。

入参 `{dsId, dbName?, tables: [{tb, layer="ODS", bizDomain="", name?}]}`；
出参 `{imported, skipped: [{tb, reason}]}`；错误码 4001/400、4002/400。

**连接经 `create_app(..., model_connector=fake)` 注入** —— 不触真实数据库
（域规范：本机只做代码/静态/类型/逻辑稽核，真库联调归 192.168.1.9）。
"""

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.model.models import DataSourceRecord, DwLayerRecord, DwModelFieldRecord, DwModelRecord

# information_schema.COLUMNS 的 10 列序（与旧侧 `api/model.py:663-669` 的 SELECT 一致）：
# COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_COMMENT,
# COLUMN_KEY, CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE
COL_KEYS = {"name", "dataType", "length", "precision", "nullable",
            "defaultValue", "comment", "isPk", "isPartition", "dictRef"}


def _col(name, dtype, *, column_type="", nullable="YES", default=None, comment="",
         key="", char_len=None, num_p=None, num_s=None):
    """构造一条 COLUMNS 行（10 元组，位置即旧侧解包序）。"""
    return (name, dtype, column_type, nullable, default, comment, key, char_len, num_p, num_s)


# ---------------------------------------------------------------- fake 内省连接


class FakeImportCursor:
    """按表名回放 `fetchall()` 的假游标（形状对齐 pymysql 游标；非上下文管理器）。"""

    def __init__(self, conn):
        self.conn = conn
        self._rows = []
        self.closed = False

    def execute(self, sql, params=None):
        self.conn.calls.append({"sql": sql, "params": params})
        # 第二条 %s 为表名 → 按表名取该表的列行
        self._rows = self.conn.columns.get(params[1], []) if params else []

    def fetchall(self):
        return self._rows

    def close(self):
        self.closed = True


class FakeImportConnection:
    """按表名分桶回放列行的假连接（每表一次 `cursor()`）。"""

    def __init__(self, *, columns=None):
        self.columns = columns or {}
        self.calls = []
        self.cursors = []
        self.closed = False

    def cursor(self):
        cur = FakeImportCursor(self)
        self.cursors.append(cur)
        return cur

    def close(self):
        self.closed = True


class FakeImportConnector:
    """`connector(ds, ...)` 工厂 —— 每次调用新建一个 `FakeImportConnection` 并留档。"""

    def __init__(self, *, columns=None):
        self.columns = columns or {}
        self.connections = []
        self.calls = []

    def __call__(self, ds, **kw):
        self.calls.append({"ds_id": ds.id, "db": kw.get("db")})
        conn = FakeImportConnection(columns=self.columns)
        self.connections.append(conn)
        return conn


# ---------------------------------------------------------------- 夹具


def _client(*, model_connector=None):
    app = create_app(
        "sqlite+pysqlite:///:memory:",
        token_secret="model-revimport-secret",
        model_connector=model_connector,
    )
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    return client, app, {"token": login.json()["data"]["token"]}


def _seed_ds(session, *, ds_type="mysql", db_name="trade"):
    ds = DataSourceRecord(
        name="源库", type=ds_type, host="127.0.0.1", port=3306,
        db_name=db_name, user="root", pwd="secret",
    )
    session.add(ds)
    session.commit()
    return ds


def _seed_model(session, *, code, name="", engine="MySQL", layer="ODS"):
    m = DwModelRecord(
        code=code, name=name or code, layer=layer, type="明细表", engine=engine,
        status="draft", version=1, security_level="内部", owner="admin",
    )
    session.add(m)
    session.commit()
    return m


def _import(client, headers, ds_id, tables, db_name=None):
    body = {"dsId": ds_id, "tables": tables}
    if db_name is not None:
        body["dbName"] = db_name
    return client.post("/api/v1/rebuild/models/reverse/import", json=body, headers=headers)


def _model_row(session, code):
    m = session.query(DwModelRecord).filter(DwModelRecord.code == code).first()
    assert m is not None, f"模型未落库: {code}"
    fields = (session.query(DwModelFieldRecord)
              .filter(DwModelFieldRecord.model_id == m.id)
              .order_by(DwModelFieldRecord.seq).all())
    return m, fields


# ---------------------------------------------------------------- 鉴权 / 权限


def test_reverse_import_requires_login():
    client, app, _ = _client()
    try:
        response = client.post(
            "/api/v1/rebuild/models/reverse/import",
            json={"dsId": 1, "tables": [{"tb": "ods_x"}]},
        )
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_write_permission_required_for_viewer():
    """写端点 `model:write` ↔ `EDIT_DEFINITION`：viewer → 403/1004。"""
    client, app, _ = _client()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="viewer", password="pw-123456", role=Role.VIEWER)
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "viewer", "password": "pw-123456"})
        headers = {"token": login.json()["data"]["token"]}
        response = _import(client, headers, 1, [{"tb": "ods_x"}])
        assert response.status_code == 403
        assert response.json()["code"] == 1004
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- 数据源闸


def test_reverse_import_datasource_missing_is_4001():
    """`dsId` 指向不存在的行 → 4001/400（msg 用内置文案「数据源不存在」）。"""
    client, app, headers = _client(model_connector=FakeImportConnector())
    try:
        response = _import(client, headers, 9999, [{"tb": "ods_x"}])
        assert response.status_code == 400
        assert response.json()["code"] == 4001
        assert response.json()["msg"] == "数据源不存在"
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_non_connection_datasource_is_4002():
    """`type` 非 mysql/greatdb（file/doris）→ 4002/400（旧侧此处用 PARAM_INVALID，照抄）。"""
    for bad_type in ("file", "doris", "postgresql"):
        fake = FakeImportConnector()
        client, app, headers = _client(model_connector=fake)
        try:
            with app.state.session_factory() as session:
                ds = _seed_ds(session, ds_type=bad_type)
                ds_id = ds.id
            response = _import(client, headers, ds_id, [{"tb": "ods_x"}])
            assert response.status_code == 400, bad_type
            assert response.json()["code"] == 4002, bad_type
            assert "连接型" in response.json()["msg"], bad_type
            assert fake.connections == [], bad_type  # 闸在连接之前
        finally:
            client.__exit__(None, None, None)


# ---------------------------------------------------------------- 成功路径


def test_reverse_import_creates_draft_model_and_fields():
    """成功路径：草稿模型 + 字段落库，`_reverse_create` 默认值逐项对照旧侧。"""
    columns = {"ods_trade_order": [
        _col("id", "bigint", column_type="bigint", nullable="NO", key="PRI"),
        _col("amt", "decimal", column_type="decimal(12,2)", num_p=12, num_s=2),
        _col("note", "varchar", column_type="varchar(64)", char_len=64, comment="备注"),
    ]}
    fake = FakeImportConnector(columns=columns)
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session)
            ds_id = ds.id
        data = _import(
            client, headers, ds_id,
            [{"tb": "ods_trade_order", "layer": "ODS", "bizDomain": "交易域", "name": "交易订单"}],
        ).json()["data"]
        assert data == {"imported": 1, "skipped": []}

        with app.state.session_factory() as session:
            m, fields = _model_row(session, "ods_trade_order")
            assert m.name == "交易订单"
            assert m.layer == "ODS"
            assert m.type == "明细表"          # 旧侧硬编码，非入参
            assert m.biz_domain == "交易域"
            assert m.engine == "MySQL"         # _REV_ENGINE_MAP["mysql"]
            assert m.status == "draft"
            assert m.version == 1
            assert m.security_level == "内部"
            assert m.owner == "admin"
            assert [f.seq for f in fields] == [1, 2, 3]
            assert {f.name for f in fields} == {"id", "amt", "note"}
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_field_mapping_per_type_family():
    """字段映射：类型族决定 length/precision 取哪一列（`_col_to_field` 照抄）。"""
    columns = {"ods_map": [
        _col("c_varchar", "varchar", char_len=64),
        _col("c_char", "char", char_len=8),
        _col("c_decimal", "decimal", num_p=12, num_s=2),
        _col("c_numeric", "numeric", num_p=10, num_s=0),
        _col("c_int", "int", num_p=11, num_s=0),          # 非字符串/非小数 → 皆空
        _col("c_lower", "varchar", char_len=32),          # 小写 data_type → 大写
    ]}
    fake = FakeImportConnector(columns=columns)
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session)
            ds_id = ds.id
        _import(client, headers, ds_id, [{"tb": "ods_map"}])
        with app.state.session_factory() as session:
            _, fields = _model_row(session, "ods_map")
        got = {f.name: (f.data_type, f.length, f.precision) for f in fields}
        assert got["c_varchar"] == ("VARCHAR", "64", "")
        assert got["c_char"] == ("CHAR", "8", "")
        assert got["c_decimal"] == ("DECIMAL", "12", "2")
        # num_s=0 为 falsy → 旧侧 `str(num_s or "")` 得 ""（scale 0 不显式落库）。
        # 该 quirk 忠实照抄，并由 test_model_col_to_field_legacy_equivalence 差分锁定。
        assert got["c_numeric"] == ("NUMERIC", "10", "")
        assert got["c_int"] == ("INT", "", "")            # 类型族不匹配 → 两列皆空
        assert got["c_lower"] == ("VARCHAR", "32", "")    # .upper() 归一
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_field_nullable_default_pk_flags():
    """`nullable`/`defaultValue`/`isPk`/`isPartition`/`dictRef` 逐项（含 `None` 兜底）。"""
    columns = {"ods_flags": [
        _col("a", "int", nullable="YES", default="0", comment="c", key=""),
        _col("b", "int", nullable="NO", default=None, comment=None, key="PRI"),
    ]}
    fake = FakeImportConnector(columns=columns)
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session)
            ds_id = ds.id
        _import(client, headers, ds_id, [{"tb": "ods_flags"}])
        with app.state.session_factory() as session:
            _, fields = _model_row(session, "ods_flags")
        by_name = {f.name: f for f in fields}
        assert by_name["a"].nullable is True
        assert by_name["a"].default_value == "0"
        assert by_name["a"].comment == "c"
        assert by_name["a"].is_pk is False
        assert by_name["b"].nullable is False
        assert by_name["b"].default_value == ""     # None → ""
        assert by_name["b"].comment == ""           # None → ""
        assert by_name["b"].is_pk is True           # COLUMN_KEY == "PRI"
        for f in fields:
            assert f.is_partition is False          # 旧侧恒 False
            assert f.dict_ref == ""                 # 旧侧恒 ""
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_name_falls_back_to_code():
    """`name` 缺省/空 → 模型名回落为编码（旧侧 `name or code`）。"""
    columns = {"ods_noname": [_col("x", "int")]}
    fake = FakeImportConnector(columns=columns)
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session)
            ds_id = ds.id
        data = _import(client, headers, ds_id, [{"tb": "ods_noname"}]).json()["data"]
        assert data["imported"] == 1
        with app.state.session_factory() as session:
            m, _ = _model_row(session, "ods_noname")
            assert m.name == "ods_noname"
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_tb_is_stripped():
    """`tb.strip()` 后才作编码（旧侧 `code = t.tb.strip()`）。"""
    columns = {"ods_pad": [_col("x", "int")]}
    fake = FakeImportConnector(columns=columns)
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session)
            ds_id = ds.id
        data = _import(client, headers, ds_id, [{"tb": "  ods_pad  "}]).json()["data"]
        assert data["imported"] == 1
        with app.state.session_factory() as session:
            assert session.query(DwModelRecord).filter_by(code="ods_pad").first() is not None
            assert session.query(DwModelRecord).filter_by(code="  ods_pad  ").first() is None
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_engine_map_for_greatdb():
    """`_REV_ENGINE_MAP["greatdb"] = "GreatDB"`（连接型数据源两种类型各测一次）。"""
    columns = {"ods_gdb": [_col("x", "int")]}
    fake = FakeImportConnector(columns=columns)
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session, ds_type="greatdb")
            ds_id = ds.id
        data = _import(client, headers, ds_id, [{"tb": "ods_gdb"}]).json()["data"]
        assert data["imported"] == 1
        with app.state.session_factory() as session:
            m, _ = _model_row(session, "ods_gdb")
            assert m.engine == "GreatDB"
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_sql_targets_override_db():
    """`dbName` 覆盖数据源库 → 内省 SQL 参数用覆盖值（`body.dbName or ds.db_name or ""`）。"""
    columns = {"ods_any": [_col("x", "int")]}
    fake = FakeImportConnector(columns=columns)
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session, db_name="trade")
            ds_id = ds.id
        _import(client, headers, ds_id, [{"tb": "ods_any"}], db_name="other_db")
        assert fake.connections[0].calls[0]["params"] == ("other_db", "ods_any")
        assert fake.connections[0].calls[0]["sql"].startswith("SELECT COLUMN_NAME")
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- skipped 分支


def test_reverse_import_skips_existing_model():
    """同名模型已存在 → skipped「同名模型已存在」，不建第二条。"""
    columns = {"ods_dup": [_col("x", "int")]}
    fake = FakeImportConnector(columns=columns)
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session)
            ds_id = ds.id
            _seed_model(session, code="ods_dup")
        data = _import(client, headers, ds_id, [{"tb": "ods_dup"}]).json()["data"]
        assert data == {"imported": 0, "skipped": [{"tb": "ods_dup", "reason": "同名模型已存在"}]}
        with app.state.session_factory() as session:
            assert session.query(DwModelRecord).filter_by(code="ods_dup").count() == 1
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_skips_invalid_code():
    """编码不合正则 → skipped，reason 取异常文案缺省「校验未通过」（8003 无 msg）。"""
    fake = FakeImportConnector(columns={})
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session)
            ds_id = ds.id
        data = _import(client, headers, ds_id, [{"tb": "1Bad_Code"}]).json()["data"]
        assert data == {"imported": 0, "skipped": [{"tb": "1Bad_Code", "reason": "校验未通过"}]}
        # 连接在循环前开一次（旧侧 :649），但校验不过的表**不建游标**（不内省）
        assert len(fake.connections) == 1
        assert fake.connections[0].cursors == []
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_skips_naming_rule_violation():
    """分层命名规范不过 → skipped，reason = 异常文案（8004 带 msg）。

    种子 ODS 层 rule=`ods_源库名_源表名，保留原始字段` → 前缀 `ods`；
    表名 `t_user` 不以 `ods_` 开头 → 8004。
    """
    fake = FakeImportConnector(columns={})
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session)
            ds_id = ds.id
            rule = session.get(DwLayerRecord, "ODS").rule
        data = _import(client, headers, ds_id, [{"tb": "t_user", "layer": "ODS"}]).json()["data"]
        assert data["imported"] == 0
        assert data["skipped"] == [{"tb": "t_user", "reason": f"编码需符合分层命名规范：{rule}"}]
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_missing_layer_skips_naming_rule():
    """分层记录不存在 → 命名规范**静默跳过**（旧侧 `if l and l.rule`），照常导入。"""
    columns = {"t_nolayer": [_col("x", "int")]}
    fake = FakeImportConnector(columns=columns)
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session)
            ds_id = ds.id
            assert session.get(DwLayerRecord, "XYZ") is None  # 该分层无记录
        data = _import(client, headers, ds_id, [{"tb": "t_nolayer", "layer": "XYZ"}]).json()["data"]
        assert data == {"imported": 1, "skipped": []}
        with app.state.session_factory() as session:
            m, _ = _model_row(session, "t_nolayer")
            assert m.layer == "XYZ"
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_skips_table_without_columns():
    """内省为空 → skipped「未找到列（表不存在？）」，不建 0 字段草稿。"""
    fake = FakeImportConnector(columns={})  # 任何表都取不到列
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session)
            ds_id = ds.id
        data = _import(client, headers, ds_id, [{"tb": "ods_missing"}]).json()["data"]
        assert data == {"imported": 0, "skipped": [{"tb": "ods_missing", "reason": "未找到列（表不存在？）"}]}
        with app.state.session_factory() as session:
            assert session.query(DwModelRecord).filter_by(code="ods_missing").first() is None
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_mixed_batch_counts_imported_and_skipped():
    """混合批：成功与 skipped 各自计数，逐表独立（旧侧无整批事务）。"""
    columns = {"ods_ok": [_col("x", "int")]}
    fake = FakeImportConnector(columns=columns)
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session)
            ds_id = ds.id
            _seed_model(session, code="ods_dup")
        data = _import(client, headers, ds_id, [
            {"tb": "ods_ok"},
            {"tb": "ods_dup"},
            {"tb": "1bad"},
            {"tb": "ods_missing"},
        ]).json()["data"]
        assert data["imported"] == 1
        reasons = {s["tb"]: s["reason"] for s in data["skipped"]}
        assert reasons == {
            "ods_dup": "同名模型已存在",
            "1bad": "校验未通过",
            "ods_missing": "未找到列（表不存在？）",
        }
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- 释放 / 路由


def test_reverse_import_closes_cursor_and_connection():
    """逐表游标与连接都释放（旧侧非上下文管理器写法，`finally` 双层）。"""
    columns = {"ods_a": [_col("x", "int")], "ods_b": [_col("y", "int")]}
    fake = FakeImportConnector(columns=columns)
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session)
            ds_id = ds.id
        _import(client, headers, ds_id, [{"tb": "ods_a"}, {"tb": "ods_b"}])
        conn = fake.connections[0]
        assert len(conn.cursors) == 2           # 每表一个游标
        assert all(c.closed for c in conn.cursors)
        assert conn.closed is True
    finally:
        client.__exit__(None, None, None)


def _route_pairs(app):
    """展平后的 (method, path) 有序表 —— 与请求匹配同序。"""
    pairs = []
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            pairs.append((method.upper(), path))
    return pairs


def test_reverse_import_route_is_registered_and_reachable():
    """A6-19 路由可达性：`POST /models/reverse/import` 命中逆向导入处理器。

    两段皆**字面**（`reverse`/`import`）：与同段数的 `/models/reverse/scan`
    （尾段 `scan`）互异 → 互不前缀吞并；亦不会吞并两段 `/models/{model_id}`。
    行为验证：无数据源行 → 4001（路由确由 import 处理器处理）。
    """
    app = create_app(
        "sqlite+pysqlite:///:memory:",
        token_secret="revimport-order-secret",
        model_connector=FakeImportConnector(),
    )
    pairs = _route_pairs(app)
    path = "/api/v1/rebuild/models/reverse/import"
    target = [i for i, (method, p) in enumerate(pairs) if p == path and method == "POST"]
    assert target, "A6-19 POST /models/reverse/import 未注册"
    rivals = [
        (i, method, p) for i, (method, p) in enumerate(pairs)
        if p.startswith("/api/v1/rebuild/models/")
        and len(p.split("/")) == len(path.split("/"))
        and p.split("/")[-1].startswith("{")
    ]
    assert not [r for r in rivals if r[0] < target[0]], (
        f"存在更早注册的同段数动态尾段路由可抢匹配 A6-19：{rivals}"
    )

    client = TestClient(app)
    client.__enter__()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
        headers = {"token": login.json()["data"]["token"]}
        body = client.post(
            path, json={"dsId": 1, "tables": [{"tb": "ods_x"}]}, headers=headers
        ).json()
        assert body["code"] == 4001  # 无数据源行 → 闸生效（路由确由 import 处理器处理）
        # 两段 POST /models（A6-3 新建）语义不受影响
        created = client.post(
            "/api/v1/rebuild/models",
            json={"name": "x", "code": "dwd_x", "layer": "DWD", "engine": "MySQL"},
            headers=headers,
        )
        assert created.status_code == 200
        assert "skipped" not in created.json()["data"]
    finally:
        client.__exit__(None, None, None)
