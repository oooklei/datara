"""Pure, fail-closed mapping for legacy I19 metadata and tag snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping

from rebuild.governance.legacy_mapping import MappedLegacyRow, MappingIssue, TargetIdentityReference
from rebuild.governance.legacy_source_reader import I19_SOURCE_COLUMNS


_TABLES = set(I19_SOURCE_COLUMNS)


@dataclass(frozen=True)
class I19ScopedTarget:
    """An operator/source-snapshot-bound target ID and its owning project."""

    target_id: int
    project_id: int


@dataclass(frozen=True)
class I19TagTarget:
    """The explicit normalized tag identity and optional legacy detail identity."""

    normalized_tag_id: int
    project_id: int
    legacy_definition_id: int | None = None


@dataclass(frozen=True)
class LegacyI19MappingContext:
    target_project_id: int | None = None
    target_ids: Mapping[tuple[str, str], int] = field(default_factory=dict)
    asset_targets: Mapping[tuple[int, str, str], I19ScopedTarget] = field(default_factory=dict)
    tag_targets: Mapping[str, I19TagTarget] = field(default_factory=dict)
    tagging_asset_targets: Mapping[tuple[str, str], I19ScopedTarget] = field(default_factory=dict)


@dataclass(frozen=True)
class MappedI19TagBundle:
    source_id: str
    normalized_tag_id: int | TargetIdentityReference
    normalized_tag_values: Mapping[str, object]
    definition: MappedLegacyRow
    mapping_issues: tuple[MappingIssue, ...] = ()

    @property
    def ready_to_import(self) -> bool:
        return not self.mapping_issues and self.definition.ready_to_import


@dataclass(frozen=True)
class MappedI19Snapshot:
    extensions: tuple[MappedLegacyRow, ...]
    tags: tuple[MappedI19TagBundle, ...]
    tag_references: tuple[MappedLegacyRow, ...]
    mapping_issues: tuple[MappingIssue, ...]

    @property
    def ready_to_import(self) -> bool:
        return (
            not self.mapping_issues
            and all(row.ready_to_import for row in self.extensions + self.tag_references)
            and all(tag.ready_to_import for tag in self.tags)
        )


def map_i19_snapshot(snapshot: object, context: LegacyI19MappingContext) -> MappedI19Snapshot:
    """Map the three I19 tables without connecting to source or target storage."""

    rows = getattr(snapshot, "rows", None)
    if getattr(snapshot, "schema", None) != "datara_meta" or not isinstance(rows, Mapping) or set(rows) != _TABLES:
        return _empty(
            MappingIssue(
                "invalid_i19_snapshot_shape", "", "", "expected datara_meta snapshot with all three I19 tables"
            )
        )
    project_id = context.target_project_id
    if not _positive_int(project_id):
        return _empty(MappingIssue("target_project_required", "", "", "target project must be an explicit positive id"))

    issues = _validate_context(context, project_id)
    if issues:
        return _empty(*issues)

    source_rows: dict[str, dict[str, Mapping[str, object]]] = {}
    for table, (_, columns) in I19_SOURCE_COLUMNS.items():
        values = rows[table]
        if not isinstance(values, (tuple, list)):
            issues.append(MappingIssue("invalid_i19_snapshot_shape", table, "", "rows must be ordered sequences"))
            continue
        indexed: dict[str, Mapping[str, object]] = {}
        for source in values:
            if not isinstance(source, Mapping):
                issues.append(MappingIssue("invalid_source_row", table, "", "row must be a mapping"))
                continue
            source_id = _source_id(source.get("id"), table, issues)
            if source_id is None:
                continue
            if set(source) != set(columns):
                issues.append(
                    MappingIssue("incomplete_source_row", table, source_id, "column set differs from reader contract")
                )
                continue
            if source_id in indexed:
                issues.append(MappingIssue("duplicate_source_identity", table, source_id, "duplicate source id"))
                continue
            indexed[source_id] = source
        source_rows[table] = indexed
    if any(table not in source_rows for table in _TABLES):
        return _empty(*issues)

    extensions = _map_extensions(source_rows["t_meta_table_ext"], context, issues)
    tags = _map_tags(source_rows["t_meta_tag"], context, issues)
    tag_refs = _map_taggings(source_rows["t_meta_tagging"], tags, context, issues)
    for row in extensions + tag_refs:
        issues.extend(row.mapping_issues)
        issues.extend(
            MappingIssue("unresolved_reference", row.source_table, row.source_id, f"{table}:{identity}")
            for table, identity in row.unresolved_references
        )
    for tag in tags:
        issues.extend(tag.mapping_issues)
        issues.extend(tag.definition.mapping_issues)
    return MappedI19Snapshot(
        extensions=extensions,
        tags=tags,
        tag_references=tag_refs,
        mapping_issues=tuple(dict.fromkeys(issues)),
    )


def _map_extensions(source_rows, context, issues):
    output: list[MappedLegacyRow] = []
    seen_natural_keys: set[tuple[int, str, str]] = set()
    for source_id, source in sorted(source_rows.items(), key=lambda item: _identity_sort(item[0])):
        local: list[MappingIssue] = []
        ds_id = source.get("ds_id")
        if not _positive_int(ds_id):
            local.append(MappingIssue("invalid_source_value", "t_meta_table_ext", source_id, "ds_id must be positive"))
        db_name = _text(source.get("db_name"), 128, "t_meta_table_ext", source_id, "db_name", local, required=True)
        table_name = _text(
            source.get("table_name"), 128, "t_meta_table_ext", source_id, "table_name", local, required=True
        )
        for field_name, max_length in {
            "biz_domain": 64,
            "security_level": 16,
            "owner": 64,
            "remark": 255,
        }.items():
            _text(source.get(field_name), max_length, "t_meta_table_ext", source_id, field_name, local)

        natural_key = (ds_id, db_name, table_name) if _positive_int(ds_id) and db_name and table_name else None
        target = context.asset_targets.get(natural_key) if natural_key is not None else None
        asset_id: int | TargetIdentityReference | None = None
        unresolved: tuple[tuple[str, str], ...] = ()
        if target is None and natural_key is not None:
            encoded = _asset_key(*natural_key)
            asset_id = TargetIdentityReference("i19_asset_identity", encoded)
            unresolved = (("i19_asset_identity", encoded),)
            local.append(MappingIssue("unresolved_asset_identity", "t_meta_table_ext", source_id, encoded))
        elif target is not None:
            asset_id = target.target_id

        if natural_key is not None:
            if natural_key in seen_natural_keys:
                local.append(
                    MappingIssue("duplicate_asset_extension_identity", "t_meta_table_ext", source_id, repr(natural_key))
                )
            seen_natural_keys.add(natural_key)
        row = _mapped(
            "t_meta_table_ext",
            source_id,
            "rebuild_governance_asset_metadata_extension",
            {
                "asset_id": asset_id,
                "legacy_datasource_id": ds_id,
                "database_name": db_name or "",
                "table_name": table_name or "",
                "business_domain": source.get("biz_domain", ""),
                "security_level": source.get("security_level", ""),
                "owner_name": source.get("owner", ""),
                "remark": source.get("remark", ""),
                "source_created_at": _datetime_value(
                    source.get("create_time"), "t_meta_table_ext", source_id, "create_time", local
                ),
                "source_updated_at": _datetime_value(
                    source.get("update_time"), "t_meta_table_ext", source_id, "update_time", local
                ),
            },
            context,
            local,
            unresolved_references=unresolved,
        )
        issues.extend(local)
        output.append(row)
    return tuple(output)


def _map_tags(source_rows, context, issues):
    output: list[MappedI19TagBundle] = []
    seen_names: set[str] = set()
    for source_id, source in sorted(source_rows.items(), key=lambda item: _identity_sort(item[0])):
        local: list[MappingIssue] = []
        name = _text(source.get("name"), 64, "t_meta_tag", source_id, "name", local, required=True)
        category = _text(source.get("cat"), 16, "t_meta_tag", source_id, "cat", local)
        color = _text(source.get("color"), 16, "t_meta_tag", source_id, "color", local)
        description = _text(source.get("desc"), 255, "t_meta_tag", source_id, "desc", local)
        created_at = _datetime_value(source.get("create_time"), "t_meta_tag", source_id, "create_time", local)
        updated_at = _datetime_value(source.get("update_time"), "t_meta_tag", source_id, "update_time", local)
        if name:
            if name in seen_names:
                local.append(MappingIssue("duplicate_tag_name", "t_meta_tag", source_id, name))
            seen_names.add(name)

        target = context.tag_targets.get(source_id)
        if target is None:
            normalized_tag_id: int | TargetIdentityReference = TargetIdentityReference("i19_normalized_tag", source_id)
            definition_id = context.target_ids.get(("t_meta_tag", source_id))
        else:
            normalized_tag_id = target.normalized_tag_id
            definition_id = target.legacy_definition_id
            explicit_definition_id = context.target_ids.get(("t_meta_tag", source_id))
            if explicit_definition_id is not None and definition_id not in (None, explicit_definition_id):
                local.append(
                    MappingIssue(
                        "conflicting_tag_definition_identity", "t_meta_tag", source_id, str(explicit_definition_id)
                    )
                )
            if definition_id is None:
                definition_id = explicit_definition_id

        tag_values = {
            "project_id": context.target_project_id,
            "namespace": "legacy_i19",
            "tag_key": f"legacy-{source_id}",
            "display_name": name or "",
            "description": description or "",
        }
        definition = MappedLegacyRow(
            source_system="datara_meta",
            source_table="t_meta_tag",
            source_id=source_id,
            target_table="rebuild_governance_legacy_tag_definition",
            values={
                "normalized_tag_id": normalized_tag_id,
                "tag_category": category or "",
                "color": color or "",
                "tag_description": description or "",
                "source_created_at": created_at,
                "source_updated_at": updated_at,
            },
            target_id=definition_id,
            mapping_issues=tuple(local),
        )
        bundle = MappedI19TagBundle(source_id, normalized_tag_id, tag_values, definition, tuple(local))
        issues.extend(local)
        output.append(bundle)
    return tuple(output)


def _map_taggings(source_rows, tags, context, issues):
    tag_bundles = {bundle.source_id: bundle for bundle in tags}
    output: list[MappedLegacyRow] = []
    seen_keys: set[tuple[int, str, str]] = set()
    for source_id, source in sorted(source_rows.items(), key=lambda item: _identity_sort(item[0])):
        local: list[MappingIssue] = []
        tag_id = source.get("tag_id")
        if not _positive_int(tag_id):
            local.append(MappingIssue("invalid_source_value", "t_meta_tagging", source_id, "tag_id must be positive"))
        target_type = _text(
            source.get("target_type"), 16, "t_meta_tagging", source_id, "target_type", local, required=True
        )
        target_key = _text(
            source.get("target_key"), 255, "t_meta_tagging", source_id, "target_key", local, required=True
        )
        created_by = _text(source.get("created_by"), 64, "t_meta_tagging", source_id, "created_by", local)
        source_created_at = _datetime_value(
            source.get("create_time"), "t_meta_tagging", source_id, "create_time", local
        )

        tag_bundle = tag_bundles.get(str(tag_id)) if _positive_int(tag_id) else None
        explicit_tag = context.tag_targets.get(str(tag_id)) if _positive_int(tag_id) else None
        normalized_tag_id: int | TargetIdentityReference | None = None
        definition_id: int | TargetIdentityReference | None = None
        if tag_bundle is not None:
            normalized_tag_id = tag_bundle.normalized_tag_id
            definition_id = tag_bundle.definition.target_id
            if definition_id is None:
                definition_id = TargetIdentityReference("t_meta_tag", str(tag_id))
        elif explicit_tag is not None:
            normalized_tag_id = explicit_tag.normalized_tag_id
            definition_id = explicit_tag.legacy_definition_id or context.target_ids.get(("t_meta_tag", str(tag_id)))
        if normalized_tag_id is None or definition_id is None:
            local.append(MappingIssue("unresolved_tag_identity", "t_meta_tagging", source_id, str(tag_id)))
            normalized_tag_id = normalized_tag_id or TargetIdentityReference("i19_normalized_tag", str(tag_id))
            definition_id = definition_id or TargetIdentityReference("t_meta_tag", str(tag_id))

        relation_key = (tag_id, target_type or "", target_key or "") if _positive_int(tag_id) else None
        if relation_key is not None:
            if relation_key in seen_keys:
                local.append(
                    MappingIssue("duplicate_tagging_identity", "t_meta_tagging", source_id, repr(relation_key))
                )
            seen_keys.add(relation_key)

        target_asset = context.tagging_asset_targets.get((target_type or "", target_key or ""))
        resolved_asset_id: int | None = None
        mapping_notes: tuple[Mapping[str, object], ...] = ()
        if target_asset is None:
            mapping_notes = ({"resolution": "unresolved", "reason": "no exact project asset identity"},)
        else:
            resolved_asset_id = target_asset.target_id

        unresolved_refs = ()
        if any(issue.code == "unresolved_tag_identity" for issue in local):
            unresolved_refs = (("t_meta_tag", str(tag_id)),)
        row = _mapped(
            "t_meta_tagging",
            source_id,
            "rebuild_governance_legacy_tag_reference",
            {
                "tag_id": normalized_tag_id,
                "project_id": context.target_project_id,
                "legacy_tag_definition_id": definition_id,
                "target_type": target_type or "",
                "target_key": target_key or "",
                "resolved_asset_id": resolved_asset_id,
                "created_by": created_by or "",
                "source_created_at": source_created_at,
                "source_updated_at": None,
            },
            context,
            local,
            unresolved_references=unresolved_refs,
            mapping_notes=mapping_notes,
        )
        issues.extend(local)
        output.append(row)
    return tuple(output)


def _validate_context(context, project_id):
    issues: list[MappingIssue] = []
    valid_source_tables = _TABLES
    for (source_table, source_id), target_id in context.target_ids.items():
        if source_table in valid_source_tables and not _positive_int(target_id):
            issues.append(MappingIssue("invalid_explicit_target_id", source_table, source_id, repr(target_id)))
    for natural_key, target in context.asset_targets.items():
        if not _valid_natural_key(natural_key) or not isinstance(target, I19ScopedTarget):
            issues.append(
                MappingIssue("invalid_asset_identity_map", "t_meta_table_ext", repr(natural_key), "invalid target map")
            )
        elif not _positive_int(target.target_id) or not _positive_int(target.project_id):
            issues.append(
                MappingIssue("invalid_scoped_target_id", "t_meta_table_ext", _asset_key(*natural_key), repr(target))
            )
        elif target.project_id != project_id:
            issues.append(
                MappingIssue(
                    "cross_project_target_identity",
                    "t_meta_table_ext",
                    _asset_key(*natural_key),
                    str(target.project_id),
                )
            )
    for source_id, target in context.tag_targets.items():
        if not _positive_int_string(source_id) or not isinstance(target, I19TagTarget):
            issues.append(MappingIssue("invalid_tag_identity_map", "t_meta_tag", str(source_id), "invalid target map"))
        elif (
            not _positive_int(target.normalized_tag_id)
            or not _positive_int(target.project_id)
            or (target.legacy_definition_id is not None and not _positive_int(target.legacy_definition_id))
        ):
            issues.append(MappingIssue("invalid_scoped_target_id", "t_meta_tag", source_id, repr(target)))
        elif target.project_id != project_id:
            issues.append(
                MappingIssue("cross_project_target_identity", "t_meta_tag", source_id, str(target.project_id))
            )
    for key, target in context.tagging_asset_targets.items():
        if not isinstance(key, tuple) or len(key) != 2 or not isinstance(target, I19ScopedTarget):
            issues.append(
                MappingIssue("invalid_tag_target_asset_map", "t_meta_tagging", repr(key), "invalid target map")
            )
        elif not _positive_int(target.target_id) or not _positive_int(target.project_id):
            issues.append(MappingIssue("invalid_scoped_target_id", "t_meta_tagging", repr(key), repr(target)))
        elif target.project_id != project_id:
            issues.append(
                MappingIssue("cross_project_target_identity", "t_meta_tagging", repr(key), str(target.project_id))
            )
    return issues


def _mapped(
    source_table, source_id, target_table, values, context, issues, *, unresolved_references=(), mapping_notes=()
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


def _text(value, max_length, table, source_id, field_name, issues, *, required=False):
    if not isinstance(value, str) or (required and not value):
        issues.append(MappingIssue("invalid_source_value", table, source_id, f"{field_name} must be text"))
        return None
    if len(value) > max_length:
        issues.append(MappingIssue("target_text_too_long", table, source_id, field_name))
        return None
    return value


def _datetime_value(value, table, source_id, field_name, issues):
    if value is None:
        return None
    if isinstance(value, str):
        if "T" not in value and " " not in value:
            issues.append(MappingIssue("invalid_source_value", table, source_id, f"{field_name} must include a time"))
            return None
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            issues.append(
                MappingIssue("invalid_source_value", table, source_id, f"{field_name} must be an ISO datetime")
            )
            return None
    if not isinstance(value, datetime):
        issues.append(
            MappingIssue("invalid_source_value", table, source_id, f"{field_name} must be a datetime or null")
        )
        return None
    if value.tzinfo is not None and value.utcoffset() is not None:
        issues.append(MappingIssue("timezone_aware_source_datetime", table, source_id, field_name))
        return None
    return value


def _source_id(value, table, issues):
    if not _positive_int(value):
        issues.append(MappingIssue("invalid_source_identity", table, repr(value), "expected positive integer id"))
        return None
    return str(value)


def _positive_int(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _positive_int_string(value):
    return isinstance(value, str) and value.isdigit() and int(value) > 0


def _valid_natural_key(value):
    return (
        isinstance(value, tuple)
        and len(value) == 3
        and _positive_int(value[0])
        and isinstance(value[1], str)
        and bool(value[1])
        and isinstance(value[2], str)
        and bool(value[2])
    )


def _asset_key(ds_id, db_name, table_name):
    return f"{ds_id}/{db_name}/{table_name}"


def _identity_sort(value):
    return (0, f"{int(value):020d}") if value.isdigit() else (1, value)


def _empty(*issues):
    return MappedI19Snapshot((), (), (), tuple(issues))
