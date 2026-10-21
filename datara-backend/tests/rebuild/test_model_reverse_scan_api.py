"""17.2-18 A6-18 `POST /api/v1/rebuild/models/reverse/scan` 契约测试。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md` A6-18
（旧侧实锚 `datara-backend/api/model.py:572-594` `reverse_scan`）。

入参 `{dsId, dbName?}`；出参 `{db, tables: [{tb, comment, rows, cols}]}`；
错误码 4001/400（数据源不存在）、4002/400（逆向仅支持连接型数据源）。
内省走 `information_schema`，`rows` 为估算值。

**连接经 `create_app(..., model_connector=fake)` 注入** —— 不触真实数据库
（域规范：本机只做代码/静态/类型/逻辑稽核，真库联调归 192.168.1.9）。
"""

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.model.models import DataSourceRecord

SCAN_KEYS = {"db", "tables"}
TABLE_KEYS = {"tb", "comment", "rows", "cols"}


# ---------------------------------------------------------------- fake 内省连接


class FakeReverseCursor:
    """按调用序回放 `fetchall()` 的假游标（形状对齐 pymysql 游标；非上下文管理器）。"""

    def __init__(self, conn):
        self.conn = conn
        self._rows = []
        self.closed = False

    def execute(self, sql, params=None):
        self.conn.calls.append({"sql": sql, "params": params})
        self._rows = self.conn.results[len(self.conn.calls) - 1]

    def fetchall(self):
        return self._rows

    def close(self):
        self.closed = True


class FakeReverseConnection:
    """回放两条 information_schema 查询的假连接（TABLES → COLUMNS 计数）。"""

    def __init__(self, table_rows=(), col_rows=()):
        self.results = [list(table_rows), list(col_rows)]
        self.calls = []
        self.closed = False
        self.cursor_obj = FakeReverseCursor(self)

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


class FakeReverseConnector:
    """`connector(ds, ...)` 工厂 —— 每次调用新建一个 `FakeReverseConnection` 并留档。"""

    def __init__(self, *, table_rows=(), col_rows=()):
        self.table_rows = table_rows
        self.col_rows = col_rows
        self.connections = []
        self.calls = []

    def __call__(self, ds, **kw):
        self.calls.append({"ds_id": ds.id, "db": kw.get("db")})
        conn = FakeReverseConnection(self.table_rows, self.col_rows)
        self.connections.append(conn)
        return conn


# ---------------------------------------------------------------- 夹具


def _client(*, model_connector=None):
    app = create_app(
        "sqlite+pysqlite:///:memory:",
        token_secret="model-revscan-secret",
        model_connector=model_connector,
    )
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    return client, app, {"token": login.json()["data"]["token"]}


def _seed_ds(session, *, ds_id=None, ds_type="mysql", db_name="trade"):
    ds = DataSourceRecord(
        name="源库", type=ds_type, host="127.0.0.1", port=3306,
        db_name=db_name, user="root", pwd="secret",
    )
    if ds_id is not None:
        ds.id = ds_id
    session.add(ds)
    session.commit()
    return ds


def _scan(client, headers, ds_id, db_name=None):
    body = {"dsId": ds_id}
    if db_name is not None:
        body["dbName"] = db_name
    return client.post("/api/v1/rebuild/models/reverse/scan", json=body, headers=headers)


# ---------------------------------------------------------------- 鉴权 / 权限


def test_reverse_scan_requires_login():
    client, app, _ = _client()
    try:
        response = client.post("/api/v1/rebuild/models/reverse/scan", json={"dsId": 1})
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_reverse_scan_write_permission_required_for_viewer():
    """写端点 `model:write` ↔ `EDIT_DEFINITION`：viewer → 403/1004。"""
    client, app, _ = _client()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="viewer", password="pw-123456", role=Role.VIEWER)
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "viewer", "password": "pw-123456"})
        headers = {"token": login.json()["data"]["token"]}
        response = _scan(client, headers, 1)
        assert response.status_code == 403
        assert response.json()["code"] == 1004
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- 数据源闸


def test_reverse_scan_datasource_missing_is_4001():
    """`dsId` 指向不存在的行 → 4001/400（msg 用内置文案「数据源不存在」）。"""
    client, app, headers = _client(model_connector=FakeReverseConnector())
    try:
        response = _scan(client, headers, 9999)
        assert response.status_code == 400
        assert response.json()["code"] == 4001
        assert response.json()["msg"] == "数据源不存在"
    finally:
        client.__exit__(None, None, None)


def test_reverse_scan_non_connection_datasource_is_4002():
    """`type` 非 mysql/greatdb（file/doris）→ 4002/400（旧侧此处用 PARAM_INVALID，照抄）。"""
    for bad_type in ("file", "doris", "postgresql"):
        fake = FakeReverseConnector()
        client, app, headers = _client(model_connector=fake)
        try:
            with app.state.session_factory() as session:
                ds = _seed_ds(session, ds_type=bad_type)
                ds_id = ds.id
            response = _scan(client, headers, ds_id)
            assert response.status_code == 400, bad_type
            assert response.json()["code"] == 4002, bad_type
            assert "连接型" in response.json()["msg"], bad_type
            assert fake.connections == [], bad_type  # 闸在连接之前
        finally:
            client.__exit__(None, None, None)


# ---------------------------------------------------------------- 成功路径


def test_reverse_scan_shape_and_values():
    """出参形状 + 行/列数计算 + `None` 兜底（comment/rows/cols）。"""
    fake = FakeReverseConnector(
        table_rows=[("t_order", "订单表", 120), ("t_user", None, None)],
        col_rows=[("t_order", 5), ("t_user", 3)],
    )
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session, db_name="trade")
            ds_id = ds.id
        data = _scan(client, headers, ds_id).json()["data"]
        assert set(data) == SCAN_KEYS
        assert data["db"] == "trade"
        assert len(data["tables"]) == 2
        assert all(set(t) == TABLE_KEYS for t in data["tables"])
        # 表序 = SQL ORDER BY TABLE_NAME（Python 侧不重排）
        assert [t["tb"] for t in data["tables"]] == ["t_order", "t_user"]
        assert data["tables"][0] == {"tb": "t_order", "comment": "订单表", "rows": 120, "cols": 5}
        # None → "" / 0
        assert data["tables"][1] == {"tb": "t_user", "comment": "", "rows": 0, "cols": 3}
    finally:
        client.__exit__(None, None, None)


def test_reverse_scan_db_name_override():
    """`dbName` 覆盖数据源 `db_name`（旧侧 `body.dbName or ds.db_name or ""`）。"""
    fake = FakeReverseConnector(table_rows=[], col_rows=[])
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session, db_name="trade")
            ds_id = ds.id
        data = _scan(client, headers, ds_id, db_name="other_db").json()["data"]
        assert data["db"] == "other_db"
    finally:
        client.__exit__(None, None, None)


def test_reverse_scan_db_name_empty_string_is_falsy_fallback():
    """`dbName=""` 为 falsy → 回退数据源 `db_name`（照抄，未改 `is not None`）。"""
    fake = FakeReverseConnector(table_rows=[], col_rows=[])
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session, db_name="trade")
            ds_id = ds.id
        data = _scan(client, headers, ds_id, db_name="").json()["data"]
        assert data["db"] == "trade"
    finally:
        client.__exit__(None, None, None)


def test_reverse_scan_empty_target_db_when_both_blank():
    """数据源 `db_name` 与入参 `dbName` 皆空 → `target_db = ""`（空串库名合法，不报错）。"""
    fake = FakeReverseConnector(table_rows=[], col_rows=[])
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session, db_name="")
            ds_id = ds.id
        data = _scan(client, headers, ds_id).json()["data"]
        assert data["db"] == ""
        assert data["tables"] == []
    finally:
        client.__exit__(None, None, None)


def test_reverse_scan_two_information_schema_queries_and_params():
    """两条 SQL 的形态与 `%s` 参数（`TABLE_SCHEMA = target_db`）。"""
    fake = FakeReverseConnector(table_rows=[], col_rows=[])
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session, db_name="trade")
            ds_id = ds.id
        _scan(client, headers, ds_id)
        calls = fake.connections[0].calls
        assert len(calls) == 2
        first, second = calls
        assert "information_schema.TABLES" in first["sql"]
        assert "TABLE_TYPE = 'BASE TABLE'" in first["sql"]
        assert "ORDER BY TABLE_NAME" in first["sql"]
        assert first["params"] == ("trade",)
        assert "information_schema.COLUMNS" in second["sql"]
        assert "GROUP BY TABLE_NAME" in second["sql"]
        assert second["params"] == ("trade",)
    finally:
        client.__exit__(None, None, None)


def test_reverse_scan_closes_cursor_and_connection():
    """双层 `finally`：游标与连接都释放（旧侧非上下文管理器写法）。"""
    fake = FakeReverseConnector(table_rows=[], col_rows=[])
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session)
            ds_id = ds.id
        _scan(client, headers, ds_id)
        conn = fake.connections[0]
        assert conn.cursor_obj.closed is True
        assert conn.closed is True
    finally:
        client.__exit__(None, None, None)


def test_reverse_scan_connects_without_db_override():
    """连接用 `open_connection(ds)` —— **不传 `db`**（旧侧同；target_db 只进 SQL）。"""
    fake = FakeReverseConnector(table_rows=[], col_rows=[])
    client, app, headers = _client(model_connector=fake)
    try:
        with app.state.session_factory() as session:
            ds = _seed_ds(session, db_name="trade")
            ds_id = ds.id
        _scan(client, headers, ds_id)
        assert len(fake.calls) == 1
        assert fake.calls[0]["ds_id"] == ds_id
        assert fake.calls[0]["db"] is None
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


def test_reverse_scan_route_is_registered_and_reachable():
    """A6-18 路由可达性：`POST /models/reverse/scan` 命中逆向内省处理器。

    两段皆**字面**（`reverse`/`scan`）：不会吞并两段 `/models/{model_id}`，也不被
    同段数的 `/models/{model_id}/ddl`（尾段 `ddl`）或 `/physicalize` 吞并。
    此处断言 ① 已注册；② 行为上 scan 语义生效（返回 `tables`）；
    ③ 同段数动态尾段路由不抢匹配（`/models/reverse/scan` 不返回模型行）。
    """
    app = create_app(
        "sqlite+pysqlite:///:memory:",
        token_secret="revscan-order-secret",
        model_connector=FakeReverseConnector(),
    )
    pairs = _route_pairs(app)
    path = "/api/v1/rebuild/models/reverse/scan"
    target = [i for i, (method, p) in enumerate(pairs) if p == path and method == "POST"]
    assert target, "A6-18 POST /models/reverse/scan 未注册"
    # 同段数动态尾段路由（/models/{model_id}/<dynamic>）不得先于本路由抢匹配
    rivals = [
        (i, method, p) for i, (method, p) in enumerate(pairs)
        if p.startswith("/api/v1/rebuild/models/")
        and len(p.split("/")) == len(path.split("/"))
        and p.split("/")[-1].startswith("{")
    ]
    assert not [r for r in rivals if r[0] < target[0]], (
        f"存在更早注册的同段数动态尾段路由可抢匹配 A6-18：{rivals}"
    )

    client = TestClient(app)
    client.__enter__()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
        headers = {"token": login.json()["data"]["token"]}
        # 三段逆向语义生效
        body = client.post(
            "/api/v1/rebuild/models/reverse/scan", json={"dsId": 1}, headers=headers
        ).json()
        assert body["code"] == 4001  # 无数据源行 → 闸生效（路由确由 scan 处理器处理）
        # 两段 POST /models（A6-3 新建）语义不受影响
        created = client.post(
            "/api/v1/rebuild/models",
            json={"name": "x", "code": "dwd_x", "layer": "DWD", "engine": "MySQL"},
            headers=headers,
        )
        assert created.status_code == 200
        assert "tables" not in created.json()["data"]
    finally:
        client.__exit__(None, None, None)
