"""Pure, fail-closed mapping for legacy I21 quality snapshots."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from rebuild.governance.legacy_mapping import (
    LegacyMappingContext,
    MappedLegacyRow,
    MappingIssue,
    TargetIdentityReference,
)
from rebuild.governance.legacy_source_reader import I21_SOURCE_COLUMNS


_TABLES = set(I21_SOURCE_COLUMNS)


@dataclass(frozen=True)
class MappedI21TaskRuleLink:
    source_task_id: str
    ordinal_position: int
    task_id: int | TargetIdentityReference
    rule_definition_id: int | TargetIdentityReference
    unresolved_references: tuple[tuple[str, str], ...] = ()
    mapping_issues: tuple[MappingIssue, ...] = ()


@dataclass(frozen=True)
class MappedI21TaskBundle:
    task: MappedLegacyRow
    rule_links: tuple[MappedI21TaskRuleLink, ...]
    mapping_issues: tuple[MappingIssue, ...] = ()

    @property
    def ready_to_import(self) -> bool:
        return (
            self.task.ready_to_import
            and not self.mapping_issues
            and all(not link.mapping_issues and not link.unresolved_references for link in self.rule_links)
        )


@dataclass(frozen=True)
class MappedI21Snapshot:
    rules: tuple[MappedLegacyRow, ...]
    tasks: tuple[MappedI21TaskBundle, ...]
    runs: tuple[MappedLegacyRow, ...]
    exceptions: tuple[MappedLegacyRow, ...]
    reports: tuple[MappedLegacyRow, ...]
    alarm_policies: tuple[MappedLegacyRow, ...]
    mapping_issues: tuple[MappingIssue, ...]

    @property
    def ready_to_import(self) -> bool:
        return (
            not self.mapping_issues
            and all(
                row.ready_to_import
                for row in self.rules + self.runs + self.exceptions + self.reports + self.alarm_policies
            )
            and all(task.ready_to_import for task in self.tasks)
        )


def map_i21_snapshot(snapshot: object, context: LegacyMappingContext) -> MappedI21Snapshot:
    """Map all six legacy QC tables without executing quality rules or SQL."""

    rows = getattr(snapshot, "rows", None)
    if getattr(snapshot, "schema", None) != "datara_meta" or not isinstance(rows, Mapping) or set(rows) != _TABLES:
        return _empty_with_issue(
            MappingIssue("invalid_i21_snapshot_shape", "", "", "expected datara_meta snapshot with all six I21 tables")
        )
    project_id = context.target_project_id
    if not isinstance(project_id, int) or isinstance(project_id, bool) or project_id < 1:
        return _empty_with_issue(
            MappingIssue("target_project_required", "", "", "target project must be an explicit positive integer")
        )
    invalid_target_ids = [
        MappingIssue("invalid_explicit_target_id", source_table, source_id, repr(target_id))
        for (source_table, source_id), target_id in context.target_ids.items()
        if source_table in _TABLES and (not isinstance(target_id, int) or isinstance(target_id, bool) or target_id < 1)
    ]
    if invalid_target_ids:
        return _empty_with_issues(invalid_target_ids)

    source_rows: dict[str, dict[str, Mapping[str, object]]] = {}
    issues: list[MappingIssue] = []
    for table_name in I21_SOURCE_COLUMNS:
        table_rows = rows[table_name]
        if not isinstance(table_rows, (tuple, list)):
            issues.append(MappingIssue("invalid_i21_snapshot_shape", table_name, "", "rows must be ordered sequences"))
            continue
        indexed: dict[str, Mapping[str, object]] = {}
        for source in table_rows:
            if not isinstance(source, Mapping):
                issues.append(MappingIssue("invalid_source_row", table_name, "", "row must be a mapping"))
                continue
            source_id = _source_id(source.get("id"), table_name, issues)
            if source_id is None:
                continue
            if set(source) != set(I21_SOURCE_COLUMNS[table_name][1]):
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
        return _empty_with_issues(issues)

    rules = tuple(
        _map_rule(source_id, source, project_id, context, issues)
        for source_id, source in sorted(source_rows["t_qc_rule"].items(), key=lambda item: _identity_sort(item[0]))
    )
    rule_refs = {row.source_id: row for row in rules}
    tasks = tuple(
        _map_task(source_id, source, project_id, context, rule_refs, issues)
        for source_id, source in sorted(source_rows["t_qc_task"].items(), key=lambda item: _identity_sort(item[0]))
    )
    task_refs = source_rows["t_qc_task"]
    runs = tuple(
        _map_run(source_id, source, context, task_refs, issues)
        for source_id, source in sorted(source_rows["t_qc_run"].items(), key=lambda item: _identity_sort(item[0]))
    )
    run_refs = {row.source_id: row for row in runs}
    exceptions = tuple(
        _map_exception(source_id, source, project_id, context, rule_refs, run_refs, task_refs, issues)
        for source_id, source in sorted(source_rows["t_qc_exception"].items(), key=lambda item: _identity_sort(item[0]))
    )
    reports = tuple(
        _map_report(source_id, source, project_id, context, issues)
        for source_id, source in sorted(source_rows["t_qc_report"].items(), key=lambda item: _identity_sort(item[0]))
    )
    alarm_policies = tuple(
        _map_alarm(source_id, source, project_id, context, issues)
        for source_id, source in sorted(
            source_rows["t_qc_alarm_policy"].items(), key=lambda item: _identity_sort(item[0])
        )
    )
    for task in tasks:
        issues.extend(task.mapping_issues)
        for link in task.rule_links:
            issues.extend(link.mapping_issues)
    for record in rules + runs + exceptions + reports + alarm_policies:
        issues.extend(record.mapping_issues)
        issues.extend(
            MappingIssue("unresolved_reference", record.source_table, record.source_id, f"{table}:{identity}")
            for table, identity in record.unresolved_references
        )
    return MappedI21Snapshot(
        rules=rules,
        tasks=tasks,
        runs=runs,
        exceptions=exceptions,
        reports=reports,
        alarm_policies=alarm_policies,
        mapping_issues=tuple(dict.fromkeys(issues)),
    )


def _map_rule(source_id, source, project_id, context, issues):
    local: list[MappingIssue] = []
    params_json = _json_text(source.get("params_json"), "t_qc_rule", source_id, "params_json", local)
    for key, max_length in {
        "name": 128,
        "dim": 32,
        "rule_type": 32,
        "db_name": 128,
        "table_name": 128,
        "column_name": 128,
        "level": 16,
        "status": 16,
        "owner": 64,
        "remark": 255,
    }.items():
        _check_text(source.get(key), max_length, "t_qc_rule", source_id, key, local)
    threshold = _number(source.get("threshold"), "t_qc_rule", source_id, "threshold", local)
    row = _mapped(
        "t_qc_rule",
        source_id,
        "rebuild_governance_quality_rule_definition",
        {
            "project_id": project_id,
            "quality_rule_id": None,
            "name": source.get("name", ""),
            "dimension": source.get("dim", ""),
            "rule_type": source.get("rule_type", ""),
            "legacy_datasource_id": _optional_legacy_id(source.get("ds_id"), "t_qc_rule", source_id, "ds_id", local),
            "target_database": source.get("db_name", ""),
            "target_table": source.get("table_name", ""),
            "target_column": source.get("column_name", ""),
            "params_json": params_json,
            "threshold": threshold,
            "severity": source.get("level", ""),
            "status": source.get("status", ""),
            "owner_name": source.get("owner", ""),
            "remark": source.get("remark", ""),
            "source_created_at": _datetime_value(
                source.get("create_time"), "t_qc_rule", source_id, "create_time", local
            ),
            "source_updated_at": _datetime_value(
                source.get("update_time"), "t_qc_rule", source_id, "update_time", local
            ),
        },
        context,
        local,
        mapping_notes=({"source_schema_missing_columns": ["update_time"]},),
    )
    issues.extend(local)
    return row


def _map_task(source_id, source, project_id, context, rule_refs, issues):
    local: list[MappingIssue] = []
    for key, max_length in {"name": 128, "crontab": 64, "status": 16, "last_result": 16}.items():
        _check_text(source.get(key), max_length, "t_qc_task", source_id, key, local)
    if not isinstance(source.get("enabled"), bool):
        local.append(MappingIssue("invalid_source_value", "t_qc_task", source_id, "enabled must be boolean"))
    rule_ids = source.get("rule_ids")
    if rule_ids is None:
        rule_ids = []
    if not isinstance(rule_ids, list):
        local.append(MappingIssue("invalid_task_rule_ids", "t_qc_task", source_id, "rule_ids must be a JSON array"))
        rule_ids = []
    task_ref = _reference("t_qc_task", source_id, context)
    links: list[MappedI21TaskRuleLink] = []
    seen: set[str] = set()
    for index, rule_id in enumerate(rule_ids, start=1):
        if not isinstance(rule_id, int) or isinstance(rule_id, bool) or rule_id < 1:
            local.append(MappingIssue("invalid_task_rule_id", "t_qc_task", source_id, repr(rule_id)))
            continue
        rule_source_id = str(rule_id)
        if rule_source_id in seen:
            local.append(MappingIssue("duplicate_task_rule_identity", "t_qc_task", source_id, rule_source_id))
            continue
        seen.add(rule_source_id)
        unresolved: list[tuple[str, str]] = []
        rule_ref = _resolve_reference("t_qc_rule", rule_source_id, context, rule_refs, unresolved, "rule_definition_id")
        link_issues = tuple(
            MappingIssue("unresolved_reference", "t_qc_task", source_id, f"{table}:{identity}")
            for table, identity in unresolved
        )
        local.extend(link_issues)
        links.append(
            MappedI21TaskRuleLink(
                source_task_id=source_id,
                ordinal_position=index,
                task_id=task_ref,
                rule_definition_id=rule_ref,
                unresolved_references=tuple(unresolved),
                mapping_issues=link_issues,
            )
        )
    task = _mapped(
        "t_qc_task",
        source_id,
        "rebuild_governance_quality_task",
        {
            "project_id": project_id,
            "name": source.get("name", ""),
            "cron_expression": source.get("crontab", ""),
            "enabled": source.get("enabled", False),
            "status": source.get("status", ""),
            "last_run_at": _datetime_value(source.get("last_run_at"), "t_qc_task", source_id, "last_run_at", local),
            "last_result": source.get("last_result", ""),
            "owner_name": "",
            "remark": "",
            "source_created_at": _datetime_value(None, "t_qc_task", source_id, "create_time", local),
            "source_updated_at": None,
        },
        context,
        local,
        mapping_notes=({"source_schema_missing_columns": ["owner", "remark", "create_time"]},),
    )
    issues.extend(local)
    return MappedI21TaskBundle(task, tuple(links), tuple(local))


def _map_run(source_id, source, context, task_refs, issues):
    local: list[MappingIssue] = []
    _check_text(source.get("trigger"), 16, "t_qc_run", source_id, "trigger", local)
    _check_text(source.get("result"), 16, "t_qc_run", source_id, "result", local)
    score = _number(source.get("score"), "t_qc_run", source_id, "score", local)
    stats_json = _json_text(source.get("stats_json"), "t_qc_run", source_id, "stats_json", local)
    legacy_task_id = _optional_legacy_id(source.get("task_id"), "t_qc_run", source_id, "task_id", local)
    unresolved: list[tuple[str, str]] = []
    if legacy_task_id is not None:
        _resolve_reference("t_qc_task", str(legacy_task_id), context, task_refs, unresolved, "legacy_task_id")
    local.extend(
        MappingIssue("unresolved_reference", "t_qc_run", source_id, f"{table}:{identity}")
        for table, identity in unresolved
    )
    row = _mapped(
        "t_qc_run",
        source_id,
        "rebuild_governance_quality_run_legacy_details",
        {
            "quality_run_id": None,
            "legacy_task_id": legacy_task_id,
            "trigger_source": source.get("trigger", ""),
            "started_at": _datetime_value(source.get("started_at"), "t_qc_run", source_id, "started_at", local),
            "finished_at": _datetime_value(source.get("finished_at"), "t_qc_run", source_id, "finished_at", local),
            "legacy_result": source.get("result", ""),
            "score": score,
            "stats_json": stats_json,
            "source_created_at": None,
            "source_updated_at": None,
        },
        context,
        local,
        unresolved_references=tuple(unresolved),
    )
    issues.extend(local)
    return row


def _map_exception(source_id, source, project_id, context, rule_refs, run_refs, task_refs, issues):
    local: list[MappingIssue] = []
    for key, max_length in {"target": 255, "status": 16, "fix_note": 255}.items():
        _check_text(source.get(key), max_length, "t_qc_exception", source_id, key, local)
    for key in ("hit_count", "run_id", "rule_id"):
        value = source.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < (0 if key == "hit_count" else 1):
            local.append(MappingIssue("invalid_source_value", "t_qc_exception", source_id, key))
    unresolved: list[tuple[str, str]] = []
    run_id = source.get("run_id")
    rule_id = source.get("rule_id")
    task_id = source.get("task_id")
    run_ref = (
        _resolve_reference("t_qc_run", str(run_id), context, run_refs, unresolved, "run_details_id")
        if isinstance(run_id, int) and not isinstance(run_id, bool) and run_id > 0
        else None
    )
    rule_ref = (
        _resolve_reference("t_qc_rule", str(rule_id), context, rule_refs, unresolved, "rule_definition_id")
        if isinstance(rule_id, int) and not isinstance(rule_id, bool) and rule_id > 0
        else None
    )
    if isinstance(task_id, int) and not isinstance(task_id, bool) and task_id > 0:
        _resolve_reference("t_qc_task", str(task_id), context, task_refs, unresolved, "legacy_task_id")
    local.extend(
        MappingIssue("unresolved_reference", "t_qc_exception", source_id, f"{table}:{identity}")
        for table, identity in unresolved
    )
    row = _mapped(
        "t_qc_exception",
        source_id,
        "rebuild_governance_quality_exception",
        {
            "project_id": project_id,
            "run_details_id": run_ref,
            "rule_definition_id": rule_ref,
            "legacy_task_id": _optional_legacy_id(task_id, "t_qc_exception", source_id, "task_id", local),
            "target": source.get("target", ""),
            "sample_sql": _text_value(source.get("sample_sql"), "t_qc_exception", source_id, "sample_sql", local),
            "hit_count": source.get("hit_count", 0),
            "status": source.get("status", ""),
            "fix_note": source.get("fix_note", ""),
            "handled_by": "",
            "handled_at": _datetime_value(source.get("handled_at"), "t_qc_exception", source_id, "handled_at", local),
            "source_created_at": None,
            "source_updated_at": None,
        },
        context,
        local,
        unresolved_references=tuple(unresolved),
        mapping_notes=({"source_schema_missing_columns": ["handled_by"]},),
    )
    issues.extend(local)
    return row


def _map_report(source_id, source, project_id, context, issues):
    local: list[MappingIssue] = []
    for key, max_length in {"title": 128, "scope": 128, "period": 64, "created_by": 64}.items():
        _check_text(source.get(key), max_length, "t_qc_report", source_id, key, local)
    content_json = _json_text(source.get("content_json"), "t_qc_report", source_id, "content_json", local)
    row = _mapped(
        "t_qc_report",
        source_id,
        "rebuild_governance_quality_report",
        {
            "project_id": project_id,
            "title": source.get("title", ""),
            "scope": source.get("scope", ""),
            "period": source.get("period", ""),
            "content_json": content_json,
            "created_by": source.get("created_by", ""),
            "source_created_at": _datetime_value(
                source.get("create_time"), "t_qc_report", source_id, "create_time", local
            ),
            "source_updated_at": None,
        },
        context,
        local,
    )
    issues.extend(local)
    return row


def _map_alarm(source_id, source, project_id, context, issues):
    local: list[MappingIssue] = []
    for key, max_length in {"name": 128, "scope": 128, "metric": 32, "op": 4}.items():
        _check_text(source.get(key), max_length, "t_qc_alarm_policy", source_id, key, local)
    threshold = _number(source.get("threshold"), "t_qc_alarm_policy", source_id, "threshold", local)
    if not isinstance(source.get("enabled"), bool):
        local.append(MappingIssue("invalid_source_value", "t_qc_alarm_policy", source_id, "enabled must be boolean"))
    row = _mapped(
        "t_qc_alarm_policy",
        source_id,
        "rebuild_governance_quality_alarm_policy",
        {
            "project_id": project_id,
            "name": source.get("name", ""),
            "scope": source.get("scope", ""),
            "metric": source.get("metric", ""),
            "operator": source.get("op", ""),
            "threshold": threshold,
            "enabled": source.get("enabled", False),
            "last_fired_at": _datetime_value(
                source.get("last_fired_at"), "t_qc_alarm_policy", source_id, "last_fired_at", local
            ),
            "source_created_at": None,
            "source_updated_at": None,
        },
        context,
        local,
    )
    issues.extend(local)
    return row


def _mapped(
    source_table,
    source_id,
    target_table,
    values,
    context,
    issues,
    unresolved_references=(),
    mapping_notes=(),
):
    return MappedLegacyRow(
        source_system="datara_meta",
        source_table=source_table,
        source_id=source_id,
        target_table=target_table,
        values=values,
        unresolved_references=tuple(unresolved_references),
        target_id=context.target_ids.get((source_table, source_id)),
        mapping_issues=tuple(issues),
        mapping_notes=tuple(mapping_notes),
    )


def _resolve_reference(source_table, source_id, context, current_rows, unresolved, reference_field):
    identity = (source_table, source_id)
    target_id = context.target_ids.get(identity)
    if target_id is not None:
        return target_id
    if source_id in current_rows or identity in context.pending_identities:
        return TargetIdentityReference(source_table, source_id)
    unresolved.append(identity)
    return TargetIdentityReference(source_table, source_id)


def _reference(source_table, source_id, context):
    return context.target_ids.get((source_table, source_id), TargetIdentityReference(source_table, source_id))


def _source_id(value, table, issues):
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        issues.append(MappingIssue("invalid_source_identity", table, repr(value), "expected positive integer id"))
        return None
    return str(value)


def _check_text(value, max_length, table, source_id, field, issues):
    if not isinstance(value, str):
        issues.append(MappingIssue("invalid_source_value", table, source_id, f"{field} must be text"))
    elif len(value) > max_length:
        issues.append(MappingIssue("target_text_too_long", table, source_id, field))


def _number(value, table, source_id, field, issues):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        issues.append(MappingIssue("invalid_source_value", table, source_id, f"{field} must be finite numeric"))
        return 0.0
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        issues.append(MappingIssue("invalid_source_value", table, source_id, f"{field} must be finite numeric"))
        return 0.0
    return float(value)


def _optional_legacy_id(value, table, source_id, field, issues):
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        issues.append(
            MappingIssue("invalid_source_value", table, source_id, f"{field} must be a positive integer or null")
        )
        return None
    return value


def _datetime_value(value, table, source_id, field, issues):
    if value is None:
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
        issues.append(MappingIssue("invalid_source_value", table, source_id, f"{field} must be a datetime or null"))
        return None
    if value.tzinfo is not None and value.utcoffset() is not None:
        issues.append(MappingIssue("timezone_aware_source_datetime", table, source_id, field))
        return None
    return value


def _text_value(value, table, source_id, field, issues):
    if not isinstance(value, str):
        issues.append(MappingIssue("invalid_source_value", table, source_id, f"{field} must be text"))
        return ""
    return value


def _json_text(value, table, source_id, field, issues):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        issues.append(MappingIssue("invalid_json_value", table, source_id, field))
        return "null"


def _empty_with_issue(issue):
    return _empty_with_issues([issue])


def _empty_with_issues(issues):
    return MappedI21Snapshot((), (), (), (), (), (), tuple(issues))


def _identity_sort(value):
    return (0, f"{int(value):020d}") if value.isdigit() else (1, value)
