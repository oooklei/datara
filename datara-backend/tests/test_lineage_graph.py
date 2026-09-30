"""GET /lineage/graph 血缘图聚合契约测试（Task 4）。

覆盖：
1. 空库空图；2. design+runtime 同表对聚合（sources 双值去重 + refs 多实例去重）；
3. source 筛选；4. wfCode 过滤；5. 中心表扩散 direction/depth；6. limit 截断
（扩散 + 全图两形态）；7. 环图不进环；8. field 级边带 transform + 表部匹配；
9. file: 边 _bare 特判（不误剥路径、输出保留原值）；10. tmpFlag 节点聚合 + opaque 重算。

造数：design 行走真实 API（保存含 sql 节点的工作流，同 test_wf_design_lineage）；
runtime 行/独立定义直插 sqlite（conftest 内存库），零外部依赖。
"""

import json

from api.lineage import _bare  # noqa: E402
from common.models import LineageEdge, LineageField, WfDefinition  # noqa: E402


# ---------------- 夹具 ----------------

def _mk_wf(client, name="血缘图wf"):
    r = client.post("/api/v1/workflow-definitions", json={"name": name})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    data["name"] = name  # create 响应不含 name，save doc 需要
    return data


def _sql_node(nid, sql, datasource="dw"):
    return {"id": nid, "type": "sql", "data": {"datasource": datasource, "sql": sql}}


def _save(client, wf, nodes):
    doc = {"id": wf["id"], "name": wf["name"], "nodes": nodes, "edges": []}
    r = client.put("/api/v1/workflow-definitions/%s/save" % wf["id"], json={"doc": doc})
    assert r.status_code == 200, r.text


def _rt_edge(db, wf_code, frm, to, node_id="r1", stmt_no=1, tmp=False,
             instance="inst-1", fields=()):
    """直插 runtime 血缘边（+可选字段行），src_type 默认 runtime。"""
    edge = LineageEdge(wf_code=wf_code, wf_name="rt", instance_id=instance,
                       node_id=node_id, stmt_no=stmt_no, from_table=frm, to_table=to,
                       tmp_flag=tmp, src_type="runtime")
    db.add(edge)
    db.flush()
    for ft, ff, tf, tr in fields:
        db.add(LineageField(edge_id=edge.id, from_table=ft, from_field=ff,
                            to_field=tf, transform=tr, src_type="runtime"))
    db.flush()
    return edge


def _graph(client, **params):
    r = client.get("/api/v1/lineage/graph", params=params)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _fqs(d):
    return {n["fq"] for n in d["nodes"]}


# ---------------- 空库空图 ----------------

def test_graph_empty_db(client):
    assert _graph(client) == {"nodes": [], "edges": [], "opaques": [], "truncated": False}


# ---------------- design+runtime 同表对聚合 ----------------

def test_graph_design_runtime_same_pair_dedup_sources(client, db_session):
    wf = _mk_wf(client, "双源聚合")
    _save(client, wf, [_sql_node("n1", "INSERT INTO dw.t SELECT x FROM ods.a")])
    _rt_edge(db_session, wf["code"], "ods.a", "dw.t", node_id="r1")
    # 同节点同语句整体重跑（新实例号）→ refs 仍按 (wf,node,stmt) 去重
    _rt_edge(db_session, wf["code"], "ods.a", "dw.t", node_id="r1", instance="inst-2")

    d = _graph(client)
    assert len(d["edges"]) == 1, "同 (from,to) 聚合为一条边"
    e = d["edges"][0]
    assert (e["from"], e["to"], e["level"]) == ("ods.a", "dw.t", "table")
    assert e["sources"] == ["design", "runtime"], "src_type 去重双值"
    assert {(r["wfCode"], r["nodeId"], r["stmtNo"]) for r in e["refs"]} == {
        (wf["code"], "n1", 1), (wf["code"], "r1", 1)}
    assert all(set(r) == {"wfCode", "nodeId", "stmtNo"} for r in e["refs"])

    nodes = {n["fq"]: n for n in d["nodes"]}
    assert set(nodes) == {"ods.a", "dw.t"}
    assert nodes["ods.a"]["sources"] == ["design", "runtime"]
    assert nodes["ods.a"]["wfs"] == [wf["code"]]
    assert nodes["dw.t"]["ds"] == "dw" and nodes["dw.t"]["table"] == "t"


# ---------------- source 筛选 ----------------

def test_graph_source_filter(client, db_session):
    wf = _mk_wf(client, "源筛选")
    _save(client, wf, [_sql_node("n1", "INSERT INTO dw.t SELECT x FROM ods.a")])
    _rt_edge(db_session, wf["code"], "rt.b", "dw.t2")

    d = _graph(client, source="design")
    assert [(e["from"], e["to"]) for e in d["edges"]] == [("ods.a", "dw.t")]
    assert all(e["sources"] == ["design"] for e in d["edges"])
    d = _graph(client, source="runtime")
    assert [(e["from"], e["to"]) for e in d["edges"]] == [("rt.b", "dw.t2")]


# ---------------- wfCode 过滤 ----------------

def test_graph_wfcode_filter(client):
    wf1 = _mk_wf(client, "过滤A")
    _save(client, wf1, [_sql_node("n1", "INSERT INTO dw.t1 SELECT x FROM ods.a1")])
    wf2 = _mk_wf(client, "过滤B")
    _save(client, wf2, [_sql_node("n1", "INSERT INTO dw.t2 SELECT x FROM ods.a2")])

    d = _graph(client, wfCode=wf1["code"])
    assert [(e["from"], e["to"]) for e in d["edges"]] == [("ods.a1", "dw.t1")]
    assert all(n["wfs"] == [wf1["code"]] for n in d["nodes"])
    assert {r["wfCode"] for e in d["edges"] for r in e["refs"]} == {wf1["code"]}


# ---------------- 中心表扩散：direction / depth / 裸表名匹配 ----------------

def _chain_wf(client, name, hops):
    """单 wf 内 h 跳链：dw.c0 → dw.c1 → ... → dw.c{h}。"""
    wf = _mk_wf(client, name)
    nodes = [_sql_node("n%d" % i, "INSERT INTO dw.c%d SELECT x FROM dw.c%d" % (i, i - 1))
             for i in range(1, hops + 1)]
    _save(client, wf, nodes)


def test_graph_diffusion_direction_and_depth(client):
    _chain_wf(client, "扩散链", 3)

    d = _graph(client, table="dw.c1")
    assert _fqs(d) == {"dw.c0", "dw.c1", "dw.c2", "dw.c3"}
    assert d["truncated"] is False

    d = _graph(client, table="c1", direction="upstream")  # 裸表名精确匹配
    assert _fqs(d) == {"dw.c0", "dw.c1"}

    d = _graph(client, table="c1", direction="downstream")
    assert _fqs(d) == {"dw.c1", "dw.c2", "dw.c3"}

    d = _graph(client, table="dw.c1", depth=1)
    assert _fqs(d) == {"dw.c0", "dw.c1", "dw.c2"}, "depth=1 只扩一跳"


def test_graph_diffusion_diamond_converge(client):
    """菱形拓扑 A→B、A→C、B→D、C→D：both 从 A 扩散收敛 D，visited/边无重复。"""
    wf = _mk_wf(client, "菱形拓扑")
    _save(client, wf, [
        _sql_node("n1", "INSERT INTO dw.B SELECT x FROM dw.A"),
        _sql_node("n2", "INSERT INTO dw.C SELECT x FROM dw.A"),
        _sql_node("n3", "INSERT INTO dw.D SELECT x FROM dw.B"),
        _sql_node("n4", "INSERT INTO dw.D SELECT x FROM dw.C"),
    ])
    d = _graph(client, table="dw.A", direction="both")
    assert _fqs(d) == {"dw.A", "dw.B", "dw.C", "dw.D"}, "分叉经 B/C 汇聚到 D"
    assert d["truncated"] is False
    pairs = [(e["from"], e["to"]) for e in d["edges"]]
    assert len(pairs) == 4 and len(set(pairs)) == 4, "汇聚点 visited 防重，聚边不重复"


def test_graph_seeds_over_limit_truncated(client):
    """中心表多 seed 命中（field 级宽表逐字段）超 limit：seed 截断并置 truncated。"""
    wf = _mk_wf(client, "宽表多seed")
    _save(client, wf, [
        _sql_node("n1", "INSERT INTO dw.w SELECT a AS f1, b AS f2, c AS f3 FROM ods.src")])
    d = _graph(client, level="field", table="dw.w", limit=2)
    assert d["truncated"] is True and len(d["nodes"]) == 2


# ---------------- limit 截断（扩散 + 全图） ----------------

def test_graph_limit_truncated_diffusion(client):
    _chain_wf(client, "扩散截断", 4)  # c0→c1→c2→c3→c4
    d = _graph(client, table="dw.c0", direction="downstream", limit=2)
    assert _fqs(d) == {"dw.c0", "dw.c1"}
    assert d["truncated"] is True
    assert [(e["from"], e["to"]) for e in d["edges"]] == [("dw.c0", "dw.c1")]


def test_graph_limit_truncated_full_graph(client):
    wf = _mk_wf(client, "全图截断")
    _save(client, wf, [
        _sql_node("n1", "INSERT INTO dw.b1 SELECT x FROM dw.a1"),
        _sql_node("n2", "INSERT INTO dw.b2 SELECT x FROM dw.a2"),
        _sql_node("n3", "INSERT INTO dw.b3 SELECT x FROM dw.a3"),
    ])
    d = _graph(client, limit=4)
    assert len(d["nodes"]) == 4 and d["truncated"] is True
    kept = _fqs(d)
    assert all(e["from"] in kept and e["to"] in kept for e in d["edges"]), \
        "被截断节点的悬空边一并剔除"


# ---------------- 环图不进环 ----------------

def test_graph_cycle_no_revisit(client):
    wf = _mk_wf(client, "环图")
    _save(client, wf, [
        _sql_node("n1", "INSERT INTO dw.b SELECT x FROM dw.a"),
        _sql_node("n2", "INSERT INTO dw.c SELECT x FROM dw.b"),
        _sql_node("n3", "INSERT INTO dw.a SELECT x FROM dw.c"),
    ])
    d = _graph(client, table="dw.a")
    assert _fqs(d) == {"dw.a", "dw.b", "dw.c"}, "visited 防环，不重入不爆炸"
    assert len(d["edges"]) == 3 and d["truncated"] is False


# ---------------- field 级边带 transform ----------------

def test_graph_field_level_transform(client):
    wf = _mk_wf(client, "字段级")
    _save(client, wf, [
        _sql_node("n1", "INSERT INTO dw.t SELECT o.amount * 0.9 AS amt FROM ods.orders o")])

    d = _graph(client, level="field")
    assert len(d["edges"]) == 1
    e = d["edges"][0]
    assert (e["from"], e["to"], e["level"]) == ("ods.orders.amount", "dw.t.amt", "field")
    assert e["sources"] == ["design"]
    assert len(e["refs"]) == 1
    ref = e["refs"][0]
    assert (ref["wfCode"], ref["nodeId"], ref["stmtNo"]) == (wf["code"], "n1", 1)
    assert "0.9" in ref["transform"]
    assert _fqs(d) == {"ods.orders.amount", "dw.t.amt"}

    # 中心表按字段节点表部匹配（field 级节点名含字段段，裸表名/带前缀均可命中）
    d = _graph(client, level="field", table="dw.t")
    assert _fqs(d) == {"ods.orders.amount", "dw.t.amt"}


# ---------------- file: 边 _bare 特判 ----------------

def test_bare_file_prefix_guard():
    assert _bare("file:x/y.csv") == "file:x/y.csv", "file: 前缀路径不得按点误剥"
    assert _bare("ods.orders") == "orders"
    assert _bare("raw_txt") == "raw_txt"


def test_graph_file_edge_original_fq_and_center_match(client, db_session):
    wf = _mk_wf(client, "文件边")
    _rt_edge(db_session, wf["code"], "file:x/y.csv", "dw.t9")

    d = _graph(client)
    nodes = {n["fq"]: n for n in d["nodes"]}
    assert set(nodes) == {"file:x/y.csv", "dw.t9"}, "边端点输出保留原值不剥前缀"
    assert nodes["file:x/y.csv"]["table"] == "file:x/y.csv" and nodes["file:x/y.csv"]["ds"] == ""
    assert nodes["dw.t9"]["ds"] == "dw" and nodes["dw.t9"]["table"] == "t9"

    # 中心表匹配：全名精确 + endswith 兜底（裸路径传入）
    assert _fqs(_graph(client, table="file:x/y.csv")) == {"file:x/y.csv", "dw.t9"}
    assert _fqs(_graph(client, table="x/y.csv")) == {"file:x/y.csv", "dw.t9"}


# ---------------- tmpFlag 节点聚合 + opaque 重算 ----------------

def test_graph_tmp_flag_and_opaques(client, db_session):
    wf = _mk_wf(client, "临时表与opaque")
    _save(client, wf, [_sql_node("n1", "INSERT INTO dw.t SELECT x FROM ods.a")])
    _rt_edge(db_session, wf["code"], "ods.tmp1", "dw.h", tmp=True)
    # opaque：解析期不产边的组件（python）未落库，直插定义由查询端重算
    db_session.add(WfDefinition(
        id="wf_op", code=99001, name="py流",
        graph_json=json.dumps({"nodes": [{"id": "p1", "type": "python", "data": {}}],
                               "edges": []})))
    db_session.commit()

    d = _graph(client)
    nodes = {n["fq"]: n for n in d["nodes"]}
    assert nodes["ods.tmp1"]["tmpFlag"] == 1 and nodes["dw.h"]["tmpFlag"] == 1
    assert nodes["dw.t"]["tmpFlag"] == 0
    assert d["opaques"] == [{"wfCode": 99001, "nodeId": "p1", "type": "python"}]

    # wfCode 过滤 / 中心表扩散：opaque 随工作流范围收窄
    assert _graph(client, wfCode=wf["code"])["opaques"] == []
    assert _graph(client, table="dw.t")["opaques"] == []
