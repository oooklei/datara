"""GET /lineage/graph 血缘图聚合契约测试（Task 4）。

覆盖：
1. 空库空图；2. design+runtime 同表对聚合（sources 双值去重 + refs 多实例去重）；
3. source 筛选；4. wfCode 过滤；5. 中心表扩散 direction/depth；6. limit 截断
（扩散 + 全图两形态）；7. 环图不进环；8. field 级边带 transform + 表部匹配；
9. file: 边 _bare 特判（不误剥路径、file: 端点原样保留）；10. tmpFlag 节点聚合 + opaque 重算；
11. 三形态聚合一（design ds-ID 前缀 / runtime ds 名前缀或裸名 → 双源命中，1.9 实测回归）；
12. 归一防误伤（字段级两形态聚合一不串行、file: 边不受归一影响）。

口径：聚合键/边端点/节点 fq 均 _bare 裸表名归一（对齐展示层），节点 ds 保留首见原形态。

造数：design 行走真实 API（保存含 sql 节点的工作流，同 test_wf_design_lineage）；
runtime 行/独立定义直插 sqlite（conftest 内存库），零外部依赖。
"""

import json
from datetime import datetime
from types import SimpleNamespace

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
             instance="inst-1", fields=(), create_time=None):
    """直插 runtime 血缘边（+可选字段行），src_type 默认 runtime；create_time 可显式定值。"""
    edge = LineageEdge(wf_code=wf_code, wf_name="rt", instance_id=instance,
                       node_id=node_id, stmt_no=stmt_no, from_table=frm, to_table=to,
                       tmp_flag=tmp, src_type="runtime", create_time=create_time)
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
    assert (e["from"], e["to"], e["level"]) == ("a", "t", "table"), "端点输出裸表名"
    assert e["sources"] == ["design", "runtime"], "src_type 去重双值"
    assert {(r["wfCode"], r["nodeId"], r["stmtNo"]) for r in e["refs"]} == {
        (wf["code"], "n1", 1), (wf["code"], "r1", 1)}
    assert all(set(r) == {"wfCode", "nodeId", "stmtNo"} for r in e["refs"])

    nodes = {n["fq"]: n for n in d["nodes"]}
    assert set(nodes) == {"a", "t"}
    assert nodes["a"]["sources"] == ["design", "runtime"]
    assert nodes["a"]["wfs"] == [wf["code"]]
    assert nodes["t"]["ds"] == "dw" and nodes["t"]["table"] == "t"


# ---------------- source 筛选 ----------------

def test_graph_source_filter(client, db_session):
    wf = _mk_wf(client, "源筛选")
    _save(client, wf, [_sql_node("n1", "INSERT INTO dw.t SELECT x FROM ods.a")])
    _rt_edge(db_session, wf["code"], "rt.b", "dw.t2")

    d = _graph(client, source="design")
    assert [(e["from"], e["to"]) for e in d["edges"]] == [("a", "t")]
    assert all(e["sources"] == ["design"] for e in d["edges"])
    d = _graph(client, source="runtime")
    assert [(e["from"], e["to"]) for e in d["edges"]] == [("b", "t2")]


# ---------------- wfCode 过滤 ----------------

def test_graph_wfcode_filter(client):
    wf1 = _mk_wf(client, "过滤A")
    _save(client, wf1, [_sql_node("n1", "INSERT INTO dw.t1 SELECT x FROM ods.a1")])
    wf2 = _mk_wf(client, "过滤B")
    _save(client, wf2, [_sql_node("n1", "INSERT INTO dw.t2 SELECT x FROM ods.a2")])

    d = _graph(client, wfCode=wf1["code"])
    assert [(e["from"], e["to"]) for e in d["edges"]] == [("a1", "t1")]
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
    assert _fqs(d) == {"c0", "c1", "c2", "c3"}
    assert d["truncated"] is False

    d = _graph(client, table="c1", direction="upstream")  # 裸表名精确匹配
    assert _fqs(d) == {"c0", "c1"}

    d = _graph(client, table="c1", direction="downstream")
    assert _fqs(d) == {"c1", "c2", "c3"}

    d = _graph(client, table="dw.c1", depth=1)
    assert _fqs(d) == {"c0", "c1", "c2"}, "depth=1 只扩一跳"


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
    assert _fqs(d) == {"A", "B", "C", "D"}, "分叉经 B/C 汇聚到 D"
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
    assert _fqs(d) == {"c0", "c1"}
    assert d["truncated"] is True
    assert [(e["from"], e["to"]) for e in d["edges"]] == [("c0", "c1")]


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
    assert _fqs(d) == {"a", "b", "c"}, "visited 防环，不重入不爆炸"
    assert len(d["edges"]) == 3 and d["truncated"] is False


# ---------------- field 级边带 transform ----------------

def test_graph_field_level_transform(client):
    wf = _mk_wf(client, "字段级")
    _save(client, wf, [
        _sql_node("n1", "INSERT INTO dw.t SELECT o.amount * 0.9 AS amt FROM ods.orders o")])

    d = _graph(client, level="field")
    assert len(d["edges"]) == 1
    e = d["edges"][0]
    assert (e["from"], e["to"], e["level"]) == ("orders.amount", "t.amt", "field")
    assert e["sources"] == ["design"]
    assert len(e["refs"]) == 1
    ref = e["refs"][0]
    assert (ref["wfCode"], ref["nodeId"], ref["stmtNo"]) == (wf["code"], "n1", 1)
    assert "0.9" in ref["transform"]
    assert _fqs(d) == {"orders.amount", "t.amt"}

    # 中心表按字段节点表部匹配（field 级节点名含字段段，裸表名/带前缀均可命中）
    d = _graph(client, level="field", table="dw.t")
    assert _fqs(d) == {"orders.amount", "t.amt"}


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
    assert set(nodes) == {"file:x/y.csv", "t9"}, "file: 端点原样保留，db 前缀端点归一剥前缀"
    assert nodes["file:x/y.csv"]["table"] == "file:x/y.csv" and nodes["file:x/y.csv"]["ds"] == ""
    assert nodes["t9"]["ds"] == "dw" and nodes["t9"]["table"] == "t9"

    # 中心表匹配：全名精确 + endswith 兜底（裸路径传入）
    assert _fqs(_graph(client, table="file:x/y.csv")) == {"file:x/y.csv", "t9"}
    assert _fqs(_graph(client, table="x/y.csv")) == {"file:x/y.csv", "t9"}


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
    assert nodes["tmp1"]["tmpFlag"] == 1 and nodes["h"]["tmpFlag"] == 1
    assert nodes["t"]["tmpFlag"] == 0
    assert d["opaques"] == [{"wfCode": 99001, "nodeId": "p1", "type": "python"}]

    # wfCode 过滤 / 中心表扩散：opaque 随工作流范围收窄
    assert _graph(client, wfCode=wf["code"])["opaques"] == []
    assert _graph(client, table="dw.t")["opaques"] == []


# ---------------- 三形态聚合一（1.9 实测缺陷回归） ----------------

def test_graph_mixed_prefix_forms_merge_dual_source(client, db_session):
    """design 落数据源 ID 前缀（9.a→4.b）/ runtime 落数据源名前缀（ec.a）或裸名（b）：
    同一物理血缘按 _bare 归一聚成一条边，sources 双值命中（1.9 实测：原值聚合裂边
    design 1 条 + runtime N 条零合并，双源永不命中）。"""
    wf_d = _mk_wf(client, "设计态ID前缀")
    _save(client, wf_d, [_sql_node("n1", "INSERT INTO 4.b SELECT x FROM 9.a")])
    _rt_edge(db_session, 97, "ec.a", "b", node_id="r1")

    d = _graph(client)
    assert len(d["edges"]) == 1, "两形态同一物理血缘不裂边"
    e = d["edges"][0]
    assert (e["from"], e["to"]) == ("a", "b")
    assert e["sources"] == ["design", "runtime"], "双源归一命中（本缺陷核心断言）"
    assert {(r["wfCode"], r["nodeId"]) for r in e["refs"]} == {
        (wf_d["code"], "n1"), (97, "r1")}, "refs 两来源明细合并收集"
    nodes = {n["fq"]: n for n in d["nodes"]}
    assert set(nodes) == {"a", "b"}, "多形态同表聚为单节点（fq 全局一致）"
    assert nodes["a"]["sources"] == ["design", "runtime"]
    # design SQL 解析落库实形态 dw.9.a（datasource 配置名 + ds-ID + 表名三段），
    # ds=_split_fq 首段保留原形态不硬造（"dw.9"/"9"/"ec" 取决于首见行）
    assert nodes["a"]["ds"] in ("9", "ec", "dw.9"), "ds 取首见原形态（不硬造）"
    assert nodes["b"]["table"] == "b"


# ---------------- 归一防误伤（字段级 + file:） ----------------

def test_graph_field_mixed_prefix_and_file_guard(client, db_session):
    """①file: 路径端点不受 _bare 归一影响（不剥不并）；②design（ds-ID 前缀）与
    runtime（ds 名前缀）同表同字段归一为一条字段边、双源命中，不同字段不串行。"""
    wf = _mk_wf(client, "字段归一防误伤")
    _save(client, wf, [
        _sql_node("n1", "INSERT INTO 4.pay SELECT o.amount * 0.9 AS amt FROM 9.orders o")])
    _rt_edge(db_session, wf["code"], "ec.orders", "pay", node_id="r1",
             fields=[("ec.orders", "amount", "amt", "amount")])
    _rt_edge(db_session, wf["code"], "file:x/y.csv", "dw.ext", node_id="r2")

    d = _graph(client, level="field")
    fe = [e for e in d["edges"] if e["to"] == "pay.amt"]
    assert len(fe) == 1, "两形态同字段聚合为一条字段边（不串不裂）"
    assert (fe[0]["from"], fe[0]["to"]) == ("orders.amount", "pay.amt")
    assert fe[0]["sources"] == ["design", "runtime"], "字段级双源归一命中"
    assert {(r["wfCode"], r["nodeId"]) for r in fe[0]["refs"]} == {
        (wf["code"], "n1"), (wf["code"], "r1")}
    design_ref = next(r for r in fe[0]["refs"] if r["nodeId"] == "n1")
    assert "0.9" in design_ref["transform"]
    # field 级图只聚合字段行；file 边仅表级行无字段行，不出现于 field 图（表级段验证）
    assert _fqs(d) >= {"orders.amount", "pay.amt"}

    # 表级同口径：orders→pay 一条双源边 + file: 边独立保留
    dt = _graph(client)
    by_pair = {(e["from"], e["to"]): e for e in dt["edges"]}
    assert by_pair[("orders", "pay")]["sources"] == ["design", "runtime"]
    assert by_pair[("file:x/y.csv", "ext")]["sources"] == ["runtime"], "file: 边不剥不并"


# ---------------- 节点 lastCollected（聚合行 create_time max，/stats lastTime 同口径） ----------------

def test_graph_last_collected_max_per_node(client, db_session):
    """同表多条边取最大 create_time，序列化 'YYYY-MM-DD HH:mm:ss'；各节点独立。"""
    wf = _mk_wf(client, "最近采集")
    _rt_edge(db_session, wf["code"], "ods.a", "dw.t", node_id="r1",
             create_time=datetime(2026, 9, 30, 10, 0, 0))
    _rt_edge(db_session, wf["code"], "ods.a", "dw.t", node_id="r2",
             create_time=datetime(2026, 9, 30, 11, 30, 5))
    _rt_edge(db_session, wf["code"], "ods.b", "dw.u", node_id="r3",
             create_time=datetime(2026, 9, 1, 8, 0, 0))

    d = _graph(client)
    nodes = {n["fq"]: n for n in d["nodes"]}
    assert nodes["a"]["lastCollected"] == "2026-09-30 11:30:05", "同节点多行取 max"
    assert nodes["t"]["lastCollected"] == "2026-09-30 11:30:05"
    assert nodes["b"]["lastCollected"] == "2026-09-01 08:00:00", "各节点独立取各自 max"
    assert nodes["u"]["lastCollected"] == "2026-09-01 08:00:00"


def test_graph_last_collected_field_level_from_parent_edge(client, db_session):
    """field 级节点 lastCollected 取组内父边 create_time max（字段行自身无独立时间口径）。"""
    wf = _mk_wf(client, "字段最近采集")
    _rt_edge(db_session, wf["code"], "ec.orders", "pay", node_id="r1",
             create_time=datetime(2026, 9, 30, 12, 0, 0),
             fields=[("ec.orders", "amount", "amt", "amount")])
    _rt_edge(db_session, wf["code"], "ec.orders", "pay", node_id="r2",
             create_time=datetime(2026, 9, 30, 15, 0, 0),
             fields=[("ec.orders", "amount", "amt", "amount")])

    d = _graph(client, level="field")
    nodes = {n["fq"]: n for n in d["nodes"]}
    assert nodes["orders.amount"]["lastCollected"] == "2026-09-30 15:00:00"
    assert nodes["pay.amt"]["lastCollected"] == "2026-09-30 15:00:00"


def test_graph_last_collected_null_when_missing(client, db_session, monkeypatch):
    """create_time 缺失（存量可空列防御）：聚合行 create_time=None → lastCollected=null
    不硬造不炸；None 行不参与同节点有值行的 max。库结构该列 NOT NULL（default 兜底），
    集成无法造 NULL 行，故以查询行替身直测 graph 聚合分支。"""
    import api.lineage as mod

    rows = [
        SimpleNamespace(id=1, wf_code=1, wf_name="rt", instance_id="inst-1",
                        node_id="r1", stmt_no=1, from_table="ods.x", to_table="dw.y",
                        tmp_flag=0, src_type="runtime",
                        create_time=datetime(2026, 9, 30, 9, 0, 0)),
        SimpleNamespace(id=2, wf_code=1, wf_name="rt", instance_id="inst-1",
                        node_id="r2", stmt_no=1, from_table="ods.x", to_table="dw.y",
                        tmp_flag=0, src_type="runtime", create_time=None),
        SimpleNamespace(id=3, wf_code=1, wf_name="rt", instance_id="inst-1",
                        node_id="r3", stmt_no=1, from_table="ods.z", to_table="dw.w",
                        tmp_flag=0, src_type="runtime", create_time=None),
    ]

    class _FakeQuery:
        def __init__(self, data):
            self._data = data

        def filter(self, *args, **kwargs):
            return self  # 故意透传：本用例只验聚合分支的 None 防御，过滤条件变化不需同步替身

        def all(self):
            return self._data

    monkeypatch.setattr(mod, "_base_query", lambda db: _FakeQuery(rows))

    d = _graph(client)
    nodes = {n["fq"]: n for n in d["nodes"]}
    assert nodes["x"]["lastCollected"] == "2026-09-30 09:00:00", "None 行不参与 max"
    assert nodes["y"]["lastCollected"] == "2026-09-30 09:00:00"
    assert nodes["z"]["lastCollected"] is None, "全 None 节点输出 null"
    assert nodes["w"]["lastCollected"] is None


# ---------------- opaque 内容寻址缓存 ----------------

def test_opaques_cache_hit_and_invalidate(client, db_session, monkeypatch):
    """_collect_opaques 内容寻址缓存：graph_json 摘要未变直接复用解析结果（不重复调
    extract_wf_lineage），改写定义换戳自动重算（免显式失效钩子）。save 端点自身经
    redesign 也会解析，计数快照围住每次 graph 调用前后，不与 rebuild 耦合。"""
    import api.lineage as lineage_mod
    real_extract = lineage_mod.extract_wf_lineage
    calls = {"n": 0}

    def _counting(nodes, edges, code):
        calls["n"] += 1
        return real_extract(nodes, edges, code)

    monkeypatch.setattr(lineage_mod, "extract_wf_lineage", _counting)
    lineage_mod._opaques_cache.clear()  # 隔离同进程其他用例的缓存残留

    _mk_wf(client, "opaque缓存")
    db_session.add(WfDefinition(
        id="wf_cache", code=99002, name="py流缓存",
        graph_json=json.dumps({"nodes": [{"id": "p1", "type": "python", "data": {}}],
                               "edges": []})))
    db_session.commit()

    before = calls["n"]
    d1 = _graph(client)
    assert calls["n"] > before, "首查解析并写入缓存"
    assert d1["opaques"] == [{"wfCode": 99002, "nodeId": "p1", "type": "python"}]

    before = calls["n"]
    d2 = _graph(client)
    assert calls["n"] == before, "定义未变（摘要同）命中缓存不再解析"
    assert d2["opaques"] == d1["opaques"]

    row = db_session.query(WfDefinition).filter(WfDefinition.code == 99002).one()
    row.graph_json = json.dumps({"nodes": [{"id": "p2", "type": "shell", "data": {}}],
                                 "edges": []})
    db_session.commit()

    before = calls["n"]
    d3 = _graph(client)
    assert calls["n"] == before + 1, "内容变化换戳自动重算"
    assert d3["opaques"] == [{"wfCode": 99002, "nodeId": "p2", "type": "shell"}]
