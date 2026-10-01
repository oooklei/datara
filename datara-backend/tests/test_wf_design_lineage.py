"""设计态血缘重算落库单测（Task 3）：保存/发布/删除触发 + redesign 端点。

- 夹具走真实 API（conftest sqlite 内存库），doc 节点用真实目录 type（sql/start/end，
  sql 表单项全可选 → 直接过 save 闸门；发布严格模式补 componentRef）
- 断言直查 t_lineage_edge / t_lineage_field 的 src_type='design' 行
- 旁路用例 monkeypatch api.lineage.rebuild_design_lineage（触发端经
  redesign_wf_lineage 模块内全局查名调用，补丁生效）
"""

import json
from types import SimpleNamespace

import pytest

from api.auth import get_current_user  # noqa: E402
from common.models import LineageEdge, LineageField  # noqa: E402

from sqlalchemy import text  # noqa: E402


# ---------------- 夹具 ----------------

def _set_role(client, role: str) -> None:
    client.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, user_name="tester", user_role=role)


def _mk_wf(client, name="血缘wf"):
    r = client.post("/api/v1/workflow-definitions", json={"name": name})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    data["name"] = name  # create 响应不含 name，save doc 需要
    return data


def _sql_node(nid, sql, datasource="dw", ref=None):
    data = {"datasource": datasource, "sql": sql}
    if ref is not None:
        data["componentRef"] = ref
    return {"id": nid, "type": "sql", "data": data}


def _save(client, wf, nodes, edges=None):
    doc = {"id": wf["id"], "name": wf["name"], "nodes": nodes, "edges": edges or []}
    return client.put("/api/v1/workflow-definitions/%s/save" % wf["id"], json={"doc": doc})


def _design_edges(db, code):
    return (
        db.query(LineageEdge)
        .filter(LineageEdge.src_type == "design", LineageEdge.wf_code == code)
        .order_by(LineageEdge.id)
        .all()
    )


def _design_fields(db, code):
    edges = _design_edges(db, code)
    if not edges:
        return []
    return (
        db.query(LineageField)
        .filter(LineageField.edge_id.in_([e.id for e in edges]),
                LineageField.src_type == "design")
        .all()
    )


# ---------------- 保存触发：落库 ----------------

def test_save_writes_design_edges_and_fields(client, db_session):
    wf = _mk_wf(client, "血缘落库")
    r = _save(client, wf, [
        _sql_node("n1", "INSERT INTO dw.t SELECT o.amount * 0.9 AS amt FROM ods.orders o")])
    assert r.status_code == 200, r.text
    edges = _design_edges(db_session, wf["code"])
    assert [(e.from_table, e.to_table) for e in edges] == [("ods.orders", "dw.t")]
    e = edges[0]
    assert e.instance_id == "0" and e.node_id == "n1" and e.stmt_no == 1
    assert e.wf_name == "血缘落库" and not e.tmp_flag
    assert e.node_name == ""  # 夹具节点无 name，展示冗余留空
    fields = _design_fields(db_session, wf["code"])
    assert len(fields) == 1
    f = fields[0]
    assert f.edge_id == e.id
    assert (f.from_table, f.from_field, f.to_field) == ("ods.orders", "amount", "amt")
    assert "0.9" in (f.transform or "")


def test_save_control_flow_only_no_rows(client, db_session):
    """纯控制流（start/end 跳过组）不产行，保存不受影响。"""
    wf = _mk_wf(client, "纯控制流")
    r = _save(client, wf,
              [{"id": "s", "type": "start", "data": {}},
               {"id": "e", "type": "end", "data": {}}],
              edges=[{"source": "s", "target": "e"}])
    assert r.status_code == 200, r.text
    assert _design_edges(db_session, wf["code"]) == []
    assert _design_fields(db_session, wf["code"]) == []


def test_save_idempotent_replace(client, db_session):
    """重复保存：行数不翻倍、旧边被替换（delete-then-reinsert）。"""
    wf = _mk_wf(client, "幂等重算")
    node_a = _sql_node("n1", "INSERT INTO dw.a SELECT x FROM ods.a1")
    assert _save(client, wf, [node_a]).status_code == 200
    first = _design_edges(db_session, wf["code"])
    assert [(e.from_table, e.to_table) for e in first] == [("ods.a1", "dw.a")]

    assert _save(client, wf, [node_a]).status_code == 200
    db_session.expire_all()  # sqlite 删除后自增 id 复用，失效 identity map 再查
    second = _design_edges(db_session, wf["code"])
    assert len(second) == 1, "重复保存行数不得翻倍"
    assert (second[0].from_table, second[0].to_table) == ("ods.a1", "dw.a")

    # 改图再保存：旧边被新边替换（SELECT * 只产表级边）
    node_b = _sql_node("n1", "INSERT INTO dw.b SELECT * FROM ods.b1")
    assert _save(client, wf, [node_b]).status_code == 200
    db_session.expire_all()
    third = _design_edges(db_session, wf["code"])
    assert [(e.from_table, e.to_table) for e in third] == [("ods.b1", "dw.b")]
    assert _design_fields(db_session, wf["code"]) == []


# ---------------- 发布触发 ----------------

def test_publish_triggers_rebuild(client, db_session):
    wf = _mk_wf(client, "发布触发")
    node = _sql_node("n1", "INSERT INTO dw.t SELECT x FROM ods.t",
                     ref={"type": "sql", "version": 1})
    assert _save(client, wf, [node]).status_code == 200
    r = client.post("/api/v1/workflow-definitions/%s/publish" % wf["id"])
    assert r.status_code == 200, r.text
    edges = _design_edges(db_session, wf["code"])
    assert [(e.from_table, e.to_table) for e in edges] == [("ods.t", "dw.t")]


# ---------------- 回滚触发 ----------------

def test_rollback_triggers_rebuild(client, db_session):
    """回滚覆写 graph_json 语义等同保存：design 行按回滚后的图重算。"""
    wf = _mk_wf(client, "回滚重算")
    node_a = _sql_node("n1", "INSERT INTO dw.a SELECT x FROM ods.a1")
    assert _save(client, wf, [node_a]).status_code == 200  # v2：快照含 A 边
    node_b = _sql_node("n1", "INSERT INTO dw.b SELECT * FROM ods.b1")
    assert _save(client, wf, [node_b]).status_code == 200  # v3：design 行变 B
    assert [(e.from_table, e.to_table)
            for e in _design_edges(db_session, wf["code"])] == [("ods.b1", "dw.b")]

    r = client.post("/api/v1/workflow-definitions/%s/rollback" % wf["id"],
                    json={"version": 2})
    assert r.status_code == 200, r.text
    db_session.expire_all()
    edges = _design_edges(db_session, wf["code"])
    assert [(e.from_table, e.to_table) for e in edges] == [("ods.a1", "dw.a")], \
        "回滚后 design 行应回到 v2 图的 A 边"
    assert len(edges) == 1, "回滚重算不得残留 v3 的 B 边"


# ---------------- redesign 端点 ----------------

def test_redesign_permission_and_404(client):
    wf = _mk_wf(client, "重算端点")
    _set_role(client, "analyst")  # 无 design_component
    r = client.post("/api/v1/lineage/redesign/%s" % wf["code"])
    assert r.status_code == 403 and r.json()["code"] == 1004  # NO_PERM

    _set_role(client, "dev")
    r = client.post("/api/v1/lineage/redesign/999999")
    assert r.status_code == 404 and r.json()["code"] == 2001  # WF_NOT_FOUND


def test_redesign_rebuilds_from_current_doc(client, db_session):
    wf = _mk_wf(client, "按需重算")
    assert _save(client, wf, [
        _sql_node("n1", "INSERT INTO dw.a SELECT x FROM ods.a")]).status_code == 200
    # 绕过 save 直接改库内文档（原生 SQL 手法，test_graph_rules 同款），再手动重算
    new_doc = {"id": wf["id"], "name": wf["name"],
               "nodes": [_sql_node("n2", "INSERT INTO dw.c SELECT z FROM ods.c")], "edges": []}
    db_session.execute(
        text("UPDATE t_wf_definition SET graph_json = :g WHERE id = :i"),
        {"g": json.dumps(new_doc), "i": wf["id"]})
    db_session.commit()
    db_session.expire_all()

    r = client.post("/api/v1/lineage/redesign/%s" % wf["code"])
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {"tableEdges": 1, "fieldEdges": 1, "opaqueNodes": 0}
    edges = _design_edges(db_session, wf["code"])
    assert [(e.from_table, e.to_table) for e in edges] == [("ods.c", "dw.c")]
    assert edges[0].node_id == "n2"
    fields = _design_fields(db_session, wf["code"])
    assert len(fields) == 1 and fields[0].edge_id == edges[0].id
    assert (fields[0].from_table, fields[0].from_field, fields[0].to_field) == ("ods.c", "z", "z")


# ---------------- 旁路：血缘失败不阻断保存 ----------------

def test_save_bypass_on_lineage_failure(client, db_session, monkeypatch):
    import api.lineage as lineage_mod

    def boom(db, definition):
        raise RuntimeError("lineage boom")

    monkeypatch.setattr(lineage_mod, "rebuild_design_lineage", boom)
    wf = _mk_wf(client, "旁路")
    r = _save(client, wf, [_sql_node("n1", "INSERT INTO dw.t SELECT x FROM ods.t")])
    assert r.status_code == 200, r.text
    assert r.json()["data"]["version"] == 2, "保存主流程不受影响"
    assert _design_edges(db_session, wf["code"]) == [], "旁路失败零落库"


# ---------------- 删除级联清理 ----------------

def test_delete_cleans_design_rows(client, db_session):
    wf = _mk_wf(client, "删除清理")
    assert _save(client, wf, [
        _sql_node("n1", "INSERT INTO dw.t SELECT o.amount AS amt FROM ods.t o")]).status_code == 200
    assert len(_design_edges(db_session, wf["code"])) == 1
    assert len(_design_fields(db_session, wf["code"])) == 1

    r = client.delete("/api/v1/workflow-definitions/%s" % wf["id"])
    assert r.status_code == 200, r.text
    assert _design_edges(db_session, wf["code"]) == []
    assert _design_fields(db_session, wf["code"]) == [], "字段行随边级联清理"


# ---------------- 服务级：字段行无归属表级边跳过不炸 ----------------

def test_orphan_field_edge_skipped(db_session, monkeypatch):
    import api.lineage as lineage_mod

    fake = {
        "table_edges": [{"wf_code": 7, "instance_id": 0, "node_id": "n1", "stmt_no": 1,
                         "from_table": "a.t1", "to_table": "b.t2", "tmp_flag": 0,
                         "src_type": "design"}],
        "field_edges": [{"node_id": "nX", "stmt_no": 9, "to_table": "b.t2",
                         "to_field": "x", "from_table": "ghost.g",
                         "from_field": "y", "transform": "", "src_type": "design"}],
        "opaques": [],
    }
    monkeypatch.setattr(lineage_mod, "extract_wf_lineage", lambda nodes, edges, code: fake)
    definition = SimpleNamespace(
        id="wf_x", code=7, name="孤儿", graph_json=json.dumps({"nodes": [], "edges": []}))
    stats = lineage_mod.rebuild_design_lineage(db_session, definition)
    assert stats == {"tableEdges": 1, "fieldEdges": 0, "opaqueNodes": 0}
    assert len(_design_edges(db_session, 7)) == 1
    assert _design_fields(db_session, 7) == []


# ---------------- 服务级：批内 uk 去重防御 ----------------

def test_batch_internal_dedup(client, db_session):
    """同 id 重复节点产出完全相同的边 → 批内去重（uk_lineage 防御），行数不虚高。"""
    wf = _mk_wf(client, "批内去重")
    dup = _sql_node("n1", "INSERT INTO dw.t1 SELECT x FROM ods.t1")
    assert _save(client, wf, [dict(dup), dict(dup)]).status_code == 200
    edges = _design_edges(db_session, wf["code"])
    assert [(e.from_table, e.to_table) for e in edges] == [("ods.t1", "dw.t1")]


# ---------------- 部分写库失败：flush 抛错 → rollback 完整恢复旧行 ----------------

def _fake_parsed(frm, to):
    """extract_wf_lineage 替身：一条表级边 + 一条可挂靠字段行。"""
    return {
        "table_edges": [{"wf_code": 7, "instance_id": 0, "node_id": "n1", "stmt_no": 1,
                         "from_table": frm, "to_table": to, "tmp_flag": 0,
                         "src_type": "design"}],
        "field_edges": [{"node_id": "n1", "stmt_no": 1, "to_table": to,
                         "to_field": "amt", "from_table": frm,
                         "from_field": "amount", "transform": "amount",
                         "src_type": "design"}],
        "opaques": [],
    }


def _snap(db, code):
    """该 wf_code 全部 design 行内容快照（边 + 字段），供失败前后比对。"""
    return (
        [(e.from_table, e.to_table, e.node_id, e.stmt_no)
         for e in _design_edges(db, code)],
        sorted((f.to_field, f.from_table, f.from_field)
               for f in _design_fields(db, code)),
    )


def _flush_boom(session, monkeypatch):
    """flush 在存在待写新行时抛错（delete 前的 autoflush 空转透传，精准模拟落库中途失败）。"""
    real_flush = session.flush

    def flaky(*args, **kwargs):
        if session.new:
            raise RuntimeError("flush boom")
        return real_flush(*args, **kwargs)

    monkeypatch.setattr(session, "flush", flaky)


def test_rebuild_flush_failure_rolls_back_to_old_rows(db_session, monkeypatch):
    """重算中途 flush 抛错：异常上抛；rollback 后旧 design 行完整保留、无半写行
    （delete-then-reinsert 同事务语义：未提交整体作废，不丢旧图）。"""
    import api.lineage as lineage_mod

    definition = SimpleNamespace(
        id="wf_x", code=7, name="回滚", graph_json=json.dumps({"nodes": [], "edges": []}))
    monkeypatch.setattr(lineage_mod, "extract_wf_lineage",
                        lambda nodes, edges, code: _fake_parsed("ods.a1", "dw.a"))
    lineage_mod.rebuild_design_lineage(db_session, definition)
    old_snap = _snap(db_session, 7)
    assert old_snap == ([("ods.a1", "dw.a", "n1", 1)], [("amt", "ods.a1", "amount")])

    monkeypatch.setattr(lineage_mod, "extract_wf_lineage",
                        lambda nodes, edges, code: _fake_parsed("ods.b1", "dw.b"))
    _flush_boom(db_session, monkeypatch)
    with pytest.raises(RuntimeError, match="flush boom"):
        lineage_mod.rebuild_design_lineage(db_session, definition)
    db_session.rollback()

    assert _snap(db_session, 7) == old_snap, "rollback 后旧 design 行完整保留、无半写行"


def test_redesign_flush_failure_swallows_and_keeps_old_rows(db_session, monkeypatch):
    """旁路入口 redesign_wf_lineage 遇中途失败：不向调用方抛异常，rollback 后旧行保留
    （保存/发布主流程不受血缘重算失败影响）。"""
    import api.lineage as lineage_mod

    definition = SimpleNamespace(
        id="wf_x", code=7, name="旁路回滚", graph_json=json.dumps({"nodes": [], "edges": []}))
    monkeypatch.setattr(lineage_mod, "extract_wf_lineage",
                        lambda nodes, edges, code: _fake_parsed("ods.a1", "dw.a"))
    lineage_mod.rebuild_design_lineage(db_session, definition)
    old_snap = _snap(db_session, 7)

    monkeypatch.setattr(lineage_mod, "extract_wf_lineage",
                        lambda nodes, edges, code: _fake_parsed("ods.b1", "dw.b"))
    _flush_boom(db_session, monkeypatch)
    lineage_mod.redesign_wf_lineage(db_session, definition)  # 内部吞异常，不得上抛

    assert _snap(db_session, 7) == old_snap, "旁路回滚后旧 design 行完整保留"


# ---------------- field 挂靠精确键：同表对多语句/多节点各归各边 ----------------

def test_same_pair_multi_node_fields_attach_own_edges(client, db_session):
    """同 wf 两节点产同 (from,to) 表对：字段行按 (node_id,stmt_no,from,to) 精确挂靠
    各自表级边，不再全挂首边（/trace 与 graph refs 归属正确）。"""
    wf = _mk_wf(client, "同表对挂靠")
    assert _save(client, wf, [
        _sql_node("n1", "INSERT INTO dw.t SELECT x AS c1 FROM ods.s"),
        _sql_node("n2", "INSERT INTO dw.t SELECT y AS c1 FROM ods.s"),
    ]).status_code == 200
    edges = _design_edges(db_session, wf["code"])
    assert [(e.node_id, e.from_table, e.to_table) for e in edges] == [
        ("n1", "ods.s", "dw.t"), ("n2", "ods.s", "dw.t")]
    fields = _design_fields(db_session, wf["code"])
    assert len(fields) == 2
    by_edge: dict = {}
    for f in fields:
        by_edge.setdefault(f.edge_id, []).append(f)
    e1, e2 = edges
    assert {f.from_field for f in by_edge[e1.id]} == {"x"}, "n1 边只挂 n1 的字段"
    assert {f.from_field for f in by_edge[e2.id]} == {"y"}, "n2 边只挂 n2 的字段"


def test_same_pair_multi_stmt_fields_attach_own_edges(client, db_session):
    """同节点多语句产同 (from,to) 表对：字段行按 stmt_no 各归各语句边。"""
    wf = _mk_wf(client, "同表对多语句")
    assert _save(client, wf, [
        _sql_node("n1", "INSERT INTO dw.t SELECT x AS c1 FROM ods.s;"
                          " INSERT INTO dw.t SELECT y AS c1 FROM ods.s"),
    ]).status_code == 200
    edges = _design_edges(db_session, wf["code"])
    assert [(e.stmt_no, e.node_id, e.to_table) for e in edges] == [
        (1, "n1", "dw.t"), (2, "n1", "dw.t")]
    fields = _design_fields(db_session, wf["code"])
    assert len(fields) == 2
    assert len({f.edge_id for f in fields}) == 2, "字段行必须分挂两条语句边"


def test_field_pair_fallback_when_precise_key_misses(db_session, monkeypatch):
    """精确键 (node_id,stmt_no,from,to) 未命中但同表对命中 → 兜底挂靠（防孤儿跳过）。"""
    import api.lineage as lineage_mod

    fake = {
        "table_edges": [{"wf_code": 7, "instance_id": 0, "node_id": "n1", "stmt_no": 1,
                         "from_table": "a.t1", "to_table": "b.t2", "tmp_flag": 0,
                         "src_type": "design"}],
        "field_edges": [{"node_id": "nX", "stmt_no": 9, "to_table": "b.t2",
                         "to_field": "x", "from_table": "a.t1",
                         "from_field": "y", "transform": "", "src_type": "design"}],
        "opaques": [],
    }
    monkeypatch.setattr(lineage_mod, "extract_wf_lineage", lambda nodes, edges, code: fake)
    definition = SimpleNamespace(
        id="wf_x", code=7, name="兜底", graph_json=json.dumps({"nodes": [], "edges": []}))
    stats = lineage_mod.rebuild_design_lineage(db_session, definition)
    assert stats == {"tableEdges": 1, "fieldEdges": 1, "opaqueNodes": 0}
    fields = _design_fields(db_session, 7)
    assert len(fields) == 1 and fields[0].from_field == "y"
