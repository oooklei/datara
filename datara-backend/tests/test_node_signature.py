from master.signature import node_signature


def test_signature_is_stable_for_mapping_order_and_changes_for_params():
    base = node_signature("sql", 1, {"sql": "select 1", "timeout": 30}, {"a": "x"})
    assert base == node_signature("sql", 1, {"timeout": 30, "sql": "select 1"}, {"a": "x"})
    assert base != node_signature("sql", 1, {"sql": "select 2", "timeout": 30}, {"a": "x"})


def test_upstream_change_invalidates_but_unrelated_input_does_not():
    base = node_signature("python", "2", {"script": "x"}, {"upstream": "one"})
    assert base != node_signature("python", "2", {"script": "x"}, {"upstream": "two"})
    assert base == node_signature("python", "2", {"script": "x"}, {"upstream": "one", "unrelated": None})
