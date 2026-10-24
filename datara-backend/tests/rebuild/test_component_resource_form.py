import json

from scripts.seed_rebuild_component_catalog import _normalize_spec_json


def test_executable_component_specs_declare_versioned_resource_reference():
    for kind, extension in (("sql", ".sql"), ("python", ".py"), ("shell", ".sh")):
        spec = json.loads(_normalize_spec_json(json.dumps({"form": {"params": []}}), kind))
        params = {item["key"]: item for item in spec["form"]["params"]}
        assert params["sourceMode"]["default"] == "inline"
        assert params["resourceRef"]["uiType"] == "resource"
        assert params["resourceRef"]["cap"]["kind"] == kind
        assert extension in params["resourceRef"]["cap"]["extensions"]
        assert params["resourceRef"]["cap"]["versioned"] is True
        assert params["resourceRef"]["cap"]["allowLatest"] is False
        assert any(item["id"] == "c-resource-mode" for item in spec["form"]["conditions"])


def test_normalization_is_idempotent_for_resource_fields():
    first = _normalize_spec_json(json.dumps({"form": {"params": []}}), "python")
    second = _normalize_spec_json(first, "python")
    assert json.loads(first) == json.loads(second)
