from common.std_engine import check_name, check_type


def test_std_engine_naming_and_type():
    assert check_name("pay_amount")
    assert not check_name("PayAmount")
    assert check_type("VARCHAR", "VARCHAR", 20, 30)
    assert not check_type("VARCHAR", "BIGINT")


def test_std_element_create_and_check(client):
    body = {"code": "DE-TEST", "cn": "支付金额", "en": "pay_amount", "data_type": "DECIMAL", "length": 18}
    r = client.post("/api/v1/std/elements", json=body)
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    check = client.get(f"/api/v1/std/elements/{eid}/check")
    assert check.status_code == 200 and check.json()["pass"] == 1


def test_std_element_rejects_bad_name(client):
    body = {"code": "DE-BAD", "cn": "坏名称", "en": "BadName", "data_type": "VARCHAR"}
    assert client.post("/api/v1/std/elements", json=body).status_code == 400


def test_std_code_value_lifecycle_and_reports(client):
    code = client.post("/api/v1/std/codes", json={"code": "C-TEST", "name": "测试码表"}).json()
    value = client.post(f"/api/v1/std/codes/{code['id']}/values", json={"c": "A", "n": "有效", "seq": 1}).json()
    assert client.put(f"/api/v1/std/codes/{code['id']}/values/{value['id']}", json={"c": "B", "n": "无效", "seq": 2}).status_code == 200
    assert client.delete(f"/api/v1/std/codes/{code['id']}/values/{value['id']}").status_code == 200
    assert client.post("/api/v1/std/naming/scan").status_code == 200
    assert client.post("/api/v1/std/mappings/run-all").status_code == 200
    assert client.post("/api/v1/std/elements/audit").status_code == 200
    assert client.get("/api/v1/std/reports").status_code == 200


def test_std_code_delete_guard_and_report_issue_flow(client):
    code = client.post("/api/v1/std/codes", json={"code": "C-GUARD", "name": "删除保护"}).json()
    value = client.post(f"/api/v1/std/codes/{code['id']}/values", json={"c": "A", "n": "有效"}).json()
    assert client.delete(f"/api/v1/std/codes/{code['id']}").status_code == 409
    assert client.delete(f"/api/v1/std/codes/{code['id']}/values/{value['id']}").status_code == 200
    assert client.delete(f"/api/v1/std/codes/{code['id']}").status_code == 200
    report = client.post("/api/v1/std/naming/scan").json()
    rid = report["id"]
    assert client.post(f"/api/v1/std/reports/{rid}/issues/0/fix", json={"opinion": "已修复"}).status_code == 200
    assert client.post(f"/api/v1/std/reports/{rid}/issues/0/verify").status_code == 200


def test_std_code_submit_serializes_snapshot(client):
    code = client.post("/api/v1/std/codes", json={"code": "C-SNAPSHOT", "name": "快照序列化"}).json()
    approval = client.post(f"/api/v1/std/codes/{code['id']}/submit")
    assert approval.status_code == 200
    assert isinstance(approval.json()["payload_json"]["create_time"], str)
