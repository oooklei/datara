"""Pure, loss-preserving mapping for I20 metric snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from rebuild.governance.legacy_mapping import (
    LegacyMappingContext,
    MappedLegacyRow,
    MappingIssue,
    TargetIdentityReference,
)
from rebuild.governance.legacy_source_reader import I20_SOURCE_COLUMNS


_SOURCE_TABLES = {"t_indicator", "t_indicator_version"}
_METRIC_STATUS = {"draft": "draft", "published": "active"}


@dataclass(frozen=True)
class MappedI20MetricBundle:
    """One source indicator's metric/profile parent and its historical versions."""

    metric: MappedLegacyRow
    profile_values: Mapping[str, object]
    versions: tuple[MappedLegacyRow, ...]
    dimension_rows: tuple[Mapping[str, object], ...] = ()
    mapping_issues: tuple[MappingIssue, ...] = ()

    @property
    def ready_to_import(self) -> bool:
        return (
            self.metric.ready_to_import
            and not self.mapping_issues
            and all(version.ready_to_import for version in self.versions)
        )


@dataclass(frozen=True)
class MappedI20Snapshot:
    metrics: tuple[MappedI20MetricBundle, ...]
    orphan_versions: tuple[MappingIssue, ...]
    mapping_issues: tuple[MappingIssue, ...]


def map_i20_snapshot(snapshot: object, context: LegacyMappingContext) -> MappedI20Snapshot:
    """Map I20 source rows without interpreting raw dimensions or version JSON."""

    rows = getattr(snapshot, "rows", None)
    schema = getattr(snapshot, "schema", None)
    if schema != "datara_meta" or not isinstance(rows, Mapping) or set(rows) != _SOURCE_TABLES:
        issue = MappingIssue("invalid_i20_snapshot_shape", "", "", "expected datara_meta snapshot with both I20 tables")
        return MappedI20Snapshot((), (), (issue,))
    if (
        not isinstance(context.target_project_id, int)
        or isinstance(context.target_project_id, bool)
        or context.target_project_id < 1
    ):
        issue = MappingIssue("target_project_required", "", "", "target project must be an explicit positive integer")
        return MappedI20Snapshot((), (), (issue,))

    raw_metrics = rows["t_indicator"]
    raw_versions = rows["t_indicator_version"]
    if not isinstance(raw_metrics, (tuple, list)) or not isinstance(raw_versions, (tuple, list)):
        issue = MappingIssue("invalid_i20_snapshot_shape", "", "", "I20 table rows must be ordered sequences")
        return MappedI20Snapshot((), (), (issue,))

    issues: list[MappingIssue] = []
    metrics_by_id: dict[str, MappedI20MetricBundle] = {}
    base_edges: dict[str, str] = {}
    for source in raw_metrics:
        if not isinstance(source, Mapping):
            issues.append(MappingIssue("invalid_metric_row", "t_indicator", "", "source row must be a mapping"))
            continue
        if set(source) != set(I20_SOURCE_COLUMNS["t_indicator"][1]):
            issues.append(
                MappingIssue(
                    "incomplete_metric_source_row",
                    "t_indicator",
                    repr(source.get("id", "")),
                    "column set differs from reader contract",
                )
            )
            continue
        source_id = _source_id(source.get("id"), "t_indicator", issues)
        if source_id is None:
            continue
        if source_id in metrics_by_id:
            issues.append(MappingIssue("duplicate_metric_identity", "t_indicator", source_id, "duplicate source id"))
            continue

        row_issues: list[MappingIssue] = []
        status = source.get("status")
        target_status = _METRIC_STATUS.get(status) if isinstance(status, str) else None
        if target_status is None:
            row_issues.append(MappingIssue("unsupported_metric_status", "t_indicator", source_id, repr(status)))
            target_status = "draft"

        code = _required_text(source, "code", source_id, row_issues, max_length=128)
        name = _required_text(source, "name", source_id, row_issues, max_length=256)
        business_definition = _required_text(source, "biz_def", source_id, row_issues)
        technical_definition = _optional_text(source, "tech_def", source_id, row_issues)
        if code is None or name is None or business_definition is None or technical_definition is None:
            row_issues.append(
                MappingIssue(
                    "invalid_metric_fields", "t_indicator", source_id, "required metric text is missing or invalid"
                )
            )
            code = code or ""
            name = name or ""
            business_definition = business_definition or ""
            technical_definition = technical_definition or ""

        metric = MappedLegacyRow(
            source_system="datara_meta",
            source_table="t_indicator",
            source_id=source_id,
            target_table="rebuild_governance_semantic_metric",
            values={
                "project_id": context.target_project_id,
                "code": code,
                "name": name,
                "formula": technical_definition,
                "description": business_definition,
                "status": target_status,
                "source_created_at": source.get("create_time"),
                "source_updated_at": source.get("update_time"),
            },
            target_id=context.target_ids.get(("t_indicator", source_id)),
            mapping_issues=tuple(row_issues),
        )

        own_ref: int | TargetIdentityReference = context.target_ids.get(
            ("t_indicator", source_id), TargetIdentityReference("t_indicator", source_id)
        )
        unresolved: list[tuple[str, str]] = []
        base_value = source.get("base_metric_id")
        base_ref: int | TargetIdentityReference | None = None
        if base_value not in (None, ""):
            if not isinstance(base_value, int) or isinstance(base_value, bool) or base_value < 1:
                row_issues.append(MappingIssue("invalid_base_metric_id", "t_indicator", source_id, repr(base_value)))
            else:
                base_identity = ("t_indicator", str(base_value))
                base_ref = _resolve_metric_reference(base_identity, context, unresolved, "base_metric_id")
                if base_identity[1] == source_id:
                    row_issues.append(MappingIssue("cyclic_base_metric_reference", "t_indicator", source_id, source_id))
                else:
                    base_edges[source_id] = base_identity[1]
        row_issues.extend(
            MappingIssue("unresolved_reference", "t_indicator", source_id, f"{table}:{identity}")
            for table, identity in unresolved
        )
        profile_values = {
            "metric_id": own_ref,
            "base_metric_id": base_ref,
            "legacy_base_metric_id": base_value,
            "metric_type": source.get("type", "原子"),
            "business_domain": source.get("biz_domain", ""),
            "business_definition": business_definition,
            "technical_definition": technical_definition,
            "source_kind": source.get("src_kind", "table"),
            "source_reference": source.get("src_ref", ""),
            "source_field": source.get("src_field", ""),
            "output_table": source.get("out_table", ""),
            "output_task": source.get("out_task", ""),
            "period": source.get("period", "日"),
            "unit": source.get("unit", ""),
            "aggregation_function": source.get("agg_fn"),
            "numerator_field": source.get("num_field"),
            "time_field": source.get("time_field"),
            "dimension_field": source.get("dim_field"),
            "filter_condition": source.get("filter_cond"),
            "legacy_dimensions": source.get("dims", ""),
            "legacy_status": status if isinstance(status, str) else repr(status),
            "legacy_version": source.get("version", 1),
            "owner_name": source.get("owner", ""),
            "source_created_at": source.get("create_time"),
            "source_updated_at": source.get("update_time"),
        }
        _validate_profile_values(profile_values, source_id, row_issues)
        metric = _with_issues(metric, row_issues, tuple(unresolved))
        metrics_by_id[source_id] = MappedI20MetricBundle(
            metric=metric,
            profile_values=profile_values,
            versions=(),
            mapping_issues=tuple(row_issues),
        )

    _append_base_cycle_issues(base_edges, metrics_by_id, issues)

    seen_version_ids: set[str] = set()
    seen_metric_versions: set[tuple[str, int]] = set()
    orphan_versions: list[MappingIssue] = []
    versions_by_metric: dict[str, list[MappedLegacyRow]] = {}
    for source in raw_versions:
        if not isinstance(source, Mapping):
            issue = MappingIssue(
                "invalid_metric_version_row", "t_indicator_version", "", "source row must be a mapping"
            )
            issues.append(issue)
            continue
        if set(source) != set(I20_SOURCE_COLUMNS["t_indicator_version"][1]):
            issues.append(
                MappingIssue(
                    "incomplete_metric_version_source_row",
                    "t_indicator_version",
                    repr(source.get("id", "")),
                    "column set differs from reader contract",
                )
            )
            continue
        version_id = _source_id(source.get("id"), "t_indicator_version", issues)
        if version_id is None:
            continue
        if version_id in seen_version_ids:
            issues.append(
                MappingIssue(
                    "duplicate_metric_version_identity", "t_indicator_version", version_id, "duplicate source id"
                )
            )
            continue
        seen_version_ids.add(version_id)
        metric_source_id = _source_id(source.get("indicator_id"), "t_indicator_version", issues)
        if metric_source_id is None:
            continue
        if metric_source_id not in metrics_by_id and ("t_indicator", metric_source_id) not in context.target_ids:
            orphan_versions.append(
                MappingIssue("orphan_metric_version", "t_indicator_version", version_id, metric_source_id)
            )
            continue

        raw_version = source.get("version")
        if not isinstance(raw_version, int) or isinstance(raw_version, bool) or raw_version < 1:
            issues.append(MappingIssue("invalid_metric_version", "t_indicator_version", version_id, repr(raw_version)))
            continue
        pair = (metric_source_id, raw_version)
        if pair in seen_metric_versions:
            issues.append(MappingIssue("duplicate_metric_version", "t_indicator_version", version_id, repr(pair)))
            continue
        seen_metric_versions.add(pair)
        snapshot_json = source.get("snapshot_json")
        if not isinstance(snapshot_json, str):
            issues.append(
                MappingIssue(
                    "invalid_metric_version_snapshot",
                    "t_indicator_version",
                    version_id,
                    "snapshot_json must remain text",
                )
            )
            continue
        version_issues: list[MappingIssue] = []
        change_note = _required_text(source, "change_note", version_id, version_issues, max_length=255)
        created_by = _required_text(source, "created_by", version_id, version_issues, max_length=64)
        if version_issues:
            issues.extend(version_issues)
            continue

        version_row = MappedLegacyRow(
            source_system="datara_meta",
            source_table="t_indicator_version",
            source_id=version_id,
            target_table="rebuild_governance_semantic_metric_version",
            values={
                "metric_id": context.target_ids.get(
                    ("t_indicator", metric_source_id), TargetIdentityReference("t_indicator", metric_source_id)
                ),
                "version": raw_version,
                "snapshot_json": snapshot_json,
                "change_note": change_note,
                "created_by": created_by,
                "source_created_at": source.get("create_time"),
                "source_updated_at": None,
            },
            target_id=context.target_ids.get(("t_indicator_version", version_id)),
        )
        versions_by_metric.setdefault(metric_source_id, []).append(version_row)

    bundles = tuple(
        MappedI20MetricBundle(
            metric=bundle.metric,
            profile_values=bundle.profile_values,
            versions=tuple(
                sorted(versions_by_metric.get(source_id, ()), key=lambda row: (row.values["version"], row.source_id))
            ),
            dimension_rows=(),
            mapping_issues=bundle.mapping_issues,
        )
        for source_id, bundle in sorted(metrics_by_id.items(), key=lambda item: _identity_sort(item[0]))
    )
    for bundle in bundles:
        issues.extend(bundle.mapping_issues)
        for version in bundle.versions:
            issues.extend(version.mapping_issues)
    issues.extend(orphan_versions)
    return MappedI20Snapshot(bundles, tuple(orphan_versions), tuple(_unique_issues(issues)))


def _source_id(value: object, table: str, issues: list[MappingIssue]) -> str | None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        issues.append(
            MappingIssue("invalid_source_identity", table, repr(value), "expected positive integer source id")
        )
        return None
    return str(value)


def _required_text(
    row: Mapping[str, object], key: str, source_id: str, issues: list[MappingIssue], max_length: int | None = None
) -> str | None:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        issues.append(MappingIssue("invalid_metric_field", "t_indicator", source_id, f"{key} must be non-empty text"))
        return None
    if max_length is not None and len(value) > max_length:
        issues.append(MappingIssue("metric_field_too_long", "t_indicator", source_id, key))
        return None
    return value


def _optional_text(row: Mapping[str, object], key: str, source_id: str, issues: list[MappingIssue]) -> str | None:
    value = row.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        issues.append(MappingIssue("invalid_metric_field", "t_indicator", source_id, f"{key} must be text"))
        return None
    return value


def _validate_profile_values(values: Mapping[str, object], source_id: str, issues: list[MappingIssue]) -> None:
    limits = {
        "metric_type": 16,
        "business_domain": 64,
        "business_definition": 512,
        "technical_definition": 512,
        "source_kind": 16,
        "source_reference": 255,
        "source_field": 128,
        "output_table": 128,
        "output_task": 128,
        "period": 16,
        "unit": 16,
        "aggregation_function": 16,
        "numerator_field": 128,
        "time_field": 128,
        "dimension_field": 128,
        "filter_condition": 255,
        "legacy_dimensions": 255,
        "legacy_status": 16,
        "owner_name": 64,
    }
    nullable = {"aggregation_function", "numerator_field", "time_field", "dimension_field", "filter_condition"}
    for field_name, max_length in limits.items():
        value = values[field_name]
        if value is None and field_name in nullable:
            continue
        if not isinstance(value, str):
            issues.append(MappingIssue("invalid_metric_profile_field", "t_indicator", source_id, field_name))
        elif len(value) > max_length:
            issues.append(MappingIssue("metric_profile_field_too_long", "t_indicator", source_id, field_name))
    legacy_version = values["legacy_version"]
    if not isinstance(legacy_version, int) or isinstance(legacy_version, bool) or legacy_version < 1:
        issues.append(MappingIssue("invalid_metric_version", "t_indicator", source_id, repr(legacy_version)))


def _append_base_cycle_issues(
    base_edges: Mapping[str, str], bundles: dict[str, MappedI20MetricBundle], issues: list[MappingIssue]
) -> None:
    for origin in base_edges:
        seen_at: dict[str, int] = {}
        path: list[str] = []
        current = origin
        while current in base_edges:
            if current in seen_at:
                for source_id in sorted(path[seen_at[current] :], key=_identity_sort):
                    bundle = bundles[source_id]
                    issue = MappingIssue("cyclic_base_metric_reference", "t_indicator", source_id, "base metric cycle")
                    issues.append(issue)
                    bundle_issues = bundle.mapping_issues + (issue,)
                    bundles[source_id] = MappedI20MetricBundle(
                        metric=_with_issues(bundle.metric, bundle_issues),
                        profile_values=bundle.profile_values,
                        versions=bundle.versions,
                        dimension_rows=bundle.dimension_rows,
                        mapping_issues=bundle_issues,
                    )
                break
            seen_at[current] = len(path)
            path.append(current)
            current = base_edges[current]


def _resolve_metric_reference(
    identity: tuple[str, str],
    context: LegacyMappingContext,
    unresolved: list[tuple[str, str]],
    reference_field: str,
) -> int | TargetIdentityReference:
    canonical = context.approved_reference_aliases.get(identity, identity)
    if canonical not in context.target_ids and canonical not in context.pending_identities:
        canonical = identity
    target_id = context.target_ids.get(canonical)
    if target_id is not None:
        return target_id
    if canonical in context.pending_identities:
        return TargetIdentityReference(*canonical)
    unresolved.append((reference_field, identity[1]))
    return TargetIdentityReference(*canonical)


def _with_issues(
    row: MappedLegacyRow,
    issues: list[MappingIssue] | tuple[MappingIssue, ...],
    unresolved_references: tuple[tuple[str, str], ...] | None = None,
) -> MappedLegacyRow:
    merged = tuple(row.mapping_issues) + tuple(issue for issue in issues if issue not in row.mapping_issues)
    return MappedLegacyRow(
        source_system=row.source_system,
        source_table=row.source_table,
        source_id=row.source_id,
        target_table=row.target_table,
        values=row.values,
        unresolved_references=row.unresolved_references if unresolved_references is None else unresolved_references,
        child_rows=row.child_rows,
        identity_aliases=row.identity_aliases,
        target_id=row.target_id,
        mapping_issues=merged,
        mapping_notes=row.mapping_notes,
    )


def _unique_issues(issues: list[MappingIssue]) -> list[MappingIssue]:
    return list(dict.fromkeys(issues))


def _identity_sort(value: str) -> tuple[int, str]:
    return (0, f"{int(value):020d}") if value.isdigit() else (1, value)
