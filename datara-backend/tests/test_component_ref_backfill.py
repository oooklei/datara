"""D2 componentRef 回填脚本 + 物化器注入单测（实施计划 20260926，治理设计 §9.5/§9.6）。

覆盖：
1. scripts/backfill_component_ref.py backfill()：缺 ref 注入（sys_exec_ 豁免 /
   已有 ref 不动 / version 取治理库 published or 1）、幂等零写放大、
   comp_versions 缺省时读 t_component；
2. master.engine.materialize_sync_exec：物化节点按源组件 published 版本注入
   componentRef（无供给兜底 v1），原件不被污染。

DB：sqlite 内存库（conftest），存量文档经原生 SQL 灌入（模型模块分裂免疫，
test_graph_rules.test_publish_endpoint_r5_gate 同手法）。
"""

import importlib.util
import json
import pathlib
import sys

import pytest
from sqlalchemy import text

BACKEND = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _load_backfill():
    name = "datara_test_backfill_component_ref"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / "scripts" / "backfill_component_ref.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[name] = mod
    return mod


_backfill_mod = _load_backfill()
backfill = _backfill_mod.backfill


def _mk_doc(nodes):
    return {"id": "wf_x", "name": "n", "version": 3, "nodes": nodes, "edges": []}


def _graph_of(db_session, wf_id):
    row = db_session.execute(
        text("SELECT graph_json FROM t_wf_definition WHERE id = :i"), {"i": wf_id}).fetchone()
    return json.loads(row[0])


@pytest.fixture()
def wf_rows(client, db_session):
    """经 API 建两工作流，再原生 SQL 灌入存量形态图（缺 ref / 已有 ref 各一）。"""
    ids = []
    for name in ("回填A", "回填B"):
        r = client.post("/api/v1/workflow-definitions", json={"name": name})
        assert r.status_code == 200, r.text
        ids.append(r.json()["data"]["id"])
    legacy = _mk_doc([
        {"id": "n1", "type": "comp_b", "data": {"sql": "select 1"}},
        {"id": "sys_exec_ab12cd34", "type": "sync", "data": {"type": "sync"}},
    ])
    already = _mk_doc([
        {"id": "n1", "type": "comp_b",
         "data": {"sql": "select 1", "componentRef": {"type": "comp_b", "version": 2}}},
    ])
    db_session.execute(
        text("UPDATE t_wf_definition SET graph_json = :g WHERE id = :i"),
        [{"g": json.dumps(legacy, ensure_ascii=False), "i": ids[0]},
         {"g": json.dumps(already, ensure_ascii=False), "i": ids[1]}],
    )
    db_session.commit()
    return ids


# ---------------- backfill 幂等回填（§9.5） ----------------

def test_backfill_injects_and_skips(wf_rows, db_session):
    """缺 ref 注入（sys_exec_ 豁免）；version 取治理库 published；已有 ref 不动。"""
    ids = wf_rows
    stats = backfill(db_session, comp_versions={"comp_b": 2})
    db_session.commit()
    assert stats["docs"] == 2 and stats["scanned"] == 2
    assert stats["patched"] == 1 and stats["nodes"] == 1

    doc = _graph_of(db_session, ids[0])
    assert doc["nodes"][0]["data"]["componentRef"] == {"type": "comp_b", "version": 2}
    assert doc["version"] == 3  # 其余字段原样保留
    # sys_exec_ 物化产物豁免（§9.6）：设计态不入库 ref，由物化器运行时注入
    assert "componentRef" not in doc["nodes"][1]["data"]
    # 已有 ref 的文档零写放大（§9.5 幂等口径）
    assert _graph_of(db_session, ids[1])["nodes"][0]["data"]["componentRef"] == {"type": "comp_b", "version": 2}


def test_backfill_default_version_and_idempotent(wf_rows, db_session):
    """供给外类型（系统目录 37 type）兜底 v1；重复执行 patched/nodes 归零（幂等）。"""
    ids = wf_rows
    backfill(db_session, comp_versions={})
    db_session.commit()
    assert _graph_of(db_session, ids[0])["nodes"][0]["data"]["componentRef"] == {"type": "comp_b", "version": 1}

    stats = backfill(db_session, comp_versions={})
    db_session.commit()
    assert stats["nodes"] == 0 and stats["patched"] == 0


def test_backfill_reads_component_table_when_supply_absent(wf_rows, db_session):
    """comp_versions 缺省 → 查 t_component 组装（治理库组件注入 published 版本）。"""
    ids = wf_rows
    db_session.execute(text(
        "INSERT INTO t_component (type, name, profile, scope, execution_model, executor,"
        " executable, state, published_version, draft_rev, create_time, update_time)"
        " VALUES ('comp_b', 'B组件', 'dag', 'builtin', 'dag-engine', NULL, 1, 'published', 4, 0,"
        " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"))
    db_session.commit()

    backfill(db_session)
    db_session.commit()
    assert _graph_of(db_session, ids[0])["nodes"][0]["data"]["componentRef"] == {"type": "comp_b", "version": 4}


# ---------------- 物化器 componentRef 注入（§9.6） ----------------

from master.engine import materialize_sync_exec  # noqa: E402


def _ep_doc():
    return {"nodes": [
        {"id": "ep", "type": "endpoint_select", "data": {"baseMode": "src_base"}},
        {"id": "a", "type": "assert", "data": {}},
    ], "edges": [{"source": "ep", "target": "a"}]}


def test_materializer_injects_ref_from_supply():
    """物化节点按源组件（endpoint_select）published 版本注入 ref；无供给兜底 v1。"""
    doc = _ep_doc()
    out = materialize_sync_exec(doc, comp_versions={"endpoint_select": 5})
    node = [n for n in out["nodes"] if str(n["id"]).startswith("sys_exec_")][0]
    assert node["data"]["componentRef"] == {"type": "endpoint_select", "version": 5}
    # 原件不被污染（浅两层拷贝口径）
    assert doc["nodes"][0]["data"] == {"baseMode": "src_base"}

    out2 = materialize_sync_exec(_ep_doc())
    node2 = [n for n in out2["nodes"] if str(n["id"]).startswith("sys_exec_")][0]
    assert node2["data"]["componentRef"]["version"] == 1


def test_parse_graph_passes_supply_to_materializer():
    """parse_graph 透传 comp_versions（scheduler/failover 接线路径全链生效）。"""
    from master.dag import parse_graph
    doc = _ep_doc()
    doc["nodes"].insert(0, {"id": "s", "type": "start", "data": {}})
    doc["edges"].insert(0, {"source": "s", "target": "ep"})
    graph, _stream_spec = parse_graph(doc, comp_versions={"endpoint_select": 7})
    node = [n for n in graph.nodes.values() if n["id"].startswith("sys_exec_")][0]
    assert node["data"]["componentRef"] == {"type": "endpoint_select", "version": 7}
