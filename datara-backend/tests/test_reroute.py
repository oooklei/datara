from master.dag import parse_graph


def test_parse_graph_eliminates_reroute_and_reconnects_neighbors():
    doc = {
        "nodes": [
            {"id": "start", "type": "start", "data": {}},
            {"id": "route", "type": "reroute", "data": {}},
            {"id": "sql", "type": "sql", "data": {}},
        ],
        "edges": [
            {"source": "start", "target": "route", "sourceHandle": "out"},
            {"source": "route", "target": "sql", "label": "continued"},
        ],
    }

    graph, stream_spec = parse_graph(doc)

    assert stream_spec is None
    assert set(graph.nodes) == {"start", "sql"}
    assert [(edge["source"], edge["target"]) for edge in graph.edges] == [("start", "sql")]
    assert graph.edges[0]["sourceHandle"] == "out"
    assert graph.edges[0]["label"] == "continued"

