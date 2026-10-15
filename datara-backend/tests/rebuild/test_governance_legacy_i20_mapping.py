from types import SimpleNamespace

from rebuild.governance.legacy_mapping import LegacyMappingContext, TargetIdentityReference
from rebuild.governance.legacy_i20_mapping import map_i20_snapshot


def _snapshot(metrics=None, versions=None):
    return SimpleNamespace(
        schema="datara_meta",
        rows={
            "t_indicator": tuple(metrics or ()),
            "t_indicator_version": tuple(versions or ()),
        },
    )


def _metric(**overrides):
    row = {
        "id": 2,
        "code": "M_ORDER_COUNT",
        "name": "订单数",
        "type": "原子",
        "biz_domain": "交易",
        "biz_def": "订单数量口径",
        "tech_def": "COUNT(order_id)",
        "src_kind": "table",
        "src_ref": "10/ods/orders",
        "src_field": "order_id",
        "out_table": "dws_order",
        "out_task": "refresh_orders",
        "period": "日",
        "dims": "日期/渠道",
        "unit": "单",
        "status": "published",
        "version": 2,
        "owner": "analyst",
        "base_metric_id": None,
        "agg_fn": "COUNT",
        "num_field": "order_id",
        "time_field": "order_date",
        "dim_field": "channel",
        "filter_cond": "status = 'valid'",
        "create_time": "2026-01-01T00:00:00",
        "update_time": "2026-02-01T00:00:00",
    }
    return row | overrides


def _version(**overrides):
    row = {
        "id": 21,
        "indicator_id": 2,
        "version": 1,
        "snapshot_json": '{"dims":"日期/渠道","version":1}',
        "change_note": "initial wording",
        "created_by": "analyst",
        "create_time": "2026-01-01T00:00:00",
    }
    return row | overrides


def _context(**kwargs):
    return LegacyMappingContext(target_project_id=7, pending_identities=frozenset({("t_indicator", "2")}), **kwargs)


def test_i20_mapper_preserves_metric_profile_raw_dimensions_and_history_versions():
    mapped = map_i20_snapshot(_snapshot([_metric()], [_version()]), _context())

    assert mapped.mapping_issues == ()
    assert len(mapped.metrics) == 1
    bundle = mapped.metrics[0]
    assert bundle.metric.target_table == "rebuild_governance_semantic_metric"
    assert bundle.metric.values == {
        "project_id": 7,
        "code": "M_ORDER_COUNT",
        "name": "订单数",
        "formula": "COUNT(order_id)",
        "description": "订单数量口径",
        "status": "active",
        "source_created_at": "2026-01-01T00:00:00",
        "source_updated_at": "2026-02-01T00:00:00",
    }
    assert bundle.profile_values["metric_id"] == TargetIdentityReference("t_indicator", "2")
    assert bundle.profile_values["business_domain"] == "交易"
    assert bundle.profile_values["business_definition"] == "订单数量口径"
    assert bundle.profile_values["technical_definition"] == "COUNT(order_id)"
    assert bundle.profile_values["legacy_dimensions"] == "日期/渠道"
    assert bundle.dimension_rows == ()
    assert bundle.profile_values["source_created_at"] == "2026-01-01T00:00:00"
    assert len(bundle.versions) == 1
    assert bundle.versions[0].values["snapshot_json"] == '{"dims":"日期/渠道","version":1}'
    assert bundle.versions[0].values["metric_id"] == TargetIdentityReference("t_indicator", "2")


def test_i20_mapper_preserves_draft_status_and_nullable_profile_fields():
    mapped = map_i20_snapshot(
        _snapshot([_metric(status="draft", base_metric_id=None, agg_fn=None, filter_cond=None)]), _context()
    )

    bundle = mapped.metrics[0]
    assert bundle.metric.values["status"] == "draft"
    assert bundle.profile_values["legacy_status"] == "draft"
    assert bundle.profile_values["aggregation_function"] is None
    assert bundle.profile_values["filter_condition"] is None
    assert mapped.mapping_issues == ()


def test_i20_mapper_resolves_base_metric_only_by_explicit_identity():
    metrics = [_metric(id=2, base_metric_id=1)]
    context = _context(
        target_ids={("t_indicator", "1"): 101},
    )

    mapped = map_i20_snapshot(_snapshot(metrics), context)

    assert mapped.metrics[0].profile_values["base_metric_id"] == 101
    assert mapped.mapping_issues == ()


def test_i20_mapper_keeps_same_batch_base_metric_as_pending_identity():
    metrics = [_metric(id=2, base_metric_id=1), _metric(id=1, code="M_BASE", name="基础指标")]
    context = LegacyMappingContext(
        target_project_id=7,
        pending_identities=frozenset({("t_indicator", "1"), ("t_indicator", "2")}),
    )

    mapped = map_i20_snapshot(_snapshot(metrics), context)

    child = next(bundle for bundle in mapped.metrics if bundle.metric.source_id == "2")
    assert child.profile_values["base_metric_id"] == TargetIdentityReference("t_indicator", "1")
    assert not mapped.mapping_issues


def test_i20_mapper_blocks_cycles_in_same_batch_base_metric_references():
    metrics = [
        _metric(id=1, code="M1", name="M1", base_metric_id=2),
        _metric(id=2, code="M2", name="M2", base_metric_id=1),
    ]
    context = LegacyMappingContext(
        target_project_id=7,
        pending_identities=frozenset({("t_indicator", "1"), ("t_indicator", "2")}),
    )

    mapped = map_i20_snapshot(_snapshot(metrics), context)

    assert {issue.code for issue in mapped.mapping_issues} == {"cyclic_base_metric_reference"}
    assert all(not bundle.ready_to_import for bundle in mapped.metrics)


def test_i20_mapper_marks_unresolved_base_metric_and_unknown_status_as_blockers():
    mapped = map_i20_snapshot(_snapshot([_metric(base_metric_id=99, status="archived")]), _context())

    codes = {issue.code for issue in mapped.mapping_issues}
    assert "unresolved_reference" in codes
    assert "unsupported_metric_status" in codes
    assert not mapped.metrics[0].metric.ready_to_import


def test_i20_mapper_reports_orphan_versions_without_dropping_source_identity():
    mapped = map_i20_snapshot(_snapshot([], [_version(indicator_id=99)]), _context())

    assert mapped.metrics == ()
    assert len(mapped.orphan_versions) == 1
    issue = mapped.orphan_versions[0]
    assert issue.source_table == "t_indicator_version"
    assert issue.source_id == "21"
    assert issue.code == "orphan_metric_version"


def test_i20_mapper_rejects_duplicate_metric_and_version_identities():
    mapped = map_i20_snapshot(
        _snapshot([_metric(), _metric(name="duplicate")], [_version(), _version(version=1, id=22)]), _context()
    )

    assert "duplicate_metric_identity" in {issue.code for issue in mapped.mapping_issues}
    assert "duplicate_metric_version" in {issue.code for issue in mapped.mapping_issues}


def test_i20_mapper_requires_explicit_project_and_complete_snapshot_shape():
    no_project = LegacyMappingContext()
    assert "target_project_required" in {
        issue.code for issue in map_i20_snapshot(_snapshot([_metric()]), no_project).mapping_issues
    }
    incomplete = SimpleNamespace(schema="datara_meta", rows={"t_indicator": ()})
    assert "invalid_i20_snapshot_shape" in {
        issue.code for issue in map_i20_snapshot(incomplete, _context()).mapping_issues
    }


def test_i20_mapper_blocks_values_that_cannot_fit_target_contract_without_truncation():
    mapped = map_i20_snapshot(_snapshot([_metric(code="x" * 129)]), _context())

    assert "metric_field_too_long" in {issue.code for issue in mapped.mapping_issues}
    assert not mapped.metrics[0].ready_to_import


def test_i20_mapper_blocks_incomplete_source_rows_and_unrepresentable_profile_values():
    incomplete = _metric()
    incomplete.pop("dims")
    missing = map_i20_snapshot(_snapshot([incomplete]), _context())
    long_dims = map_i20_snapshot(_snapshot([_metric(dims="d" * 256)]), _context())

    assert "incomplete_metric_source_row" in {issue.code for issue in missing.mapping_issues}
    assert "metric_profile_field_too_long" in {issue.code for issue in long_dims.mapping_issues}
