from datetime import datetime
from types import SimpleNamespace

from rebuild.governance.legacy_i19_mapping import (
    I19ScopedTarget,
    I19TagTarget,
    LegacyI19MappingContext,
    map_i19_snapshot,
)
from rebuild.governance.legacy_mapping import TargetIdentityReference
from rebuild.governance.legacy_source_reader import I19_SOURCE_COLUMNS


def _row(table, **values):
    row = {column: None for column in I19_SOURCE_COLUMNS[table][1]}
    row.update(values)
    return row


def _snapshot(**table_rows):
    return SimpleNamespace(
        schema="datara_meta", rows={table: tuple(table_rows.get(table, ())) for table in I19_SOURCE_COLUMNS}
    )


def _context(**overrides):
    values = {"target_project_id": 7}
    values.update(overrides)
    return LegacyI19MappingContext(**values)


def _extension(**overrides):
    values = {
        "id": 1,
        "ds_id": 10,
        "db_name": "ods",
        "table_name": "orders",
        "biz_domain": "交易域",
        "security_level": "内部",
        "owner": "quality",
        "remark": "catalog note",
        "create_time": "2026-01-01T00:00:00",
        "update_time": "2026-02-01T00:00:00",
    }
    values.update(overrides)
    return _row("t_meta_table_ext", **values)


def _tag(**overrides):
    values = {
        "id": 3,
        "name": "核心数据",
        "cat": "用途",
        "color": "#1677ff",
        "desc": "important data",
        "create_time": "2026-01-01T00:00:00",
        "update_time": "2026-02-01T00:00:00",
    }
    values.update(overrides)
    return _row("t_meta_tag", **values)


def _tagging(**overrides):
    values = {
        "id": 5,
        "tag_id": 3,
        "target_type": "table",
        "target_key": "10/ods/orders",
        "created_by": "operator",
        "create_time": "2026-02-02T00:00:00",
    }
    values.update(overrides)
    return _row("t_meta_tagging", **values)


def test_i19_mapper_preserves_extension_tag_definition_and_exact_asset_reference():
    mapped = map_i19_snapshot(
        _snapshot(t_meta_table_ext=[_extension()], t_meta_tag=[_tag()], t_meta_tagging=[_tagging()]),
        _context(
            asset_targets={(10, "ods", "orders"): I19ScopedTarget(500, 7)},
            tagging_asset_targets={("table", "10/ods/orders"): I19ScopedTarget(500, 7)},
        ),
    )

    assert mapped.ready_to_import
    extension = mapped.extensions[0]
    assert extension.target_table == "rebuild_governance_asset_metadata_extension"
    assert extension.values["asset_id"] == 500
    assert extension.values["legacy_datasource_id"] == 10
    assert extension.values["business_domain"] == "交易域"
    assert extension.values["source_created_at"] == datetime(2026, 1, 1)
    tag = mapped.tags[0]
    assert tag.normalized_tag_values == {
        "project_id": 7,
        "namespace": "legacy_i19",
        "tag_key": "legacy-3",
        "display_name": "核心数据",
        "description": "important data",
    }
    assert tag.definition.values["tag_category"] == "用途"
    assert tag.definition.values["color"] == "#1677ff"
    reference = mapped.tag_references[0]
    assert reference.values["tag_id"] == TargetIdentityReference("i19_normalized_tag", "3")
    assert reference.values["legacy_tag_definition_id"] == TargetIdentityReference("t_meta_tag", "3")
    assert reference.values["resolved_asset_id"] == 500
    assert reference.values["target_key"] == "10/ods/orders"


def test_i19_mapper_empty_snapshot_is_ready_with_explicit_project_scope():
    mapped = map_i19_snapshot(_snapshot(), _context())

    assert mapped.ready_to_import
    assert mapped.mapping_issues == ()
    assert mapped.extensions == mapped.tags == mapped.tag_references == ()


def test_i19_mapper_requires_exact_project_asset_identity_for_table_extension():
    mapped = map_i19_snapshot(_snapshot(t_meta_table_ext=[_extension()]), _context())

    assert not mapped.ready_to_import
    assert mapped.extensions[0].values["asset_id"] == TargetIdentityReference("i19_asset_identity", "10/ods/orders")
    assert "unresolved_asset_identity" in {issue.code for issue in mapped.mapping_issues}


def test_i19_mapper_blocks_cross_project_asset_and_tag_targets():
    mapped = map_i19_snapshot(
        _snapshot(t_meta_table_ext=[_extension()], t_meta_tag=[_tag()], t_meta_tagging=[_tagging()]),
        _context(
            asset_targets={(10, "ods", "orders"): I19ScopedTarget(500, 8)},
            tagging_asset_targets={("table", "10/ods/orders"): I19ScopedTarget(500, 8)},
        ),
    )

    assert not mapped.ready_to_import
    assert "cross_project_target_identity" in {issue.code for issue in mapped.mapping_issues}


def test_i19_mapper_preserves_unknown_tag_target_key_as_unresolved_without_guessing():
    mapped = map_i19_snapshot(
        _snapshot(t_meta_tag=[_tag()], t_meta_tagging=[_tagging(target_type="future", target_key="raw/key")]),
        _context(),
    )

    assert mapped.ready_to_import
    reference = mapped.tag_references[0]
    assert reference.values["target_type"] == "future"
    assert reference.values["target_key"] == "raw/key"
    assert reference.values["resolved_asset_id"] is None
    assert reference.mapping_notes == ({"resolution": "unresolved", "reason": "no exact project asset identity"},)


def test_i19_mapper_uses_explicit_existing_tag_identity_and_target_record_ids():
    mapped = map_i19_snapshot(
        _snapshot(t_meta_tag=[_tag()], t_meta_tagging=[_tagging()]),
        _context(
            target_ids={("t_meta_tag", "3"): 703, ("t_meta_tagging", "5"): 705},
            tag_targets={"3": I19TagTarget(normalized_tag_id=603, project_id=7, legacy_definition_id=703)},
            tagging_asset_targets={("table", "10/ods/orders"): I19ScopedTarget(500, 7)},
        ),
    )

    assert mapped.ready_to_import
    assert mapped.tags[0].normalized_tag_id == 603
    assert mapped.tags[0].definition.target_id == 703
    assert mapped.tag_references[0].target_id == 705
    assert mapped.tag_references[0].values["tag_id"] == 603
    assert mapped.tag_references[0].values["legacy_tag_definition_id"] == 703


def test_i19_mapper_blocks_orphan_tag_reference_without_lossless_tag_mapping():
    mapped = map_i19_snapshot(
        _snapshot(t_meta_tagging=[_tagging(tag_id=99)]),
        _context(),
    )

    assert not mapped.ready_to_import
    assert "unresolved_tag_identity" in {issue.code for issue in mapped.mapping_issues}


def test_i19_mapper_requires_complete_snapshot_and_project():
    missing = SimpleNamespace(schema="datara_meta", rows={"t_meta_tag": ()})
    assert "invalid_i19_snapshot_shape" in {
        issue.code for issue in map_i19_snapshot(missing, _context()).mapping_issues
    }
    assert "target_project_required" in {
        issue.code for issue in map_i19_snapshot(_snapshot(), LegacyI19MappingContext()).mapping_issues
    }


def test_i19_mapper_blocks_duplicate_source_and_natural_identities():
    mapped = map_i19_snapshot(
        _snapshot(
            t_meta_table_ext=[_extension(), _extension(id=2)],
            t_meta_tag=[_tag(), _tag(id=4)],
            t_meta_tagging=[_tagging(), _tagging(id=6)],
        ),
        _context(asset_targets={(10, "ods", "orders"): I19ScopedTarget(500, 7)}),
    )

    codes = {issue.code for issue in mapped.mapping_issues}
    assert "duplicate_asset_extension_identity" in codes
    assert "duplicate_tag_name" in codes
    assert "duplicate_tagging_identity" in codes
    assert not mapped.ready_to_import


def test_i19_mapper_rejects_invalid_target_ids_types_lengths_and_timezone_values():
    invalid_fields = map_i19_snapshot(
        _snapshot(
            t_meta_table_ext=[_extension(table_name="x" * 129)],
            t_meta_tag=[_tag(color="c" * 17)],
            t_meta_tagging=[_tagging(target_key=42)],
        ),
        _context(asset_targets={(10, "ods", "x" * 129): I19ScopedTarget(500, 7)}),
    )
    invalid_target = map_i19_snapshot(
        _snapshot(),
        _context(asset_targets={(10, "ods", "orders"): I19ScopedTarget(0, 7)}),
    )

    codes = {issue.code for issue in invalid_fields.mapping_issues}
    assert "target_text_too_long" in codes
    assert "invalid_source_value" in codes
    assert "invalid_scoped_target_id" in {issue.code for issue in invalid_target.mapping_issues}
    assert not invalid_fields.ready_to_import
    assert not invalid_target.ready_to_import


def test_i19_mapper_blocks_aware_or_date_only_source_timestamps():
    mapped = map_i19_snapshot(
        _snapshot(
            t_meta_table_ext=[_extension(create_time="2026-01-01")],
            t_meta_tag=[_tag(update_time="2026-02-01T00:00:00+08:00")],
        ),
        _context(asset_targets={(10, "ods", "orders"): I19ScopedTarget(500, 7)}),
    )

    codes = {issue.code for issue in mapped.mapping_issues}
    assert "invalid_source_value" in codes
    assert "timezone_aware_source_datetime" in codes
    assert not mapped.ready_to_import
