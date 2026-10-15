"""Project-scoped read-only snapshot of normalized I18 target rows."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.governance.legacy_dry_run import I18TargetSnapshot, semantic_fingerprint
from rebuild.governance.legacy_mapping import MappedLegacyRow
from rebuild.governance.models import (
    GovernanceDomainRecord,
    ModelEngineRecord,
    WarehouseLayerRecord,
    WarehouseModelFieldRecord,
    WarehouseModelRecord,
    WarehouseModelRelationFieldRecord,
    WarehouseModelRelationRecord,
    WarehouseModelVersionRecord,
)


LEGACY_SOURCE_SYSTEM = "datara_meta"


class LegacyI18TargetSnapshotRepository:
    """Read I18-shaped target rows without ORM mutation or implicit commits."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def read_project_snapshot(self, project_id: int) -> I18TargetSnapshot:
        if project_id <= 0:
            raise ValueError("project_id must be positive")

        domains = self._rows(GovernanceDomainRecord, project_id)
        layers = self._rows(WarehouseLayerRecord, project_id)
        engines = self._rows(ModelEngineRecord, project_id)
        models = self._rows(WarehouseModelRecord, project_id)
        model_ids = {row.id for row in models}
        fields = self.session.scalars(
            select(WarehouseModelFieldRecord)
            .join(WarehouseModelRecord, WarehouseModelRecord.id == WarehouseModelFieldRecord.model_id)
            .where(WarehouseModelRecord.project_id == project_id)
            .order_by(WarehouseModelFieldRecord.model_id, WarehouseModelFieldRecord.ordinal_position)
        ).all()
        relations = self._rows(WarehouseModelRelationRecord, project_id)
        relation_ids = {row.id for row in relations}
        relation_fields = self.session.scalars(
            select(WarehouseModelRelationFieldRecord)
            .where(WarehouseModelRelationFieldRecord.relation_id.in_(relation_ids))
            .order_by(
                WarehouseModelRelationFieldRecord.relation_id,
                WarehouseModelRelationFieldRecord.ordinal_position,
            )
        ).all() if relation_ids else []
        versions = self.session.scalars(
            select(WarehouseModelVersionRecord)
            .where(WarehouseModelVersionRecord.model_id.in_(model_ids))
            .order_by(WarehouseModelVersionRecord.model_id, WarehouseModelVersionRecord.version)
        ).all() if model_ids else []

        relation_fields_by_id: dict[int, list[WarehouseModelRelationFieldRecord]] = {}
        for child in relation_fields:
            relation_fields_by_id.setdefault(child.relation_id, []).append(child)
        model_fields_mutable: dict[int, set[str]] = {}
        for field in fields:
            model_fields_mutable.setdefault(field.model_id, set()).add(field.field_name)
        model_fields = {model_id: frozenset(names) for model_id, names in model_fields_mutable.items()}

        source_rows: list[MappedLegacyRow] = []
        for row in domains:
            values = {
                "project_id": row.project_id,
                "name": row.name,
                "description": row.description,
                **self._source_times(row),
            }
            source_rows.append(
                self._mapped(
                    row,
                    "rebuild_governance_domain",
                    values,
                    aliases=(("t_biz_domain", row.name),),
                )
            )
        for row in layers:
            values = {
                "project_id": row.project_id,
                "code": row.code,
                "name": row.name,
                "naming_rule": row.naming_rule,
                "color": row.color,
                "sequence": row.sequence,
                **self._source_times(row),
            }
            source_rows.append(self._mapped(row, "rebuild_governance_warehouse_layer", values))
        for row in engines:
            values = {
                "project_id": row.project_id,
                "name": row.name,
                "ddl_dialect": row.ddl_dialect,
                "vendor_flag": row.vendor_flag,
                **self._source_times(row),
            }
            source_rows.append(self._mapped(row, "rebuild_governance_model_engine", values))
        for row in models:
            values = {
                "project_id": row.project_id,
                "code": row.code,
                "name": row.name,
                "layer_id": row.layer_id,
                "model_type": row.model_type,
                "domain_id": row.domain_id,
                "engine_id": row.engine_id,
                "legacy_datasource_id": row.legacy_datasource_id,
                "database_name": row.database_name,
                "security_level": row.security_level,
                "status": row.status,
                "version": row.version,
                "er_position_json": self._decode_json(row.er_position_json),
                "last_ddl_snapshot": row.last_ddl_snapshot,
                "built_at": row.built_at,
                "built_by": row.built_by,
                "owner_name": row.owner_name,
                "description": row.description,
                **self._source_times(row),
            }
            source_rows.append(self._mapped(row, "rebuild_governance_warehouse_model", values))
        for row in fields:
            values = {
                "model_id": row.model_id,
                "ordinal_position": row.ordinal_position,
                "field_name": row.field_name,
                "data_type": row.data_type,
                "length": row.length,
                "precision": row.precision,
                "nullable": row.nullable,
                "default_value": row.default_value,
                "description": row.description,
                "is_primary_key": row.is_primary_key,
                "is_partition_key": row.is_partition_key,
                "dictionary_reference": row.dictionary_reference,
                **self._source_times(row),
            }
            source_rows.append(self._mapped(row, "rebuild_governance_warehouse_model_field", values))
        for row in relations:
            child_rows = tuple(
                {
                    "ordinal_position": child.ordinal_position,
                    "source_field_name": child.source_field_name,
                    "target_field_name": child.target_field_name,
                }
                for child in relation_fields_by_id.get(row.id, ())
            )
            values = {
                "project_id": row.project_id,
                "source_model_id": row.source_model_id,
                "target_model_id": row.target_model_id,
                "relation_type": row.relation_type,
                "join_description": row.join_description,
                "created_by": row.created_by,
                **self._source_times(row),
            }
            source_rows.append(
                self._mapped(row, "rebuild_governance_warehouse_model_relation", values, child_rows=child_rows)
            )
        for row in versions:
            values = {
                "model_id": row.model_id,
                "version": row.version,
                "snapshot_json": row.snapshot_json,
                "change_note": row.change_note,
                "created_by": row.created_by,
                **self._source_times(row),
            }
            source_rows.append(self._mapped(row, "rebuild_governance_warehouse_model_version", values))

        target_ids: dict[tuple[str, str], int] = {}
        fingerprints: dict[tuple[str, str], str] = {}
        for row in source_rows:
            if row.source_system != LEGACY_SOURCE_SYSTEM or not row.source_table or not row.source_id:
                continue
            identity = (row.source_table, row.source_id)
            if identity in target_ids:
                raise ValueError(f"duplicate target source identity: {row.source_table}:{row.source_id}")
            target_ids[identity] = self._target_id(row)
            for alias in row.identity_aliases:
                target_ids[alias] = self._target_id(row)
            fingerprints[identity] = semantic_fingerprint(row)

        unique_key_owners: dict[tuple[object, ...], tuple[str, str]] = {}
        for row in domains:
            self._add_key(unique_key_owners, ("domain", project_id, row.name), row, "t_biz_domain")
        for row in layers:
            self._add_key(unique_key_owners, ("layer", project_id, row.code), row, "t_dw_layer")
        for row in engines:
            self._add_key(unique_key_owners, ("engine", project_id, row.name), row, "t_engine_type")
        for row in models:
            self._add_key(unique_key_owners, ("model", project_id, row.code), row, "t_dw_model")
        for row in fields:
            self._add_key(unique_key_owners, ("model_field", row.model_id, row.field_name), row, "t_dw_model_field")
        for row in versions:
            self._add_key(unique_key_owners, ("model_version", row.model_id, row.version), row, "t_dw_model_version")

        captured_at = datetime.now(ZoneInfo("Asia/Shanghai"))
        digest_payload = {
            "project_id": project_id,
            "row_fingerprints": sorted((list(key), value) for key, value in fingerprints.items()),
            "target_ids": sorted((list(key), value) for key, value in target_ids.items()),
            "model_fields": sorted((key, sorted(value)) for key, value in model_fields.items()),
            "unique_key_owners": sorted((list(key), list(value)) for key, value in unique_key_owners.items()),
        }
        digest = hashlib.sha256(
            json.dumps(digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return I18TargetSnapshot(
            project_id=project_id,
            captured_at=captured_at,
            digest=digest,
            row_fingerprints=fingerprints,
            target_ids=target_ids,
            model_fields=model_fields,
            unique_key_owners=unique_key_owners,
        )

    def _rows(self, model, project_id: int):
        return self.session.scalars(select(model).where(model.project_id == project_id)).all()

    @staticmethod
    def _source_times(row) -> dict[str, object]:
        return {
            "source_created_at": row.source_created_at,
            "source_updated_at": row.source_updated_at,
        }

    @staticmethod
    def _mapped(row, target_table, values, *, child_rows=(), aliases=()):
        return MappedLegacyRow(
            source_system=row.source_system or "",
            source_table=row.source_table or "",
            source_id=row.source_id or "",
            target_table=target_table,
            values=values,
            child_rows=child_rows,
            identity_aliases=aliases,
            target_id=row.id,
        )

    @staticmethod
    def _decode_json(value: str):
        try:
            return json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return value

    @staticmethod
    def _target_id(row) -> int:
        if row.target_id is None:
            raise ValueError("target identity row is missing its normalized primary key")
        return row.target_id

    @staticmethod
    def _add_key(key_owners, key, row, source_table):
        identity = (
            (row.source_table, row.source_id)
            if row.source_system == LEGACY_SOURCE_SYSTEM and row.source_table and row.source_id
            else (source_table, f"target:{row.id}")
        )
        existing = key_owners.get(key)
        if existing is not None and existing != identity:
            raise ValueError(f"duplicate target unique key: {key!r}")
        key_owners[key] = identity
