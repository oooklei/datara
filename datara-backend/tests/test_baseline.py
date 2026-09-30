"""组件基线化 API 单测（M-B0）。

覆盖：
1. 进度清单：目录 35 type 全量返回、stats 正确、无进度行视为 pending；
2. 底稿保存：乐观锁 409（带 currentRev）、纯数据 422、pending→designing、draft_rev 递增；
3. 体检：合法底稿全项过、违规只报告不拦截（HTTP 仍 200）、lineage_decl 执行类报红 /
   逻辑控制类豁免；
4. 认可发版：四处写入（t_component scope=builtin + t_component_version v1 published +
   t_component_log + 进度行 published）、重复 409、无权限 403、无进度行 404；
5. lineage-decl：发布后可读、未基线化 unbaseline 空态。
   （/lineage/graph 旧 stub 用例已随 stub 删除迁移至 test_lineage_graph.py 新契约，Task 4）

DB：sqlite 内存库（conftest compiles 补丁），零外部依赖；造底稿直接 PUT 保存最小合法 spec。
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from api.auth import get_current_user  # noqa: E402
from common.models import BaselineProgress, Component, ComponentLog, ComponentVersion  # noqa: E402


def set_role(client, role: str) -> None:
    """切换注入用户角色（conftest.set_role 的 client 便捷版；权限矩阵用例）。"""
    client.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, user_name="tester", user_role=role)


# ---------------- 测试底稿 ----------------


def _legal_spec() -> dict:
    """执行类（sql，executor 在注册表内）的最小合法八段底稿：体检 10 项全过。"""
    return {
        "form": {
            "inputs": [{"key": "sql_text", "label": "SQL 语句", "uiType": "text"}],
            "outputs": [{"key": "out_rows", "label": "输出行", "uiType": "number"}],
            "params": [{"key": "timeout", "label": "超时秒数", "uiType": "number"}],
            "conditions": [], "constraints": [], "exclusions": [], "refs": [],
            "exports": [{"key": "rows", "from": "result"}],
        },
        "lineage": {"assets": [
            {"role": "source", "pick": "sql_text", "assetType": "table"},
            {"role": "target", "pick": "out_rows", "assetType": "table"},
        ]},
    }


def _logic_spec() -> dict:
    """逻辑控制类（start，executor 空）底稿：lineage_decl 豁免，contract 报红但不拦截。"""
    return {
        "form": {"inputs": [], "outputs": [], "params": [], "conditions": [],
                 "constraints": [], "exclusions": [], "refs": [], "exports": []},
        "lineage": {"assets": []},
    }


def _save_draft(client, type_name: str, spec: dict, draft_rev: int = 0):
    return client.put("/api/v1/components/baseline/%s/draft" % type_name,
                      json={"draft_rev": draft_rev, "spec": spec})


# ---------------- 进度清单 ----------------


def test_progress_lists_all_35_types(client):
    r = client.get("/api/v1/components/baseline/progress")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["stats"]["total"] == 35
    assert len(d["items"]) == 35
    # 无进度行：全部视为 pending、无底稿
    assert d["stats"]["byStatus"] == {"pending": 35}
    for item in d["items"]:
        assert item["status"] == "pending" and item["draftRev"] == 0
        assert item["hasDraft"] is False and item["confirmedBy"] is None
    # 目录元数据随行下发（code/label/executionModel 为快照真源）
    by_type = {i["type"]: i for i in d["items"]}
    assert by_type["sql"]["executionModel"] == "dag-engine" and by_type["sql"]["code"]


def test_progress_stats_reflect_saving(client):
    assert _save_draft(client, "sql", _legal_spec()).status_code == 200
    d = client.get("/api/v1/components/baseline/progress").json()["data"]
    assert d["stats"]["byStatus"] == {"designing": 1, "pending": 34}
    row = next(i for i in d["items"] if i["type"] == "sql")
    assert row["status"] == "designing" and row["hasDraft"] is True and row["draftRev"] == 1


# ---------------- 底稿读取 / 保存 ----------------


def test_draft_read_empty_state(client):
    d = client.get("/api/v1/components/baseline/sql/draft").json()["data"]
    assert d["type"] == "sql" and d["status"] == "pending" and d["draftRev"] == 0
    assert d["spec"] == {} and d["specHash"] is None


def test_draft_read_unknown_type_404(client):
    r = client.get("/api/v1/components/baseline/not_in_catalog/draft")
    assert r.status_code == 404 and r.json()["code"] == 6001  # COMP_NOT_FOUND


def test_draft_save_success_pending_to_designing(client, db_session):
    r = _save_draft(client, "sql", _legal_spec())
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["draftRev"] == 1 and d["status"] == "designing" and d["specHash"]
    row = db_session.query(BaselineProgress).filter_by(type="sql").one()
    assert row.status == "designing" and row.draft_rev == 1
    assert json.loads(row.draft_spec)["form"]["inputs"][0]["key"] == "sql_text"


def test_draft_save_lock_conflict_409(client):
    assert _save_draft(client, "sql", _legal_spec(), draft_rev=0).status_code == 200
    r = _save_draft(client, "sql", _legal_spec(), draft_rev=0)  # 服务端已是 1
    assert r.status_code == 409 and r.json()["code"] == 6007  # COMP_LOCK_CONFLICT
    assert r.json()["data"]["currentRev"] == 1


def test_draft_save_pure_data_422(client):
    bad = _legal_spec()
    bad["form"]["inputs"][0]["label"] = "xdef y"  # 命中禁用片段
    r = _save_draft(client, "sql", bad)
    assert r.status_code == 422 and r.json()["code"] == 6008  # COMP_SPEC_INVALID
    assert r.json()["data"]["violations"]


def test_draft_save_repeated_increments(client):
    assert _save_draft(client, "sql", _legal_spec(), draft_rev=0).json()["data"]["draftRev"] == 1
    r = _save_draft(client, "sql", _legal_spec(), draft_rev=1)
    assert r.json()["data"]["draftRev"] == 2
    assert r.json()["data"]["status"] == "designing"  # designing 不回退


# ---------------- 体检（只报告不拦截） ----------------


def test_check_legal_draft_all_green(client, db_session):
    assert _save_draft(client, "sql", _legal_spec()).status_code == 200
    r = client.post("/api/v1/components/baseline/sql/check")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["checkedAt"] and len(d["items"]) == 10
    assert all(i["ok"] for i in d["items"]), [i for i in d["items"] if not i["ok"]]
    # 结果落 check_report（含 checkedAt）
    row = db_session.query(BaselineProgress).filter_by(type="sql").one()
    assert row.check_report["checkedAt"] == d["checkedAt"]
    assert len(row.check_report["items"]) == 10


def test_check_reports_violations_without_blocking(client, db_session):
    """form 多余键 + 执行类无血缘：体检报红，但 HTTP 仍 200 且状态不变。"""
    bad = {"form": {"inputs": [], "outputs": [], "params": [], "conditions": [],
                    "constraints": [], "exclusions": [], "refs": [], "exports": [],
                    "extra_key": 1}}
    assert _save_draft(client, "sql", bad).status_code == 200
    r = client.post("/api/v1/components/baseline/sql/check")
    assert r.status_code == 200, "体检只报告不拦截"
    items = r.json()["data"]["items"]
    failed = {i["check"] for i in items if not i["ok"]}
    assert "form_whitelist" in failed and "lineage_decl" in failed
    row = db_session.query(BaselineProgress).filter_by(type="sql").one()
    assert row.status == "designing" and row.check_report is not None  # 状态不被体检改动


def test_check_lineage_decl_executor_rules(client):
    """执行类缺血缘报红；逻辑控制类（executor 空）豁免血缘声明。"""
    # start：master 路由控制流节点，无 worker executor → lineage_decl 豁免 + contract 通过
    assert _save_draft(client, "start", _logic_spec()).status_code == 200
    items = client.post("/api/v1/components/baseline/start/check").json()["data"]["items"]
    by_name = {i["check"]: i for i in items}
    assert by_name["lineage_decl"]["ok"] is True
    assert "豁免" in by_name["lineage_decl"]["msg"]
    assert by_name["contract"]["ok"] is True  # master 路由 dag-engine 豁免 executor
    # sql：executor 非空但底稿无 lineage.assets → lineage_decl 报红
    assert _save_draft(client, "sql", _logic_spec()).status_code == 200
    items = client.post("/api/v1/components/baseline/sql/check").json()["data"]["items"]
    lineage = next(i for i in items if i["check"] == "lineage_decl")
    assert lineage["ok"] is False and "assets" in lineage["msg"]


# ---------------- 认可发 v1 ----------------


def _publish(client, type_name: str):
    return client.post("/api/v1/components/%s/baseline/publish" % type_name, json={})


def test_publish_writes_all_tables(client, db_session):
    assert _save_draft(client, "sql", _legal_spec()).status_code == 200
    set_role(client, "admin")
    r = _publish(client, "sql")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["type"] == "sql" and d["publishedVersion"] == 1 and d["specHash"]
    assert d["confirmedAt"] and len(d["checkItems"]) == 10
    # t_component：builtin 身份行（治理基础：认可前 t_component 无目录行）
    comp = db_session.query(Component).filter_by(type="sql").one()
    assert comp.scope == "builtin" and comp.state == "published"
    assert comp.published_version == 1 and comp.profile == "dag"
    assert comp.execution_model == "dag-engine" and comp.executor == "sql"
    assert comp.executable is True and comp.draft_rev == 0
    # t_component_version：v1 published，spec_json=底稿全文
    ver = db_session.query(ComponentVersion).filter_by(component_id=comp.id).one()
    assert ver.version == 1 and ver.state == "published"
    assert json.loads(ver.spec_json) == _legal_spec()
    assert ver.published_by == "tester" and ver.published_time is not None
    # t_component_log：action=publish 审计
    log = db_session.query(ComponentLog).filter_by(component_id=comp.id).one()
    assert log.action == "publish" and log.version == 1 and log.spec_hash == d["specHash"]
    # 进度行：published + 认可人
    row = db_session.query(BaselineProgress).filter_by(type="sql").one()
    assert row.status == "published" and row.confirmed_by == "tester"
    assert row.confirmed_at is not None and row.check_report is not None


def test_publish_duplicate_409(client):
    assert _save_draft(client, "sql", _legal_spec()).status_code == 200
    set_role(client, "admin")
    assert _publish(client, "sql").status_code == 200
    r = _publish(client, "sql")
    assert r.status_code == 409 and r.json()["code"] == 6002  # COMP_STATE_CONFLICT


def test_publish_requires_permission(client):
    assert _save_draft(client, "sql", _legal_spec()).status_code == 200
    r = _publish(client, "sql")  # 默认 dev：无 publish_component
    assert r.status_code == 403 and r.json()["code"] == 1004  # NO_PERM


def test_publish_without_progress_404(client):
    set_role(client, "admin")
    r = _publish(client, "sql")  # 无底稿无进度行
    assert r.status_code == 404 and r.json()["code"] == 6001


# ---------------- 声明级血缘 ----------------


def test_lineage_decl_after_publish(client, db_session):
    assert _save_draft(client, "sql", _legal_spec()).status_code == 200
    set_role(client, "admin")
    assert _publish(client, "sql").status_code == 200
    d = client.get("/api/v1/components/sql/lineage-decl").json()["data"]
    assert d["type"] == "sql" and d["baselineState"] == "published"
    assert d["lineage"]["assets"][0]["role"] == "source"


def test_lineage_decl_unbaseline(client):
    d = client.get("/api/v1/components/never_published/lineage-decl").json()["data"]
    assert d == {"type": "never_published", "baselineState": "unbaseline", "lineage": None}


# ---------------- 修订前置：published 底稿不可直接改（R3） ----------------


def test_save_draft_rejected_on_published(client):
    """已认可发版的 type：PUT draft 必须 409/6002，底稿不被改写。"""
    set_role(client, "admin")
    # 造已发版：保存底稿 → 认可发 v1
    assert _save_draft(client, "sql", _legal_spec(), draft_rev=0).status_code == 200
    assert _publish(client, "sql").status_code == 200
    # 发版后再保存（rev 匹配）→ 409 COMP_STATE_CONFLICT，不得静默改写
    r = _save_draft(client, "sql", _legal_spec(), draft_rev=1)
    assert r.status_code == 409
    assert r.json()["code"] == 6002  # COMP_STATE_CONFLICT
    # 且底稿未被改写：draft_rev 仍为 1、status 仍 published
    d = client.get("/api/v1/components/baseline/sql/draft").json()["data"]
    assert d["status"] == "published" and d["draftRev"] == 1


# ---------------- 进度行下发 publishedVersion（修订轮次地基） ----------------


def test_progress_contains_published_version(client):
    """published 类型进度行带 publishedVersion；未发为 0。"""
    set_role(client, "admin")
    client.put("/api/v1/components/baseline/sql/draft", json={"draft_rev": 0, "spec": _legal_spec()})
    client.post("/api/v1/components/sql/baseline/publish", json={})
    r = client.get("/api/v1/components/baseline/progress")
    items = {i["type"]: i for i in r.json()["data"]["items"]}
    assert items["sql"]["publishedVersion"] == 1
    assert items["start"]["publishedVersion"] == 0


# ---------------- 修订轮次：redraft（复制上版开修订） ----------------


def test_redraft_copies_published_spec(client, db_session):
    """published → redraft：复制最新 published spec 为底稿，rev+1，status=designing，log 记 redraft。"""
    set_role(client, "admin")
    client.put("/api/v1/components/baseline/sql/draft", json={"draft_rev": 0, "spec": _legal_spec()})
    client.post("/api/v1/components/sql/baseline/publish", json={})
    published_spec = client.get("/api/v1/components/baseline/sql/draft").json()["data"]["spec"]
    # 模拟底稿与版本表漂移（防御未来实现误从进度行复制）：redraft 必须以版本表为准
    _row = db_session.query(BaselineProgress).filter_by(type="sql").one()
    _row.draft_spec = json.dumps({"drifted": True}, ensure_ascii=False)
    db_session.commit()
    # 开修订
    r = client.post("/api/v1/components/sql/baseline/redraft", json={"remark": "修订第一轮"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["status"] == "designing"
    assert d["fromVersion"] == 1
    assert d["draftRev"] == 2  # published 时 rev=1，redraft +1
    # 底稿 = 上版内容（从 t_component_version 复制，不受 publish 后底稿字段影响）
    cur = client.get("/api/v1/components/baseline/sql/draft").json()["data"]
    assert cur["spec"] == published_spec
    # log 记 redraft（审计）
    comp = db_session.query(Component).filter_by(type="sql").one()
    log = db_session.query(ComponentLog).filter_by(component_id=comp.id, action="redraft").one()
    assert log.version == 1 and log.remark == "修订第一轮"
    # 修订中可正常保存（rev=2 → 3）
    r = client.put("/api/v1/components/baseline/sql/draft", json={"draft_rev": 2, "spec": _legal_spec()})
    assert r.status_code == 200


def test_redraft_requires_published(client):
    """designing（未发版）redraft → 409；无进度行 → 404。"""
    set_role(client, "admin")
    r = client.post("/api/v1/components/start/baseline/redraft", json={})
    assert r.status_code == 404  # 无进度行
    client.put("/api/v1/components/baseline/notify/draft", json={"draft_rev": 0, "spec": _legal_spec()})
    r = client.post("/api/v1/components/notify/baseline/redraft", json={})
    assert r.status_code == 409  # designing 且未发版


# ---------------- 修订轮次：publish vN（修订发布） ----------------


def test_publish_revision_creates_v2(client, db_session):
    """修订中（designing + 已发 v1）认可 → v2：新版本行 + published_version 更新 + v1 留档。"""
    set_role(client, "admin")
    client.put("/api/v1/components/baseline/sql/draft", json={"draft_rev": 0, "spec": _legal_spec()})
    client.post("/api/v1/components/sql/baseline/publish", json={})
    client.post("/api/v1/components/sql/baseline/redraft", json={})
    # 改底稿（rev=2 → 3）再发布
    client.put("/api/v1/components/baseline/sql/draft", json={"draft_rev": 2, "spec": _legal_spec()})
    r = client.post("/api/v1/components/sql/baseline/publish", json={"remark": "修订发布"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["publishedVersion"] == 2
    # 版本行两枚且均 published（v1 留档）
    r = client.get("/api/v1/components/sql/versions")
    vers = r.json()["data"]["items"]
    assert [v["version"] for v in vers] == [2, 1]
    assert all(v["state"] == "published" for v in vers)
    # DB 层：主表版本指针推进 v2；修订 log（action=publish, version=2，带 remark/hash）
    comp = db_session.query(Component).filter_by(type="sql").one()
    assert comp.published_version == 2
    log = db_session.query(ComponentLog).filter_by(
        component_id=comp.id, action="publish", version=2).one()
    assert log.remark == "修订发布" and log.spec_hash == d["specHash"]
    # 进度行 draft_rev 不重置（1→redraft 2→保存 3，修订轮连续递增）
    assert db_session.query(BaselineProgress).filter_by(type="sql").one().draft_rev == 3
    # 进度行回 published；重复认可仍 409
    assert client.get("/api/v1/components/baseline/sql/draft").json()["data"]["status"] == "published"
    assert client.post("/api/v1/components/sql/baseline/publish", json={}).status_code == 409


def test_publish_still_rejected_when_published_no_revision(client):
    """status=published（未开修订）直接再认可 → 409 不变。"""
    set_role(client, "admin")
    client.put("/api/v1/components/baseline/sql/draft", json={"draft_rev": 0, "spec": _legal_spec()})
    client.post("/api/v1/components/sql/baseline/publish", json={})
    assert client.post("/api/v1/components/sql/baseline/publish", json={}).status_code == 409


def test_publish_rejected_when_user_component_occupies_type(client, db_session):
    """数据漂移防御：user 组件占用目录 type（published_version=None）→ 409 而非 500。

    create_component 不拦目录内 type（现实漏洞）：user 自建组件可占 type=sql，
    该 type 进度 designing 时认可发版若误判为修订型会对未发版行做 published_version+1。
    """
    set_role(client, "admin")
    db_session.add(Component(type="sql", name="冒名 sql", profile="dag", scope="user",
                             execution_model="dag-engine", state="draft", published_version=None))
    db_session.commit()
    assert _save_draft(client, "sql", _legal_spec()).status_code == 200
    r = _publish(client, "sql")
    assert r.status_code == 409, r.text
    assert r.json()["code"] == 6002  # COMP_STATE_CONFLICT
    assert "未发版" in r.json()["msg"]


# ---------------- 修订轮次：discard_draft（放弃修订） ----------------


def test_discard_revision_restores_published(client, db_session):
    """修订中放弃：底稿重置为最新 published 版，status 回 published，log 记 discard。"""
    set_role(client, "admin")
    client.put("/api/v1/components/baseline/sql/draft", json={"draft_rev": 0, "spec": _legal_spec()})
    client.post("/api/v1/components/sql/baseline/publish", json={})
    published_spec = client.get("/api/v1/components/baseline/sql/draft").json()["data"]["spec"]
    client.post("/api/v1/components/sql/baseline/redraft", json={})
    client.put("/api/v1/components/baseline/sql/draft", json={"draft_rev": 2, "spec": _legal_spec()})
    # 模拟修订稿与版本表漂移（防御未来实现误从进度行复制）：discard 必须以版本表为准
    _row = db_session.query(BaselineProgress).filter_by(type="sql").one()
    _row.draft_spec = json.dumps({"drifted": True}, ensure_ascii=False)
    db_session.commit()
    r = client.post("/api/v1/components/sql/baseline/discard_draft", json={})
    assert r.status_code == 200, r.text
    d = client.get("/api/v1/components/baseline/sql/draft").json()["data"]
    assert d["status"] == "published"
    assert d["spec"] == published_spec  # 重置为上版内容（漂移值被丢弃）
    assert d["draftRev"] == 4  # redraft 2 → 保存 3 → discard 4（连续递增）
    # log 记 discard（审计）
    comp = db_session.query(Component).filter_by(type="sql").one()
    log = db_session.query(ComponentLog).filter_by(component_id=comp.id, action="discard").one()
    assert log.version == 1 and "放弃修订" in log.remark


def test_discard_rejected_when_not_revision(client):
    """首发型 designing（未发版）无放弃语义（无已发版本可回）→ 409。"""
    set_role(client, "admin")
    client.put("/api/v1/components/baseline/notify/draft", json={"draft_rev": 0, "spec": _legal_spec()})
    assert client.post("/api/v1/components/notify/baseline/discard_draft", json={}).status_code == 409
