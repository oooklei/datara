from datetime import datetime, timezone

from rebuild.governance.legacy_dry_run import I18TargetSnapshot, build_i18_dry_run_plan, semantic_fingerprint
from rebuild.governance.legacy_mapping import LegacyMappingContext, map_legacy_row


def _mapped_i18_rows(existing_model_id=None):
    target_ids = {("t_dw_model", "17"): existing_model_id} if existing_model_id is not None else {}
    context = LegacyMappingContext(
        target_project_id=41,
        target_ids=target_ids,
        pending_identities=frozenset({("t_dw_model", "17")}),
    )
    return [
        map_legacy_row("t_dw_model", {"id": 17, "code": "orders", "name": "订单"}, context),
        map_legacy_row(
            "t_dw_model_field",
            {"id": 29, "model_id": 17, "seq": 1, "name": "order_id", "data_type": "BIGINT"},
            context,
        ),
    ]


def _snapshot(project_id, fingerprints=None, target_ids=None, model_fields=None, unique_key_owners=None):
    return I18TargetSnapshot(
        project_id=project_id,
        captured_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        digest="a" * 64,
        row_fingerprints=fingerprints or {},
        target_ids=target_ids
        or {identity: 500 + index for index, identity in enumerate((fingerprints or {}).keys())},
        model_fields=model_fields or {},
        unique_key_owners=unique_key_owners or {},
    )


def test_dry_run_classifies_create_and_unchanged_only_from_target_snapshot():
    rows = _mapped_i18_rows(existing_model_id=517)
    fingerprints = {("t_dw_model", "17"): semantic_fingerprint(rows[0])}

    plan = build_i18_dry_run_plan(
        rows,
        project_id=41,
        snapshot=I18TargetSnapshot(
            project_id=41,
            captured_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
            digest="a" * 64,
            row_fingerprints=fingerprints,
            target_ids={("t_dw_model", "17"): 517},
            model_fields={517: frozenset()},
            unique_key_owners={},
        ),
    )

    assert plan.source_count == 2
    assert plan.counts == {"create": 1, "unchanged": 1, "conflict": 0, "blocked": 0, "skipped": 0}
    assert plan.import_order == (("t_dw_model_field", "29"),)
    assert plan.blocking_issues == ()


def test_dry_run_retains_approved_orphan_as_explicit_skipped_item():
    context = LegacyMappingContext(
        target_project_id=41,
        pending_identities=frozenset({("t_dw_model_version", "1")}),
    )
    version = map_legacy_row(
        "t_dw_model_version",
        {"id": 1, "model_id": 1, "version": 1, "snapshot_json": "{}"},
        context,
    )

    plan = build_i18_dry_run_plan(
        [version],
        project_id=41,
        snapshot=_snapshot(41),
        approved_skips={("t_dw_model_version", "1"): "approved_missing_model_reference"},
    )

    assert plan.counts == {"create": 0, "unchanged": 0, "conflict": 0, "blocked": 0, "skipped": 1}
    assert plan.entries[0].disposition == "skipped"
    assert plan.entries[0].disposition_reason == "approved_missing_model_reference"
    assert plan.import_order == ()
    assert plan.ready_to_import
    assert plan.blocking_issues == ()


def test_dry_run_classifies_changed_existing_identity_as_conflict_not_update():
    rows = _mapped_i18_rows(existing_model_id=517)

    plan = build_i18_dry_run_plan(
        rows,
        project_id=41,
        snapshot=_snapshot(
            41,
            {("t_dw_model", "17"): "different-semantic-content"},
            target_ids={("t_dw_model", "17"): 517},
        ),
    )

    assert plan.counts == {"create": 1, "unchanged": 0, "conflict": 1, "blocked": 0, "skipped": 0}
    assert not any(entry.disposition == "update" for entry in plan.entries)


def test_dry_run_detects_project_scoped_unique_key_collision_without_source_identity():
    rows = _mapped_i18_rows()
    snapshot = _snapshot(
        41,
        unique_key_owners={("model", 41, "orders"): ("rebuild_governance_warehouse_model", "old-row")},
    )

    plan = build_i18_dry_run_plan(rows, project_id=41, snapshot=snapshot)

    assert plan.counts == {"create": 0, "unchanged": 0, "conflict": 1, "blocked": 1, "skipped": 0}
    collision = next(issue for issue in plan.blocking_issues if issue.code == "target_business_key_collision")
    assert collision.detail.endswith("rebuild_governance_warehouse_model:old-row")


def test_dry_run_blocks_unresolved_references_and_project_mismatch():
    context = LegacyMappingContext(
        target_project_id=41,
        pending_identities=frozenset({("t_dw_model", "17")}),
    )
    model = map_legacy_row(
        "t_dw_model",
        {"id": 17, "code": "orders", "name": "订单"},
        context,
    )
    row = map_legacy_row(
        "t_dw_model_field",
        {"id": 29, "model_id": 999, "seq": 1, "name": "order_id"},
        context,
    )

    plan = build_i18_dry_run_plan([model, row], project_id=42, snapshot=_snapshot(42))

    assert plan.counts == {"create": 0, "unchanged": 0, "conflict": 0, "blocked": 2, "skipped": 0}
    assert {issue.code for issue in plan.blocking_issues} == {
        "unresolved_reference",
        "project_scope_mismatch",
        "pending_identity_missing_from_batch",
    }


def test_dry_run_rejects_snapshot_for_a_different_project():
    rows = _mapped_i18_rows()

    plan = build_i18_dry_run_plan(rows, project_id=41, snapshot=_snapshot(42))

    assert plan.counts["blocked"] == 2
    assert {issue.code for issue in plan.blocking_issues} == {"target_snapshot_project_mismatch"}


def test_dry_run_blocks_child_when_parent_is_outside_selected_project():
    context = LegacyMappingContext(
        target_project_id=41,
        pending_identities=frozenset({("t_dw_model", "17")}),
    )
    rows = [
        map_legacy_row("t_dw_model", {"id": 17, "code": "orders", "name": "订单"}, context),
        map_legacy_row(
            "t_dw_model_field",
            {"id": 29, "model_id": 17, "seq": 1, "name": "order_id"},
            context,
        ),
    ]

    plan = build_i18_dry_run_plan(rows, project_id=42, snapshot=_snapshot(42))

    assert plan.counts["blocked"] == 2
    assert any(issue.code == "dependency_not_importable" for issue in plan.blocking_issues)


def test_semantic_fingerprint_is_stable_for_mapping_order_and_datetime_values():
    rows = _mapped_i18_rows()
    row = rows[0]
    reordered_values = dict(reversed(list(row.values.items())))
    reordered = type(row)(
        source_system=row.source_system,
        source_table=row.source_table,
        source_id=row.source_id,
        target_table=row.target_table,
        values=reordered_values,
        unresolved_references=row.unresolved_references,
        child_rows=row.child_rows,
        identity_aliases=row.identity_aliases,
    )

    assert semantic_fingerprint(row) == semantic_fingerprint(reordered)



def test_dry_run_blocks_invalid_model_field_sequence_before_import():
    context = LegacyMappingContext(
        target_project_id=41,
        pending_identities=frozenset({("t_dw_model", "17")}),
    )
    rows = [
        map_legacy_row("t_dw_model", {"id": 17, "code": "orders", "name": "orders"}, context),
        map_legacy_row(
            "t_dw_model_field",
            {"id": 29, "model_id": 17, "seq": 0, "name": "order_id"},
            context,
        ),
    ]

    plan = build_i18_dry_run_plan(rows, project_id=41, snapshot=_snapshot(41))

    assert plan.counts == {"create": 1, "unchanged": 0, "conflict": 0, "blocked": 1, "skipped": 0}
    assert not plan.ready_to_import
    issue = next(issue for issue in plan.blocking_issues if issue.code == "invalid_ordinal_position")
    assert (issue.source_table, issue.source_id) == ("t_dw_model_field", "29")
