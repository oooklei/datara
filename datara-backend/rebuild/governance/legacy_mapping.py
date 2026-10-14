"""Pure source-to-target mappings for the legacy governance carry-forward."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Mapping


class LegacyMappingError(ValueError):
    """Raised when a source row cannot be mapped without inventing data."""


@dataclass(frozen=True)
class LegacyMappingContext:
    """Explicit operator-supplied scope and source-to-target identity maps."""

    target_project_id: int | None = None
    target_ids: Mapping[tuple[str, str], int] = field(default_factory=dict)
    pending_identities: frozenset[tuple[str, str]] = frozenset()


@dataclass(frozen=True)
class TargetIdentityReference:
    """A declared source identity that will receive its target ID during import."""

    source_table: str
    source_id: str


@dataclass(frozen=True)
class MappedLegacyRow:
    source_system: str
    source_table: str
    source_id: str
    target_table: str
    values: Mapping[str, object]
    unresolved_references: tuple[tuple[str, str], ...] = ()
    child_rows: tuple[Mapping[str, object], ...] = ()
    identity_aliases: tuple[tuple[str, str], ...] = ()
    target_id: int | None = None

    @property
    def ready_to_import(self) -> bool:
        return not self.unresolved_references


@dataclass(frozen=True)
class MappingIssue:
    code: str
    source_table: str
    source_id: str
    detail: str


_MODEL_REFERENCES = (
    ("layer", "t_dw_layer", "layer_id"),
    ("biz_domain", "t_biz_domain", "domain_id"),
    ("engine", "t_engine_type", "engine_id"),
)


def _resolve_target_identity(
    identity: tuple[str, str],
    context: LegacyMappingContext,
    unresolved: list[tuple[str, str]],
    reference_field: str,
) -> int | TargetIdentityReference:
    target_id = context.target_ids.get(identity)
    if target_id is not None:
        return target_id
    if identity in context.pending_identities:
        return TargetIdentityReference(*identity)
    unresolved.append((reference_field, identity[1]))
    return TargetIdentityReference(*identity)


def validate_i18_mapping_graph(
    rows: list[MappedLegacyRow],
    existing_model_fields: Mapping[int, frozenset[str]] | None = None,
) -> tuple[MappingIssue, ...]:
    """Check same-batch identities and model-relation field pairs before import."""

    issues: list[MappingIssue] = []
    identity_counts: dict[tuple[str, str], int] = {}
    for row in rows:
        identity = (row.source_table, row.source_id)
        identity_counts[identity] = identity_counts.get(identity, 0) + 1
        for alias in row.identity_aliases:
            identity_counts[alias] = identity_counts.get(alias, 0) + 1
    batch_identities = set(identity_counts)
    for (source_table, source_id), count in identity_counts.items():
        if count > 1:
            issues.append(MappingIssue("duplicate_source_identity", source_table, source_id, str(count)))

    for row in rows:
        for source_table, source_id in row.unresolved_references:
            issues.append(
                MappingIssue(
                    "unresolved_reference",
                    row.source_table,
                    row.source_id,
                    f"{source_table}:{source_id}",
                )
            )
        for value in row.values.values():
            if isinstance(value, TargetIdentityReference) and (
                value.source_table,
                value.source_id,
            ) not in batch_identities:
                issues.append(
                    MappingIssue(
                        "pending_identity_missing_from_batch",
                        row.source_table,
                        row.source_id,
                        f"{value.source_table}:{value.source_id}",
                    )
                )

    model_fields: dict[tuple[str, str], set[str]] = {}
    for row in rows:
        if row.source_table != "t_dw_model_field":
            continue
        model_ref = row.values.get("model_id")
        if isinstance(model_ref, TargetIdentityReference):
            model_identity = (model_ref.source_table, model_ref.source_id)
            model_fields.setdefault(model_identity, set()).add(str(row.values.get("field_name", "")))

    existing_model_fields = existing_model_fields or {}
    for row in rows:
        if row.source_table != "t_dw_model_relation":
            continue
        source_ref = row.values.get("source_model_id")
        target_ref = row.values.get("target_model_id")
        for role, model_ref in (("source", source_ref), ("target", target_ref)):
            if isinstance(model_ref, TargetIdentityReference):
                identity = (model_ref.source_table, model_ref.source_id)
                fields = model_fields.get(identity, set())
            elif isinstance(model_ref, int):
                fields = set(existing_model_fields.get(model_ref, frozenset()))
            else:
                continue
            if not fields:
                issues.append(
                    MappingIssue(
                        f"relation_{role}_model_fields_unavailable",
                        row.source_table,
                        row.source_id,
                        str(model_ref),
                    )
                )
        source_fields = _fields_for_model_ref(source_ref, model_fields, existing_model_fields)
        target_fields = _fields_for_model_ref(target_ref, model_fields, existing_model_fields)
        for child in row.child_rows:
            source_name = str(child.get("source_field_name", ""))
            target_name = str(child.get("target_field_name", ""))
            if source_fields is not None and source_name not in source_fields:
                issues.append(
                    MappingIssue(
                        "relation_source_field_missing", row.source_table, row.source_id, source_name
                    )
                )
            if target_fields is not None and target_name not in target_fields:
                issues.append(
                    MappingIssue(
                        "relation_target_field_missing", row.source_table, row.source_id, target_name
                    )
                )
    return tuple(issues)


def _fields_for_model_ref(
    model_ref: object,
    model_fields: Mapping[tuple[str, str], set[str]],
    existing_model_fields: Mapping[int, frozenset[str]],
) -> set[str] | None:
    if isinstance(model_ref, TargetIdentityReference):
        identity = (model_ref.source_table, model_ref.source_id)
        return model_fields.get(identity, set())
    if isinstance(model_ref, int):
        fields = existing_model_fields.get(model_ref)
        return set(fields) if fields is not None else None
    return None


def map_legacy_row(
    source_table: str,
    source: Mapping[str, object],
    context: LegacyMappingContext,
) -> MappedLegacyRow:
    """Map one I18 source row without inferring scope or foreign identities."""

    target_tables = {
        "t_biz_domain": "rebuild_governance_domain",
        "t_dw_layer": "rebuild_governance_warehouse_layer",
        "t_engine_type": "rebuild_governance_model_engine",
        "t_dw_model": "rebuild_governance_warehouse_model",
        "t_dw_model_field": "rebuild_governance_warehouse_model_field",
        "t_dw_model_relation": "rebuild_governance_warehouse_model_relation",
        "t_dw_model_version": "rebuild_governance_warehouse_model_version",
    }
    target_table = target_tables.get(source_table)
    if target_table is None:
        raise LegacyMappingError(f"unsupported legacy source table: {source_table}")

    identity_fields = {"t_dw_layer": "code", "t_engine_type": "name"}
    source_id = source.get(identity_fields.get(source_table, "id"))
    if source_id is None:
        raise LegacyMappingError(f"legacy {source_table} row is missing its identity")
    if context.target_project_id is None:
        raise LegacyMappingError("target project must be explicit for project-scoped legacy rows")

    dictionary_values: dict[str, object] | None = None
    if source_table == "t_biz_domain":
        dictionary_values = {
            "name": source.get("name", ""),
            "description": source.get("remark", ""),
        }
    elif source_table == "t_dw_layer":
        dictionary_values = {
            "code": source_id,
            "name": source.get("name", ""),
            "naming_rule": source.get("rule", ""),
            "color": source.get("color", "#64748b"),
            "sequence": source.get("seq", 0),
        }
    elif source_table == "t_engine_type":
        dictionary_values = {
            "name": source_id,
            "ddl_dialect": source.get("ddl", ""),
            "vendor_flag": source.get("xc", False),
        }
    if dictionary_values is not None:
        dictionary_values.update(
            {
                "project_id": context.target_project_id,
                "source_created_at": source.get("create_time"),
                "source_updated_at": source.get("update_time"),
            }
        )
        return MappedLegacyRow(
            source_system="datara_meta",
            source_table=source_table,
            source_id=str(source_id),
            target_table=target_table,
            values=dictionary_values,
            identity_aliases=(
                ((source_table, str(dictionary_values["name"])),)
                if source_table == "t_biz_domain" and dictionary_values["name"]
                else ()
            ),
        )

    if source_table == "t_dw_model_field":
        model_identity = ("t_dw_model", str(source.get("model_id", "")))
        unresolved: list[tuple[str, str]] = []
        model_id = _resolve_target_identity(model_identity, context, unresolved, "model_id")
        values: dict[str, object] = {
            "model_id": model_id,
            "ordinal_position": source.get("seq", 0),
            "field_name": source.get("name", ""),
            "data_type": source.get("data_type", "VARCHAR"),
            "length": source.get("length", ""),
            "precision": source.get("precision", ""),
            "nullable": source.get("nullable", True),
            "default_value": source.get("default_value", ""),
            "description": source.get("comment", ""),
            "is_primary_key": source.get("is_pk", False),
            "is_partition_key": source.get("is_partition", False),
            "dictionary_reference": source.get("dict_ref", ""),
            "source_created_at": source.get("create_time"),
            "source_updated_at": source.get("update_time"),
        }
        return MappedLegacyRow(
            source_system="datara_meta",
            source_table=source_table,
            source_id=str(source_id),
            target_table=target_table,
            values=values,
            unresolved_references=tuple(unresolved),
        )

    if source_table == "t_dw_model_version":
        model_identity = ("t_dw_model", str(source.get("model_id", "")))
        unresolved: list[tuple[str, str]] = []
        model_id = _resolve_target_identity(model_identity, context, unresolved, "model_id")
        values = {
            "model_id": model_id,
            "version": source.get("version", 1),
            "snapshot_json": source.get("snapshot_json", "{}"),
            "change_note": source.get("change_note", ""),
            "created_by": source.get("created_by", ""),
            "source_created_at": source.get("create_time"),
            "source_updated_at": source.get("update_time"),
        }
        return MappedLegacyRow(
            source_system="datara_meta",
            source_table=source_table,
            source_id=str(source_id),
            target_table=target_table,
            values=values,
            unresolved_references=tuple(unresolved),
        )

    if source_table == "t_dw_model_relation":
        src_identity = ("t_dw_model", str(source.get("src_model_id", "")))
        tgt_identity = ("t_dw_model", str(source.get("tgt_model_id", "")))
        unresolved = []
        src_model_id = _resolve_target_identity(src_identity, context, unresolved, "src_model_id")
        tgt_model_id = _resolve_target_identity(tgt_identity, context, unresolved, "tgt_model_id")
        try:
            source_fields = json.loads(source.get("src_fields") or "[]")
            target_fields = json.loads(source.get("tgt_fields") or "[]")
        except (TypeError, json.JSONDecodeError) as exc:
            raise LegacyMappingError("invalid relation field pairs: expected JSON arrays") from exc
        if (
            not isinstance(source_fields, list)
            or not isinstance(target_fields, list)
            or len(source_fields) != len(target_fields)
            or any(not isinstance(name, str) or not name for name in source_fields + target_fields)
        ):
            raise LegacyMappingError("invalid relation field pairs: arrays must contain paired non-empty names")
        return MappedLegacyRow(
            source_system="datara_meta",
            source_table=source_table,
            source_id=str(source_id),
            target_table=target_table,
            values={
                "project_id": context.target_project_id,
                "source_model_id": src_model_id,
                "target_model_id": tgt_model_id,
                "relation_type": source.get("rel_type", "1:N"),
                "join_description": source.get("join_desc", ""),
                "created_by": source.get("created_by", ""),
                "source_created_at": source.get("create_time"),
                "source_updated_at": source.get("update_time"),
            },
            unresolved_references=tuple(unresolved),
            child_rows=tuple(
                {
                    "ordinal_position": index,
                    "source_field_name": source_name,
                    "target_field_name": target_name,
                }
                for index, (source_name, target_name) in enumerate(zip(source_fields, target_fields), start=1)
            ),
        )

    unresolved: list[tuple[str, str]] = []
    references: dict[str, int | TargetIdentityReference | None] = {}
    for source_field, identity_table, target_field in _MODEL_REFERENCES:
        identity_value = source.get(source_field)
        if identity_value in (None, ""):
            references[target_field] = None
            continue
        identity = (identity_table, str(identity_value))
        references[target_field] = _resolve_target_identity(identity, context, unresolved, source_field)

    values: dict[str, object] = {
        "project_id": context.target_project_id,
        "code": source.get("code", ""),
        "name": source.get("name", ""),
        "model_type": source.get("type", "明细表"),
        "legacy_datasource_id": source.get("ds_id"),
        "database_name": source.get("db_name"),
        "security_level": source.get("security_level", "内部"),
        "status": source.get("status", "draft"),
        "version": source.get("version", 1),
        "er_position_json": source.get("er_pos") or {},
        "last_ddl_snapshot": source.get("last_ddl"),
        "built_at": source.get("built_at"),
        "built_by": source.get("built_by"),
        "owner_name": source.get("owner", ""),
        "description": source.get("remark", ""),
        "source_created_at": source.get("create_time"),
        "source_updated_at": source.get("update_time"),
        **references,
    }
    return MappedLegacyRow(
        source_system="datara_meta",
        source_table=source_table,
        source_id=str(source_id),
        target_table=target_table,
        values=values,
        unresolved_references=tuple(unresolved),
    )
