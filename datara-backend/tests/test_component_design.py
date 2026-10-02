"""组件草稿 API 单测（实施计划 20260926 Task B2，治理设计 §16/§18.2/红线 2）。

覆盖：
1. 纯数据校验器（红线 2）：函数/代码片段、NaN、autoName 占位符白名单、合法声明不误伤；
2. 三端点契约（§18.2 前三端点）：创建（type 唯一/格式）、读草稿、保存（乐观锁 409 带
   currentRev、纯数据 422 带逐条违规）；
3. RBAC：analyst/viewer 无 design_component → 403；dev 可设计；M1 无发布入口（§19.1）；
4. 审计只追加：create / update_draft 落 t_component_log 含内容哈希。

DB：sqlite 内存库（conftest compiles 补丁），零外部依赖。
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import text

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from api.auth import get_current_user  # noqa: E402
from api.component_design import (  # noqa: E402
    _spec_hash,
    validate_spec_pure_data,
)
from common.models import Component, ComponentLog, ComponentVersion  # noqa: E402


def set_role(app, role: str) -> None:
    """切换注入用户角色（权限矩阵用例；与 conftest.set_role 同实现）。"""
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, user_name="tester", user_role=role)

# ---------------------------------------------------------------- 纯数据校验器


def _ok_spec() -> dict:
    return {
        "type": "dag_transform_sql",
        "name": "SQL 转换",
        "fields": [{"key": "sql", "label": "SQL", "uiType": "textarea", "required": True}],
        "dropPolicy": {"autoName": "SQL转换_{n}", "maxInstances": 0},
    }


def test_valid_spec_passes():
    assert validate_spec_pure_data(_ok_spec()) == []


def test_chinese_text_not_flagged():
    spec = _ok_spec()
    spec["summary"] = "从数据源导入数据并进行函数式汇总（说明文本）"
    assert validate_spec_pure_data(spec) == []


@pytest.mark.parametrize("snippet", ["function", "=>", "eval(", "new Function", "Function(",
                                     "<script", "javascript:", "__import__", "import ",
                                     "def ", "lambda ", "${", "`", "require(", "exec("])
def test_forbidden_snippets_detected(snippet):
    spec = _ok_spec()
    spec["fields"][0]["label"] = "x%sy" % snippet
    assert validate_spec_pure_data(spec), snippet


def test_forbidden_snippet_in_key_detected():
    spec = _ok_spec()
    spec["eval(x)"] = 1
    assert validate_spec_pure_data(spec)


def test_nan_rejected():
    spec = _ok_spec()
    spec["fields"][0]["default"] = float("nan")
    violations = validate_spec_pure_data(spec)
    assert violations and "严格 JSON" in violations[0]


def test_non_object_spec_rejected():
    assert validate_spec_pure_data([1, 2]) != []
    assert validate_spec_pure_data("x") != []
    assert validate_spec_pure_data(None) != []


def test_autoname_placeholder_whitelist():
    spec = _ok_spec()
    assert validate_spec_pure_data(spec) == []          # {n} 允许
    spec["dropPolicy"]["autoName"] = "{type}_{n}"
    assert validate_spec_pure_data(spec) == []          # {type} 允许
    spec["dropPolicy"]["autoName"] = "{expr: eval_x}"
    assert validate_spec_pure_data(spec)                # 其它占位符拒绝


def test_spec_hash_is_canonical():
    """键序无关：规范化哈希一致（B5 冻结版本一致性校验的依据）。"""
    a = {"x": 1, "y": {"a": 2, "b": 3}}
    b = {"y": {"b": 3, "a": 2}, "x": 1}
    assert _spec_hash(a) == _spec_hash(b)


# ---------------------------------------------------------------- 创建草稿

VALID_BODY = {
    "type": "user_demo",
    "name": "演示组件",
    "profile": "dag",
    "execution_model": "dag-engine",
    "executor": "demo_handler",
    "description": "测试用",
    "spec": {"fields": [{"key": "sql", "label": "SQL", "uiType": "textarea"}]},
}


def test_create_draft_success(client, db_session):
    r = client.post("/api/v1/components", json=VALID_BODY)
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["type"] == "user_demo" and d["draftRev"] == 0 and d["draftVersion"] == 1
    # 主表身份行 + v1 草稿版本行
    comp = db_session.query(Component).filter_by(type="user_demo").one()
    assert comp.scope == "user" and comp.state == "draft" and comp.draft_rev == 0
    assert comp.published_version is None
    ver = db_session.query(ComponentVersion).filter_by(component_id=comp.id).one()
    assert ver.state == "draft" and ver.version == 1
    # 审计 create
    logs = db_session.query(ComponentLog).filter_by(component_id=comp.id).all()
    assert len(logs) == 1 and logs[0].action == "create" and logs[0].spec_hash


def test_create_duplicate_type_409(client):
    client.post("/api/v1/components", json=VALID_BODY)
    r = client.post("/api/v1/components", json=VALID_BODY)
    assert r.status_code == 409
    assert r.json()["code"] == 6005  # COMP_DUPLICATE_TYPE


def test_create_rejects_bad_type_format(client):
    bad = dict(VALID_BODY, type="1bad-Type")
    r = client.post("/api/v1/components", json=bad)
    assert r.status_code == 200, "业务失败走统一响应包"
    assert r.json()["code"] == 6008


def test_create_rejects_bad_enum(client):
    for field, value in (("profile", "nope"), ("execution_model", "magic")):
        r = client.post("/api/v1/components", json=dict(VALID_BODY, **{field: value}))
        assert r.status_code == 422, field


def test_create_rejects_impure_spec(client):
    bad = dict(VALID_BODY, spec={"onChange": "function(x){return x}"})
    r = client.post("/api/v1/components", json=bad)
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == 6008 and body["data"]["violations"]


# ---------------------------------------------------------------- 页面设计器（execution_model=page）

def test_create_page_component_ok(client):
    """page 组件可创建：executable 显式 false（页面设计器产出的 UI 组件不可执行）。"""
    set_role(client.app, "dev")
    r = client.post("/api/v1/components", json={
        "type": "page_sales_board", "name": "销售看板", "profile": "dag",
        "execution_model": "page", "executable": False,
        "spec": {"page": {"version": 1, "canvas": {"width": 288, "height": 520}, "widgets": []}},
    })
    assert r.status_code == 200, r.text


def test_page_model_executable_forbidden(client):
    """page + executable=true → 422 COMP_SPEC_INVALID（断言业务码，区别于 Literal 的 FastAPI 422）。"""
    set_role(client.app, "dev")
    r = client.post("/api/v1/components", json={
        "type": "page_bad_exec", "name": "x", "profile": "dag",
        "execution_model": "page", "executable": True,
        "spec": {"page": {"version": 1, "canvas": {}, "widgets": []}},
    })
    assert r.status_code == 422
    assert r.json()["code"] == 6008  # COMP_SPEC_INVALID


def _page_spec(widgets):
    return {"page": {"version": 1, "name": "看板", "icon": "bar", "color": "#1677ff",
                     "canvas": {"width": 288, "height": 520, "background": {"fill": "#ffffff"}},
                     "widgets": widgets}}


def test_page_spec_structural_violations():
    from api.component_design import validate_spec_pure_data
    # widget 缺 id；binding（static）缺 fallback
    bad = _page_spec([{"kind": "text", "rect": {"x": 0, "y": 0, "w": 100, "h": 24},
                       "bindings": {"value": {"kind": "static"}}}])
    violations = validate_spec_pure_data(bad)
    assert any("widget.id" in v or "widget.kind" in v for v in violations)
    assert any("fallback" in v for v in violations)


def test_page_spec_valid_passes():
    from api.component_design import validate_spec_pure_data
    ok = _page_spec([{"id": "w1", "kind": "text", "rect": {"x": 8, "y": 8, "w": 120, "h": 24},
                      "props": {"text": "销售"},
                      "style": {}, "bindings": {"value": {"kind": "static", "fallback": "销售"}}}])
    assert validate_spec_pure_data(ok) == []


# ---------------------------------------------------------------- 读/保存草稿


def _created(client):
    r = client.post("/api/v1/components", json=VALID_BODY)
    assert r.status_code == 200
    return r.json()["data"]


def test_get_draft_roundtrip(client):
    _created(client)
    r = client.get("/api/v1/components/user_demo/draft")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["type"] == "user_demo" and d["draftRev"] == 0 and d["draftVersion"] == 1
    assert d["spec"]["fields"][0]["key"] == "sql"
    assert d["state"] == "draft" and d["publishedVersion"] is None


def test_get_draft_unknown_type_404(client):
    r = client.get("/api/v1/components/__nope__/draft")
    assert r.status_code == 404 and r.json()["code"] == 6001


def test_save_draft_bumps_rev(client, db_session):
    _created(client)
    spec = {"fields": [{"key": "sql", "label": "SQL v2", "uiType": "textarea"}]}
    r = client.put("/api/v1/components/user_demo/draft",
                   json={"draft_rev": 0, "spec": spec})
    assert r.status_code == 200
    assert r.json()["data"]["draftRev"] == 1
    comp = db_session.query(Component).filter_by(type="user_demo").one()
    assert comp.draft_rev == 1
    ver = db_session.query(ComponentVersion).filter_by(component_id=comp.id).one()
    assert "SQL v2" in ver.spec_json
    logs = db_session.query(ComponentLog).filter_by(component_id=comp.id).all()
    assert [lg.action for lg in logs] == ["create", "update_draft"]


def test_save_draft_stale_rev_409_with_current(client):
    _created(client)
    r = client.put("/api/v1/components/user_demo/draft",
                   json={"draft_rev": 0, "spec": {"a": 1}})
    assert r.status_code == 200
    # 用过期 rev 再存 → 409 + data.currentRev
    r = client.put("/api/v1/components/user_demo/draft",
                   json={"draft_rev": 0, "spec": {"a": 2}})
    assert r.status_code == 409
    body = r.json()
    assert body["code"] == 6007 and body["data"]["currentRev"] == 1


def test_save_draft_impure_spec_422(client):
    _created(client)
    r = client.put("/api/v1/components/user_demo/draft",
                   json={"draft_rev": 0, "spec": {"tpl": "${window.alert}"}})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == 6008 and body["data"]["violations"]


def test_save_draft_unknown_type_404(client):
    r = client.put("/api/v1/components/__nope__/draft", json={"draft_rev": 0, "spec": {}})
    assert r.status_code == 404 and r.json()["code"] == 6001


# ---------------------------------------------------------------- B5 冻结版本

def _freeze(client, remark=None):
    payload = {"remark": remark} if remark else {}
    return client.post("/api/v1/components/user_demo/versions", json=payload)


def _versions(client):
    r = client.get("/api/v1/components/user_demo/versions")
    assert r.status_code == 200
    return r.json()["data"]


def test_freeze_creates_immutable_version(client, db_session):
    """冻结：v1 → frozen + 自动开启 v2 空草稿（§8 状态机自环）；draft_rev 不 bump。"""
    _created(client)
    r = client.put("/api/v1/components/user_demo/draft",
                   json={"draft_rev": 0, "spec": VALID_BODY["spec"]})
    saved_hash = r.json()["data"]["specHash"]
    r = _freeze(client, remark="首个冻结")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["frozenVersion"] == 1 and d["draftVersion"] == 2 and d["draftRev"] == 1
    data = _versions(client)
    assert data["publishedVersion"] is None  # M1 无发布
    items = {i["version"]: i for i in data["items"]}
    assert items[1]["state"] == "frozen" and items[1]["specHash"] == saved_hash
    assert items[2]["state"] == "draft"
    # 新草稿可正常读写（自环）
    draft = client.get("/api/v1/components/user_demo/draft").json()["data"]
    assert draft["draftVersion"] == 2 and draft["spec"] == {} and draft["draftRev"] == 1
    # 审计 freeze_version 落日志
    comp = db_session.query(Component).filter_by(type="user_demo").one()
    logs = db_session.query(ComponentLog).filter_by(component_id=comp.id).all()
    assert [lg.action for lg in logs] == ["create", "update_draft", "freeze_version"]
    assert logs[-1].remark == "首个冻结" and logs[-1].spec_hash == saved_hash


def test_frozen_version_immutable_after_further_edits(client, db_session):
    """§19.1 硬验收：冻结后再怎么编辑新草稿，冻结行 spec_json/spec_hash 永不变化。"""
    _created(client)
    client.put("/api/v1/components/user_demo/draft",
               json={"draft_rev": 0, "spec": {"fields": [{"key": "a"}]}})
    _freeze(client)
    frozen_hash = _versions(client)["items"][-1]["specHash"]
    frozen_json = (
        db_session.query(ComponentVersion)
        .filter_by(type="user_demo", version=1).one().spec_json
    )
    # 持续编辑 v2 草稿并再冻结 v2
    client.put("/api/v1/components/user_demo/draft",
               json={"draft_rev": 1, "spec": {"fields": [{"key": "b"}, {"key": "c"}]}})
    _freeze(client)
    comp = db_session.query(Component).filter_by(type="user_demo").one()
    v1 = db_session.query(ComponentVersion).filter_by(component_id=comp.id, version=1).one()
    v2 = db_session.query(ComponentVersion).filter_by(component_id=comp.id, version=2).one()
    assert v1.spec_json == frozen_json and v1.spec_hash == frozen_hash
    assert v1.state == "frozen" and v2.state == "frozen"
    items = {i["version"]: i for i in _versions(client)["items"]}
    assert items[1]["specHash"] != items[2]["specHash"]
    assert client.get("/api/v1/components/user_demo/draft").json()["data"]["draftVersion"] == 3


def test_freeze_without_draft_409(client, db_session):
    """无进行中草稿（异常态防御）：冻结 409 COMP_STATE_CONFLICT。"""
    _created(client)
    comp = db_session.query(Component).filter_by(type="user_demo").one()
    db_session.query(ComponentVersion).filter_by(component_id=comp.id).delete()
    db_session.commit()
    r = _freeze(client)
    assert r.status_code == 409 and r.json()["code"] == 6002  # COMP_STATE_CONFLICT


def test_freeze_rejects_impure_spec_422(client, db_session):
    """存量脏数据防御（绕过 save 闸门直写库）：冻结 422 纯数据违规。"""
    _created(client)
    comp = db_session.query(Component).filter_by(type="user_demo").one()
    ver = db_session.query(ComponentVersion).filter_by(component_id=comp.id).one()
    ver.spec_json = '{"tpl": "${eval(x)}"}'
    db_session.commit()
    r = _freeze(client)
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == 6008 and body["data"]["violations"]
    # 失败不落冻结：草稿行仍是 draft，可修复后再冻
    assert db_session.query(ComponentVersion).filter_by(component_id=comp.id).one().state == "draft"


def test_versions_unknown_type_404(client):
    assert client.get("/api/v1/components/__nope__/versions").status_code == 404


def test_freeze_rbac(client):
    """B5 权限位：dev 可冻结（design_component），analyst/viewer 403。"""
    _created(client)
    set_role(client.app, "analyst")
    assert _freeze(client).status_code == 403
    assert client.get("/api/v1/components/user_demo/versions").status_code == 403
    set_role(client.app, "dev")
    assert _freeze(client).status_code == 200


def test_freeze_hash_matches_canonical_spec(client):
    """冻结哈希 = 规范化内容哈希：键序不同的等价声明冻结结果一致。"""
    _created(client)
    client.put("/api/v1/components/user_demo/draft",
               json={"draft_rev": 0, "spec": {"y": {"b": 1, "a": 2}, "x": 1}})
    _freeze(client)
    items = {i["version"]: i for i in _versions(client)["items"]}
    assert items[1]["specHash"] == _spec_hash({"x": 1, "y": {"a": 2, "b": 1}})


# ---------------------------------------------------------------- RBAC / 闸门


def test_analyst_viewer_cannot_design(client):
    _created(client)
    for role in ("analyst", "viewer"):
        set_role(client.app, role)
        assert client.get("/api/v1/components/user_demo/draft").status_code == 403
        assert client.put("/api/v1/components/user_demo/draft",
                          json={"draft_rev": 0, "spec": {}}).status_code == 403
    set_role(client.app, "dev")


def test_m1_has_no_publish_entry(client):
    """M2 D3 起 offline/rollback 端点已引入（§18.3）；draft 组件操作 → 409 状态冲突。"""
    _created(client)
    set_role(client.app, "admin")
    r = client.post("/api/v1/components/user_demo/offline", json={})
    assert r.status_code == 409 and r.json()["code"] == 6002  # COMP_STATE_CONFLICT
    r = client.post("/api/v1/components/user_demo/rollback", json={"version": 1})
    assert r.status_code == 409 and r.json()["code"] == 6002  # 版本不存在
    set_role(client.app, "dev")


def test_m0_readonly_catalog_still_works(client):
    """共存校验：M0 目录只读端点不受本模块挂载影响。"""
    r = client.get("/api/v1/components")
    assert r.status_code == 200 and r.json()["data"]["total"] == 75


# ---------------------------------------------------------------- M2 发布闸门（Task D1，§13 八项）

def _publishable_spec() -> dict:
    """可通过全部闸门的最小声明（uiType 取 9 基元）。"""
    return {"fields": [{"key": "sql", "label": "SQL", "uiType": "text"}]}


def _make_frozen(client, type_name="gate_demo", execution_model="dag-engine",
                 executor="sql", spec=None, executable=True) -> dict:
    """建组件（初始 spec 直接合法）→ 冻结 v1（draft_rev 恒 0，freeze 不 bump）。"""
    body = {
        "type": type_name, "name": type_name, "profile": "dag",
        "execution_model": execution_model, "executor": executor,
        "executable": executable,
        "spec": spec if spec is not None else _publishable_spec(),
    }
    r = client.post("/api/v1/components", json=body)
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/components/%s/versions" % type_name, json={})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _publish(client, type_name="gate_demo", version=1, draft_rev=0, **extra):
    set_role(client.app, "admin")
    return client.post("/api/v1/components/%s/publish" % type_name,
                       json={"version": version, "draft_rev": draft_rev, **extra})


def _gate_item(body: dict, gate: str) -> dict:
    return next(i for i in body["data"]["items"] if i["gate"] == gate)


def test_publish_success_frozen_to_published(client, db_session):
    """闸门全过：frozen→published，主表 published_version 生效，审计落 publish。"""
    _make_frozen(client)
    r = _publish(client)
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["publishedVersion"] == 1 and d["supersededVersion"] is None and d["specHash"]
    comp = db_session.query(Component).filter_by(type="gate_demo").one()
    assert comp.state == "published" and comp.published_version == 1
    ver = db_session.query(ComponentVersion).filter_by(component_id=comp.id, version=1).one()
    assert ver.state == "published" and ver.published_by == "tester" and ver.published_time
    logs = db_session.query(ComponentLog).filter_by(component_id=comp.id).all()
    assert [lg.action for lg in logs] == ["create", "freeze_version", "publish"]


def test_publish_rbac_dev_403(client):
    """§13-1 权限：dev 可设计不可发布（publish_component 由 admin 独占，§14）。"""
    _make_frozen(client)
    assert client.post("/api/v1/components/gate_demo/publish",
                       json={"version": 1, "draft_rev": 0}).status_code == 403


def test_publish_gate_pure_data_dirty_frozen_row(client, db_session):
    """§13-2 纯数据：存量脏数据（绕过冻结校验直写库）发布被 422 拦截。"""
    _make_frozen(client)
    comp = db_session.query(Component).filter_by(type="gate_demo").one()
    ver = db_session.query(ComponentVersion).filter_by(component_id=comp.id, version=1).one()
    ver.spec_json = '{"tpl": "${eval(x)}"}'
    db_session.commit()
    r = _publish(client)
    assert r.status_code == 422 and r.json()["code"] == 6003  # COMP_GATE_FAILED
    item = _gate_item(r.json(), "pure_data")
    assert not item["ok"] and "eval" in item["msg"]
    # 失败不落状态：版本行仍 frozen、主表未发布
    db_session.expire_all()
    assert db_session.query(ComponentVersion).filter_by(
        component_id=comp.id, version=1).one().state == "frozen"
    assert db_session.query(Component).filter_by(type="gate_demo").one().state == "draft"


def test_publish_gate_whitelist_uitype(client):
    """§13-3 白名单：uiType 不在 9 基元 → 拒（textarea 是系统目录历史控件，声明契约外）。"""
    _make_frozen(client, spec={"fields": [{"key": "a", "label": "A", "uiType": "textarea"}]})
    r = _publish(client)
    assert r.status_code == 422
    item = _gate_item(r.json(), "whitelist")
    assert not item["ok"] and "uiType" in item["msg"]


def test_publish_gate_whitelist_pick_keys(client):
    """§13-3 白名单：pick 键不在 ResourcePick 契约内 → 拒（mode 合法键不误伤）。"""
    spec = {"fields": [{"key": "ds", "label": "数据源", "uiType": "resource",
                        "pick": {"mode": "table", "bogusKey": 1}}]}
    _make_frozen(client, spec=spec)
    r = _publish(client)
    assert r.status_code == 422
    assert "bogusKey" in _gate_item(r.json(), "whitelist")["msg"]


def test_publish_gate_drop_policy(client):
    """§13-4 dropPolicy：未知键与非法枚举 → 拒（占位符/函数由纯数据闸门覆盖）。"""
    spec = dict(_publishable_spec(),
                dropPolicy={"mystery": 1, "autoConnect": {"upstream": "sideways"}})
    _make_frozen(client, spec=spec)
    r = _publish(client)
    assert r.status_code == 422
    msg = _gate_item(r.json(), "drop_policy")["msg"]
    assert "mystery" in msg and "sideways" in msg


def test_publish_gate_contract_demo_only(client):
    """§13-5 执行契约（红线 1）：demo-only 禁止发布——GAP-30 的主拦截项。"""
    _make_frozen(client, type_name="gate_demo_only", execution_model="demo-only", executor=None)
    r = _publish(client, type_name="gate_demo_only")
    assert r.status_code == 422
    assert not _gate_item(r.json(), "contract")["ok"]


def test_publish_gate_contract_executor_missing(client):
    """§13-5：dag-engine 未绑 executor → 拒。"""
    _make_frozen(client, type_name="gate_no_exec", executor=None)
    r = _publish(client, type_name="gate_no_exec")
    assert r.status_code == 422
    assert "executor" in _gate_item(r.json(), "contract")["msg"]


def test_publish_gate_contract_executor_not_in_registry(client):
    """§13-5：dag-engine executor 不在分派注册表 → 拒（声明与执行脱节的硬拦截）。"""
    _make_frozen(client, type_name="gate_bad_exec", executor="magic_handler")
    r = _publish(client, type_name="gate_bad_exec")
    assert r.status_code == 422
    assert "magic_handler" in _gate_item(r.json(), "contract")["msg"]


def test_publish_gate_contract_canvas_device(client):
    """§13-5：canvas-device 必须 executable=false；置 false 后可发布。"""
    _make_frozen(client, type_name="gate_canvas_bad",
                 execution_model="canvas-device", executor=None, executable=True)
    r = _publish(client, type_name="gate_canvas_bad")
    assert r.status_code == 422
    assert not _gate_item(r.json(), "contract")["ok"]
    # 置 false（回填语义：装饰件本来就不执行）
    client.post("/api/v1/components", json={
        "type": "gate_canvas_ok", "name": "装饰", "profile": "dag",
        "execution_model": "canvas-device", "executable": False,
        "spec": _publishable_spec()})
    client.post("/api/v1/components/gate_canvas_ok/versions", json={})
    assert _publish(client, type_name="gate_canvas_ok").status_code == 200


def test_publish_gate_contract_runtime_only_palette(client):
    """§13-5：runtime-only 强制 paletteVisible=false（仅装载物化消费）。"""
    _make_frozen(client, type_name="gate_rt_bad", execution_model="runtime-only", executor=None)
    r = _publish(client, type_name="gate_rt_bad")
    assert r.status_code == 422
    assert "paletteVisible" in _gate_item(r.json(), "contract")["msg"]
    # 显式声明后可发布
    client.put("/api/v1/components/gate_rt_bad/draft",
               json={"draft_rev": 0, "spec": dict(_publishable_spec(), paletteVisible=False)})
    client.post("/api/v1/components/gate_rt_bad/versions", json={})
    r = _publish(client, type_name="gate_rt_bad", version=2, draft_rev=1)
    assert r.status_code == 200, r.text


def test_publish_gate_hash_consistency_catalog_collision(client):
    """§13-6 同名一致：与系统内置目录同名（op_script）→ 拒（杜绝 componentRef 引用歧义）。"""
    _make_frozen(client, type_name="op_script")
    r = _publish(client, type_name="op_script")
    assert r.status_code == 422
    assert not _gate_item(r.json(), "hash_consistency")["ok"]


def test_publish_lock_conflict_409(client):
    """§13-7 乐观锁：draft_rev 不一致 → 409 COMP_LOCK_CONFLICT 带 currentRev（§16）。"""
    _make_frozen(client)
    client.put("/api/v1/components/gate_demo/draft",
               json={"draft_rev": 0, "spec": _publishable_spec()})  # rev → 1
    r = _publish(client, draft_rev=0)
    assert r.status_code == 409
    body = r.json()
    assert body["code"] == 6007 and body["data"]["currentRev"] == 1


def test_publish_state_conflicts(client):
    """仅 frozen 可发布：draft 版本/不存在版本/已发布版本 → 409 COMP_STATE_CONFLICT。"""
    _make_frozen(client)  # v1 frozen，v2 draft
    r = _publish(client, version=2)
    assert r.status_code == 409 and r.json()["code"] == 6002
    r = _publish(client, version=99)
    assert r.status_code == 409 and r.json()["code"] == 6002
    assert _publish(client).status_code == 200
    r = _publish(client)  # v1 已 published，重复发布
    assert r.status_code == 409 and r.json()["code"] == 6002


def test_publish_supersedes_previous_published(client, db_session):
    """发布 v2：v1 自动转 offline 让位（既有工作流引用仍可运行，§8），主表指向 v2。"""
    _make_frozen(client)
    assert _publish(client).status_code == 200
    client.put("/api/v1/components/gate_demo/draft",
               json={"draft_rev": 0, "spec": _publishable_spec()})
    client.post("/api/v1/components/gate_demo/versions", json={})
    r = _publish(client, version=2, draft_rev=1)
    assert r.status_code == 200
    assert r.json()["data"]["supersededVersion"] == 1
    comp = db_session.query(Component).filter_by(type="gate_demo").one()
    assert comp.published_version == 2
    v1, v2 = (
        db_session.query(ComponentVersion)
        .filter_by(component_id=comp.id, version=v).one() for v in (1, 2)
    )
    assert v1.state == "offline" and v2.state == "published"


def test_publish_gate_references(client):
    """§13-8 引用完整性：prefillFromUpstream 引用不存在的字段 key → 拒。"""
    spec = dict(_publishable_spec(), dropPolicy={"prefillFromUpstream": ["ghost_key"]})
    _make_frozen(client, spec=spec)
    r = _publish(client)
    assert r.status_code == 422
    assert "ghost_key" in _gate_item(r.json(), "references")["msg"]


def test_publish_gate_no_force_bypass(client):
    """闸门不可绕过（§13 设计决策）：塞 force/豁免字段被 pydantic 丢弃，照常拦截。"""
    _make_frozen(client, execution_model="demo-only", executor=None)
    r = _publish(client, force=True, skipGates=True)
    assert r.status_code == 422 and r.json()["code"] == 6003


def test_run_publish_gates_returns_all_items_in_order():
    """闸门纯函数：六项全评估不短路，按 §13 序返回（2/3/4/5/6/8；1、7 在端点层）。"""
    from api.component_design import run_publish_gates
    comp = SimpleNamespace(type="x_demo", execution_model="demo-only",
                           executor=None, executable=True)
    items = run_publish_gates(comp, {"fields": "bad", "tpl": "${eval(x)}"},
                              catalog_types=frozenset({"x_demo"}))
    assert [i["gate"] for i in items] == [
        "pure_data", "whitelist", "drop_policy", "contract", "hash_consistency", "references"]
    by = {i["gate"]: i["ok"] for i in items}
    assert not by["pure_data"] and not by["whitelist"] and not by["contract"]
    assert not by["hash_consistency"]
    assert by["drop_policy"] and by["references"]  # 无 dropPolicy 时两项自然通过


# ---- §19.2 回归：无执行实现（demo-only）组件若尝试发布 → 闸门第 5 项强制拦截 ----
# 2026-09-29 基线化目录对账更新：M-B2 执行器注册后目录 unroutedByProfile 已清零，
# 原「从目录 stats.unroutedByProfile 实名派生」会静默缩水为 0 个用例，故 27 个
# etl/stream demo-only 实名清单（op_script 跨 profile 去重，列 26 个）改为硬编码；
# 另 3 个 dag 流节点（executor=null，C1 接线前为硬缺口）。DB 建模 type 加前缀以
# 隔离闸门第 6 项同名拦截（同名拒绝已在专门用例覆盖），execution 契约按目录原样复刻。
_GAP_DEMO = [
    # etl（16 + op_script，与 stream 共享、只列一次）
    "src_db", "src_file", "out_db", "out_file",
    "op_filter", "op_join", "op_expr", "op_agg", "op_dedup", "op_select",
    "op_sort", "op_split", "op_merge", "op_replace", "op_sample", "op_udf",
    "op_script",
    # stream（9 + op_script 共享）
    "s_kafka", "s_cdc", "p_filter", "p_join", "p_window", "op_cep",
    "o_doris", "o_kafka", "o_alert",
]
_GAP_CASES = (
    [("gap27_%s" % t, "demo-only") for t in _GAP_DEMO]
    + [("gap3_%s" % t, "dag-engine") for t in ("stream_input", "stream_fuse", "stream_output")]
)


@pytest.mark.parametrize("type_name,em", _GAP_CASES)
def test_gate30_gap_components_rejected(client, type_name, em):
    _make_frozen(client, type_name=type_name, execution_model=em, executor=None)
    r = _publish(client, type_name=type_name)
    assert r.status_code == 422, type_name
    body = r.json()
    assert body["code"] == 6003
    contract = _gate_item(body, "contract")
    assert not contract["ok"], type_name


# ---------------------------------------------------------------- D3 下线 / 回滚 / 影响面

def _offline(client, type_name="gate_demo", remark=None):
    set_role(client.app, "admin")
    payload = {"remark": remark} if remark else {}
    return client.post("/api/v1/components/%s/offline" % type_name, json=payload)


def _rollback(client, type_name="gate_demo", version=1, remark=None):
    set_role(client.app, "admin")
    payload = {"version": version}
    if remark:
        payload["remark"] = remark
    return client.post("/api/v1/components/%s/rollback" % type_name, json=payload)


def test_offline_success_keeps_published_version(client, db_session):
    """§8 published→offline：版本行随行下线；published_version 保留（R6 供给不变 →
    既有工作流引用照常通过，offline 不阻断既有流的治理语义）；审计落 offline。"""
    _make_frozen(client)
    assert _publish(client).status_code == 200
    r = _offline(client, remark="停用观察")
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {"type": "gate_demo", "state": "offline", "publishedVersion": 1}
    comp = db_session.query(Component).filter_by(type="gate_demo").one()
    assert comp.state == "offline" and comp.published_version == 1
    ver = db_session.query(ComponentVersion).filter_by(component_id=comp.id, version=1).one()
    assert ver.state == "offline" and ver.published_time
    logs = db_session.query(ComponentLog).filter_by(component_id=comp.id).all()
    assert [lg.action for lg in logs] == ["create", "freeze_version", "publish", "offline"]
    assert logs[-1].remark == "停用观察"


def test_offline_idempotent(client):
    """已 offline 再下线 → 幂等返回当前态（与工作流下线同语义）。"""
    _make_frozen(client)
    assert _publish(client).status_code == 200
    assert _offline(client).status_code == 200
    r = _offline(client)
    assert r.status_code == 200 and r.json()["data"]["state"] == "offline"


def test_offline_draft_conflict_409(client):
    """draft 组件无生效版本，下线 409 状态冲突（原 M1 无入口断言随 D3 落地作废重写）。"""
    _created(client)
    r = _offline(client, type_name="user_demo")
    assert r.status_code == 409 and r.json()["code"] == 6002


def test_offline_rbac_dev_403(client):
    """§14：下线属 publish_component（admin 独占），dev 可设计不可下线。"""
    _make_frozen(client)
    assert _publish(client).status_code == 200
    set_role(client.app, "dev")
    assert client.post("/api/v1/components/gate_demo/offline", json={}).status_code == 403


def test_rollback_reactivates_offline_version(client, db_session):
    """§8 offline→rollback→published：下线组件经回滚恢复 v1；审计落 rollback。"""
    _make_frozen(client)
    assert _publish(client).status_code == 200
    assert _offline(client).status_code == 200
    r = _rollback(client, version=1, remark="恢复上线")
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["publishedVersion"] == 1 and d["supersededVersion"] is None
    comp = db_session.query(Component).filter_by(type="gate_demo").one()
    assert comp.state == "published" and comp.published_version == 1
    ver = db_session.query(ComponentVersion).filter_by(component_id=comp.id, version=1).one()
    assert ver.state == "published"
    logs = db_session.query(ComponentLog).filter_by(component_id=comp.id).all()
    assert [lg.action for lg in logs] == [
        "create", "freeze_version", "publish", "offline", "rollback"]
    assert logs[-1].remark == "恢复上线"


def test_rollback_supersedes_current_published(client, db_session):
    """发布 v2 后回滚 v1：v2（published 行）让位 offline，v1 重新生效——降版显式留痕。"""
    _make_frozen(client)
    assert _publish(client).status_code == 200
    client.put("/api/v1/components/gate_demo/draft", json={"draft_rev": 0, "spec": _publishable_spec()})
    client.post("/api/v1/components/gate_demo/versions", json={})
    assert _publish(client, version=2, draft_rev=1).status_code == 200
    r = _rollback(client, version=1)
    assert r.status_code == 200
    assert r.json()["data"]["supersededVersion"] == 2
    comp = db_session.query(Component).filter_by(type="gate_demo").one()
    v1, v2 = (
        db_session.query(ComponentVersion)
        .filter_by(component_id=comp.id, version=v).one() for v in (1, 2)
    )
    assert v1.state == "published" and v2.state == "offline"
    assert comp.published_version == 1


def test_rollback_rejects_unpublishable_targets(client):
    """回滚目标必须「曾发布后下线」：frozen 行 / 不存在版本 → 409。"""
    _make_frozen(client)  # v1 frozen（从未发布）
    assert _rollback(client, version=1).status_code == 409
    assert _rollback(client, version=99).status_code == 409


def test_rollback_rbac_dev_403(client):
    _make_frozen(client)
    assert _publish(client).status_code == 200
    assert _offline(client).status_code == 200
    set_role(client.app, "dev")
    r = client.post("/api/v1/components/gate_demo/rollback", json={"version": 1})
    assert r.status_code == 403


def _insert_wf(db_session, wf_id: str, code: int, doc: dict, release_state: str = "offline") -> None:
    """直插工作流定义行（原生 SQL：模型模块分裂坑见 B5 注记；NOT NULL 列显式给值）。"""
    db_session.execute(text(
        "INSERT INTO t_wf_definition (id, code, name, version, release_state, flag,"
        " project_code, graph_json, create_time, update_time)"
        " VALUES (:id, :code, :name, 1, :rs, 'yes', 'default', :gj,"
        " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"),
        {"id": wf_id, "code": code, "name": wf_id, "rs": release_state,
         "gj": json.dumps(doc, ensure_ascii=False)})
    db_session.commit()
    db_session.expire_all()


def _node(ntype: str, version: int, nid: str = "n1") -> dict:
    return {"id": nid, "type": ntype, "data": {"componentRef": {"type": ntype, "version": version}}}


def test_impacted_lists_referencing_workflows(client, db_session):
    """§9.4 影响面：按 componentRef.type 命中清单 + behind/aligned 标记；不引用不计入。"""
    _make_frozen(client)
    assert _publish(client, version=1).status_code == 200  # published v1
    _insert_wf(db_session, "wf_a", 101, {"nodes": [_node("gate_demo", 1), _node("other_x", 1, "n2")]})
    _insert_wf(db_session, "wf_b", 102, {"nodes": [_node("gate_demo", 2)]})   # 引用超前 v2
    _insert_wf(db_session, "wf_c", 103, {"nodes": [_node("other_x", 1)]})     # 不引用
    _insert_wf(db_session, "wf_d", 104, {"nodes": []})                        # 空文档
    r = client.get("/api/v1/components/gate_demo/impacted")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["type"] == "gate_demo" and d["publishedVersion"] == 1 and d["state"] == "published"
    rows = {i["id"]: i for i in d["items"]}
    assert set(rows) == {"wf_a", "wf_b"}
    a, b = rows["wf_a"], rows["wf_b"]
    assert a["refVersions"] == [1] and a["aligned"] is True and a["behind"] is False
    assert b["refVersions"] == [2] and b["aligned"] is False and b["behind"] is False
    assert a["code"] == 101 and a["releaseState"] == "offline" and a["version"] == 1


def test_impacted_behind_marks_upgrade_targets(client, db_session):
    """组件升版后引用旧版本的工作流标记 behind=True（批量升级向导目标集，§9.3）。"""
    _make_frozen(client)
    assert _publish(client, version=1).status_code == 200
    _insert_wf(db_session, "wf_old", 201, {"nodes": [_node("gate_demo", 1)]})
    client.put("/api/v1/components/gate_demo/draft", json={"draft_rev": 0, "spec": _publishable_spec()})
    client.post("/api/v1/components/gate_demo/versions", json={})
    assert _publish(client, version=2, draft_rev=1).status_code == 200
    d = client.get("/api/v1/components/gate_demo/impacted").json()["data"]
    assert d["items"][0]["behind"] is True and d["items"][0]["aligned"] is False
    # 排序：behind 在前（向导目标集置顶）
    assert d["items"][0]["id"] == "wf_old"


def test_impacted_after_offline_still_visible(client, db_session):
    """组件下线后影响面照常可查（published_version 保留，下线前评估 §9.4）。"""
    _make_frozen(client)
    assert _publish(client).status_code == 200
    _insert_wf(db_session, "wf_x", 301, {"nodes": [_node("gate_demo", 1)]})
    assert _offline(client).status_code == 200
    d = client.get("/api/v1/components/gate_demo/impacted").json()["data"]
    assert d["state"] == "offline" and d["publishedVersion"] == 1
    assert len(d["items"]) == 1


def test_impacted_unknown_type_404(client):
    assert client.get("/api/v1/components/__nope__/impacted").status_code == 404


def test_registry_lists_governance_rows(client, db_session):
    """M2 registry：t_component 全量轻量清单（画布序列化注入 version 供给 + 目录页生命周期标签）。"""
    _make_frozen(client)
    assert _publish(client).status_code == 200
    r = client.get("/api/v1/components/registry")
    assert r.status_code == 200
    rows = {i["type"]: i for i in r.json()["data"]["items"]}
    assert "gate_demo" in rows
    row = rows["gate_demo"]
    assert row["state"] == "published" and row["publishedVersion"] == 1
    assert row["scope"] == "user" and row["executionModel"] == "dag-engine"
    assert "spec" not in row and "fields" not in row  # 轻量：不暴露声明全文
