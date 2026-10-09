from types import SimpleNamespace

from api.lineage import _bare, _field_node, _latest_edges


def _edge(edge_id, **overrides):
    values = {
        "id": edge_id,
        "wf_code": 10,
        "node_id": "sql-1",
        "stmt_no": 1,
        "from_table": "ods.orders",
        "to_table": "dwd.orders",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_latest_edges_keeps_newest_run_per_logical_edge() -> None:
    old = _edge(1)
    newest = _edge(7)
    another_source = _edge(5, from_table="ods.users")

    result = _latest_edges([newest, old, another_source])

    assert {edge.id for edge in result} == {7, 5}


def test_bare_and_field_node_match_frontend_graph_ids() -> None:
    assert _bare("datara_dw.dwd_order") == "dwd_order"
    assert _field_node("datara_dw.dwd_order", "order_id") == "dwd_order.order_id"
    assert _field_node("", "literal") == ""
