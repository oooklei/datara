"""I18 数仓建模 API 单测（P0 批）。

DB：sqlite 内存库（conftest compiles 补丁），零外部依赖。
TestClient 不触发 lifespan → init_db/种子不执行，字典数据用 _seed_dicts 手工补。
"""

import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from api.auth import get_current_user  # noqa: E402
from common.models import BizDomain, DataSource, DwLayer, DwModel, DwModelField, DwModelRelation, EngineType  # noqa: E402
from common.db import seed_dict_tables  # noqa: E402


def set_role(client, role: str) -> None:
    """切换注入用户角色（权限矩阵用例）。"""
    client.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, user_name="tester", user_role=role
    )


def _seed_dicts(db_session) -> None:
    """字典种子（与 init_db 同一入口，幂等）。"""
    seed_dict_tables(db_session)


def test_seed_dict_tables_idempotent(db_session):
    _seed_dicts(db_session)
    _seed_dicts(db_session)  # 二次调用不重复插入
    assert db_session.query(DwLayer).count() == 5
    assert db_session.query(BizDomain).count() == 4
    assert db_session.query(EngineType).count() == 3
    dwd = db_session.get(DwLayer, "DWD")
    assert dwd.rule.startswith("dwd_")
    gdb = db_session.get(EngineType, "GreatDB")
    assert gdb.ddl == "greatdb" and gdb.xc is True


# ---------------- Task 5: 模型 CRUD ----------------


def _mk_model(client, code="dwd_order_pay", layer="DWD", **kw) -> int:
    body = {"name": "订单支付明细", "code": code, "layer": layer,
            "engine": "MySQL", "type": "事实表", "bizDomain": "交易域"}
    body.update(kw)
    r = client.post("/api/v1/models", json=body)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def test_create_and_detail_and_list(client, db_session):
    _seed_dicts(db_session)
    mid = _mk_model(client)
    d = client.get(f"/api/v1/models/{mid}").json()["data"]
    assert d["code"] == "dwd_order_pay" and d["status"] == "draft" and d["version"] == 1
    assert d["owner"] == "tester" and d["fields"] == []
    ls = client.get("/api/v1/models").json()["data"]
    assert ls["total"] == 1
    assert {"code": "DWD", "count": 1} in ls["layers"]
    assert {"name": "交易域", "count": 1} in ls["domains"]


def test_create_dup_code_409(client, db_session):
    _seed_dicts(db_session)
    _mk_model(client)
    r = client.post("/api/v1/models", json={
        "name": "另一个", "code": "dwd_order_pay", "layer": "DWD", "engine": "MySQL", "type": "明细表"})
    assert r.status_code == 409 and r.json()["code"] == 8002


def test_create_bad_code_400(client, db_session):
    _seed_dicts(db_session)
    r = client.post("/api/v1/models", json={
        "name": "x", "code": "DWD_X", "layer": "DWD", "engine": "MySQL", "type": "明细表"})
    assert r.status_code == 400 and r.json()["code"] == 8003


def test_create_naming_rule_400(client, db_session):
    _seed_dicts(db_session)
    r = client.post("/api/v1/models", json={
        "name": "x", "code": "foo_bar", "layer": "DWD", "engine": "MySQL", "type": "明细表"})
    assert r.status_code == 400 and r.json()["code"] == 8004


def test_create_viewer_403(client, db_session):
    _seed_dicts(db_session)
    set_role(client, "viewer")
    r = client.post("/api/v1/models", json={
        "name": "x", "code": "dwd_x", "layer": "DWD", "engine": "MySQL", "type": "明细表"})
    assert r.status_code == 403
    set_role(client, "dev")


def test_update_published_locked(client, db_session):
    _seed_dicts(db_session)
    mid = _mk_model(client)
    m = db_session.get(DwModel, mid)
    m.status = "published"
    db_session.commit()
    r = client.put(f"/api/v1/models/{mid}", json={"name": "改名"})
    assert r.status_code == 409 and r.json()["code"] == 8005
    r2 = client.put(f"/api/v1/models/{mid}", json={"remark": "只改备注", "securityLevel": "机密"})
    assert r2.status_code == 200 and r2.json()["data"]["securityLevel"] == "机密"


def test_delete_refused_when_built(client, db_session):
    _seed_dicts(db_session)
    mid = _mk_model(client)
    m = db_session.get(DwModel, mid)
    m.status = "built"
    db_session.commit()
    r = client.delete(f"/api/v1/models/{mid}")
    assert r.status_code == 409


def test_delete_with_downstream_refs_409(client, db_session):
    _seed_dicts(db_session)
    a = _mk_model(client, code="dwd_a")
    b = _mk_model(client, code="dws_b", layer="DWS")
    db_session.add(DwModelRelation(src_model_id=a, tgt_model_id=b))
    db_session.commit()
    r = client.delete(f"/api/v1/models/{a}")
    assert r.status_code == 409 and r.json()["code"] == 8008
    assert r.json()["data"]["refs"][0]["code"] == "dws_b"


def test_delete_ok_cascades_fields(client, db_session):
    _seed_dicts(db_session)
    mid = _mk_model(client)
    # 先建一条字段再删（字段级联删除）
    from common.models import DwModelField

    db_session.add(DwModelField(model_id=mid, seq=1, name="id"))
    db_session.commit()
    r = client.delete(f"/api/v1/models/{mid}")
    assert r.status_code == 200
    assert client.get(f"/api/v1/models/{mid}").status_code == 404


def test_create_bad_layer_engine_400(client, db_session):
    _seed_dicts(db_session)
    r = client.post("/api/v1/models", json={
        "name": "x", "code": "dwd_x", "layer": "不存在的层", "engine": "MySQL", "type": "明细表"})
    assert r.status_code == 400
    r2 = client.post("/api/v1/models", json={
        "name": "x", "code": "dwd_x", "layer": "DWD", "engine": "Oracle", "type": "明细表"})
    assert r2.status_code == 400


def test_delete_target_keeps_edge_cleanup(client, db_session):
    """上游指向我的关系随删除一并消失（tgt 方向）。"""
    _seed_dicts(db_session)
    a = _mk_model(client, code="dwd_a")
    b = _mk_model(client, code="dws_b", layer="DWS")
    db_session.add(DwModelRelation(src_model_id=a, tgt_model_id=b))
    db_session.commit()
    r = client.delete(f"/api/v1/models/{b}")
    assert r.status_code == 200
    assert db_session.query(DwModelRelation).count() == 0


# ---------------- Task 6: 字段/发布 ----------------

_FIELDS = [
    {"name": "user_id", "dataType": "BIGINT", "length": "", "precision": "", "nullable": False,
     "defaultValue": "", "comment": "用户ID", "isPk": True, "isPartition": False, "dictRef": ""},
    {"name": "user_name", "dataType": "VARCHAR", "length": "100", "precision": "", "nullable": True,
     "defaultValue": "", "comment": "姓名", "isPk": False, "isPartition": False, "dictRef": ""},
]


def _put_fields(client, mid, rev=1, fields=None):
    return client.put(f"/api/v1/models/{mid}/fields",
                      json={"rev": rev, "fields": _FIELDS if fields is None else fields})


def test_fields_full_replace(client, db_session):
    _seed_dicts(db_session)
    mid = _mk_model(client)
    r = _put_fields(client, mid, rev=1)
    assert r.status_code == 200 and r.json()["data"]["rev"] == 2
    d = client.get(f"/api/v1/models/{mid}").json()["data"]
    assert [f["name"] for f in d["fields"]] == ["user_id", "user_name"]


def test_fields_rev_conflict_422(client, db_session):
    _seed_dicts(db_session)
    mid = _mk_model(client)
    r = _put_fields(client, mid, rev=99)
    assert r.status_code == 422 and r.json()["code"] == 8006
    assert r.json()["data"]["currentRev"] == 1


def test_fields_locked_on_published(client, db_session):
    _seed_dicts(db_session)
    mid = _mk_model(client)
    client.post(f"/api/v1/models/{mid}/publish")
    r = _put_fields(client, mid, rev=1)
    assert r.status_code == 409 and r.json()["code"] == 8007


def test_publish_state_matrix(client, db_session):
    _seed_dicts(db_session)
    mid = _mk_model(client)
    r = client.post(f"/api/v1/models/{mid}/publish")
    assert r.status_code == 200 and r.json()["data"]["status"] == "published"
    r2 = client.post(f"/api/v1/models/{mid}/publish")
    assert r2.status_code == 409 and r2.json()["code"] == 8005


def test_fields_rev_increments_on_save(client, db_session):
    _seed_dicts(db_session)
    mid = _mk_model(client)
    assert _put_fields(client, mid, rev=1).status_code == 200  # version → 2
    r = _put_fields(client, mid, rev=1)  # 旧 rev 再次保存 → 冲突
    assert r.status_code == 422 and r.json()["code"] == 8006
    assert r.json()["data"]["currentRev"] == 2
    r2 = _put_fields(client, mid, rev=2)
    assert r2.status_code == 200 and r2.json()["data"]["rev"] == 3


def test_fields_clear_all(client, db_session):
    _seed_dicts(db_session)
    mid = _mk_model(client)
    assert _put_fields(client, mid, rev=1).status_code == 200
    r = _put_fields(client, mid, rev=2, fields=[])
    assert r.status_code == 200
    d = client.get(f"/api/v1/models/{mid}").json()["data"]
    assert d["fields"] == []


# ---------------- Task 7: DDL/物理化 ----------------

_DS = {"name": "测试库", "type": "mysql", "host": "127.0.0.1", "port": 3306,
       "db_name": "dwd", "user": "root", "pwd": ""}


def _mk_ds(db_session) -> int:
    ds = DataSource(**_DS)
    db_session.add(ds)
    db_session.commit()
    return ds.id


class _FakeCursor:
    def __init__(self, fail_on: int = 0):
        self.n = 0
        self.fail_on = fail_on
        self.executed = []

    def execute(self, sql, args=None):
        self.n += 1
        # 规格修正：fail_on 语义=「第 fail_on 条执行失败」（原文 n > fail_on 在单语句 DDL 下永不触发，
        # 无法满足 data.executed == 0 断言）
        if self.fail_on and self.n >= self.fail_on:
            raise RuntimeError("mock 执行失败")
        self.executed.append(sql)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, fail_on: int = 0):
        self.cursor_obj = _FakeCursor(fail_on)

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        pass

    def close(self):
        pass


def test_ddl_preview_dialects(client, db_session):
    _seed_dicts(db_session)
    mid = _mk_model(client)
    # 规格修正：断言依赖分区字段（PARTITION BY RANGE / mysql 提示），默认 _FIELDS 无 isPartition
    _put_fields(client, mid, fields=[dict(_FIELDS[0], isPartition=True), _FIELDS[1]])
    r = client.get(f"/api/v1/models/{mid}/ddl?engine=doris")
    d = r.json()["data"]
    assert d["engine"] == "doris" and "PARTITION BY RANGE" in d["ddl"] and d["notes"] == []
    r2 = client.get(f"/api/v1/models/{mid}/ddl?engine=mysql")
    assert r2.json()["data"]["notes"] == ["该引擎不支持分区声明"]


def test_physicalize_script_mode(client, db_session):
    _seed_dicts(db_session)
    mid = _mk_model(client)
    _put_fields(client, mid)
    r = client.post(f"/api/v1/models/{mid}/physicalize",
                    json={"engine": "mysql", "mode": "script"})
    assert r.status_code == 200
    assert r.json()["data"]["script"].startswith("CREATE TABLE `dwd_order_pay`")
    assert db_session.get(DwModel, mid).status == "draft"  # 状态不变


def test_physicalize_exec_success(client, db_session, monkeypatch):
    _seed_dicts(db_session)
    ds_id = _mk_ds(db_session)
    mid = _mk_model(client)
    _put_fields(client, mid)
    fake = _FakeConn()
    monkeypatch.setattr("api.model.open_connection", lambda ds, **kw: fake)
    r = client.post(f"/api/v1/models/{mid}/physicalize",
                    json={"engine": "mysql", "mode": "exec", "dsId": ds_id, "dbName": "dwd"})
    assert r.status_code == 200 and r.json()["data"]["status"] == "built"
    m = db_session.get(DwModel, mid)
    assert m.status == "built" and m.built_by == "tester" and m.last_ddl
    assert fake.cursor_obj.executed and fake.cursor_obj.executed[0].startswith("CREATE TABLE")


def test_physicalize_exec_fail_keeps_status(client, db_session, monkeypatch):
    _seed_dicts(db_session)
    ds_id = _mk_ds(db_session)
    mid = _mk_model(client)
    _put_fields(client, mid)
    monkeypatch.setattr("api.model.open_connection", lambda ds, **kw: _FakeConn(fail_on=1))
    r = client.post(f"/api/v1/models/{mid}/physicalize",
                    json={"engine": "mysql", "mode": "exec", "dsId": ds_id})
    assert r.status_code == 400 and r.json()["code"] == 8009
    assert r.json()["data"]["executed"] == 0
    assert db_session.get(DwModel, mid).status == "draft"


def test_physicalize_requires_connection_ds(client, db_session):
    _seed_dicts(db_session)
    mid = _mk_model(client)
    r = client.post(f"/api/v1/models/{mid}/physicalize",
                    json={"engine": "mysql", "mode": "exec"})
    assert r.status_code == 400


def test_physicalize_exec_rejects_non_create(client, db_session, monkeypatch):
    _seed_dicts(db_session)
    ds_id = _mk_ds(db_session)
    mid = _mk_model(client)
    _put_fields(client, mid)
    monkeypatch.setattr("api.model.open_connection", lambda ds, **kw: _FakeConn())
    r = client.post(f"/api/v1/models/{mid}/physicalize",
                    json={"engine": "mysql", "mode": "exec", "dsId": ds_id,
                          "ddl": "DROP TABLE sensitive; --"})
    assert r.status_code == 400 and r.json()["code"] == 8009
    assert db_session.get(DwModel, mid).status == "draft"


def test_physicalize_exec_bad_ddl_400(client, db_session, monkeypatch):
    _seed_dicts(db_session)
    ds_id = _mk_ds(db_session)
    mid = _mk_model(client)
    _put_fields(client, mid)
    r = client.post(f"/api/v1/models/{mid}/physicalize",
                    json={"engine": "mysql", "mode": "exec", "dsId": ds_id,
                          "ddl": "CREATE TABLE x ("})
    assert r.status_code == 400


def test_physicalize_bad_mode_and_engine(client, db_session):
    _seed_dicts(db_session)
    mid = _mk_model(client)
    _put_fields(client, mid)
    r = client.post(f"/api/v1/models/{mid}/physicalize",
                    json={"engine": "mysql", "mode": "Exec"})
    assert r.status_code == 400
    r2 = client.post(f"/api/v1/models/{mid}/physicalize",
                     json={"engine": "pg", "mode": "script"})
    assert r2.status_code == 400


# ---------------- Task 8: 逆向导入 ----------------

_SCAN_ROWS = [
    ("ods_gdb_biz_user_info", "用户信息原始表", 1200),
    ("ods_gdb_biz_order", "订单表", 3400),
]
_COL_ROWS = [
    ("id", "bigint", "bigint(20)", "NO", None, "主键", "PRI", None, 20, 0),
    ("user_name", "varchar", "varchar(100)", "YES", "anon", "姓名", "", 100, None, None),
]
_COL_COUNT_ROWS = [
    ("ods_gdb_biz_user_info", 2),
    ("ods_gdb_biz_order", 2),
]


class _MetaCursor:
    """information_schema 内省 mock：按 SQL 形态分流返回。

    - 含 GROUP BY → 列计数查询（scan 单条聚合），返回 [(tb, n), ...]
    - 含 COLUMNS → import 逐表内省（empty_tables 中的表返回空列表）
    - 其余 → scan 表清单（3 列行）
    """

    def __init__(self, empty_tables: tuple = ()):
        self.empty_tables = frozenset(empty_tables)
        self.last_sql = ""
        self.last_args: tuple = ()
        self.executed: list[str] = []

    def execute(self, sql, args=None):
        self.last_sql = sql
        self.last_args = args or ()
        self.executed.append(sql)

    def fetchall(self):
        sql = self.last_sql.upper()
        if "GROUP BY" in sql:
            return _COL_COUNT_ROWS
        if "COLUMNS" in sql:
            if len(self.last_args) >= 2 and self.last_args[1] in self.empty_tables:
                return []
            return _COL_ROWS
        return _SCAN_ROWS

    def close(self):
        pass


class _MetaConn:
    def __init__(self, empty_tables: tuple = ()):
        self.cursor_obj = _MetaCursor(empty_tables)

    def cursor(self):
        return self.cursor_obj

    def close(self):
        pass


def test_reverse_scan(client, db_session, monkeypatch):
    _seed_dicts(db_session)
    ds_id = _mk_ds(db_session)
    fake = _MetaConn()
    monkeypatch.setattr("api.model.open_connection", lambda ds, **kw: fake)
    r = client.post("/api/v1/models/reverse/scan", json={"dsId": ds_id, "dbName": "ods"})
    d = r.json()["data"]
    assert d["db"] == "ods" and len(d["tables"]) == 2
    assert d["tables"][0]["tb"] == "ods_gdb_biz_user_info" and d["tables"][0]["cols"] == 2
    # N+1 消除：整个 scan 仅 2 条 SQL（表清单 + 单条 GROUP BY 列计数）
    assert len(fake.cursor_obj.executed) == 2


def test_reverse_import_skip_existing(client, db_session, monkeypatch):
    _seed_dicts(db_session)
    ds_id = _mk_ds(db_session)
    _mk_model(client, code="ods_gdb_biz_user_info", layer="ODS")
    monkeypatch.setattr("api.model.open_connection", lambda ds, **kw: _MetaConn())
    r = client.post("/api/v1/models/reverse/import", json={
        "dsId": ds_id, "dbName": "ods",
        "tables": [{"tb": "ods_gdb_biz_user_info", "layer": "ODS"},
                   {"tb": "ods_gdb_biz_order", "layer": "ODS"}]})
    d = r.json()["data"]
    assert d["imported"] == 1 and d["skipped"][0]["tb"] == "ods_gdb_biz_user_info"
    new = db_session.query(DwModel).filter(DwModel.code == "ods_gdb_biz_order").first()
    assert new is not None and new.status == "draft"
    # engine 按 ds.type 映射 EngineType 主键（_mk_ds 为 mysql 类型 → "MySQL"）
    assert new.engine == "MySQL"
    # 规格适配：DwModel 无 fields relationship，改为直接查 DwModelField
    fs = sorted(f.name for f in
                db_session.query(DwModelField).filter(DwModelField.model_id == new.id).all())
    assert fs == ["id", "user_name"]


def test_reverse_import_naming_skip(client, db_session, monkeypatch):
    """编码不符合分层命名规范（ODS 层要求 ods_ 前缀）→ skipped，不建模型。"""
    _seed_dicts(db_session)
    ds_id = _mk_ds(db_session)
    monkeypatch.setattr("api.model.open_connection", lambda ds, **kw: _MetaConn())
    r = client.post("/api/v1/models/reverse/import", json={
        "dsId": ds_id, "dbName": "ods",
        "tables": [{"tb": "dwd_bad", "layer": "ODS"},
                   {"tb": "ods_gdb_biz_order", "layer": "ODS"}]})
    d = r.json()["data"]
    assert d["imported"] == 1
    assert d["skipped"][0]["tb"] == "dwd_bad"
    assert "命名规范" in d["skipped"][0]["reason"]
    assert db_session.query(DwModel).filter(DwModel.code == "dwd_bad").first() is None


def test_reverse_import_empty_cols_skipped(client, db_session, monkeypatch):
    """目标表无列信息（表不存在等）→ 计入 skipped，不建 0 字段模型。"""
    _seed_dicts(db_session)
    ds_id = _mk_ds(db_session)
    monkeypatch.setattr(
        "api.model.open_connection",
        lambda ds, **kw: _MetaConn(empty_tables=("ods_gdb_biz_user_info",)))
    r = client.post("/api/v1/models/reverse/import", json={
        "dsId": ds_id, "dbName": "ods",
        "tables": [{"tb": "ods_gdb_biz_user_info", "layer": "ODS"},
                   {"tb": "ods_gdb_biz_order", "layer": "ODS"}]})
    d = r.json()["data"]
    assert d["imported"] == 1
    assert d["skipped"] == [{"tb": "ods_gdb_biz_user_info", "reason": "未找到列（表不存在？）"}]
    assert db_session.query(DwModel).filter(DwModel.code == "ods_gdb_biz_user_info").first() is None
    assert db_session.query(DwModel).filter(DwModel.code == "ods_gdb_biz_order").first() is not None


def test_reverse_import_ddl_file(client, db_session):
    _seed_dicts(db_session)
    ddl = (b"CREATE TABLE `ods_gdb_biz_user_info` (\n"
           b"  `user_id` BIGINT NOT NULL COMMENT 'ID',\n"
           b"  `user_name` VARCHAR(100) COMMENT 'name',\n"
           b"  PRIMARY KEY (`user_id`)\n"
           b") COMMENT='users';\n")
    r = client.post("/api/v1/models/reverse/import-ddl",
                    files={"file": ("init.sql", ddl, "text/plain")})
    d = r.json()["data"]
    assert d["imported"] == 1 and d["skipped"] == []
    m = db_session.query(DwModel).filter(DwModel.code == "ods_gdb_biz_user_info").first()
    assert m is not None and m.layer == "ODS"
    # 规格适配：DwModel 无 fields relationship，改为直接查 DwModelField
    f = (db_session.query(DwModelField).filter(DwModelField.model_id == m.id)
         .order_by(DwModelField.seq).first())
    assert f.data_type == "BIGINT" and f.is_pk is True


def test_reverse_import_ddl_bad_file_400(client, db_session):
    _seed_dicts(db_session)
    r = client.post("/api/v1/models/reverse/import-ddl",
                    files={"file": ("bad.sql", b"CREATE TABLE `x` (", "text/plain")})
    assert r.status_code == 400 and r.json()["code"] == 8010


def test_reverse_import_ddl_oversize_400(client, db_session):
    """超过 5MB 上限 → 400，不落任何模型。"""
    _seed_dicts(db_session)
    big = b"x" * (5 * 1024 * 1024 + 1)
    r = client.post("/api/v1/models/reverse/import-ddl",
                    files={"file": ("big.sql", big, "text/plain")})
    assert r.status_code == 400 and r.json()["code"] == 4002
    assert "5MB" in r.json()["msg"]
    assert db_session.query(DwModel).count() == 0


def test_reverse_import_ddl_gbk(client, db_session):
    """GBK 编码的合法 DDL（中文 COMMENT）→ 降级解码成功导入。"""
    _seed_dicts(db_session)
    ddl = ("CREATE TABLE `ods_gdb_biz_user_info` (\n"
           "  `user_id` BIGINT NOT NULL COMMENT '用户ID',\n"
           "  PRIMARY KEY (`user_id`)\n"
           ") COMMENT='用户信息表';\n").encode("gbk")
    r = client.post("/api/v1/models/reverse/import-ddl",
                    files={"file": ("init.sql", ddl, "text/plain")})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["imported"] == 1 and d["skipped"] == []
    m = db_session.query(DwModel).filter(DwModel.code == "ods_gdb_biz_user_info").first()
    assert m is not None and m.remark == "用户信息表"
    f = (db_session.query(DwModelField).filter(DwModelField.model_id == m.id)
         .order_by(DwModelField.seq).first())
    assert f.comment == "用户ID"


# ---------------- Task 9: 血缘/影响/审计 ----------------


def test_lineage_merged_declared_runtime(client, db_session):
    from common.models import LineageEdge

    _seed_dicts(db_session)
    a = _mk_model(client, code="dwd_a")
    b = _mk_model(client, code="dws_b", layer="DWS")
    db_session.add(DwModelRelation(src_model_id=a, tgt_model_id=b))
    db_session.add(LineageEdge(wf_code=1, wf_name="wf1", instance_id="r1", node_id="n1",
                               stmt_no=1, from_table="ods_raw.x", to_table="ods.dwd_a",
                               src_type="runtime"))
    db_session.commit()
    r = client.get(f"/api/v1/models/{a}/lineage").json()["data"]
    ids = {n["id"] for n in r["nodes"]}
    assert "dws_b" in ids and "ods_raw.x" in ids
    kinds = {(e["from"], e["to"], e["kind"]) for e in r["edges"]}
    assert ("dwd_a", "dws_b", "declared") in kinds
    assert ("ods_raw.x", "ods.dwd_a", "runtime") in kinds
    assert r["sources"] == {"declared": 1, "runtime": 1}


def test_impact_recursive_chain(client, db_session):
    _seed_dicts(db_session)
    a = _mk_model(client, code="dwd_a")
    b = _mk_model(client, code="dws_b", layer="DWS")
    c = _mk_model(client, code="ads_c", layer="ADS")
    db_session.add_all([
        DwModelRelation(src_model_id=a, tgt_model_id=b),
        DwModelRelation(src_model_id=b, tgt_model_id=c),
    ])
    db_session.commit()
    r = client.get(f"/api/v1/models/{a}/impact").json()["data"]
    codes = {x["code"] for x in r["list"]}
    assert codes == {"dws_b", "ads_c"}
    assert all("dwd_a" in x["path"] for x in r["list"])


def test_publish_audit_recorded(client, db_session, monkeypatch):
    calls = []
    monkeypatch.setattr("api.model.audit", SimpleNamespace(
        info=lambda *a, **k: calls.append(a),
        error=lambda *a, **k: calls.append(a),
    ))
    _seed_dicts(db_session)
    mid = _mk_model(client)
    client.post(f"/api/v1/models/{mid}/publish")
    assert any(str(c[0]).startswith("model.publish") for c in calls)
