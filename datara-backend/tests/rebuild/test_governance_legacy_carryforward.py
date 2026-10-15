from rebuild.common.db import Base
from rebuild.governance import models


EXPECTED_CARRY_FORWARD_TABLES = {
    "rebuild_governance_domain",
    "rebuild_governance_warehouse_layer",
    "rebuild_governance_model_engine",
    "rebuild_governance_warehouse_model",
    "rebuild_governance_warehouse_model_field",
    "rebuild_governance_warehouse_model_relation",
    "rebuild_governance_warehouse_model_relation_field",
    "rebuild_governance_warehouse_model_version",
    "rebuild_governance_asset_metadata_extension",
    "rebuild_governance_legacy_tag_definition",
    "rebuild_governance_legacy_tag_reference",
    "rebuild_governance_semantic_metric_profile",
    "rebuild_governance_semantic_metric_dimension",
    "rebuild_governance_semantic_metric_version",
    "rebuild_governance_quality_task",
    "rebuild_governance_quality_task_rule",
    "rebuild_governance_quality_rule_definition",
    "rebuild_governance_quality_run_legacy_details",
    "rebuild_governance_quality_exception",
    "rebuild_governance_quality_report",
    "rebuild_governance_quality_alarm_policy",
    "rebuild_governance_standard_element",
    "rebuild_governance_standard_code_set",
    "rebuild_governance_standard_code_value",
    "rebuild_governance_standard_naming_rule",
    "rebuild_governance_standard_mapping",
    "rebuild_governance_standard_approval",
    "rebuild_governance_standard_check_report",
    "rebuild_governance_legacy_identity_mapping",
}


def test_normalized_carry_forward_registers_every_legacy_semantic_entity():
    carry_forward_tables = getattr(models, "LEGACY_CARRY_FORWARD_TABLES", ())

    assert {table.name for table in carry_forward_tables} == EXPECTED_CARRY_FORWARD_TABLES
    assert EXPECTED_CARRY_FORWARD_TABLES <= set(Base.metadata.tables)


def test_every_carry_forward_entity_has_source_identity_and_database_timestamps():
    carry_forward_tables = getattr(models, "LEGACY_CARRY_FORWARD_TABLES", ())
    required_columns = {
        "source_system",
        "source_table",
        "source_id",
        "migration_batch_id",
        "created_at",
        "updated_at",
        "generated_at",
    }

    assert carry_forward_tables
    for table in carry_forward_tables:
        assert required_columns <= set(table.columns.keys()), table.name


def test_normalized_children_have_real_foreign_keys_not_json_only_links():
    carry_forward_tables = {table.name: table for table in getattr(models, "LEGACY_CARRY_FORWARD_TABLES", ())}

    expected_foreign_keys = {
        "rebuild_governance_warehouse_model_field": {"rebuild_governance_warehouse_model.id"},
        "rebuild_governance_warehouse_model_relation_field": {
            "rebuild_governance_warehouse_model_relation.id"
        },
        "rebuild_governance_semantic_metric_dimension": {"rebuild_governance_semantic_metric.id"},
        "rebuild_governance_semantic_metric_profile": {"rebuild_governance_semantic_metric.id"},
        "rebuild_governance_quality_task_rule": {"rebuild_governance_quality_task.id"},
        "rebuild_governance_quality_rule_definition": {"rebuild_governance_quality_rule.id"},
        "rebuild_governance_quality_run_legacy_details": {"rebuild_governance_quality_run.id"},
        "rebuild_governance_standard_code_value": {"rebuild_governance_standard_code_set.id"},
        "rebuild_governance_standard_approval": {"rebuild_governance_standard.id"},
    }

    assert carry_forward_tables
    for table_name, expected_targets in expected_foreign_keys.items():
        actual_targets = {foreign_key.target_fullname for foreign_key in carry_forward_tables[table_name].foreign_keys}
        assert expected_targets <= actual_targets, table_name


def test_metric_quality_and_unresolved_tag_extensions_preserve_legacy_fields():
    tables = {table.name: table for table in getattr(models, "LEGACY_CARRY_FORWARD_TABLES", ())}

    expected_fields = {
        "rebuild_governance_warehouse_model": {"security_level", "built_at", "built_by", "owner_name"},
        "rebuild_governance_asset_metadata_extension": {"security_level"},
        "rebuild_governance_legacy_tag_definition": {"tag_category", "color", "tag_description"},
        "rebuild_governance_legacy_tag_reference": {"target_type", "target_key"},
        "rebuild_governance_semantic_metric_profile": {
            "source_kind",
            "source_reference",
            "source_field",
            "output_table",
            "output_task",
            "period",
            "unit",
            "base_metric_id",
            "aggregation_function",
            "numerator_field",
            "time_field",
            "dimension_field",
            "filter_condition",
        },
        "rebuild_governance_quality_rule_definition": {
            "rule_type",
            "target_database",
            "target_table",
            "target_column",
            "params_json",
            "threshold",
        },
        "rebuild_governance_quality_run_legacy_details": {
            "trigger_source",
            "started_at",
            "finished_at",
            "legacy_result",
            "score",
            "stats_json",
        },
    }

    assert tables
    for table_name, fields in expected_fields.items():
        assert fields <= set(tables[table_name].columns.keys()), table_name
