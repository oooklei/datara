"""17.2-20 A6-20 `POST /api/v1/rebuild/models/reverse/import-ddl` 契约测试。

契约真源：`docs/increments/evidence/INC17/2026-10-20-17.1-API契约冻结清单草案-Claude.md` A6-20
（旧侧实锚 `datara-backend/api/model.py:687-735` `reverse_import_ddl`）。

入参 multipart `file`（`.sql`，≤5MB）；出参 `{imported, skipped: [{tb, reason}]}`；
错误码 4002/400（超 5MB 上限）、8010/400（DDL 解析失败，msg 附行号）。

**不上传真实文件到任何存储** —— 字节只在内存中流经 `decode_ddl` → `parse_create_tables`
（纯函数），契约测试以 `TestClient` 的 multipart 上传覆盖 HTTP 边界。
真库联调归 192.168.1.9（域规范）。
"""

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.model.models import DwLayerRecord, DwModelFieldRecord, DwModelRecord

DDL_LIMIT = 5 * 1024 * 1024


# ---------------------------------------------------------------- 夹具


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="model-ddlimport-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        session.commit()
    login = client.post("/api/v1/rebuild/login", json={"username": "admin", "password": "admin-pass"})
    return client, app, {"token": login.json()["data"]["token"]}


def _seed_model(session, *, code):
    session.add(DwModelRecord(
        code=code, name=code, layer="ODS", type="明细表", engine="MySQL",
        status="draft", version=1, security_level="内部", owner="admin",
    ))
    session.commit()


def _upload(client, headers, content, *, filename="dump.sql"):
    return client.post(
        "/api/v1/rebuild/models/reverse/import-ddl",
        files={"file": (filename, content, "application/octet-stream")},
        headers=headers,
    )


def _model(session, code):
    m = session.query(DwModelRecord).filter(DwModelRecord.code == code).first()
    assert m is not None, f"模型未落库: {code}"
    fields = (session.query(DwModelFieldRecord)
              .filter(DwModelFieldRecord.model_id == m.id)
              .order_by(DwModelFieldRecord.seq).all())
    return m, fields


# ---------------------------------------------------------------- 鉴权 / 权限


def test_reverse_import_ddl_requires_login():
    client, app, _ = _client()
    try:
        response = client.post(
            "/api/v1/rebuild/models/reverse/import-ddl",
            files={"file": ("dump.sql", b"CREATE TABLE ods_t (id BIGINT);")},
        )
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_ddl_write_permission_required_for_viewer():
    """写端点 `model:write` ↔ `EDIT_DEFINITION`：viewer → 403/1004。"""
    client, app, _ = _client()
    try:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="viewer", password="pw-123456", role=Role.VIEWER)
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": "viewer", "password": "pw-123456"})
        headers = {"token": login.json()["data"]["token"]}
        response = _upload(client, headers, b"CREATE TABLE ods_t (id BIGINT);")
        assert response.status_code == 403
        assert response.json()["code"] == 1004
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_ddl_missing_file_is_422():
    """`file` 为必填（`File(...)`）→ 缺失由框架校验拦为 422。"""
    client, app, headers = _client()
    try:
        response = client.post("/api/v1/rebuild/models/reverse/import-ddl", headers=headers)
        assert response.status_code == 422
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- 成功路径


def test_reverse_import_ddl_creates_ods_draft():
    """成功路径：CREATE TABLE → ODS 草稿（engine 恒 `MySQL`、layer 恒 `ODS`）。"""
    client, app, headers = _client()
    try:
        sql = (
            "CREATE TABLE ods_trade_order ("
            "id BIGINT NOT NULL COMMENT '主键', "
            "amt DECIMAL(12,2), "
            "PRIMARY KEY (id)) COMMENT='交易订单';"
        )
        data = _upload(client, headers, sql.encode("utf-8")).json()["data"]
        assert data == {"imported": 1, "skipped": []}
        with app.state.session_factory() as session:
            m, fields = _model(session, "ods_trade_order")
            assert m.layer == "ODS"                 # 旧侧硬编码
            assert m.engine == "MySQL"              # 旧侧硬编码
            assert m.type == "明细表"
            assert m.status == "draft"
            assert m.version == 1
            assert m.name == "ods_trade_order"      # 旧侧 name 传空串 → `name or code`
            assert m.remark == "交易订单"            # 表注释
            assert [f.name for f in fields] == ["id", "amt"]
            assert fields[0].is_pk is True          # 表级 PRIMARY KEY
            assert fields[0].comment == "主键"
            assert fields[1].data_type == "DECIMAL"
            assert (fields[1].length, fields[1].precision) == ("12", "2")
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_ddl_gbk_fallback():
    """非 UTF-8 字节（GBK 中文）→ `decode_ddl` 退 `gbk(errors='replace')` 仍解析成功。"""
    client, app, headers = _client()
    try:
        sql = "CREATE TABLE ods_gbk (id BIGINT COMMENT '中文注释');"
        data = _upload(client, headers, sql.encode("gbk")).json()["data"]
        assert data == {"imported": 1, "skipped": []}
        with app.state.session_factory() as session:
            _, fields = _model(session, "ods_gbk")
            assert fields[0].comment == "中文注释"
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_ddl_remark_falls_back_to_marker():
    """无表注释 → `remark` 为「DDL 导入」（旧侧 `t["comment"] or "DDL 导入"`）。"""
    client, app, headers = _client()
    try:
        data = _upload(client, headers, b"CREATE TABLE ods_plain (id BIGINT);").json()["data"]
        assert data["imported"] == 1
        with app.state.session_factory() as session:
            m, _ = _model(session, "ods_plain")
            assert m.remark == "DDL 导入"
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_ddl_multi_tables():
    """一段 DDL 多张表 → 各自建草稿，`imported` 计数。"""
    client, app, headers = _client()
    try:
        sql = ("CREATE TABLE ods_a (id BIGINT);"
               "CREATE TABLE ods_b (id BIGINT);"
               "CREATE TABLE ods_c (id BIGINT);")
        data = _upload(client, headers, sql.encode("utf-8")).json()["data"]
        assert data == {"imported": 3, "skipped": []}
        with app.state.session_factory() as session:
            for code in ("ods_a", "ods_b", "ods_c"):
                assert session.query(DwModelRecord).filter_by(code=code).first() is not None
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- skipped / 忽略


def test_reverse_import_ddl_skips_existing_model():
    """同名模型已存在 → skipped「同名模型已存在」。"""
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            _seed_model(session, code="ods_dup")
        data = _upload(client, headers, b"CREATE TABLE ods_dup (id BIGINT);").json()["data"]
        assert data == {"imported": 0, "skipped": [{"tb": "ods_dup", "reason": "同名模型已存在"}]}
        with app.state.session_factory() as session:
            assert session.query(DwModelRecord).filter_by(code="ods_dup").count() == 1
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_ddl_skips_naming_rule_violation():
    """分层命名规范不过 → skipped，reason = 异常文案（8004 带 msg）。

    种子 ODS 层 rule=`ods_源库名_源表名，保留原始字段` → 前缀 `ods`；
    表名 `t_user` 不以 `ods_` 开头 → 8004。
    """
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            rule = session.get(DwLayerRecord, "ODS").rule
        data = _upload(client, headers, b"CREATE TABLE t_user (id BIGINT);").json()["data"]
        assert data["imported"] == 0
        assert data["skipped"] == [{"tb": "t_user", "reason": f"编码需符合分层命名规范：{rule}"}]
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_ddl_non_create_only_is_empty_success():
    """仅非 CREATE TABLE 语句 → `imported=0, skipped=[]`（**不是**错误，旧侧静默忽略）。"""
    client, app, headers = _client()
    try:
        sql = "INSERT INTO ods_t VALUES (1); SELECT * FROM ods_t; CREATE VIEW v AS SELECT 1;"
        data = _upload(client, headers, sql.encode("utf-8")).json()["data"]
        assert data == {"imported": 0, "skipped": []}
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------- 错误路径


def test_reverse_import_ddl_syntax_error_is_8010_with_line():
    """语法错误 → 8010/400，msg 为「DDL 解析失败：…（第 N 行）」。"""
    client, app, headers = _client()
    try:
        response = _upload(client, headers, b"CREATE TABLE ods_bad (id BIGINT")
        assert response.status_code == 400
        body = response.json()
        assert body["code"] == 8010
        assert "DDL 解析失败" in body["msg"]
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_ddl_oversize_is_4002():
    """超 5MB → 4002/400「DDL 文件超过 5MB 上限」（`file.size` 快速拒绝分支）。"""
    client, app, headers = _client()
    try:
        content = b"-- " + b"x" * DDL_LIMIT
        response = _upload(client, headers, content)
        assert response.status_code == 400
        assert response.json()["code"] == 4002
        assert response.json()["msg"] == "DDL 文件超过 5MB 上限"
    finally:
        client.__exit__(None, None, None)


def test_reverse_import_ddl_exactly_at_limit_is_not_rejected_by_size_gate():
    """恰为 5MB（未超限）→ **不**被上限拦下（`file.size > limit` 为 False）。

    内容本身不含 CREATE TABLE → 静默忽略，得 200 `imported=0`（证明通过了 5MB 闸）。
    边界另一侧由 `test_reverse_import_ddl_oversize_is_4002`（5MB+3）锁定。
    """
    client, app, headers = _client()
    try:
        content = b"x" * DDL_LIMIT
        assert len(content) == DDL_LIMIT
        body = _upload(client, headers, content).json()
        assert body["code"] == 0
        assert body["data"] == {"imported": 0, "skipped": []}
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


def test_reverse_import_ddl_route_is_registered_and_reachable():
    """A6-20 路由可达性：`POST /models/reverse/import-ddl` 命中 DDL 导入处理器。

    两段皆**字面**（`reverse`/`import-ddl`）：与同段数的 `/models/reverse/scan`
    （尾段 `scan`）、`/models/reverse/import`（尾段 `import`）互异 → 互不前缀吞并。
    """
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="ddlimport-order-secret")
    pairs = _route_pairs(app)
    path = "/api/v1/rebuild/models/reverse/import-ddl"
    target = [i for i, (method, p) in enumerate(pairs) if p == path and method == "POST"]
    assert target, "A6-20 POST /models/reverse/import-ddl 未注册"
    rivals = [
        (i, method, p) for i, (method, p) in enumerate(pairs)
        if p.startswith("/api/v1/rebuild/models/")
        and len(p.split("/")) == len(path.split("/"))
        and p.split("/")[-1].startswith("{")
    ]
    assert not [r for r in rivals if r[0] < target[0]], (
        f"存在更早注册的同段数动态尾段路由可抢匹配 A6-20：{rivals}"
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
            path,
            files={"file": ("dump.sql", b"CREATE TABLE ods_t (id BIGINT);")},
            headers=headers,
        ).json()
        assert body["code"] == 0  # 三段 DDL 导入语义生效（非 404/非 405）
        assert body["data"] == {"imported": 1, "skipped": []}
    finally:
        client.__exit__(None, None, None)
