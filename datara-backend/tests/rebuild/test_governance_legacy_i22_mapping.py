from datetime import datetime
from types import SimpleNamespace

from rebuild.governance.legacy_mapping import LegacyMappingContext, TargetIdentityReference
from rebuild.governance.legacy_source_reader import I22_SOURCE_COLUMNS
from rebuild.governance.legacy_i22_mapping import map_i22_snapshot


CAPTURED = datetime(2026, 10, 15, 5, 0)


def _source_row(table: str, *, source_id: int = 1, **overrides):
    integer_fields = {"id", "biz_id", "version", "std_code_id", "seq", "length", "element_id", "code_id"}
    json_fields = {"payload_json", "summary_json", "issues_json"}
    date_fields = {"create_time", "update_time"}
    values = {}
    for name in I22_SOURCE_COLUMNS[table][1]:
        if name == "id":
            values[name] = source_id
        elif name in integer_fields:
            values[name] = None if name in {"length", "element_id", "code_id"} else 1
        elif name in json_fields:
            values[name] = {}
        elif name in date_fields:
            values[name] = CAPTURED
        else:
            values[name] = ""
    if table == "t_std_approval":
        values.update(biz_type="code", biz_id=1, action="submit", status="review")
    values.update(overrides)
    return values


def _snapshot(*, approval_id: int = 1, approval_biz_id: int = 1, include_code: bool = True):
    rows = {table: [] for table in I22_SOURCE_COLUMNS}
    if include_code:
        rows["t_std_code"].append(_source_row("t_std_code", code="C1", name="Status", status="draft"))
    rows["t_std_code_value"].append(_source_row("t_std_code_value", std_code_id=1, c="A", n="Active", seq=1))
    rows["t_std_approval"].append(
        _source_row(
            "t_std_approval", source_id=approval_id, biz_id=approval_biz_id, payload_json='{"id":1,"name":"Status"}'
        )
    )
    rows["t_std_element"].append(
        _source_row("t_std_element", code="E1", cn="状态", en="Status", data_type="varchar", length=16)
    )
    rows["t_std_naming_rule"].append(_source_row("t_std_naming_rule", name="snake", target="field", enabled=1))
    rows["t_std_mapping"].append(
        _source_row("t_std_mapping", name="source-map", target="orders.status", element_id=1, code_id=1)
    )
    rows["t_std_check_report"].append(
        _source_row("t_std_check_report", scope="project", summary_json='{"checked":1}', issues_json="[]")
    )
    return SimpleNamespace(schema="datara_meta", rows=rows, captured_at=CAPTURED)


def _context(**overrides):
    return LegacyMappingContext(
        target_project_id=7,
        pending_identities=frozenset({("t_std_code", "1"), ("t_std_element", "1")}),
        **overrides,
    )


def test_i22_mapper_preserves_all_seven_domains_and_resolves_parent_identities():
    mapped = map_i22_snapshot(_snapshot(), _context())

    assert mapped.ready_to_import
    assert len(mapped.elements) == len(mapped.code_sets) == len(mapped.code_values) == 1
    assert len(mapped.naming_rules) == len(mapped.mappings) == len(mapped.approvals) == len(mapped.check_reports) == 1
    assert mapped.code_sets[0].values["project_id"] == 7
    assert mapped.code_sets[0].values["source_created_at"] == CAPTURED
    assert mapped.code_values[0].values["code_set_id"] == TargetIdentityReference("t_std_code", "1")
    assert mapped.mappings[0].values["element_id"] == TargetIdentityReference("t_std_element", "1")
    assert mapped.mappings[0].values["code_set_id"] == TargetIdentityReference("t_std_code", "1")
    assert mapped.approvals[0].values["standard_id"] is None
    assert mapped.approvals[0].values["legacy_business_id"] == 1
    assert mapped.approvals[0].values["payload_json"] == '{"id":1,"name":"Status"}'
    assert mapped.check_reports[0].values["summary_json"] == '{"checked":1}'


def test_i22_mapper_fails_closed_for_orphan_approval_business_identity():
    mapped = map_i22_snapshot(_snapshot(approval_biz_id=2), _context())

    assert not mapped.ready_to_import
    assert any(
        issue.code == "unresolved_reference"
        and issue.source_table == "t_std_approval"
        and issue.source_id == "1"
        and issue.detail == "t_std_code:2"
        for issue in mapped.mapping_issues
    )
    assert mapped.approvals[0].values["legacy_business_id"] == 2
    assert mapped.approvals[0].values["standard_id"] is None


def test_i22_mapper_accepts_explicit_existing_identity_for_approval_reference():
    mapped = map_i22_snapshot(
        _snapshot(approval_biz_id=2),
        _context(target_ids={("t_std_code", "2"): 93}),
    )

    assert mapped.ready_to_import
    assert mapped.approvals[0].unresolved_references == ()
    assert mapped.approvals[0].values["legacy_business_id"] == 2
    assert mapped.approvals[0].values["standard_id"] is None


def test_i22_mapper_reports_orphan_code_value_parent_without_inventing_a_target():
    snapshot = _snapshot(include_code=False)
    mapped = map_i22_snapshot(snapshot, _context())

    assert not mapped.ready_to_import
    assert mapped.code_values[0].unresolved_references == (("t_std_code", "1"),)
    assert any(
        issue.code == "unresolved_reference" and issue.source_table == "t_std_code_value"
        for issue in mapped.mapping_issues
    )


def test_i22_mapper_resolves_existing_target_ids_and_keeps_nullable_mapping_references_null():
    snapshot = _snapshot()
    snapshot.rows["t_std_mapping"][0]["element_id"] = None
    mapped = map_i22_snapshot(
        snapshot,
        _context(target_ids={("t_std_code", "1"): 91, ("t_std_element", "1"): 92}),
    )

    assert mapped.ready_to_import
    assert mapped.code_values[0].values["code_set_id"] == 91
    assert mapped.mappings[0].values["element_id"] is None
    assert mapped.mappings[0].values["code_set_id"] == 91


def test_i22_mapper_rejects_unknown_approval_type_bad_json_and_invalid_enabled():
    snapshot = _snapshot()
    snapshot.rows["t_std_approval"][0]["biz_type"] = "unmapped"
    snapshot.rows["t_std_check_report"][0]["summary_json"] = "not-json"
    snapshot.rows["t_std_naming_rule"][0]["enabled"] = 2

    mapped = map_i22_snapshot(snapshot, _context())

    codes = {issue.code for issue in mapped.mapping_issues}
    assert {"unknown_approval_business_type", "invalid_json_value", "invalid_source_value"} <= codes
    assert not mapped.ready_to_import


def test_i22_mapper_rejects_wrong_snapshot_shape_project_and_duplicate_identity():
    invalid_shape = map_i22_snapshot(SimpleNamespace(schema="elsewhere", rows={}), _context())
    no_project = map_i22_snapshot(_snapshot(), LegacyMappingContext())
    duplicate = _snapshot()
    duplicate.rows["t_std_code"].append(_source_row("t_std_code", code="C2"))
    duplicate_identity = map_i22_snapshot(duplicate, _context())

    assert invalid_shape.mapping_issues[0].code == "invalid_i22_snapshot_shape"
    assert no_project.mapping_issues[0].code == "target_project_required"
    assert any(issue.code == "duplicate_source_identity" for issue in duplicate_identity.mapping_issues)


def test_i22_mapper_empty_snapshot_is_a_valid_empty_set_with_all_tables_present():
    snapshot = SimpleNamespace(schema="datara_meta", rows={table: [] for table in I22_SOURCE_COLUMNS})
    mapped = map_i22_snapshot(snapshot, _context())

    assert mapped.ready_to_import
    assert not mapped.mapping_issues
    assert not any(
        (
            mapped.elements,
            mapped.code_sets,
            mapped.code_values,
            mapped.naming_rules,
            mapped.mappings,
            mapped.approvals,
            mapped.check_reports,
        )
    )
