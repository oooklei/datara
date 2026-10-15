"""Pure, fail-closed mapping for live-schema-bound legacy I22 snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from rebuild.governance.legacy_mapping import (
    LegacyMappingContext,
    MappedLegacyRow,
    MappingIssue,
    TargetIdentityReference,
)
from rebuild.governance.legacy_source_reader import I22_SOURCE_COLUMNS


_TABLES = set(I22_SOURCE_COLUMNS)
_APPROVAL_BUSINESS_TABLES = {
    "element": "t_std_element",
    "code": "t_std_code",
    "mapping": "t_std_mapping",
}


@dataclass(frozen=True)
class MappedI22Snapshot:
    elements: tuple[MappedLegacyRow, ...]
    code_sets: tuple[MappedLegacyRow, ...]
    code_values: tuple[MappedLegacyRow, ...]
    naming_rules: tuple[MappedLegacyRow, ...]
    mappings: tuple[MappedLegacyRow, ...]
    approvals: tuple[MappedLegacyRow, ...]
    check_reports: tuple[MappedLegacyRow, ...]
    mapping_issues: tuple[MappingIssue, ...]

    @property
    def ready_to_import(self) -> bool:
        rows = (
            self.elements
            + self.code_sets
            + self.code_values
            + self.naming_rules
            + self.mappings
            + self.approvals
            + self.check_reports
        )
        return not self.mapping_issues and all(row.ready_to_import and not row.mapping_issues for row in rows)


def map_i22_snapshot(snapshot: object, context: LegacyMappingContext) -> MappedI22Snapshot:
    """Map all seven I22 tables without connecting to storage or executing business actions."""

    rows = getattr(snapshot, "rows", None)
    if getattr(snapshot, "schema", None) != "datara_meta" or not isinstance(rows, Mapping) or set(rows) != _TABLES:
        return _empty(
            MappingIssue(
                "invalid_i22_snapshot_shape", "", "", "expected datara_meta snapshot with all seven I22 tables"
            )
        )
    project_id = context.target_project_id
    if not _positive_int(project_id):
        return _empty(MappingIssue("target_project_required", "", "", "target project must be an explicit positive id"))

    issues: list[MappingIssue] = []
    for (source_table, source_id), target_id in context.target_ids.items():
        if source_table in _TABLES and (not _positive_int(target_id)):
            issues.append(MappingIssue("invalid_explicit_target_id", source_table, source_id, repr(target_id)))
    if issues:
        return _empty(*issues)

    source_rows: dict[str, dict[str, Mapping[str, object]]] = {}
    for table_name, (_identity_column, columns) in I22_SOURCE_COLUMNS.items():
        table_values = rows[table_name]
        if not isinstance(table_values, (tuple, list)):
            issues.append(MappingIssue("invalid_i22_snapshot_shape", table_name, "", "rows must be ordered sequences"))
            continue
        indexed: dict[str, Mapping[str, object]] = {}
        for source in table_values:
            if not isinstance(source, Mapping):
                issues.append(MappingIssue("invalid_source_row", table_name, "", "row must be a mapping"))
                continue
            source_id = _source_id(source.get("id"), table_name, issues)
            if source_id is None:
                continue
            if set(source) != set(columns):
                issues.append(
                    MappingIssue(
                        "incomplete_source_row", table_name, source_id, "column set differs from reader contract"
                    )
                )
                continue
            if source_id in indexed:
                issues.append(MappingIssue("duplicate_source_identity", table_name, source_id, "duplicate source id"))
                continue
            indexed[source_id] = source
        source_rows[table_name] = indexed
    if any(table not in source_rows for table in _TABLES):
        return _empty(*issues)

    elements = tuple(
        _map_element(source_id, source, project_id, context)
        for source_id, source in _ordered(source_rows["t_std_element"])
    )
    code_sets = tuple(
        _map_code_set(source_id, source, project_id, context)
        for source_id, source in _ordered(source_rows["t_std_code"])
    )
    code_refs = source_rows["t_std_code"]
    element_refs = source_rows["t_std_element"]
    code_values = tuple(
        _map_code_value(source_id, source, context, code_refs)
        for source_id, source in _ordered(source_rows["t_std_code_value"])
    )
    naming_rules = tuple(
        _map_naming_rule(source_id, source, project_id, context)
        for source_id, source in _ordered(source_rows["t_std_naming_rule"])
    )
    mappings = tuple(
        _map_mapping(source_id, source, project_id, context, element_refs, code_refs)
        for source_id, source in _ordered(source_rows["t_std_mapping"])
    )
    approvals = tuple(
        _map_approval(source_id, source, project_id, context, source_rows)
        for source_id, source in _ordered(source_rows["t_std_approval"])
    )
    check_reports = tuple(
        _map_check_report(source_id, source, project_id, context)
        for source_id, source in _ordered(source_rows["t_std_check_report"])
    )
    mapped = elements + code_sets + code_values + naming_rules + mappings + approvals + check_reports
    for record in mapped:
        issues.extend(record.mapping_issues)
        issues.extend(
            MappingIssue("unresolved_reference", record.source_table, record.source_id, f"{table}:{identity}")
            for table, identity in record.unresolved_references
        )
    return MappedI22Snapshot(
        elements=elements,
        code_sets=code_sets,
        code_values=code_values,
        naming_rules=naming_rules,
        mappings=mappings,
        approvals=approvals,
        check_reports=check_reports,
        mapping_issues=tuple(dict.fromkeys(issues)),
    )


def _map_element(source_id, source, project_id, context):
    local: list[MappingIssue] = []
    for key, limit in {
        "code": 64,
        "cn": 128,
        "en": 128,
        "data_type": 32,
        "status": 16,
        "owner": 64,
        "remark": 255,
    }.items():
        _text(source.get(key), limit, "t_std_element", source_id, key, local)
    length = source.get("length")
    if length is not None and (not _integer(length) or length < 0):
        local.append(
            MappingIssue(
                "invalid_source_value", "t_std_element", source_id, "length must be a nonnegative integer or null"
            )
        )
        length = None
    version = _required_integer(source.get("version"), 1, "t_std_element", source_id, "version", local)
    created = _datetime(source.get("create_time"), "t_std_element", source_id, "create_time", local, required=True)
    updated = _datetime(source.get("update_time"), "t_std_element", source_id, "update_time", local, required=True)
    values = {
        "project_id": project_id,
        "code": source.get("code", ""),
        "chinese_name": source.get("cn", ""),
        "english_name": source.get("en", ""),
        "data_type": source.get("data_type", ""),
        "length": length,
        "status": source.get("status", ""),
        "version": version,
        "owner_name": source.get("owner", ""),
        "remark": source.get("remark", ""),
        "source_created_at": created,
        "source_updated_at": updated,
    }
    return _mapped("t_std_element", source_id, "rebuild_governance_standard_element", values, context, local)


def _map_code_set(source_id, source, project_id, context):
    local: list[MappingIssue] = []
    for key, limit in {"code": 64, "name": 128, "remark": 255, "status": 16}.items():
        _text(source.get(key), limit, "t_std_code", source_id, key, local)
    version = _required_integer(source.get("version"), 1, "t_std_code", source_id, "version", local)
    created = _datetime(source.get("create_time"), "t_std_code", source_id, "create_time", local, required=True)
    values = {
        "project_id": project_id,
        "code": source.get("code", ""),
        "name": source.get("name", ""),
        "remark": source.get("remark", ""),
        "status": source.get("status", ""),
        "version": version,
        "source_created_at": created,
        "source_updated_at": None,
    }
    return _mapped("t_std_code", source_id, "rebuild_governance_standard_code_set", values, context, local)


def _map_code_value(source_id, source, context, code_refs):
    local: list[MappingIssue] = []
    for key, limit in {"c": 64, "n": 128, "remark": 255}.items():
        _text(source.get(key), limit, "t_std_code_value", source_id, key, local)
    ordinal = _required_integer(source.get("seq"), 0, "t_std_code_value", source_id, "seq", local)
    unresolved: list[tuple[str, str]] = []
    parent_id = _required_integer(source.get("std_code_id"), 1, "t_std_code_value", source_id, "std_code_id", local)
    code_set_ref = _resolve_reference("t_std_code", parent_id, context, code_refs, unresolved) if parent_id else None
    values = {
        "code_set_id": code_set_ref,
        "code_value": source.get("c", ""),
        "display_name": source.get("n", ""),
        "ordinal_position": ordinal,
        "remark": source.get("remark", ""),
        "source_created_at": None,
        "source_updated_at": None,
    }
    return _mapped(
        "t_std_code_value", source_id, "rebuild_governance_standard_code_value", values, context, local, unresolved
    )


def _map_naming_rule(source_id, source, project_id, context):
    local: list[MappingIssue] = []
    for key, limit in {"name": 128, "rule_type": 16, "pattern": 255, "target": 32}.items():
        _text(source.get(key), limit, "t_std_naming_rule", source_id, key, local)
    enabled = source.get("enabled")
    if isinstance(enabled, bool):
        enabled_value = enabled
    elif isinstance(enabled, int) and not isinstance(enabled, bool) and enabled in {0, 1}:
        enabled_value = bool(enabled)
    else:
        local.append(MappingIssue("invalid_source_value", "t_std_naming_rule", source_id, "enabled must be 0 or 1"))
        enabled_value = False
    values = {
        "project_id": project_id,
        "name": source.get("name", ""),
        "rule_type": source.get("rule_type", ""),
        "pattern": source.get("pattern", ""),
        "target_type": source.get("target", ""),
        "enabled": enabled_value,
        "source_created_at": None,
        "source_updated_at": None,
    }
    return _mapped("t_std_naming_rule", source_id, "rebuild_governance_standard_naming_rule", values, context, local)


def _map_mapping(source_id, source, project_id, context, element_refs, code_refs):
    local: list[MappingIssue] = []
    for key, limit in {"name": 128, "target": 255, "status": 16, "diff": 255}.items():
        _text(source.get(key), limit, "t_std_mapping", source_id, key, local)
    unresolved: list[tuple[str, str]] = []
    element_id = _optional_id(source.get("element_id"), "t_std_mapping", source_id, "element_id", local)
    code_id = _optional_id(source.get("code_id"), "t_std_mapping", source_id, "code_id", local)
    element_ref = (
        _resolve_reference("t_std_element", element_id, context, element_refs, unresolved) if element_id else None
    )
    code_ref = _resolve_reference("t_std_code", code_id, context, code_refs, unresolved) if code_id else None
    values = {
        "project_id": project_id,
        "name": source.get("name", ""),
        "target": source.get("target", ""),
        "element_id": element_ref,
        "code_set_id": code_ref,
        "status": source.get("status", ""),
        "difference": source.get("diff", ""),
        "source_created_at": None,
        "source_updated_at": None,
    }
    return _mapped(
        "t_std_mapping", source_id, "rebuild_governance_standard_mapping", values, context, local, unresolved
    )


def _map_approval(source_id, source, project_id, context, source_rows):
    local: list[MappingIssue] = []
    for key, limit in {"biz_type": 16, "action": 16, "status": 16, "opinion": 255}.items():
        _text(source.get(key), limit, "t_std_approval", source_id, key, local)
    business_id = _required_integer(source.get("biz_id"), 1, "t_std_approval", source_id, "biz_id", local)
    unresolved: list[tuple[str, str]] = []
    business_type = source.get("biz_type")
    source_table = _APPROVAL_BUSINESS_TABLES.get(business_type) if isinstance(business_type, str) else None
    if source_table is None:
        local.append(MappingIssue("unknown_approval_business_type", "t_std_approval", source_id, repr(business_type)))
    elif (
        str(business_id) not in source_rows[source_table] and (source_table, str(business_id)) not in context.target_ids
    ):
        unresolved.append((source_table, str(business_id)))
    payload_json = _json_text(source.get("payload_json"), "t_std_approval", source_id, "payload_json", local)
    created = _datetime(source.get("create_time"), "t_std_approval", source_id, "create_time", local, required=True)
    values = {
        "project_id": project_id,
        # The target FK points to canonical StandardDefinition, not the old I22 row.
        "standard_id": None,
        "business_type": business_type if isinstance(business_type, str) else "",
        "legacy_business_id": business_id,
        "action": source.get("action", ""),
        "payload_json": payload_json,
        "status": source.get("status", ""),
        "opinion": source.get("opinion", ""),
        "source_created_at": created,
        "source_updated_at": None,
    }
    return _mapped(
        "t_std_approval", source_id, "rebuild_governance_standard_approval", values, context, local, unresolved
    )


def _map_check_report(source_id, source, project_id, context):
    local: list[MappingIssue] = []
    for key, limit in {"scope": 16, "status": 16}.items():
        _text(source.get(key), limit, "t_std_check_report", source_id, key, local)
    summary = _json_text(source.get("summary_json"), "t_std_check_report", source_id, "summary_json", local)
    issues = _json_text(source.get("issues_json"), "t_std_check_report", source_id, "issues_json", local)
    created = _datetime(source.get("create_time"), "t_std_check_report", source_id, "create_time", local, required=True)
    values = {
        "project_id": project_id,
        "scope": source.get("scope", ""),
        "summary_json": summary,
        "issues_json": issues,
        "status": source.get("status", ""),
        "source_created_at": created,
        "source_updated_at": None,
    }
    return _mapped("t_std_check_report", source_id, "rebuild_governance_standard_check_report", values, context, local)


def _resolve_reference(table, source_id, context, source_rows, unresolved):
    identity = (table, str(source_id))
    target_id = context.target_ids.get(identity)
    if target_id is not None:
        return target_id
    if str(source_id) in source_rows:
        return TargetIdentityReference(*identity)
    unresolved.append(identity)
    return TargetIdentityReference(*identity)


def _mapped(table, source_id, target_table, values, context, local, unresolved=()):
    return MappedLegacyRow(
        source_system="datara_meta",
        source_table=table,
        source_id=source_id,
        target_table=target_table,
        values=values,
        unresolved_references=tuple(unresolved),
        target_id=context.target_ids.get((table, source_id)),
        mapping_issues=tuple(local),
    )


def _text(value, max_length, table, source_id, field, issues):
    if not isinstance(value, str):
        issues.append(MappingIssue("invalid_source_value", table, source_id, f"{field} must be text"))
    elif len(value) > max_length:
        issues.append(MappingIssue("target_text_too_long", table, source_id, field))


def _datetime(value, table, source_id, field, issues, *, required=False):
    if value is None:
        if required:
            issues.append(MappingIssue("invalid_source_value", table, source_id, f"{field} is required"))
        return None
    if isinstance(value, str):
        if "T" not in value and " " not in value:
            issues.append(MappingIssue("invalid_source_value", table, source_id, f"{field} must include a time"))
            return None
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            issues.append(MappingIssue("invalid_source_value", table, source_id, f"{field} must be an ISO datetime"))
            return None
    if not isinstance(value, datetime):
        issues.append(MappingIssue("invalid_source_value", table, source_id, f"{field} must be a datetime"))
        return None
    if value.tzinfo is not None and value.utcoffset() is not None:
        issues.append(MappingIssue("timezone_aware_source_datetime", table, source_id, field))
        return None
    return value


def _json_text(value, table, source_id, field, issues):
    try:
        decoded = json.loads(value) if isinstance(value, str) else value
        return json.dumps(decoded, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        issues.append(MappingIssue("invalid_json_value", table, source_id, field))
        return "null"


def _required_integer(value, minimum, table, source_id, field, issues):
    if not _integer(value) or value < minimum:
        issues.append(
            MappingIssue("invalid_source_value", table, source_id, f"{field} must be an integer >= {minimum}")
        )
        return 0
    return value


def _optional_id(value, table, source_id, field, issues):
    if value is None:
        return None
    if not _positive_int(value):
        issues.append(
            MappingIssue("invalid_source_value", table, source_id, f"{field} must be a positive integer or null")
        )
        return None
    return value


def _source_id(value, table, issues):
    if not _positive_int(value):
        issues.append(MappingIssue("invalid_source_identity", table, repr(value), "expected positive integer id"))
        return None
    return str(value)


def _positive_int(value):
    return _integer(value) and value > 0


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _ordered(rows):
    return sorted(rows.items(), key=lambda item: (0, f"{int(item[0]):020d}") if item[0].isdigit() else (1, item[0]))


def _empty(*issues):
    return MappedI22Snapshot((), (), (), (), (), (), (), tuple(issues))
