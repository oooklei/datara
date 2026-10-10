"""设计态血缘解析器单测（Task 2）：common/lineage_extract.py 纯函数直测（sqlite 无关）。

- 输入节点结构对齐 master/dag.py parse_graph 口径：nodes=[{id, type, data}]，edges=[{source, target}]
- config key 契约已核实（worker/executors/sql.py、sync.py、file_sync.py、master/engine.py
  _apply_detail_config、datara-web/src/graph/profiles/types.ts ResourcePick、docs/组件基线化/*）
- 覆盖：sql 四形态 / sync 族 / field_map 正反向与前驱回溯 / file_sync / 逻辑控制跳过 /
  opaque 记录 / 单节点异常隔离 / 空输入容错 / 真实链形态（wf=97 v5 实测同构）
"""

from common.lineage_extract import extract_wf_lineage


# ---------- 夹具构造 ----------


def _sql_node(nid, sql, datasource="ds_mysql", pre="", post=""):
    return {"id": nid, "type": "sql", "data": {"datasource": datasource, "pre": pre, "sql": sql, "post": post}}


def _ep_node(
    nid, base_mode="src_base", src_ds="mysql_src", src_table="orders", tgt_ds="dw", tgt_table="dwd_order", **extra
):
    data = {"baseMode": base_mode, "srcDs": src_ds, "srcTable": src_table, "tgtDs": tgt_ds, "tgtTable": tgt_table}
    data.update(extra)
    return {"id": nid, "type": "endpoint_select", "data": data}


def _fm_node(nid, inputs, field_map=None, union=False):
    return {
        "id": nid,
        "type": "field_map_union" if union else "field_map",
        "data": {"inputs": inputs, "fieldMap": field_map or []},
    }


def _tkey(edge):
    return (edge["node_id"], edge["stmt_no"], edge["from_table"], edge["to_table"])


def _fkey(edge):
    return (edge["to_table"], edge["to_field"], edge["from_table"], edge["from_field"])


# ---------- 1. sql ----------


class TestSqlNode:
    def test_insert_select_table_and_field_with_transform(self):
        node = _sql_node("n1", "INSERT INTO dw.t SELECT o.amount * 0.9 AS amt FROM ods.orders o")
        out = extract_wf_lineage([node], [], 97)
        assert out["opaques"] == []
        tes = sorted(out["table_edges"], key=_tkey)
        assert tes == [
            {
                "wf_code": 97,
                "instance_id": 0,
                "node_id": "n1",
                "stmt_no": 1,
                "from_table": "ods.orders",
                "to_table": "dw.t",
                "tmp_flag": 0,
                "src_type": "design",
            }
        ]
        fes = out["field_edges"]
        assert len(fes) == 1
        fe = fes[0]
        assert fe["to_table"] == "dw.t"
        assert fe["to_field"] == "amt"
        assert fe["from_table"] == "ods.orders"
        assert fe["from_field"] == "amount"
        assert "amount" in fe["transform"] and "0.9" in fe["transform"]
        assert fe["src_type"] == "design"

    def test_select_star_table_only(self):
        """SELECT *：fields 为空但 to_tables 非空 → 只落表级。"""
        node = _sql_node("n1", "INSERT INTO t2 SELECT * FROM s1.t1")
        out = extract_wf_lineage([node], [], 1)
        tes = sorted(out["table_edges"], key=_tkey)
        assert [(e["from_table"], e["to_table"]) for e in tes] == [("s1.t1", "ds_mysql.t2")]
        assert out["field_edges"] == []

    def test_pure_select_no_edge(self):
        """纯 SELECT 无 to_tables → 不产边（与运行态口径一致），也不记 opaque。"""
        node = _sql_node("n1", "SELECT * FROM a.b")
        out = extract_wf_lineage([node], [], 1)
        assert out["table_edges"] == []
        assert out["field_edges"] == []
        assert out["opaques"] == []

    def test_multi_statement_stmt_no(self):
        node = _sql_node("n1", "INSERT INTO a.t1 SELECT x FROM b.t2; INSERT INTO a.t3 SELECT y FROM b.t4")
        out = extract_wf_lineage([node], [], 1)
        pairs = {(e["stmt_no"], e["from_table"], e["to_table"]) for e in out["table_edges"]}
        assert pairs == {(1, "b.t2", "a.t1"), (2, "b.t4", "a.t3")}

    def test_same_pair_multi_stmt_fields_carry_stmt_no(self):
        """同节点同 (from,to) 表对多语句：字段边携带各自 stmt_no（挂靠键前提）。"""
        node = _sql_node("n1", "INSERT INTO a.t SELECT x AS c1 FROM b.s; INSERT INTO a.t SELECT y AS c1 FROM b.s")
        out = extract_wf_lineage([node], [], 1)
        tes = sorted(out["table_edges"], key=_tkey)
        assert [(e["stmt_no"], e["from_table"], e["to_table"]) for e in tes] == [(1, "b.s", "a.t"), (2, "b.s", "a.t")]
        fes = sorted(out["field_edges"], key=lambda f: f["stmt_no"])
        assert [(f["node_id"], f["stmt_no"], f["from_field"]) for f in fes] == [("n1", 1, "x"), ("n1", 2, "y")]

    def test_same_pair_multi_node_fields_carry_node_id(self):
        """两节点产同 (from,to) 表对：字段边携带各自 node_id，不被跨节点去重。"""
        n1 = _sql_node("n1", "INSERT INTO a.t SELECT x AS c1 FROM b.s")
        n2 = _sql_node("n2", "INSERT INTO a.t SELECT y AS c1 FROM b.s")
        out = extract_wf_lineage([n1, n2], [], 1)
        fes = sorted(out["field_edges"], key=lambda f: f["node_id"])
        assert [(f["node_id"], f["stmt_no"], f["from_field"]) for f in fes] == [("n1", 1, "x"), ("n2", 1, "y")]

    def test_pre_sql_post_stmt_no_alignment(self):
        """pre+sql+post 合并解析：stmt_no 与运行态「全语句顺序拆分序」对齐（pre 占 1）。"""
        node = _sql_node("n1", "INSERT INTO a.t1 SELECT x FROM b.t2", pre="SET @x = 1")
        out = extract_wf_lineage([node], [], 1)
        assert [(e["stmt_no"], e["from_table"], e["to_table"]) for e in out["table_edges"]] == [(2, "b.t2", "a.t1")]

    def test_unqualified_names_use_datasource_as_default_db(self):
        node = _sql_node("n1", "INSERT INTO t2 SELECT id FROM t1")
        out = extract_wf_lineage([node], [], 1)
        assert [(e["from_table"], e["to_table"]) for e in out["table_edges"]] == [("ds_mysql.t1", "ds_mysql.t2")]

    def test_empty_sql_no_edge(self):
        out = extract_wf_lineage([_sql_node("n1", "")], [], 1)
        assert out["table_edges"] == [] and out["field_edges"] == []
        assert out["opaques"] == []


# ---------- 2. 同步编排（endpoint_select / sync） ----------


class TestSyncFamily:
    def test_endpoint_src_base_table_edge(self):
        node = _ep_node("ep1")
        out = extract_wf_lineage([node], [], 97)
        assert out["table_edges"] == [
            {
                "wf_code": 97,
                "instance_id": 0,
                "node_id": "ep1",
                "stmt_no": 0,
                "from_table": "mysql_src.orders",
                "to_table": "dw.dwd_order",
                "tmp_flag": 0,
                "src_type": "design",
            }
        ]
        assert out["field_edges"] == []

    def test_endpoint_src_table_schema_object(self):
        """srcTable writeAs=schemaTable 写回 {schema, table} 对象 → {schema}.{table}。"""
        node = _ep_node("ep1", src_table={"schema": "ec_retail", "table": "ods_order"})
        out = extract_wf_lineage([node], [], 97)
        assert out["table_edges"][0]["from_table"] == "ec_retail.ods_order"

    def test_endpoint_tgt_base_probe_tables(self):
        """tgt_base：probeResult 探测表逐表 → 目标表（多源多目标每对组合）。"""
        node = _ep_node("ep1", base_mode="tgt_base", src_table="", probe_result=None, tgt_table="dwd_x")
        node["data"]["probeResult"] = "ods.a, ods.b"
        out = extract_wf_lineage([node], [], 1)
        pairs = {(e["from_table"], e["to_table"]) for e in out["table_edges"]}
        assert pairs == {("ods.a", "dw.dwd_x"), ("ods.b", "dw.dwd_x")}

    def test_endpoint_tgt_base_probe_list_form(self):
        """probeResult 数组形态 [{schema, table}]（seed 直写）。"""
        node = _ep_node("ep1", base_mode="tgt_base", tgt_table="dwd_x")
        node["data"]["probeResult"] = [{"schema": "ods", "table": "a"}]
        out = extract_wf_lineage([node], [], 1)
        assert [(e["from_table"], e["to_table"]) for e in out["table_edges"]] == [("ods.a", "dw.dwd_x")]

    def test_endpoint_file_sync_mode(self):
        node = _ep_node("ep1", base_mode="file_sync", src_table="", tgt_ds="dw", tgt_table="ods_file")
        node["data"]["filePath"] = "samples/orders_part.csv"
        out = extract_wf_lineage([node], [], 1)
        assert [(e["from_table"], e["to_table"]) for e in out["table_edges"]] == [
            ("file:samples/orders_part.csv", "dw.ods_file")
        ]

    def test_sync_runtime_keys_with_field_map(self):
        """运行态兜底键 readerDs/readerTable/writerDs/writerTable + fieldMap。"""
        node = {
            "id": "s1",
            "type": "sync",
            "data": {
                "readerDs": "s",
                "readerTable": "r",
                "writerDs": "w",
                "writerTable": "t",
                "fieldMap": [{"from": "a", "to": "b"}, {"from": "c", "to": "d"}],
            },
        }
        out = extract_wf_lineage([node], [], 1)
        assert [(e["from_table"], e["to_table"]) for e in out["table_edges"]] == [("s.r", "w.t")]
        fes = sorted(out["field_edges"], key=_fkey)
        assert [(f["from_table"], f["from_field"], f["to_table"], f["to_field"], f["transform"]) for f in fes] == [
            ("s.r", "a", "w.t", "b", ""),
            ("s.r", "c", "w.t", "d", ""),
        ]

    def test_field_map_empty_table_only(self):
        """columnMap/fieldMap 留空=全列同名 → 只落表级（决策 D2）。"""
        node = {
            "id": "s1",
            "type": "sync",
            "data": {"readerDs": "s", "readerTable": "r", "writerDs": "w", "writerTable": "t"},
        }
        out = extract_wf_lineage([node], [], 1)
        assert len(out["table_edges"]) == 1 and out["field_edges"] == []

    def test_field_map_kv_entry_compat(self):
        """fieldMap 条目前端 kv-table 形态 {key, value}（与执行器 _column_pairs 双兼容同口径）。"""
        node = {
            "id": "s1",
            "type": "sync",
            "data": {
                "readerDs": "s",
                "readerTable": "r",
                "writerDs": "w",
                "writerTable": "t",
                "fieldMap": [{"key": "a", "value": "b"}],
            },
        }
        out = extract_wf_lineage([node], [], 1)
        assert out["field_edges"] == [
            {
                "node_id": "s1",
                "stmt_no": 0,
                "to_table": "w.t",
                "to_field": "b",
                "from_table": "s.r",
                "from_field": "a",
                "transform": "",
                "src_type": "design",
            }
        ]

    def test_missing_target_table_no_edge(self):
        node = {"id": "s1", "type": "sync", "data": {"readerDs": "s", "readerTable": "r"}}
        out = extract_wf_lineage([node], [], 1)
        assert out["table_edges"] == [] and out["opaques"] == []


# ---------- 3. field_map / field_map_union ----------


class TestFieldMap:
    def test_forward_map_to_predecessor_tables(self):
        """正向：inputs 端口语义引用 → 源端表→目标端表 + 字段映射。"""
        ep = _ep_node("ep1")
        fm = _fm_node("fm1", ["ep1:sourceRef", "ep1:targetRef"], [{"from": "a", "to": "b"}])
        edges = [{"source": "ep1", "target": "fm1"}]
        out = extract_wf_lineage([ep, fm], edges, 97)
        # 表级边归属 field_map 节点（from=前驱源端表 to=前驱目标端表）
        assert [
            (e["node_id"], e["from_table"], e["to_table"]) for e in out["table_edges"] if e["node_id"] == "fm1"
        ] == [("fm1", "mysql_src.orders", "dw.dwd_order")]
        assert out["field_edges"] == [
            {
                "node_id": "fm1",
                "stmt_no": 0,
                "to_table": "dw.dwd_order",
                "to_field": "b",
                "from_table": "mysql_src.orders",
                "from_field": "a",
                "transform": "",
                "src_type": "design",
            }
        ]
        # endpoint_select 自身仍产其表级边
        assert any(e["node_id"] == "ep1" for e in out["table_edges"])

    def test_union_reverse_index_direction(self):
        """union 反向：fmSrcIndex=1/fmTgtIndex=0，无端口语义旧格式按索引定向。"""
        ep_src = _ep_node("epA")  # 源端基准端点
        ep_tgt = _ep_node("epB", tgt_ds="dw2", tgt_table="dwd_b")
        fu = _fm_node(
            "fu1",
            ["epB", "epA"],  # [0]=目标端表引用, [1]=源端探测表引用
            [{"from": "c", "to": "d"}],
            union=True,
        )
        edges = [{"source": "epA", "target": "fu1"}, {"source": "epB", "target": "fu1"}]
        out = extract_wf_lineage([ep_src, ep_tgt, fu], edges, 1)
        # 反向解析：源=epA 源端表，目标=epB 目标表（若方向未反向会得到 epB.src→epA.tgt）
        assert [
            (e["node_id"], e["from_table"], e["to_table"]) for e in out["table_edges"] if e["node_id"] == "fu1"
        ] == [("fu1", "mysql_src.orders", "dw2.dwd_b")]
        assert out["field_edges"] == [
            {
                "node_id": "fu1",
                "stmt_no": 0,
                "to_table": "dw2.dwd_b",
                "to_field": "d",
                "from_table": "mysql_src.orders",
                "from_field": "c",
                "transform": "",
                "src_type": "design",
            }
        ]

    def test_walk_back_through_control_flow(self):
        """前驱为控制流（condition_set）时继续向上回溯到 endpoint_select。"""
        ep = _ep_node("ep1")
        cond = {"id": "c1", "type": "condition_set", "data": {"filterExpr": "status = 1", "incrementalColumn": "id"}}
        fm = _fm_node("fm1", [], [{"from": "a", "to": "b"}])
        edges = [{"source": "ep1", "target": "c1"}, {"source": "c1", "target": "fm1"}]
        out = extract_wf_lineage([ep, cond, fm], edges, 1)
        assert [
            (e["node_id"], e["from_table"], e["to_table"]) for e in out["table_edges"] if e["node_id"] == "fm1"
        ] == [("fm1", "mysql_src.orders", "dw.dwd_order")]
        assert out["opaques"] == []  # condition_set 属跳过组

    def test_field_map_empty_only_table_edge(self):
        """fieldMap 留空 → 只落表级（D2）。"""
        ep = _ep_node("ep1")
        fm = _fm_node("fm1", ["ep1:sourceRef", "ep1:targetRef"], [])
        out = extract_wf_lineage([ep, fm], [{"source": "ep1", "target": "fm1"}], 1)
        fm_edges = [e for e in out["table_edges"] if e["node_id"] == "fm1"]
        assert len(fm_edges) == 1 and out["field_edges"] == []

    def test_unresolvable_no_edge_no_opaque(self):
        """inputs 与前驱均无端点 → 容错产空（不产边不记 opaque）。"""
        fm = _fm_node("fm1", [], [{"from": "a", "to": "b"}])
        out = extract_wf_lineage([fm], [], 1)
        assert out["table_edges"] == [] and out["field_edges"] == []
        assert out["opaques"] == []


# ---------- 4. file_sync / file_sync_orch ----------


class TestFileSync:
    def test_file_sync_runtime_keys(self):
        """file_sync 运行态键：filePath → targetDs/targetSchema/targetTable；from 用 file:{path}。"""
        node = {
            "id": "f1",
            "type": "file_sync",
            "data": {"filePath": "a/b.csv", "targetDs": "dw", "targetSchema": "dwd", "targetTable": "t"},
        }
        out = extract_wf_lineage([node], [], 1)
        assert [(e["from_table"], e["to_table"]) for e in out["table_edges"]] == [("file:a/b.csv", "dwd.t")]

    def test_file_sync_orch_remnant_config(self):
        """模板组件残留文件/目标键 → file:{path} → 表（运行态 file_sync 无血缘采集形态）。"""
        node = {"id": "o1", "type": "file_sync_orch", "data": {"filePath": "x/y.csv", "tgtDs": "dw", "tgtTable": "t9"}}
        out = extract_wf_lineage([node], [], 1)
        assert [(e["from_table"], e["to_table"]) for e in out["table_edges"]] == [("file:x/y.csv", "dw.t9")]

    def test_file_sync_orch_clean_template_skipped(self):
        """模板组件无配置（落图即展开）→ 跳过不记 opaque。"""
        node = {"id": "o1", "type": "file_sync_orch", "data": {"name": "文件入仓"}}
        out = extract_wf_lineage([node], [], 1)
        assert out["table_edges"] == [] and out["opaques"] == []


# ---------- 5. 逻辑控制：不产边不记 opaque ----------


class TestLogicControl:
    def test_logic_types_skipped(self):
        types = [
            "start",
            "end",
            "fork",
            "join",
            "merge",
            "switch",
            "conditions",
            "delay",
            "loop",
            "dependent",
            "variable",
            "assert",
            "condition_set",
            "src_base_orch",
            "tgt_base_orch",
            "demo_pipeline",
        ]
        nodes = [{"id": "n_%s" % t, "type": t, "data": {"name": t}} for t in types]
        out = extract_wf_lineage(nodes, [], 1)
        assert out == {"table_edges": [], "field_edges": [], "opaques": []}


# ---------- 6. opaque 记录 ----------


class TestOpaque:
    def test_opaque_types(self):
        types = [
            "python",
            "shell",
            "ssh",
            "http",
            "procedure",
            "file",
            "notify",
            "stream_input",
            "stream_fuse",
            "stream_output",
            "page_board",
        ]
        nodes = [{"id": "n_%s" % t, "type": t, "data": {}} for t in types]
        out = extract_wf_lineage(nodes, [], 97)
        assert out["table_edges"] == [] and out["field_edges"] == []
        assert sorted((o["node_id"], o["type"]) for o in out["opaques"]) == sorted(("n_%s" % t, t) for t in types)
        assert all(o["wf_code"] == 97 for o in out["opaques"])

    def test_unknown_type_opaque(self):
        out = extract_wf_lineage([{"id": "x1", "type": "mystery", "data": {}}], [], 1)
        assert out["opaques"] == [{"wf_code": 1, "node_id": "x1", "type": "mystery"}]


# ---------- 7. 异常隔离 ----------


class TestIsolation:
    def test_bad_node_does_not_break_others(self):
        class Boom(dict):
            def get(self, *args, **kwargs):
                raise RuntimeError("boom")

        bad = {"id": "bad1", "type": "sql", "data": Boom()}
        good = _sql_node("ok1", "INSERT INTO a.t1 SELECT x FROM b.t2")
        out = extract_wf_lineage([bad, good], [], 1)
        assert [(e["from_table"], e["to_table"]) for e in out["table_edges"]] == [("b.t2", "a.t1")]
        assert len(out["opaques"]) == 1
        op = out["opaques"][0]
        assert op["node_id"] == "bad1" and op["type"] == "sql"
        assert "boom" in op.get("reason", "")

    def test_envelope_exception_isolated(self):
        """节点信封本身异常（dict.get 抛错）→ 同样记 opaque 不抛出，不破纯函数契约。"""

        class BoomNode(dict):
            def get(self, *args, **kwargs):
                raise RuntimeError("boom envelope")

        good = _sql_node("ok1", "INSERT INTO a.t1 SELECT x FROM b.t2")
        out = extract_wf_lineage([BoomNode(), good], [], 1)
        assert [(e["from_table"], e["to_table"]) for e in out["table_edges"]] == [("b.t2", "a.t1")]
        assert len(out["opaques"]) == 1
        assert "boom envelope" in out["opaques"][0].get("reason", "")

    def test_non_dict_data_tolerated(self):
        out = extract_wf_lineage([{"id": "n1", "type": "sql", "data": None}], [], 1)
        assert out["opaques"] == [] and out["table_edges"] == []


# ---------- 8. 空输入容错 ----------


class TestEmpty:
    def test_empty_nodes_and_edges(self):
        out = extract_wf_lineage([], [], 1)
        assert out == {"table_edges": [], "field_edges": [], "opaques": []}

    def test_none_nodes_and_edges(self):
        out = extract_wf_lineage(None, None, 0)
        assert out == {"table_edges": [], "field_edges": [], "opaques": []}

    def test_edge_references_unknown_node_tolerated(self):
        ep = _ep_node("ep1")
        edges = [{"source": "ghost", "target": "ep1"}, {"source": "ep1", "target": "ghost"}]
        out = extract_wf_lineage([ep], edges, 1)
        assert len(out["table_edges"]) == 1 and out["opaques"] == []


# ---------- 真实链形态试运行（wf=97 v5 实测同构：endpoint_select→field_map→condition_set→assert） ----------


class TestRealChainShape:
    def test_wf97_v5_like_chain(self):
        nodes = [
            {"id": "start1", "type": "start", "data": {"name": "开始"}},
            {"id": "clean1", "type": "shell", "data": {"name": "前置清理", "script": "echo ok"}},
            _ep_node(
                "ep1",
                src_table={"schema": "ec_retail", "table": "ods_order"},
                tgt_ds="datara_dw",
                tgt_table="dwd_order_sync_test",
            ),
            _fm_node(
                "fm1",
                ["ep1:sourceRef", "ep1:targetRef"],
                [{"from": "id", "to": "id"}, {"from": "amount", "to": "pay_amount"}],
            ),
            {
                "id": "cond1",
                "type": "condition_set",
                "data": {"filterExpr": "create_time > ${last_sync_time}", "incrementalColumn": "create_time"},
            },
            {"id": "assert1", "type": "assert", "data": {"name": "对账校验"}},
            {"id": "end1", "type": "end", "data": {"name": "结束"}},
        ]
        edges = [
            {"source": a, "target": b}
            for a, b in (
                ("start1", "clean1"),
                ("clean1", "ep1"),
                ("ep1", "fm1"),
                ("fm1", "cond1"),
                ("cond1", "assert1"),
                ("assert1", "end1"),
            )
        ]
        out = extract_wf_lineage(nodes, edges, 97)
        # shell（前置清理）按决策 D3 记 opaque，其余链上节点不记
        assert [(o["node_id"], o["type"]) for o in out["opaques"]] == [("clean1", "shell")]
        tes = sorted(out["table_edges"], key=_tkey)
        assert [(e["node_id"], e["from_table"], e["to_table"]) for e in tes] == [
            ("ep1", "ec_retail.ods_order", "datara_dw.dwd_order_sync_test"),
            ("fm1", "ec_retail.ods_order", "datara_dw.dwd_order_sync_test"),
        ]
        assert all(
            e["wf_code"] == 97
            and e["instance_id"] == 0
            and e["stmt_no"] == 0
            and e["tmp_flag"] == 0
            and e["src_type"] == "design"
            for e in tes
        )
        fes = sorted(out["field_edges"], key=lambda f: f["from_field"])
        assert [(f["node_id"], f["stmt_no"]) for f in fes] == [("fm1", 0), ("fm1", 0)]
        assert [(f["from_table"], f["from_field"], f["to_table"], f["to_field"]) for f in fes] == [
            ("ec_retail.ods_order", "amount", "datara_dw.dwd_order_sync_test", "pay_amount"),
            ("ec_retail.ods_order", "id", "datara_dw.dwd_order_sync_test", "id"),
        ]
