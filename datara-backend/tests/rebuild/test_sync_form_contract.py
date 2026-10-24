import pytest

from rebuild.workflow.repository import WorkflowDomainError, _validate_sync_form_params


def test_endpoint_select_rejects_conflicting_aliases_and_bad_file_options():
    with pytest.raises(WorkflowDomainError, match="aliases"):
        _validate_sync_form_params("endpoint_select", {"baseMode": "src_base", "base_mode": "tgt_base"})
    with pytest.raises(WorkflowDomainError, match="fileType"):
        _validate_sync_form_params("endpoint_select", {"fileType": "json"})
    with pytest.raises(WorkflowDomainError, match="fileHeaderRows"):
        _validate_sync_form_params("endpoint_select", {"fileHeaderRows": -1})


def test_sync_forms_accept_empty_and_serializable_contract_values():
    _validate_sync_form_params("endpoint_select", {})
    _validate_sync_form_params("field_map", {"fieldMap": [{"from": "id", "to": "user_id"}]})
    _validate_sync_form_params("field_map_union", {"fieldMap": [{"key": "id", "value": "user_id"}]})
    _validate_sync_form_params("condition_set", {"filterExpr": "status = 1", "incrementalExpr": "${day}"})


@pytest.mark.parametrize(
    ("node_type", "params"),
    [
        ("field_map", {"fieldMap": [{"from": "id"}]}),
        ("field_map_union", {"fieldMap": ["id->user_id"]}),
        ("condition_set", {"incrementalColumn": 42}),
        ("endpoint_select", {"baseMode": "invalid"}),
    ],
)
def test_sync_forms_reject_non_contract_values(node_type, params):
    with pytest.raises(WorkflowDomainError) as exc:
        _validate_sync_form_params(node_type, params)
    assert exc.value.code == "WF_SYNC_FORM_INVALID"
