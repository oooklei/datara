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
from common.models import BizDomain, DataSource, DwLayer, DwModel, DwModelRelation, EngineType  # noqa: E402
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
    return client.put(f"/api/v1/models/{mid}/fields", json={"rev": rev, "fields": fields or _FIELDS})


def test_fields_full_replace(client, db_session):
    _seed_dicts(db_session)
    mid = _mk_model(client)
    r = _put_fields(client, mid, rev=1)
    assert r.status_code == 200 and r.json()["data"]["rev"] == 1
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
