import pytest

from rebuild.sync.materializer import SyncMaterializationError, materialize_endpoint_nodes


def test_endpoint_select_materializes_runtime_node_and_preserves_design_nodes():
    result = materialize_endpoint_nodes([
        {"node_code": "select_1", "node_type": "endpoint_select", "params": {"base_mode": "src_base", "endpoint_id": 3}},
        {"node_code": "map_1", "node_type": "field_map", "params": {}},
    ])
    assert result[0] == {
        "node_code": "sys_exec_select_1",
        "node_type": "sync",
        "runtime_only": True,
        "source_node_code": "select_1",
        "params": {"base_mode": "src_base", "endpoint_id": 3, "baseMode": "src_base"},
    }
    assert result[1]["node_code"] == "map_1"


@pytest.mark.parametrize("params", [{}, {"baseMode": "unknown"}, {"base_mode": "tgt_base", "baseMode": "src_base"}])
def test_endpoint_select_rejects_missing_or_ambiguous_mode(params):
    with pytest.raises(SyncMaterializationError):
        materialize_endpoint_nodes([{"node_code": "select_1", "node_type": "endpoint_select", "params": params}])
