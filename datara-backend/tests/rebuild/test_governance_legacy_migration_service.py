from datetime import datetime, timezone

import pytest

from rebuild.governance.legacy_dry_run import I18TargetSnapshot
from rebuild.governance.legacy_migration_service import build_i18_legacy_dry_run
from rebuild.governance.legacy_source_reader import LEGACY_SCHEMA, LegacyI18SourceSnapshot


def _source_snapshot(biz_domain="交易"):
    return LegacyI18SourceSnapshot(
        schema=LEGACY_SCHEMA,
        captured_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        digest="b" * 64,
        counts={
            "t_biz_domain": 1,
            "t_dw_layer": 1,
            "t_engine_type": 1,
            "t_dw_model": 1,
            "t_dw_model_field": 1,
            "t_dw_model_relation": 0,
            "t_dw_model_version": 0,
        },
        rows={
            "t_biz_domain": ({"id": 5, "name": "交易", "remark": "订单域"},),
            "t_dw_layer": ({"code": "DWD", "name": "明细层", "rule": "dwd_*", "color": "#123456", "seq": 2},),
            "t_engine_type": ({"name": "Doris", "ddl": "doris", "xc": True},),
            "t_dw_model": (
                {
                    "id": 17,
                    "code": "orders",
                    "name": "订单",
                    "layer": "DWD",
                    "type": "明细表",
                    "biz_domain": biz_domain,
                    "engine": "Doris",
                },
            ),
            "t_dw_model_field": ({"id": 29, "model_id": 17, "seq": 1, "name": "order_id"},),
            "t_dw_model_relation": (),
            "t_dw_model_version": (),
        },
    )


def _target_snapshot():
    return I18TargetSnapshot(
        project_id=41,
        captured_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        digest="a" * 64,
        row_fingerprints={},
        target_ids={},
        model_fields={},
        unique_key_owners={},
    )


def test_service_maps_source_rows_and_emits_deterministic_plan_without_db_writes():
    result = build_i18_legacy_dry_run(41, _source_snapshot(), _target_snapshot())

    assert result.plan.ready_to_import
    assert result.plan.source_count == 5
    assert result.plan.counts == {"create": 5, "unchanged": 0, "conflict": 0, "blocked": 0, "skipped": 0}
    assert [table for table, _source_id in result.plan.import_order] == [
        "t_biz_domain",
        "t_dw_layer",
        "t_engine_type",
        "t_dw_model",
        "t_dw_model_field",
    ]
    assert result.source_digest == "b" * 64
    assert result.target_digest == "a" * 64


def test_service_blocks_unknown_domain_reference_and_dependent_model_field():
    result = build_i18_legacy_dry_run(41, _source_snapshot(biz_domain="未登记域"), _target_snapshot())

    assert result.plan.counts == {"create": 3, "unchanged": 0, "conflict": 0, "blocked": 2, "skipped": 0}
    assert {issue.code for issue in result.plan.blocking_issues} == {
        "unresolved_reference",
        "dependency_not_importable",
        "pending_identity_missing_from_batch",
    }
    assert all(table not in {"t_dw_model", "t_dw_model_field"} for table, _ in result.plan.import_order)


def test_service_skips_only_the_approved_orphan_version_and_keeps_source_identity_accounted():
    source = _source_snapshot()
    rows = dict(source.rows)
    rows["t_dw_model_version"] = ({"id": 1, "model_id": 1, "version": 1, "snapshot_json": "{}"},)
    counts = dict(source.counts)
    counts["t_dw_model_version"] = 1
    source = LegacyI18SourceSnapshot(
        schema=source.schema,
        captured_at=source.captured_at,
        digest=source.digest,
        counts=counts,
        rows=rows,
    )

    result = build_i18_legacy_dry_run(41, source, _target_snapshot())

    assert result.plan.counts["skipped"] == 1
    assert result.plan.counts["blocked"] == 0
    assert result.plan.source_count == sum(result.plan.counts.values())
    skipped = next(entry for entry in result.plan.entries if entry.source_table == "t_dw_model_version")
    assert skipped.source_id == "1"
    assert skipped.disposition == "skipped"
    assert skipped.disposition_reason == "approved_missing_model_reference"


def test_service_fails_closed_if_the_approved_orphan_version_row_changes():
    source = _source_snapshot()
    rows = dict(source.rows)
    rows["t_dw_model_version"] = ({"id": 1, "model_id": 3, "version": 1, "snapshot_json": "{}"},)
    counts = dict(source.counts)
    counts["t_dw_model_version"] = 1
    source = LegacyI18SourceSnapshot(source.schema, source.captured_at, source.digest, counts, rows)

    with pytest.raises(ValueError, match="approved skip precondition changed"):
        build_i18_legacy_dry_run(41, source, _target_snapshot())
