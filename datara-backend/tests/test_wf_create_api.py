"""GraphWorkbench 新建工作流（前端创建对话框后端契约）单测：

- POST /workflow-definitions 仅 name：tags 落 []、v1 快照 remark="创建"（向后兼容）；
- 携带 tags/remark：tags 空白项过滤后落库、remark 落 v1 版本快照；
- 空白名称 → 2003 参数错误；GET /{id} 返回最小空 GraphDocument（name 一致）。

DB：sqlite 内存库（conftest），API 直连建流（test_component_ref_backfill 同手法）。
"""

from sqlalchemy import text


def _versions(client, wf_id):
    r = client.get(f"/api/v1/workflow-definitions/{wf_id}/versions")
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_create_name_only_keeps_legacy_contract(client):
    r = client.post("/api/v1/workflow-definitions", json={"name": " 仅名称流 "})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["id"].startswith("wf_")
    assert data["version"] == 1 and data["code"] >= 1
    # 列表回读：tags 为空（根目录普通工作流）
    lst = client.get("/api/v1/workflow-definitions", params={"page_no": 1, "page_size": 50}).json()["data"]["list"]
    row = next(x for x in lst if x["id"] == data["id"])
    assert row["name"] == "仅名称流"  # 首尾空白已裁剪
    assert row["tags"] == []
    # v1 快照 remark 缺省 = "创建"
    versions = _versions(client, data["id"])
    assert versions and versions[0]["version"] == 1
    assert versions[0]["remark"] == "创建"


def test_create_with_tags_and_remark(client):
    r = client.post(
        "/api/v1/workflow-definitions",
        json={
            "name": "带分类流",
            "tags": ["", "  ", "ETL"],
            "remark": " GraphWorkbench 对话框创建 ",
        },
    )
    assert r.status_code == 200, r.text
    wf_id = r.json()["data"]["id"]
    lst = client.get("/api/v1/workflow-definitions", params={"page_no": 1, "page_size": 50}).json()["data"]["list"]
    row = next(x for x in lst if x["id"] == wf_id)
    assert row["tags"] == ["ETL"]  # 空白项过滤、非空白裁剪语义由调用方保证，此处原样保留
    versions = _versions(client, wf_id)
    assert versions[0]["remark"] == "GraphWorkbench 对话框创建"  # 后端裁剪首尾空白


def test_create_blank_name_rejected(client):
    r = client.post("/api/v1/workflow-definitions", json={"name": "   "})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"] == 2003
    assert "不能为空" in body["msg"]


def test_created_doc_is_minimal_empty_graph(client):
    r = client.post("/api/v1/workflow-definitions", json={"name": "空图校验"})
    wf_id = r.json()["data"]["id"]
    doc = client.get(f"/api/v1/workflow-definitions/{wf_id}").json()["data"]
    assert doc["id"] == wf_id
    assert doc["name"] == "空图校验"
    assert doc["nodes"] == [] and doc["edges"] == []


def test_create_persists_owner_and_log(client, db_session):
    r = client.post("/api/v1/workflow-definitions", json={"name": "日志流", "remark": "备注落在日志"})
    wf_id = r.json()["data"]["id"]
    row = db_session.execute(
        text("SELECT owner_id, release_state, flag FROM t_wf_definition WHERE id = :i"), {"i": wf_id}
    ).fetchone()
    assert row[0] == 1  # conftest 注入用户 id=1
    assert row[1] == "offline" and row[2] == "yes"
    log = db_session.execute(
        text(
            "SELECT version, remark FROM t_wf_definition_log WHERE wf_code = "
            "(SELECT code FROM t_wf_definition WHERE id = :i) ORDER BY version DESC LIMIT 1"
        ),
        {"i": wf_id},
    ).fetchone()
    assert log[0] == 1 and log[1] == "备注落在日志"
