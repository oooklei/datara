from datetime import datetime

import pytest

from rebuild.governance.legacy_mapping import (
    LegacyMappingContext,
    LegacyMappingError,
    map_legacy_row,
)


def test_maps_legacy_warehouse_model_without_guessing_project_or_dictionary_ids():
    created = datetime(2026, 10, 12, 22, 25, 28)
    source = {
        "id": 17,
        "code": "dwd_order",
        "name": "订单明细",
        "layer": "DWD",
        "type": "明细表",
        "biz_domain": "交易",
        "engine": "Doris",
        "ds_id": 3,
        "db_name": "warehouse",
        "security_level": "内部",
        "status": "published",
        "version": 4,
        "er_pos": {"x": 120, "y": 80},
        "last_ddl": "CREATE TABLE dwd_order (...) ",
        "built_at": None,
        "built_by": "designer",
        "owner": "data-team",
        "remark": "keep source semantics",
        "create_time": created,
        "update_time": created,
    }
    context = LegacyMappingContext(
        target_project_id=41,
        target_ids={
            ("t_dw_layer", "DWD"): 8,
            ("t_biz_domain", "交易"): 9,
            ("t_engine_type", "Doris"): 10,
        },
    )

    mapped = map_legacy_row("t_dw_model", source, context)

    assert mapped.target_table == "rebuild_governance_warehouse_model"
    assert mapped.source_system == "datara_meta"
    assert mapped.source_table == "t_dw_model"
    assert mapped.source_id == "17"
    assert mapped.values["project_id"] == 41
    assert mapped.values["layer_id"] == 8
    assert mapped.values["domain_id"] == 9
    assert mapped.values["engine_id"] == 10
    assert mapped.values["security_level"] == "内部"
    assert mapped.values["last_ddl_snapshot"] == source["last_ddl"]
    assert mapped.values["source_created_at"] == created
    assert mapped.values["source_updated_at"] == created
    assert mapped.unresolved_references == ()


def test_rejects_project_scoped_legacy_mapping_without_explicit_target_project():
    with pytest.raises(LegacyMappingError, match="target project must be explicit"):
        map_legacy_row("t_dw_model", {"id": 17, "code": "dwd_order", "name": "订单明细"}, LegacyMappingContext())


def test_reports_unresolved_required_legacy_references_instead_of_guessing():
    mapped = map_legacy_row(
        "t_dw_model",
        {"id": 17, "code": "dwd_order", "name": "订单明细", "layer": "DWD", "biz_domain": "交易", "engine": "Doris"},
        LegacyMappingContext(target_project_id=41),
    )

    assert mapped.values["layer_id"] is None
    assert mapped.values["domain_id"] is None
    assert mapped.values["engine_id"] is None
    assert mapped.unresolved_references == (
        ("layer", "DWD"),
        ("biz_domain", "交易"),
        ("engine", "Doris"),
    )
    assert not mapped.ready_to_import
