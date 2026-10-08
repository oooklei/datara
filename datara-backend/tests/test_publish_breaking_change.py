"""破坏性变更闸门单测（实施计划 Task 7，方案 §2.4）。

覆盖：
1. major 变更（删字段）未确认 → 422/6009，data.code='breaking_change' + changes 四类清单，
   失败不落任何状态变更；
2. 确认后重发（breaking_confirmed=true）→ 200，major 决策（upgrade_strategy/field_mapping/
   changes）落 t_component_log（action='breaking_confirmed'）；
3. minor 变更（加可选字段/改描述）→ 无闸门直接 200，无 breaking 审计行。

闸门仅对已有 published 版本的组件生效：首次发布（v1，无 old spec）不分类。
required 收紧语义裁定（主代理）：optional→required 为破坏性收紧（存量实例缺值校验失败）；
required→optional 为安全放松，不拦截。

DB：sqlite 内存库（conftest compiles 补丁），零外部依赖；发布流程 fixture 套路
与 test_component_design.py 同款（建组件→冻结→发布→GET /draft 自愈开修订→保存→冻结→发布）。
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from api.auth import get_current_user  # noqa: E402
from api.component_design import _classify_spec_change  # noqa: E402
from common.models import Component, ComponentLog, ComponentVersion  # noqa: E402


def set_role(app, role: str) -> None:
    """切换注入用户角色（发布由 admin 独占；与 conftest.set_role 同实现）。"""
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, user_name="tester", user_role=role)


# ---------------------------------------------------------------- 纯函数分类


def test_classify_removed_and_outputs():
    old = {"fields": [{"key": "sql", "uiType": "text"}, {"key": "table", "uiType": "text"}],
           "outputs": [{"name": "out_a"}, {"name": "out_b"}]}
    new = {"fields": [{"key": "sql", "uiType": "text"}], "outputs": [{"name": "out_a"}]}
    r = _classify_spec_change(old, new)
    assert r["major"] is True
    assert r["changes"]["removed"] == ["table"]
    assert r["changes"]["outputsRemoved"] == ["out_b"]
    assert r["changes"]["uiChanged"] == [] and r["changes"]["requiredTightened"] == []


def test_classify_ui_changed_and_required_tighten():
    """裁定回归：optional→required 计收紧（破坏性）；required→optional 是放松不计。"""
    old = {"fields": [{"key": "a", "uiType": "text", "required": False},
                      {"key": "b", "uiType": "text", "required": True}]}
    new = {"fields": [{"key": "a", "uiType": "select", "required": True},
                      {"key": "b", "uiType": "text", "required": False}]}
    r = _classify_spec_change(old, new)
    assert r["major"] is True
    assert r["changes"]["uiChanged"] == ["a"]
    assert r["changes"]["requiredTightened"] == ["a"]  # b required→optional 放松不计


def test_classify_minor_no_major():
    """加可选字段 / 改 label / 加输出均非破坏性。"""
    old = {"fields": [{"key": "sql", "uiType": "text", "required": False}]}
    new = {"fields": [{"key": "sql", "uiType": "text", "required": False},
                      {"key": "extra", "uiType": "text", "required": False}],
           "outputs": [{"name": "out"}], "summary": "补充描述"}
    r = _classify_spec_change(old, new)
    assert r["major"] is False and all(not v for v in r["changes"].values())


def test_classify_malformed_spec_tolerant():
    """spec 形态异常宽容（非 dict 项跳过），不误判——交由八项闸门兜底。"""
    r = _classify_spec_change({"fields": ["bad", None], "outputs": "x"}, {"fields": []})
    assert r["major"] is False


# ---------------------------------------------------------------- 端点闸门（sqlite 集成）


def _spec(keys, required=False, ui_type="text", **extra) -> dict:
    """可通过全部八项闸门的最小声明（uiType 取 9 基元；可选字段缺省）。"""
    return {"fields": [{"key": k, "label": k.upper(), "uiType": ui_type,
                        "required": required} for k in keys], **extra}


def _make_published_v1(client, type_name="brk_demo", spec=None) -> None:
    """建组件 → 冻结 v1 → 发布 v1（首发布无 old spec，闸门不介入）。"""
    body = {
        "type": type_name, "name": type_name, "profile": "dag",
        "execution_model": "dag-engine", "executor": "sql", "executable": True,
        "spec": spec if spec is not None else _spec(["sql", "table"]),
    }
    r = client.post("/api/v1/components", json=body)
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/components/%s/versions" % type_name, json={})
    assert r.status_code == 200, r.text
    set_role(client.app, "admin")
    r = client.post("/api/v1/components/%s/publish" % type_name,
                    json={"version": 1, "draft_rev": 0})
    assert r.status_code == 200, r.text


def _publish_v2(client, type_name, spec, **extra):
    """GET /draft 自愈开修订草稿 → 保存新 spec → 冻结 v2 → 发布 v2，返回发布响应。"""
    d = client.get("/api/v1/components/%s/draft" % type_name).json()["data"]
    r = client.put("/api/v1/components/%s/draft" % type_name,
                   json={"draft_rev": d["draftRev"], "spec": spec})
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/components/%s/versions" % type_name, json={})
    assert r.status_code == 200, r.text
    fr = r.json()["data"]
    return client.post("/api/v1/components/%s/publish" % type_name,
                       json={"version": fr["frozenVersion"],
                             "draft_rev": fr["draftRev"], **extra})


def test_major_removed_field_blocked_without_confirm(client, db_session):
    """删字段未确认 → 422/6009，data.code='breaking_change' + changes；失败不落状态。"""
    _make_published_v1(client)
    set_role(client.app, "admin")
    r = _publish_v2(client, "brk_demo", _spec(["sql"]))  # 删除 table 字段
    assert r.status_code == 422 and r.json()["code"] == 6009  # COMP_BREAKING_CHANGE
    d = r.json()["data"]
    assert d["code"] == "breaking_change" and "hint" in d
    assert d["changes"]["removed"] == ["table"]
    assert d["changes"]["uiChanged"] == [] and d["changes"]["outputsRemoved"] == []
    # 失败不落状态：版本行仍 frozen、主表 published_version 仍为 1
    comp = db_session.query(Component).filter_by(type="brk_demo").one()
    assert comp.published_version == 1
    assert db_session.query(ComponentVersion).filter_by(
        component_id=comp.id, version=2).one().state == "frozen"
    actions = [lg.action for lg in db_session.query(ComponentLog)
               .filter_by(component_id=comp.id).all()]
    assert "breaking_confirmed" not in actions


def test_major_confirmed_publishes_and_audits(client, db_session):
    """确认后重发 → 200；major 决策（upgrade_strategy/field_mapping/changes）落审计。"""
    _make_published_v1(client)
    set_role(client.app, "admin")
    r = _publish_v2(client, "brk_demo", _spec(["sql"]),
                    upgrade_strategy="manual",
                    field_mapping={"table": "sql"},
                    breaking_confirmed=True)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["publishedVersion"] == 2
    comp = db_session.query(Component).filter_by(type="brk_demo").one()
    assert comp.published_version == 2
    logs = db_session.query(ComponentLog).filter_by(component_id=comp.id).order_by(
        ComponentLog.id).all()
    # Task 15：publish 末尾的策略分派审计行（upgrade_strategy）后于 breaking_confirmed 落库
    conf = next(lg for lg in logs if lg.action == "breaking_confirmed")
    assert conf.version == 2
    decision = json.loads(conf.remark)
    assert decision["upgradeStrategy"] == "manual"
    assert decision["fieldMapping"] == {"table": "sql"}
    assert decision["changes"]["removed"] == ["table"]


def test_minor_change_publishes_without_gate(client, db_session):
    """minor 变更（加可选字段/改描述）→ 无闸门直接 200，无 breaking 审计行。"""
    _make_published_v1(client)
    set_role(client.app, "admin")
    spec = _spec(["sql", "table", "extra"], summary="更新描述")
    r = _publish_v2(client, "brk_demo", spec)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["publishedVersion"] == 2
    comp = db_session.query(Component).filter_by(type="brk_demo").one()
    actions = [lg.action for lg in db_session.query(ComponentLog)
               .filter_by(component_id=comp.id).all()]
    assert "breaking_confirmed" not in actions


def test_required_tighten_blocked_unless_confirmed(client):
    """裁定回归（端点级）：optional→required 为破坏性收紧，拦截；确认后放行。"""
    _make_published_v1(client, spec=_spec(["sql"]))  # v1 全 optional
    set_role(client.app, "admin")
    r = _publish_v2(client, "brk_demo", _spec(["sql"], required=True))
    assert r.status_code == 422 and r.json()["code"] == 6009
    assert r.json()["data"]["changes"]["requiredTightened"] == ["sql"]
    r = _publish_v2(client, "brk_demo", _spec(["sql"], required=True),
                    breaking_confirmed=True, upgrade_strategy="auto")
    assert r.status_code == 200, r.text


def test_first_publish_v1_never_classified(client):
    """首发布（v1，无旧版本）不分类：无 old spec 可比，直接放行。"""
    set_role(client.app, "admin")
    client.post("/api/v1/components", json={
        "type": "brk_first", "name": "first", "profile": "dag",
        "execution_model": "dag-engine", "executor": "sql", "executable": True,
        "spec": _spec(["sql"]),
    })
    r = client.post("/api/v1/components/brk_first/versions", json={})
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/components/brk_first/publish",
                    json={"version": 1, "draft_rev": 0})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["publishedVersion"] == 1
