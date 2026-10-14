from datetime import datetime

import pytest

from rebuild.governance.legacy_mapping import (
    LegacyMappingContext,
    LegacyMappingError,
    TargetIdentityReference,
    map_legacy_row,
    validate_i18_mapping_graph,
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

    assert mapped.values["layer_id"] == TargetIdentityReference("t_dw_layer", "DWD")
    assert mapped.values["domain_id"] == TargetIdentityReference("t_biz_domain", "交易")
    assert mapped.values["engine_id"] == TargetIdentityReference("t_engine_type", "Doris")
    assert mapped.unresolved_references == (
        ("layer", "DWD"),
        ("biz_domain", "交易"),
        ("engine", "Doris"),
    )
    assert not mapped.ready_to_import


def test_maps_legacy_model_field_only_after_explicit_model_identity_resolution():
    created = datetime(2026, 10, 12, 22, 25, 30)
    source = {
        "id": 29,
        "model_id": 17,
        "seq": 2,
        "name": "order_amount",
        "data_type": "DECIMAL",
        "length": "18",
        "precision": "2",
        "nullable": False,
        "default_value": "0",
        "comment": "订单金额",
        "is_pk": False,
        "is_partition": True,
        "dict_ref": "currency_dim",
        "create_time": created,
        "update_time": created,
    }

    mapped = map_legacy_row(
        "t_dw_model_field",
        source,
        LegacyMappingContext(target_project_id=41, target_ids={("t_dw_model", "17"): 501}),
    )

    assert mapped.target_table == "rebuild_governance_warehouse_model_field"
    assert mapped.values == {
        "model_id": 501,
        "ordinal_position": 2,
        "field_name": "order_amount",
        "data_type": "DECIMAL",
        "length": "18",
        "precision": "2",
        "nullable": False,
        "default_value": "0",
        "description": "订单金额",
        "is_primary_key": False,
        "is_partition_key": True,
        "dictionary_reference": "currency_dim",
        "source_created_at": created,
        "source_updated_at": created,
    }
    assert mapped.unresolved_references == ()


def test_model_field_with_unresolved_model_identity_is_blocked():
    mapped = map_legacy_row(
        "t_dw_model_field",
        {"id": 29, "model_id": 17, "seq": 2, "name": "order_amount"},
        LegacyMappingContext(target_project_id=41),
    )

    assert mapped.unresolved_references == (("model_id", "17"),)
    assert not mapped.ready_to_import


def test_model_field_can_reference_a_model_scheduled_in_the_same_batch():
    mapped = map_legacy_row(
        "t_dw_model_field",
        {"id": 29, "model_id": 17, "seq": 2, "name": "order_amount"},
        LegacyMappingContext(
            target_project_id=41,
            pending_identities=frozenset({("t_dw_model", "17")}),
        ),
    )

    assert mapped.values["model_id"] == TargetIdentityReference("t_dw_model", "17")
    assert mapped.ready_to_import


def test_maps_legacy_model_version_snapshot_without_rewriting_its_payload():
    snapshot = '{"model":{"id":17},"fields":[{"name":"id"}],"relations":[]}'
    created = datetime(2026, 10, 13, 0, 56, 25)

    mapped = map_legacy_row(
        "t_dw_model_version",
        {
            "id": 72,
            "model_id": 17,
            "version": 4,
            "snapshot_json": snapshot,
            "change_note": "字段调整",
            "created_by": "designer",
            "create_time": created,
            "update_time": created,
        },
        LegacyMappingContext(target_project_id=41, target_ids={("t_dw_model", "17"): 501}),
    )

    assert mapped.target_table == "rebuild_governance_warehouse_model_version"
    assert mapped.values["model_id"] == 501
    assert mapped.values["version"] == 4
    assert mapped.values["snapshot_json"] == snapshot
    assert mapped.values["change_note"] == "字段调整"
    assert mapped.values["created_by"] == "designer"
    assert mapped.values["source_created_at"] == created
    assert mapped.values["source_updated_at"] == created
    assert mapped.unresolved_references == ()


def test_maps_legacy_model_relation_and_preserves_field_pairs_as_child_rows():
    mapped = map_legacy_row(
        "t_dw_model_relation",
        {
            "id": 91,
            "src_model_id": 17,
            "tgt_model_id": 18,
            "rel_type": "1:N",
            "src_fields": '["order_id", "tenant_id"]',
            "tgt_fields": '["id", "tenant_id"]',
            "join_desc": "订单关联",
            "created_by": "designer",
        },
        LegacyMappingContext(
            target_project_id=41,
            target_ids={("t_dw_model", "17"): 501, ("t_dw_model", "18"): 502},
        ),
    )

    assert mapped.target_table == "rebuild_governance_warehouse_model_relation"
    assert mapped.values == {
        "project_id": 41,
        "source_model_id": 501,
        "target_model_id": 502,
        "relation_type": "1:N",
        "join_description": "订单关联",
        "created_by": "designer",
        "source_created_at": None,
        "source_updated_at": None,
    }
    assert mapped.child_rows == (
        {
            "ordinal_position": 1,
            "source_field_name": "order_id",
            "target_field_name": "id",
        },
        {
            "ordinal_position": 2,
            "source_field_name": "tenant_id",
            "target_field_name": "tenant_id",
        },
    )
    assert mapped.unresolved_references == ()


def test_model_relation_can_reference_models_scheduled_in_the_same_batch():
    mapped = map_legacy_row(
        "t_dw_model_relation",
        {"id": 91, "src_model_id": 17, "tgt_model_id": 18},
        LegacyMappingContext(
            target_project_id=41,
            pending_identities=frozenset({("t_dw_model", "17"), ("t_dw_model", "18")}),
        ),
    )

    assert mapped.values["source_model_id"] == TargetIdentityReference("t_dw_model", "17")
    assert mapped.values["target_model_id"] == TargetIdentityReference("t_dw_model", "18")
    assert mapped.ready_to_import


def test_graph_validation_rejects_relation_fields_missing_from_either_model():
    pending = frozenset({("t_dw_model", "17"), ("t_dw_model", "18")})
    context = LegacyMappingContext(target_project_id=41, pending_identities=pending)
    rows = [
        map_legacy_row("t_dw_model", {"id": 17, "code": "orders", "name": "订单"}, context),
        map_legacy_row("t_dw_model", {"id": 18, "code": "users", "name": "用户"}, context),
        map_legacy_row(
            "t_dw_model_field", {"id": 1, "model_id": 17, "seq": 1, "name": "order_id"}, context
        ),
        map_legacy_row(
            "t_dw_model_field", {"id": 2, "model_id": 18, "seq": 1, "name": "user_id"}, context
        ),
        map_legacy_row(
            "t_dw_model_relation",
            {"id": 3, "src_model_id": 17, "tgt_model_id": 18, "src_fields": '["missing"]', "tgt_fields": '["user_id"]'},
            context,
        ),
    ]

    issues = validate_i18_mapping_graph(rows)

    assert [(issue.code, issue.source_id, issue.detail) for issue in issues] == [
        ("relation_source_field_missing", "3", "missing")
    ]


def test_graph_validation_checks_target_model_field_names_too():
    context = LegacyMappingContext(
        target_project_id=41,
        pending_identities=frozenset({("t_dw_model", "17"), ("t_dw_model", "18")}),
    )
    rows = [
        map_legacy_row("t_dw_model", {"id": 17, "code": "orders", "name": "订单"}, context),
        map_legacy_row("t_dw_model", {"id": 18, "code": "users", "name": "用户"}, context),
        map_legacy_row(
            "t_dw_model_field", {"id": 1, "model_id": 17, "seq": 1, "name": "order_id"}, context
        ),
        map_legacy_row(
            "t_dw_model_field", {"id": 2, "model_id": 18, "seq": 1, "name": "user_id"}, context
        ),
        map_legacy_row(
            "t_dw_model_relation",
            {
                "id": 3,
                "src_model_id": 17,
                "tgt_model_id": 18,
                "src_fields": '["order_id"]',
                "tgt_fields": '["missing"]',
            },
            context,
        ),
    ]

    issues = validate_i18_mapping_graph(rows)

    assert [(issue.code, issue.source_id, issue.detail) for issue in issues] == [
        ("relation_target_field_missing", "3", "missing")
    ]


@pytest.mark.parametrize(
    ("source_fields", "target_fields"),
    [("not-json", "[]"), ('["a"]', "[]"), ('[1]', '["a"]')],
)
def test_rejects_malformed_legacy_relation_field_pairs(source_fields, target_fields):
    with pytest.raises(LegacyMappingError, match="relation field pairs"):
        map_legacy_row(
            "t_dw_model_relation",
            {
                "id": 91,
                "src_model_id": 17,
                "tgt_model_id": 18,
                "src_fields": source_fields,
                "tgt_fields": target_fields,
            },
            LegacyMappingContext(
                target_project_id=41,
                target_ids={("t_dw_model", "17"): 501, ("t_dw_model", "18"): 502},
            ),
        )


@pytest.mark.parametrize(
    ("table", "source", "target_table", "target_values", "identity"),
    [
        (
            "t_dw_layer",
            {"code": "DWD", "name": "明细层", "rule": "dwd_*", "color": "#123456", "seq": 2},
            "rebuild_governance_warehouse_layer",
            {"code": "DWD", "name": "明细层", "naming_rule": "dwd_*", "color": "#123456", "sequence": 2},
            "DWD",
        ),
        (
            "t_biz_domain",
            {"id": 5, "name": "交易", "remark": "订单域"},
            "rebuild_governance_domain",
            {"name": "交易", "description": "订单域"},
            "5",
        ),
        (
            "t_engine_type",
            {"name": "Doris", "ddl": "doris", "xc": True},
            "rebuild_governance_model_engine",
            {"name": "Doris", "ddl_dialect": "doris", "vendor_flag": True},
            "Doris",
        ),
    ],
)
def test_maps_legacy_model_dictionaries_with_explicit_project_scope(
    table, source, target_table, target_values, identity
):
    mapped = map_legacy_row(table, source, LegacyMappingContext(target_project_id=41))

    assert mapped.target_table == target_table
    assert mapped.source_id == identity
    assert {key: mapped.values[key] for key in target_values} == target_values
    assert mapped.values["project_id"] == 41


def test_domain_name_reference_uses_declared_unique_source_alias_not_name_matching():
    domain = map_legacy_row(
        "t_biz_domain",
        {"id": 5, "name": "交易", "remark": "订单域"},
        LegacyMappingContext(target_project_id=41),
    )
    model = map_legacy_row(
        "t_dw_model",
        {"id": 17, "code": "orders", "name": "订单", "biz_domain": "交易"},
        LegacyMappingContext(
            target_project_id=41,
            pending_identities=frozenset({("t_biz_domain", "交易")}),
        ),
    )

    assert domain.source_id == "5"
    assert domain.identity_aliases == (("t_biz_domain", "交易"),)
    assert model.values["domain_id"] == TargetIdentityReference("t_biz_domain", "交易")
    assert model.ready_to_import
