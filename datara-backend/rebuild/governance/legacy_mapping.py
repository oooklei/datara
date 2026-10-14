"""Pure source-to-target mappings for the legacy governance carry-forward."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


class LegacyMappingError(ValueError):
    """Raised when a source row cannot be mapped without inventing data."""


@dataclass(frozen=True)
class LegacyMappingContext:
    """Explicit operator-supplied scope and source-to-target identity maps."""

    target_project_id: int | None = None
    target_ids: Mapping[tuple[str, str], int] = field(default_factory=dict)


@dataclass(frozen=True)
class MappedLegacyRow:
    source_system: str
    source_table: str
    source_id: str
    target_table: str
    values: Mapping[str, object]
    unresolved_references: tuple[tuple[str, str], ...] = ()

    @property
    def ready_to_import(self) -> bool:
        return not self.unresolved_references


_MODEL_REFERENCES = (
    ("layer", "t_dw_layer", "layer_id"),
    ("biz_domain", "t_biz_domain", "domain_id"),
    ("engine", "t_engine_type", "engine_id"),
)


def map_legacy_row(
    source_table: str,
    source: Mapping[str, object],
    context: LegacyMappingContext,
) -> MappedLegacyRow:
    """Map one legacy warehouse model without inferring project or dictionary IDs."""

    if source_table != "t_dw_model":
        raise LegacyMappingError(f"unsupported legacy source table: {source_table}")
    source_id = source.get("id")
    if source_id is None:
        raise LegacyMappingError("legacy t_dw_model row is missing id")
    if context.target_project_id is None:
        raise LegacyMappingError("target project must be explicit for project-scoped legacy rows")

    unresolved: list[tuple[str, str]] = []
    references: dict[str, int | None] = {}
    for source_field, identity_table, target_field in _MODEL_REFERENCES:
        identity_value = source.get(source_field)
        if identity_value in (None, ""):
            references[target_field] = None
            continue
        identity = (identity_table, str(identity_value))
        target_id = context.target_ids.get(identity)
        references[target_field] = target_id
        if target_id is None:
            unresolved.append((source_field, str(identity_value)))

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
        target_table="rebuild_governance_warehouse_model",
        values=values,
        unresolved_references=tuple(unresolved),
    )
