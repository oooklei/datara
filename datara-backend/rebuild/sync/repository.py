"""Persistence and mapping validation for R4-SYNC (design 正本 §6.4).

- Slot semantics mirror R4-DEPENDENCY: re-saving the same
  (project, workflow, version, task) slot replaces the draft snapshot.
- Mapping entries must record exactly the §6.4 mapping 8 fields; the snapshot
  is stored verbatim so the run-time consumes the version-bound configuration.
- Narrow scope (disclosed): publication immutability is unenforceable until
  the workflow-registry domain lands (same disclosure as R4-DEPENDENCY).
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.sync.models import SyncTaskDefinitionRecord

# §6.4 mapping 8 fields — every mapping entry records exactly these keys.
MAPPING_FIELDS: tuple[str, ...] = (
    "source_column",
    "target_column",
    "source_type",
    "target_type",
    "transform_expression",
    "nullable",
    "default_value",
    "mapping_status",
)

# mapping_status value domain: auto-generated, user-adjusted, unmatched side.
MAPPING_STATUSES: tuple[str, ...] = ("AUTO", "ADJUSTED", "UNMATCHED")


class SyncDomainError(ValueError):
    """Domain rejection carrying a stable machine code (SYNC_*)."""

    def __init__(self, code: str, msg: str, diagnostics: list[dict[str, str]] | None = None) -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.diagnostics = diagnostics or []

    def payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "msg": self.msg,
            "data": {"diagnostics": self.diagnostics} if self.diagnostics else None,
        }


def validate_mappings(mappings: Any) -> list[dict[str, Any]]:
    """Validate the verbatim §6.4 mapping snapshot (exactly the 8 fields per entry)."""
    if not isinstance(mappings, list) or not mappings:
        raise SyncDomainError("SYNC_INVALID_MAPPING", "mappings must be a non-empty list")
    diagnostics: list[dict[str, str]] = []
    for index, entry in enumerate(mappings):
        if not isinstance(entry, dict):
            diagnostics.append({"field": f"mappings[{index}]", "code": "INVALID", "message": "must be an object"})
            continue
        missing = [field for field in MAPPING_FIELDS if field not in entry]
        extra = [field for field in entry if field not in MAPPING_FIELDS]
        for field in missing:
            diagnostics.append(
                {"field": f"mappings[{index}].{field}", "code": "MISSING", "message": f"{field} is required"}
            )
        for field in extra:
            diagnostics.append(
                {"field": f"mappings[{index}].{field}", "code": "UNKNOWN", "message": f"{field} is not a mapping field"}
            )
        status = entry.get("mapping_status")
        if status is not None and status not in MAPPING_STATUSES:
            diagnostics.append(
                {
                    "field": f"mappings[{index}].mapping_status",
                    "code": "INVALID",
                    "message": f"mapping_status must be one of {list(MAPPING_STATUSES)}",
                }
            )
    if diagnostics:
        raise SyncDomainError("SYNC_INVALID_MAPPING", "mapping snapshot violates the §6.4 contract", diagnostics)
    return mappings


def generate_auto_mappings(
    source_columns: list[dict[str, Any]], target_columns: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """§6.4 自动映射: name-based matching over the explored columns.

    Matched pairs get mapping_status AUTO with the target's explored type;
    unmatched source columns stay UNMATCHED with an empty target side so the
    user can adjust them (§6.4 用户调整映射).
    """
    targets_by_name = {str(column["column_name"]): column for column in target_columns}
    mappings: list[dict[str, Any]] = []
    for source in source_columns:
        name = str(source["column_name"])
        target = targets_by_name.get(name)
        if target is None:
            mappings.append(
                {
                    "source_column": name,
                    "target_column": "",
                    "source_type": str(source.get("data_type", "")),
                    "target_type": "",
                    "transform_expression": "",
                    "nullable": bool(source.get("is_nullable", True)),
                    "default_value": None,
                    "mapping_status": "UNMATCHED",
                }
            )
            continue
        mappings.append(
            {
                "source_column": name,
                "target_column": str(target["column_name"]),
                "source_type": str(source.get("data_type", "")),
                "target_type": str(target.get("data_type", "")),
                "transform_expression": "",
                "nullable": bool(source.get("is_nullable", True)),
                "default_value": None,
                "mapping_status": "AUTO",
            }
        )
    return mappings


class SyncRepository:
    """Slot-keyed persistence for sync task definitions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save_plan(
        self,
        *,
        project_id: int,
        workflow_id: int,
        workflow_version: int,
        task_id: str,
        src_ref: dict[str, Any],
        tgt_ref: dict[str, Any],
        mappings: list[dict[str, Any]],
        transform_config: dict[str, Any] | None,
        target_properties: dict[str, Any] | None,
    ) -> SyncTaskDefinitionRecord:
        record = self.get_plan(project_id, workflow_id, workflow_version, task_id)
        if record is None:
            record = SyncTaskDefinitionRecord(
                project_id=project_id,
                workflow_id=workflow_id,
                workflow_version=workflow_version,
                task_id=task_id,
            )
            self._session.add(record)
        record.src_datasource_id = src_ref["datasource_id"]
        record.src_schema = src_ref["schema"]
        record.src_object = src_ref["object"]
        record.tgt_datasource_id = tgt_ref["datasource_id"]
        record.tgt_schema = tgt_ref["schema"]
        record.tgt_object = tgt_ref["object"]
        record.field_mappings_json = json.dumps(mappings, ensure_ascii=False)
        record.transform_config_json = json.dumps(transform_config or {}, ensure_ascii=False)
        record.target_properties_json = json.dumps(target_properties or {}, ensure_ascii=False)
        return record

    def get_plan(
        self, project_id: int, workflow_id: int, workflow_version: int, task_id: str
    ) -> SyncTaskDefinitionRecord | None:
        return self._session.scalar(
            select(SyncTaskDefinitionRecord).where(
                SyncTaskDefinitionRecord.project_id == project_id,
                SyncTaskDefinitionRecord.workflow_id == workflow_id,
                SyncTaskDefinitionRecord.workflow_version == workflow_version,
                SyncTaskDefinitionRecord.task_id == task_id,
            )
        )

    def list_plans(self, project_id: int, workflow_id: int, workflow_version: int) -> list[SyncTaskDefinitionRecord]:
        """映射随版本引用: only the snapshots bound to this workflow version."""
        return list(
            self._session.scalars(
                select(SyncTaskDefinitionRecord)
                .where(
                    SyncTaskDefinitionRecord.project_id == project_id,
                    SyncTaskDefinitionRecord.workflow_id == workflow_id,
                    SyncTaskDefinitionRecord.workflow_version == workflow_version,
                )
                .order_by(SyncTaskDefinitionRecord.id)
            )
        )


def serialize_plan(record: SyncTaskDefinitionRecord) -> dict[str, Any]:
    """JSON-serialize a stored snapshot for the wire (mappings verbatim)."""
    return {
        "project_id": record.project_id,
        "workflow_id": record.workflow_id,
        "workflow_version": record.workflow_version,
        "task_id": record.task_id,
        "source": {
            "datasource_id": record.src_datasource_id,
            "schema": record.src_schema,
            "object": record.src_object,
        },
        "target": {
            "datasource_id": record.tgt_datasource_id,
            "schema": record.tgt_schema,
            "object": record.tgt_object,
        },
        "mappings": json.loads(record.field_mappings_json),
        "transform_config": json.loads(record.transform_config_json) if record.transform_config_json else {},
        "target_properties": json.loads(record.target_properties_json) if record.target_properties_json else {},
    }
