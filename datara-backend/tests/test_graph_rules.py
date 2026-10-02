"""api/graph_rules.py 服务端图校验引擎单测（实施计划 20260926 Task A1/F4）。

以独立模块加载（tests 既有 importlib 模式），catalog 以 monkeypatch 注入受控
mini 目录——不随 dag_catalog.json 重新导出而漂移；真实快照仅做冒烟断言。
F4 R5 引用有效性：纯函数级（supply 注入）+ save/publish 端点集成（sqlite 内存库）。
"""

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_rules():
    name = "datara_test_graph_rules"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "api" / "graph_rules.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[name] = mod
    return mod


_rules = _load_rules()
validate_graph = _rules.validate_graph
_REAL_CATALOG = _rules._catalog  # 原始 lru_cache 函数（autouse fixture 替换前留存）

# 受控 mini 目录：comp_a（无条件必填 k + 条件必填 w + hint r）、comp_b（无必填）
MINI_CAT = {
    "components": [
        {"type": "comp_a", "formFields": [
            {"key": "k", "label": "必填K", "type": "text", "required": True, "hasWhen": False},
            {"key": "w", "label": "条件W", "type": "text", "required": True, "hasWhen": True},
            {"key": "r", "label": "提示R", "type": "hint", "required": True, "hasWhen": False},
        ]},
        {"type": "comp_b", "formFields": []},
    ],
    "stats": {"backendOnlyTypes": ["src_select", "tgt_select", "smoke"]},
}


@pytest.fixture(autouse=True)
def _mini_catalog(monkeypatch):
    monkeypatch.setattr(_rules, "_catalog", lambda: MINI_CAT)


def _doc(nodes, edges, wf_id="wf_x"):
    return {"id": wf_id, "nodes": nodes, "edges": edges}


def _node(nid, ntype, data=None):
    """默认注入合法 componentRef（D2 R6：publish 严格模式基线；显式传入则尊重传值）。"""
    d = dict(data or {})
    d.setdefault("componentRef", {"type": ntype, "version": 1})
    return {"id": nid, "type": ntype, "data": d}


# ---------------- R0 结构基础 ----------------

def test_r0_nodes_not_list():
    v = validate_graph({"id": "wf_x", "nodes": None, "edges": []})
    assert [x["rule"] for x in v] == ["R0"]


def test_r0_node_missing_id_or_type():
    v = validate_graph(_doc([{"id": "", "type": "comp_a"}], []))
    assert any(x["rule"] == "R0" for x in v)


# ---------------- R1 环检测 ----------------

def test_r1_cycle_detected():
    v = validate_graph(_doc(
        [_node("a", "comp_b"), _node("b", "comp_b")],
        [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}]))
    assert [x["rule"] for x in v] == ["R1"]
    assert "a" in v[0]["message"] and "b" in v[0]["message"]


def test_r1_diamond_dag_passes():
    v = validate_graph(_doc(
        [_node("a", "comp_b"), _node("b", "comp_b"), _node("c", "comp_b")],
        [{"source": "a", "target": "b"}, {"source": "a", "target": "c"}]))
    assert v == []


# ---------------- R2 类型合法性 ----------------

def test_r2_unknown_type():
    v = validate_graph(_doc([_node("a", "no_such_comp")], []))
    assert any(x["rule"] == "R2" and "no_such_comp" in x["message"] for x in v)


def test_r2_backend_only_type_allowed():
    """旧画布兼容路径（backendOnlyTypes）合法，不误伤存量文档。"""
    assert validate_graph(_doc([_node("a", "src_select")], [])) == []


def test_r2_sys_exec_materialized_exempt():
    doc = _doc([_node("sys_exec_ab12cd34", "sync")], [])
    assert [x for x in validate_graph(doc) if x["rule"] == "R2"] == []


# ---------------- R3 无条件必填 ----------------

def test_r3_missing_required():
    v = validate_graph(_doc([_node("a", "comp_a", {"w": "x"})], []))
    assert [x for x in v if x["rule"] == "R3"] == [
        {"rule": "R3", "nodeId": "a", "message": "必填项未填: 必填K"}]


def test_r3_blank_variants():
    for blank in (None, "", []):
        v = validate_graph(_doc([_node("a", "comp_a", {"k": blank})], []))
        assert any(x["rule"] == "R3" for x in v), blank


def test_r3_conditional_and_hint_skipped():
    """showIf 条件必填与 hint 类型不归服务端（边界：函数语义留前端 W1）。"""
    v = validate_graph(_doc([_node("a", "comp_a", {"k": "v"})], []))
    assert [x for x in v if x["rule"] == "R3"] == []


# ---------------- R4 悬挂边 ----------------

def test_r4_dangling_edge():
    v = validate_graph(_doc([_node("a", "comp_b")], [{"source": "a", "target": "ghost"}]))
    assert any(x["rule"] == "R4" and "ghost" in x["message"] for x in v)


# ---------------- catalog 降级 ----------------

def test_degraded_catalog_skips_r2_r3_but_keeps_r1(monkeypatch):
    monkeypatch.setattr(_rules, "_catalog", lambda: {})
    v = validate_graph(_doc(
        [_node("a", "anything"), _node("b", "anything")],
        [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}]))
    assert [x["rule"] for x in v] == ["R1"]


# ---------------- 真实快照冒烟 ----------------

def test_real_catalog_smoke(monkeypatch):
    """真实 dag_catalog.json：合法类型文档零违规；未注入 mini 时引擎可独立跑通。"""
    monkeypatch.setattr(_rules, "_catalog", _REAL_CATALOG)
    v = validate_graph(_doc(
        [_node("a", "endpoint_select", {}), _node("b", "assert", {})],
        [{"source": "a", "target": "b"}]))
    assert [x for x in v if x["rule"] == "R2"] == []
    _REAL_CATALOG.cache_clear()  # 还原缓存，避免影响其它用例


# ---------------- R5 引用有效性（Task F4） ----------------

SUPPLY = {"workflow": {"wfv_a"}, "global": {"gp_ok"}}


def test_r5_skipped_without_supply():
    """vars_supply 缺省（None）→ R5 整体跳过（A1 既有语义不回退）。"""
    v = validate_graph(_doc([_node("a", "comp_b", {"sql": "${no_such_var}"})], []))
    assert [x for x in v if x["rule"] == "R5"] == []


def test_r5_legal_refs_pass():
    """合法引用全家桶：全局参数/工作流变量/run.*/内置时间参数/date(N)/日期模式/$[wf.*]。"""
    data = {
        "sql": "select ${gp_ok}, ${wfv_a}, ${run.instanceId}, ${run.loopIter},"
               " ${biz_date}, ${ts_nodash}, ${date(3)}, ${date(-1)},"
               " ${yyyyMMdd_HHmmss}, ${yyyy-MM-dd}",
        "params": [{"key": "cnt", "value": "${cnt}"}],  # 同节点 params key 自引用合法
        "expr": "$[yyyyMMdd-1]",                        # 时间模板恒可求值，不校验
    }
    v = validate_graph(_doc([_node("a", "comp_b", data)], []), SUPPLY)
    assert [x for x in v if x["rule"] == "R5"] == []


def test_r5_unknown_var_violation():
    """未知变量逐条违规：nodeId + ${name} 精确落在消息中。"""
    data = {"sql": "select ${gp_ok}, ${no_such_var}", "path": "/x/${also_missing}"}
    v = validate_graph(_doc([_node("a", "comp_b", data)], []), SUPPLY)
    r5 = [x for x in v if x["rule"] == "R5"]
    assert sorted(x["message"] for x in r5) == [
        "引用的变量未定义: ${also_missing}",
        "引用的变量未定义: ${no_such_var}",
    ]
    assert {x["nodeId"] for x in r5} == {"a"}


def test_r5_run_vars_whitelist():
    """run.* 白名单外违规（消息含口径提示）。"""
    v = validate_graph(_doc([_node("a", "comp_b", {"sql": "${run.foo}"})], []), SUPPLY)
    r5 = [x for x in v if x["rule"] == "R5"]
    assert len(r5) == 1
    assert "${run.foo}" in r5[0]["message"] and "run.instanceId" in r5[0]["message"]


def test_r5_branches_skipped():
    """branches 键不参与占位渲染（引擎 resolve_tree skip_keys 同口径），引用不校验。"""
    data = {"branches": [{"expr": "${no_such_var} > 0"}]}
    v = validate_graph(_doc([_node("a", "comp_b", data)], []), SUPPLY)
    assert [x for x in v if x["rule"] == "R5"] == []


def test_r5_dedup_per_node():
    """同节点同名引用只报一条（去重防刷屏）；跨节点各报各的。"""
    doc = _doc([
        _node("a", "comp_b", {"sql": "${missing} ${missing}", "path": "${missing}"}),
        _node("b", "comp_b", {"sql": "${missing}"}),
    ], [])
    r5 = [x for x in validate_graph(doc, SUPPLY) if x["rule"] == "R5"]
    assert sorted(x["nodeId"] for x in r5) == ["a", "b"]


def test_r5_params_key_local_scope():
    """同节点 params key 合法（引擎 node_params 优先级最高），不依赖 supply。"""
    data = {"sql": "select ${local_k}", "params": [{"key": "local_k", "value": "1"}]}
    v = validate_graph(_doc([_node("a", "comp_b", data)], []), SUPPLY)
    assert [x for x in v if x["rule"] == "R5"] == []


def test_r5_wf_time_syntax_follows_var_chain():
    """$[wf.x] 混用语法按变量链校验（引擎 _time wf. 转发，查表用全名 wf.x 同口径）。"""
    supply_wf = {"workflow": {"wf.wfv_a"}, "global": set()}
    ok_v = validate_graph(_doc([_node("a", "comp_b", {"e": "$[wf.wfv_a]"})], []), supply_wf)
    assert [x for x in ok_v if x["rule"] == "R5"] == []
    bad_v = validate_graph(_doc([_node("a", "comp_b", {"e": "$[wf.nope]"})], []), supply_wf)
    assert [x["message"] for x in bad_v if x["rule"] == "R5"] == ["引用的变量未定义: ${wf.nope}"]


def test_r5_plain_name_not_date_pattern():
    """普通名字不误判为日期命名模式（summary 等不得因无 token 放行）。"""
    v = validate_graph(_doc([_node("a", "comp_b", {"sql": "${summary}"})], []), SUPPLY)
    assert [x for x in v if x["rule"] == "R5"]  # 必须违规


# ---------------- R6 componentRef（Task D2，治理设计 §9） ----------------

def test_r6_missing_ref_lenient_vs_strict():
    """缺 ref：save 宽松不拒（兼容存量未回填 §9.5）；publish 严格拒（§9.2 封死缺省语义）。"""
    doc = _doc([{"id": "a", "type": "comp_b", "data": {}}], [])
    assert [x for x in validate_graph(doc) if x["rule"] == "R6"] == []
    v = validate_graph(doc, require_component_ref=True)
    assert [x["rule"] for x in v] == ["R6"]
    assert "componentRef" in v[0]["message"] and v[0]["nodeId"] == "a"


def test_r6_version_banned_semantics():
    """version 禁 latest/字符串/0/null/浮点/bool（§9.2 缺省语义封死）。"""
    for ver in ("latest", "1", 0, None, 1.0, True):
        doc = _doc([_node("a", "comp_b", {"componentRef": {"type": "comp_b", "version": ver}})], [])
        v = [x for x in validate_graph(doc) if x["rule"] == "R6"]
        assert len(v) == 1 and "version" in v[0]["message"], ver


def test_r6_type_mismatch():
    """ref.type 与节点 type 不一致拒（§9.1 引用歧义封死）。"""
    doc = _doc([_node("a", "comp_b", {"componentRef": {"type": "comp_a", "version": 1}})], [])
    v = [x for x in validate_graph(doc) if x["rule"] == "R6"]
    assert len(v) == 1 and "comp_a" in v[0]["message"] and "comp_b" in v[0]["message"]


def test_r6_sys_exec_exempt_even_strict():
    """sys_exec_ 物化产物豁免（§9.6）：无 ref + 严格模式不拒（ref 由物化器注入）。"""
    doc = _doc([{"id": "sys_exec_ab12cd34", "type": "sync", "data": {}}], [])
    assert [x for x in validate_graph(doc, require_component_ref=True) if x["rule"] == "R6"] == []


def test_r6_comp_versions_gating():
    """版本存在性按 comp_versions 供给：无 published 拒发；版本漂移拒（显式升级 §9.3）；
    供给外类型仅结构校验（37 系统目录 type 不在治理库 → 永不受影响）。"""
    doc = _doc([_node("a", "comp_b")], [])

    v = [x for x in validate_graph(doc, comp_versions={"comp_b": None}) if x["rule"] == "R6"]
    assert len(v) == 1 and "无 published 版本" in v[0]["message"]

    v = [x for x in validate_graph(doc, comp_versions={"comp_b": 3}) if x["rule"] == "R6"]
    assert len(v) == 1 and "当前 published 为 v3" in v[0]["message"]

    assert [x for x in validate_graph(doc, comp_versions={"comp_b": 1}) if x["rule"] == "R6"] == []
    assert [x for x in validate_graph(doc, comp_versions={"other": 2}) if x["rule"] == "R6"] == []


# ---------------- G-21 R12 组件版本存在性（缺 ref 节点的 published 版本校验） ----------------

def _no_ref_node(nid, ntype):
    """构造缺 componentRef 的节点（R12 测试用——_node 默认注入 ref）。"""
    return {"id": nid, "type": ntype, "data": {}}


def test_r12_missing_ref_with_no_published_version_warns():
    """R12：缺 componentRef 的节点，若该 type 在 comp_versions 中无 published 版本 → R12 警告。

    save 宽松路径兼容存量未回填文档，但无 published 版本的组件其工作流不可发布
    （§8/§18.3）——R12 在 save 阶段登记留痕，R6 在 publish 阶段升级为 error 拒绝。
    """
    # comp_a 无 ref + comp_versions 中 comp_a=None（无 published）→ R12 警告
    doc = _doc([_no_ref_node("a", "comp_a")], [])
    v = [x for x in validate_graph(doc, comp_versions={"comp_a": None}) if x["rule"] == "R12"]
    assert len(v) == 1 and v[0]["rule"] == "R12" and "无 published 版本" in v[0]["message"]


def test_r12_missing_ref_with_published_version_no_warning():
    """R12：缺 ref 但组件有 published 版本 → 不触发 R12（save 宽松兼容）。"""
    doc = _doc([_no_ref_node("a", "comp_a")], [])
    v = [x for x in validate_graph(doc, comp_versions={"comp_a": 2}) if x["rule"] == "R12"]
    assert v == [], "有 published 版本时不应触发 R12"


def test_r12_ignores_template_types():
    """R12：模板类型（demo_pipeline 等）豁免——它们不走组件发布流程。"""
    doc = _doc([_no_ref_node("a", "demo_pipeline")], [])
    v = [x for x in validate_graph(doc, comp_versions={"demo_pipeline": None}) if x["rule"] == "R12"]
    assert v == [], "模板类型应豁免 R12"


def test_r12_skipped_when_comp_versions_not_supplied():
    """R12：comp_versions=None（纯函数测试无 db 上下文）→ R12 整体跳过。"""
    doc = _doc([_no_ref_node("a", "comp_a")], [])
    v = validate_graph(doc)  # comp_versions=None
    assert all(x["rule"] != "R12" for x in v), "无 comp_versions 供给时应跳过 R12"


def test_r12_with_ref_still_checked_by_r6():
    """R12 不替代 R6：有 ref 的节点走 R6 版本校验，不触发 R12。"""
    node = {"id": "a", "type": "comp_b", "data": {"componentRef": {"type": "comp_b", "version": 1}}}
    doc = _doc([node], [])
    v = [x for x in validate_graph(doc, comp_versions={"comp_b": None}) if x["rule"] in ("R6", "R12")]
    # comp_b=None + ref v1 → R6 报"无 published 版本"，不触发 R12
    assert any(x["rule"] == "R6" for x in v), "有 ref 时应走 R6"
    assert not any(x["rule"] == "R12" for x in v), "有 ref 时不应触发 R12"


def test_publish_endpoint_r6_strict(client, db_session, monkeypatch):
    """publish 严格模式端到端：缺 ref 存量文档 422(2006)；save 宽松接受合法 ref 后发布成功。"""
    _patch_real_catalog(monkeypatch)
    r = client.post("/api/v1/workflow-definitions", json={"name": "D2发布严格"})
    wf = r.json()["data"]
    save_url = "/api/v1/workflow-definitions/%s/save" % wf["id"]

    # 直接写库模拟存量未回填文档（save 会宽松放行缺 ref，故绕过 save 直写；
    # 原生 SQL 手法同 test_publish_endpoint_r5_gate——模型模块分裂免疫）
    import json as _json
    from sqlalchemy import text
    legacy = _doc([{"id": "a", "type": "comp_b", "data": {"sql": "select 1"}}], [], wf["id"])
    db_session.execute(
        text("UPDATE t_wf_definition SET graph_json = :g WHERE id = :i"),
        {"g": _json.dumps(legacy, ensure_ascii=False), "i": wf["id"]},
    )
    db_session.commit()
    db_session.expire_all()

    r = client.post("/api/v1/workflow-definitions/%s/publish" % wf["id"])
    assert r.status_code == 422
    assert r.json()["code"] == 2006 and "componentRef" in r.json()["msg"]

    # save（宽松）接受带合法 ref 的文档 → 发布（严格）通过
    assert client.put(save_url, json={"doc": _doc([_node("a", "comp_b")], [], wf["id"])}).status_code == 200
    r = client.post("/api/v1/workflow-definitions/%s/publish" % wf["id"])
    assert r.status_code == 200 and r.json()["data"]["release_state"] == "online"


def test_save_endpoint_r6_lenient_with_governed_comp(client, db_session, monkeypatch):
    """save 宽松模式对治理库组件生效：ref 版本与 published 漂移 → 422 逐条（缺 ref 仍放行）。"""
    _patch_real_catalog(monkeypatch)
    from sqlalchemy import text as _text
    r = client.post("/api/v1/workflow-definitions", json={"name": "D2保存版本"})
    wf = r.json()["data"]
    save_url = "/api/v1/workflow-definitions/%s/save" % wf["id"]
    # 治理库组件：published v2（原生 SQL 插入，模块分裂免疫；时间戳列无 SQL 默认需显式给）
    db_session.execute(_text(
        "INSERT INTO t_component (type, name, profile, scope, execution_model, executor,"
        " executable, state, published_version, draft_rev, create_time, update_time)"
        " VALUES ('comp_b', 'B组件', 'dag', 'builtin', 'dag-engine', NULL, 1, 'published', 2, 0,"
        " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
    db_session.commit()

    # 漂移：引用 v1，当前 published v2 → 拒（升级走显式升级 §9.3）
    stale = _node("a", "comp_b", {"componentRef": {"type": "comp_b", "version": 1}})
    r = client.put(save_url, json={"doc": _doc([stale], [], wf["id"])})
    assert r.status_code == 422 and r.json()["code"] == 2006
    assert "当前 published 为 v2" in r.json()["msg"]

    # 对齐 published → 放行；缺 ref（存量形态）→ 宽松放行
    good = _node("a", "comp_b", {"componentRef": {"type": "comp_b", "version": 2}})
    assert client.put(save_url, json={"doc": _doc([good], [], wf["id"])}).status_code == 200
    bare = {"id": "a", "type": "comp_b", "data": {"sql": "select 1"}}
    assert client.put(save_url, json={"doc": _doc([bare], [], wf["id"])}).status_code == 200


# ---------------- R5 端点集成（save/publish 闸门，sqlite 内存库） ----------------

def _patch_real_catalog(monkeypatch):
    import api.graph_rules as real_rules
    monkeypatch.setattr(real_rules, "_catalog", lambda: MINI_CAT)
    return real_rules


def test_save_endpoint_r5_gate(client, db_session, monkeypatch):
    """save 闸门：查库组装供给；合法引用保存成功，未知引用 422(2006) 逐条。"""
    _patch_real_catalog(monkeypatch)
    from common.models import GlobalParam, WfVariable
    r = client.post("/api/v1/workflow-definitions", json={"name": "F4引用校验"})
    assert r.status_code == 200, r.text
    wf = r.json()["data"]
    db_session.add(GlobalParam(name="gp_ok", value="1"))
    db_session.add(WfVariable(wf_code=wf["code"], name="wfv_a", value="2"))
    db_session.commit()
    save_url = "/api/v1/workflow-definitions/%s/save" % wf["id"]

    good = _node("a", "comp_b", {"sql": "select ${gp_ok}, ${wfv_a}, ${run.instanceId}"})
    r = client.put(save_url, json={"doc": _doc([good], [], wf["id"])})
    assert r.status_code == 200, r.text

    bad = _node("a", "comp_b", {"sql": "select ${no_such_var}"})
    r = client.put(save_url, json={"doc": _doc([bad], [], wf["id"])})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == 2006
    assert "${no_such_var}" in body["msg"]


def test_publish_endpoint_r5_gate(client, db_session, monkeypatch):
    """publish 闸门带供给：存量库内文档含未知引用 → 发布被拒 422（先修再发）。"""
    _patch_real_catalog(monkeypatch)
    from common.models import GlobalParam, WfVariable
    r = client.post("/api/v1/workflow-definitions", json={"name": "F4发布校验"})
    wf = r.json()["data"]
    db_session.add(WfVariable(wf_code=wf["code"], name="wfv_a", value="2"))
    db_session.add(GlobalParam(name="gp_ok", value="1"))
    db_session.commit()
    save_url = "/api/v1/workflow-definitions/%s/save" % wf["id"]
    bad = _node("a", "comp_b", {"sql": "select ${stale_var}"})
    assert client.put(save_url, json={"doc": _doc([bad], [], wf["id"])}).status_code == 422

    # 直接写库模拟「校验上线前已存在的坏引用文档」（绕过 save 闸门）。
    # 用原生 SQL：test_component_catalog 收集期 pop sys.modules['common.*'] 导致
    # 模型模块在本文件与 api 链路中各自加载（同表名不同 mapper），ORM 对象写库
    # 会绕过端点侧 identity map（expire_on_commit=False 读到旧值）；原生 SQL +
    # expire_all 对该分裂免疫。
    import json as _json
    from sqlalchemy import text
    db_session.execute(
        text("UPDATE t_wf_definition SET graph_json = :g WHERE id = :i"),
        {"g": _json.dumps(_doc([bad], [], wf["id"]), ensure_ascii=False), "i": wf["id"]},
    )
    db_session.commit()
    db_session.expire_all()

    r = client.post("/api/v1/workflow-definitions/%s/publish" % wf["id"])
    assert r.status_code == 422
    assert r.json()["code"] == 2006 and "${stale_var}" in r.json()["msg"]
    # 补上引用后发布成功
    good = _node("a", "comp_b", {"sql": "select ${gp_ok}, ${wfv_a}"})
    assert client.put(save_url, json={"doc": _doc([good], [], wf["id"])}).status_code == 200
    r = client.post("/api/v1/workflow-definitions/%s/publish" % wf["id"])
    assert r.status_code == 200 and r.json()["data"]["release_state"] == "online"
