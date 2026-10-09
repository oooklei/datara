"""升级策略三档 + upgrade-refs 批量端点单测（实施计划 Task 15，方案 §4.3/§4.4）。

覆盖：
1. auto（patch/minor）：发布即扫 graph_json 注入新版本（复用既有 _refresh_refs），
   响应 data.refs_refreshed 计数、引用版本对齐 published；
2. pin：落后引用处写 pinned=true 且版本不自动升（graph_json 中 componentRef.version 保持旧版）；
3. manual：只记录待升级清单（t_component_log，action=upgrade_strategy，供 P1 批量升级向导消费），不改图；
4. 钉住即不自动升级（§4.4）：pin 后再以 auto 发布，pinned 引用不被 bump；
5. POST /{type}/upgrade-refs 批量（自动档）：逐 wf 读图注入新版本，base_version 乐观锁
   （CAS 条件更新对齐 save_definition I12-M1），失败项 {"ok": false, "reason": ...} 不中断其余目标；
   批量决策落 t_component_log（action=upgrade_refs）。

DB：sqlite 内存库（conftest compiles 补丁），零外部依赖；发布链 fixture 套路同
test_publish_breaking_change.py（建组件→冻结→发布→draft 自愈→保存→冻结→发布）；
工作流图经 API 建档后由同一会话直改 graph_json 灌入存量形态（身份映射同源，无陈旧读）。
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import text

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from api.auth import get_current_user  # noqa: E402
from common.models import Component, ComponentLog, WfDefinition  # noqa: E402

COMP = "upg_demo"


def set_role(app, role: str) -> None:
    """切换注入用户角色（发布由 admin 独占；与 conftest.set_role 同实现）。"""
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, user_name="tester", user_role=role)


def _spec(keys, required=False, **extra) -> dict:
    """可通过全部八项闸门的最小声明（minor 变更 = 追加可选字段）。"""
    return {"fields": [{"key": k, "label": k.upper(), "uiType": "text",
                        "required": required} for k in keys], **extra}


def _make_published_v1(client, type_name=COMP) -> None:
    """建组件 → 冻结 v1 → 发布 v1（首发布无 old spec，闸门不介入）。"""
    r = client.post("/api/v1/components", json={
        "type": type_name, "name": type_name, "profile": "dag",
        "execution_model": "dag-engine", "executor": "sql", "executable": True,
        "spec": _spec(["sql", "table"]),
    })
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/components/%s/versions" % type_name, json={})
    assert r.status_code == 200, r.text
    set_role(client.app, "admin")
    r = client.post("/api/v1/components/%s/publish" % type_name,
                    json={"version": 1, "draft_rev": 0})
    assert r.status_code == 200, r.text


def _publish_minor(client, type_name, keys, **extra):
    """draft 自愈开修订 → 保存 minor 新 spec（追加可选字段）→ 冻结 → 发布，返回发布响应。"""
    d = client.get("/api/v1/components/%s/draft" % type_name).json()["data"]
    r = client.put("/api/v1/components/%s/draft" % type_name,
                   json={"draft_rev": d["draftRev"], "spec": _spec(keys)})
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/components/%s/versions" % type_name, json={})
    assert r.status_code == 200, r.text
    fr = r.json()["data"]
    return client.post("/api/v1/components/%s/publish" % type_name,
                       json={"version": fr["frozenVersion"],
                             "draft_rev": fr["draftRev"], **extra})


def _seed_wf(client, db_session, name: str, ref_version: int, wf_id_hint: str) -> str:
    """API 建工作流 → 同会话直改 graph_json 灌入含 componentRef 的存量形态图，返回工作流 id。

    （经 ORM 赋值而非裸 SQL：client 的 get_db 依赖覆盖即 db_session，身份映射同源，
    端点后续 ORM 查询读到的一定是灌入后的图。）
    """
    r = client.post("/api/v1/workflow-definitions", json={"name": name})
    assert r.status_code == 200, r.text
    wf_id = r.json()["data"]["id"]
    doc = {"id": wf_id, "name": name, "version": 1, "nodes": [
        {"id": wf_id_hint, "type": COMP,
         "data": {"sql": "select 1",
                  "componentRef": {"type": COMP, "version": ref_version}}}], "edges": []}
    row = db_session.query(WfDefinition).filter_by(id=wf_id).one()
    row.graph_json = json.dumps(doc, ensure_ascii=False)
    db_session.commit()
    return wf_id


def _graph_of(db_session, wf_id: str) -> dict:
    """裸 SQL 读回 graph_json（绕过身份映射，CAS 条件更新后断言不失真）。"""
    row = db_session.execute(
        text("SELECT graph_json FROM t_wf_definition WHERE id = :i"), {"i": wf_id}).fetchone()
    return json.loads(row[0])


def _ref_of(db_session, wf_id: str) -> dict:
    return _graph_of(db_session, wf_id)["nodes"][0]["data"]["componentRef"]


# ---------------------------------------------------------------- publish 三档策略


def test_publish_auto_strategy_bumps_refs(client, db_session):
    """auto（patch/minor）：发布即扫 graph_json 注入新版本（扩展现有 _refresh_refs）。"""
    _make_published_v1(client)
    wf_a = _seed_wf(client, db_session, "自动A", 1, "n_auto")
    set_role(client.app, "admin")
    r = _publish_minor(client, COMP, ["sql", "table", "extra"], upgrade_strategy="auto")
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["refs_refreshed"] >= 1
    assert body["refresh"]["refreshed"] == body["refs_refreshed"]  # 兼容旧 refresh 载荷
    assert _ref_of(db_session, wf_a)["version"] == 2  # 落后引用已注入 published v2


def test_publish_pin_strategy_pins_refs(client, db_session):
    """pin：引用处写入 pinned=true，版本不自动升（componentRef.version 保持 v1）。"""
    _make_published_v1(client)
    wf_a = _seed_wf(client, db_session, "钉住A", 1, "n_pin")
    set_role(client.app, "admin")
    r = _publish_minor(client, COMP, ["sql", "table", "extra"], upgrade_strategy="pin")
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["pinned"] >= 1
    ref = _ref_of(db_session, wf_a)
    assert ref["version"] == 1  # 版本不自动升
    assert ref["pinned"] is True
    # 决策落 t_component_log（action=upgrade_strategy；v1 首发布默认 auto 也有审计，按版本过滤）
    comp = db_session.query(Component).filter_by(type=COMP).one()
    logs = db_session.query(ComponentLog).filter_by(
        component_id=comp.id, action="upgrade_strategy", version=2).all()
    assert len(logs) == 1
    decision = json.loads(logs[0].remark)
    assert decision["strategy"] == "pin" and decision["pinned"] >= 1


def test_publish_manual_strategy_records_pending_only(client, db_session):
    """manual：只记录待升级清单（t_component_log），不改任何图。"""
    _make_published_v1(client)
    wf_a = _seed_wf(client, db_session, "手工A", 1, "n_man")
    set_role(client.app, "admin")
    r = _publish_minor(client, COMP, ["sql", "table", "extra"], upgrade_strategy="manual")
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["manual_pending"] >= 1
    ref = _ref_of(db_session, wf_a)
    assert ref["version"] == 1 and "pinned" not in ref  # 图未动
    # 待升级清单随策略决策落 t_component_log（供 P1 批量升级向导消费；按 v2 发布过滤）
    comp = db_session.query(Component).filter_by(type=COMP).one()
    logs = db_session.query(ComponentLog).filter_by(
        component_id=comp.id, action="upgrade_strategy", version=2).all()
    assert len(logs) == 1
    decision = json.loads(logs[0].remark)
    assert decision["strategy"] == "manual" and decision["pending"] >= 1
    assert any(it["wfId"] == wf_a for it in decision["items"])


def test_pinned_ref_not_bumped_by_next_auto_publish(client, db_session):
    """§4.4 钉住即不自动升级：pin 后再以 auto 发布，pinned 引用不被 bump。"""
    _make_published_v1(client)
    wf_a = _seed_wf(client, db_session, "钉住A", 1, "n_pin")
    set_role(client.app, "admin")
    r = _publish_minor(client, COMP, ["sql", "table", "extra"], upgrade_strategy="pin")
    assert r.status_code == 200, r.text
    # 第二次 minor 发布走 auto：pinned 引用保持 v1 不升
    r = _publish_minor(client, COMP, ["sql", "table", "extra", "more"], upgrade_strategy="auto")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["refs_refreshed"] == 0
    ref = _ref_of(db_session, wf_a)
    assert ref["version"] == 1 and ref["pinned"] is True


# ---------------------------------------------------------------- upgrade-refs 批量端点


def test_upgrade_refs_batch(client, db_session):
    """批量自动档：逐 wf 注入新版本（含 base_version CAS 成功路径），逐项返回结果。"""
    _make_published_v1(client)
    wf_a = _seed_wf(client, db_session, "批量A", 1, "n_a")
    wf_b = _seed_wf(client, db_session, "批量B", 1, "n_b")
    set_role(client.app, "admin")
    # manual 发布留下落后引用（不自动 bump）
    assert _publish_minor(client, COMP, ["sql", "table", "extra"],
                          upgrade_strategy="manual").status_code == 200
    r = client.post("/api/v1/components/%s/upgrade-refs" % COMP, json={"targets": [
        {"wf_id": wf_a, "strategy": "auto"},
        {"wf_id": wf_b, "strategy": "auto", "base_version": 1},  # CAS 命中路径
    ]})
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert {x["wfId"] for x in body["results"]} == {wf_a, wf_b}
    assert all(x["ok"] for x in body["results"])
    assert all(x["newVersion"] == 2 for x in body["results"])
    assert _ref_of(db_session, wf_a)["version"] == 2
    assert _ref_of(db_session, wf_b)["version"] == 2
    # 批量决策落 t_component_log（action=upgrade_refs）
    comp = db_session.query(Component).filter_by(type=COMP).one()
    logs = db_session.query(ComponentLog).filter_by(
        component_id=comp.id, action="upgrade_refs").all()
    assert len(logs) == 1


def test_upgrade_refs_persists_mapping_or_explicit_skip(client, db_session):
    """升级决策必须随引用持久化：字段映射与明确跳过可在后续审计/运行中区分。"""
    _make_published_v1(client)
    wf_map = _seed_wf(client, db_session, "映射升级", 1, "n_map")
    wf_skip = _seed_wf(client, db_session, "跳过迁移", 1, "n_skip")
    set_role(client.app, "admin")
    assert _publish_minor(client, COMP, ["sql", "table", "extra"],
                          upgrade_strategy="manual").status_code == 200

    r = client.post("/api/v1/components/%s/upgrade-refs" % COMP, json={"targets": [
        {"wf_id": wf_map, "base_version": 1,
         "field_mapping": {"old_table": "source_table"}},
        {"wf_id": wf_skip, "base_version": 1, "migration": "skip"},
    ]})

    assert r.status_code == 200, r.text
    results = {item["wfId"]: item for item in r.json()["data"]["results"]}
    assert results[wf_map]["migration"] == "map"
    assert results[wf_skip]["migration"] == "skip"
    assert _ref_of(db_session, wf_map) == {
        "type": COMP, "version": 2, "fieldMapping": {"old_table": "source_table"},
    }
    assert _ref_of(db_session, wf_skip) == {
        "type": COMP, "version": 2, "migration": "skip",
    }


def test_upgrade_refs_failure_isolated(client, db_session):
    """失败项不中断：不存在 / CAS 冲突 → ok=false + reason，其余目标照常注入。"""
    _make_published_v1(client)
    wf_a = _seed_wf(client, db_session, "隔离A", 1, "n_a")
    wf_b = _seed_wf(client, db_session, "隔离B", 1, "n_b")
    set_role(client.app, "admin")
    assert _publish_minor(client, COMP, ["sql", "table", "extra"],
                          upgrade_strategy="manual").status_code == 200
    r = client.post("/api/v1/components/%s/upgrade-refs" % COMP, json={"targets": [
        {"wf_id": wf_a, "strategy": "auto"},
        {"wf_id": "wf_missing", "strategy": "auto"},              # 工作流不存在
        {"wf_id": wf_b, "strategy": "auto", "base_version": 99},  # 乐观锁冲突
    ]})
    assert r.status_code == 200, r.text
    res = {x["wfId"]: x for x in r.json()["data"]["results"]}
    assert res[wf_a]["ok"] is True and res[wf_a]["newVersion"] == 2
    assert res["wf_missing"]["ok"] is False and res["wf_missing"]["reason"]
    assert res[wf_b]["ok"] is False and res[wf_b]["reason"]
    # 不中断：wf_a 已注入 v2；wf_b 图未动
    assert _ref_of(db_session, wf_a)["version"] == 2
    assert _ref_of(db_session, wf_b)["version"] == 1


def test_upgrade_refs_pin_target_keeps_version(client, db_session):
    """批量 pin 项：只写 pinned=true 不注入版本（逐目标策略分派）。"""
    _make_published_v1(client)
    wf_a = _seed_wf(client, db_session, "批钉A", 1, "n_a")
    set_role(client.app, "admin")
    assert _publish_minor(client, COMP, ["sql", "table", "extra"],
                          upgrade_strategy="manual").status_code == 200
    r = client.post("/api/v1/components/%s/upgrade-refs" % COMP,
                    json={"targets": [{"wf_id": wf_a, "strategy": "pin"}]})
    assert r.status_code == 200, r.text
    item = r.json()["data"]["results"][0]
    assert item["ok"] is True and item["newVersion"] is None
    ref = _ref_of(db_session, wf_a)
    assert ref["version"] == 1 and ref["pinned"] is True


def test_upgrade_refs_requires_published(client):
    """未发布组件（无 published 版本可注入）→ 409/6002 状态机拦截。"""
    set_role(client.app, "admin")
    client.post("/api/v1/components", json={
        "type": "upg_draft_only", "name": "草稿组件", "profile": "dag",
        "execution_model": "dag-engine", "executor": "sql", "executable": True,
        "spec": _spec(["sql"]),
    })
    r = client.post("/api/v1/components/upg_draft_only/upgrade-refs",
                    json={"targets": [{"wf_id": "wf_x", "strategy": "auto"}]})
    assert r.status_code == 409 and r.json()["code"] == 6002  # COMP_STATE_CONFLICT


# ---------------------------------------------------------------- 审查修复回归（Major-2/3）


def test_upgrade_refs_infra_exception_isolated(client, db_session, monkeypatch):
    """Major-2 逐项异常隔离：单目标写路径抛基础设施异常 → 该项 ok:false 不 500，
    其余目标照常成功落库（逐目标 commit，异常项 rollback 不拖垮同批）。"""
    import api.component_design as cd_mod

    _make_published_v1(client)
    wf_a = _seed_wf(client, db_session, "异常A", 1, "n_a")
    wf_b = _seed_wf(client, db_session, "异常B", 1, "n_b")
    set_role(client.app, "admin")
    assert _publish_minor(client, COMP, ["sql", "table", "extra"],
                          upgrade_strategy="manual").status_code == 200

    real_log = cd_mod.WfDefinitionLog
    state = {"n": 0}

    def boom_once(*args, **kwargs):
        """日志写路径替身：仅首次构造抛异常（模拟 wf_a 的 DB 约束/连接故障），
        其余调用透传真实类——wf_b 必须照常落库。"""
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("db boom")
        return real_log(*args, **kwargs)

    monkeypatch.setattr(cd_mod, "WfDefinitionLog", boom_once)
    r = client.post("/api/v1/components/%s/upgrade-refs" % COMP, json={"targets": [
        {"wf_id": wf_a, "strategy": "auto"},   # 写日志抛异常
        {"wf_id": wf_b, "strategy": "auto"},   # 异常后的目标必须照常成功
    ]})
    monkeypatch.undo()
    assert r.status_code == 200, r.text
    res = {x["wfId"]: x for x in r.json()["data"]["results"]}
    assert res[wf_a]["ok"] is False and "处理异常" in res[wf_a]["reason"]
    assert res[wf_b]["ok"] is True and res[wf_b]["newVersion"] == 2
    # 异常项回滚（图未动）；异常后的目标已持久（裸 SQL 读回，绕过身份映射）
    assert _ref_of(db_session, wf_a)["version"] == 1
    assert _ref_of(db_session, wf_b)["version"] == 2


def test_upgrade_refs_dedup_targets(client, db_session):
    """Major-3 目标去重：同一 wf_id 重复出现 → results 与 targets 一一对应，
    重复项标注原因不重复处理（图只 bump 一次，version=2 而非 3）。"""
    _make_published_v1(client)
    wf_a = _seed_wf(client, db_session, "重复A", 1, "n_a")
    set_role(client.app, "admin")
    assert _publish_minor(client, COMP, ["sql", "table", "extra"],
                          upgrade_strategy="manual").status_code == 200
    r = client.post("/api/v1/components/%s/upgrade-refs" % COMP, json={"targets": [
        {"wf_id": wf_a, "strategy": "auto"},
        {"wf_id": wf_a, "strategy": "auto"},  # 重复目标
    ]})
    assert r.status_code == 200, r.text
    results = r.json()["data"]["results"]
    assert len(results) == 2
    assert results[0]["ok"] is True and results[0]["newVersion"] == 2
    assert results[1]["ok"] is False and "重复" in results[1]["reason"]
    # 首个生效且只 bump 一次（裸 SQL 读回：非 CAS 直写路径不连 bump 两次）
    assert _ref_of(db_session, wf_a)["version"] == 2
