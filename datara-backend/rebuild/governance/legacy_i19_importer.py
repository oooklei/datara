"""Checkpointed import executor for the allowlisted I19 metadata/tag snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
from threading import RLock
from typing import Callable, Mapping

from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from rebuild.governance.legacy_dry_run import semantic_fingerprint
from rebuild.governance.legacy_i19_mapping import (
    I19ScopedTarget,
    I19TagTarget,
    LegacyI19MappingContext,
    MappedI19TagBundle,
    map_i19_snapshot,
)
from rebuild.governance.legacy_importer import (
    LegacyImportRejected,
    LegacyImportResult,
    _assert_isolated_target,
)
from rebuild.governance.legacy_mapping import MappedLegacyRow, TargetIdentityReference
from rebuild.governance.migration_checkpoints import (
    CheckpointConflict,
    CheckpointItem,
    MigrationCheckpointRepository,
)
from rebuild.governance.models import (
    AssetMetadataExtensionRecord,
    AssetRecord,
    AuditEventRecord,
    GovernanceTagRecord,
    LegacyTagDefinitionRecord,
    LegacyTagReferenceRecord,
    MigrationBatchRecord,
    MigrationItemRecord,
)
from rebuild.governance.service import GovernanceService
from rebuild.governance.legacy_source_reader import I19_SOURCE_COLUMNS, LegacyI19SourceSnapshot, _json_safe
from rebuild.identity.contracts import Permission
from rebuild.identity.models import UserRecord


_LOCAL_IMPORT_LOCK = RLock()
_TARGET_MODELS = {
    "rebuild_governance_asset_metadata_extension": AssetMetadataExtensionRecord,
    "rebuild_governance_legacy_tag_reference": LegacyTagReferenceRecord,
}


@dataclass(frozen=True)
class _ImportUnit:
    source_table: str
    source_id: str
    fingerprint: str
    row: MappedLegacyRow | None = None
    tag_bundle: MappedI19TagBundle | None = None

    @property
    def external_id(self) -> str:
        return f"{self.source_table}:{self.source_id}"


def i19_target_identity_digest(context: LegacyI19MappingContext) -> str:
    """Hash the exact project-scoped identity payload exposed by I19 preview."""

    payload = {
        "source_identities": sorted(
            (table, identity, target_id) for (table, identity), target_id in context.target_ids.items()
        ),
        "asset_natural_keys": sorted(
            (datasource_id, database_name, table_name, target.target_id)
            for (datasource_id, database_name, table_name), target in context.asset_targets.items()
        ),
        "tag_identities": sorted(
            (source_id, target.normalized_tag_id, target.legacy_definition_id)
            for source_id, target in context.tag_targets.items()
        ),
        "tagging_asset_identities": sorted(
            (target_type, target_key, target.target_id)
            for (target_type, target_key), target in context.tagging_asset_targets.items()
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_i19_mapping_context(session: Session, project_id: int) -> LegacyI19MappingContext:
    """Build a fresh I19 identity map from the current project-scoped target rows.

    Ambiguous source or natural identities fail closed. This helper is intended
    for both preview and the write executor so digest construction uses the same
    target evidence.
    """

    if project_id <= 0:
        raise ValueError("project_id must be positive")

    target_ids: dict[tuple[str, str], int] = {}
    asset_targets: dict[tuple[int, str, str], I19ScopedTarget] = {}
    asset_key_counts: dict[tuple[int, str, str], int] = {}
    extension_sources: dict[str, list[tuple[int, tuple[int, str, str], int]]] = {}

    extension_rows = session.execute(
        select(AssetMetadataExtensionRecord, AssetRecord)
        .join(AssetRecord, AssetRecord.id == AssetMetadataExtensionRecord.asset_id)
        .where(
            AssetRecord.project_id == project_id,
            AssetMetadataExtensionRecord.source_system == "datara_meta",
            AssetMetadataExtensionRecord.source_table == "t_meta_table_ext",
        )
    ).all()
    for extension, asset in extension_rows:
        key = (extension.legacy_datasource_id, extension.database_name, extension.table_name)
        asset_key_counts[key] = asset_key_counts.get(key, 0) + 1
        asset_targets[key] = I19ScopedTarget(asset.id, project_id)
        if extension.source_id:
            extension_sources.setdefault(extension.source_id, []).append((asset.id, key, extension.id))
    asset_targets = {key: value for key, value in asset_targets.items() if asset_key_counts[key] == 1}
    for source_id, candidates in extension_sources.items():
        if len(candidates) != 1:
            raise LegacyImportRejected("ambiguous I19 extension identity in target project")
        asset_id, key, extension_id = candidates[0]
        exact_asset = asset_targets.get(key)
        if exact_asset is None or exact_asset.target_id != asset_id:
            raise LegacyImportRejected("ambiguous I19 extension natural identity in target project")
        target_ids[("t_meta_table_ext", source_id)] = extension_id

    tag_targets: dict[str, I19TagTarget] = {}
    tag_rows = session.execute(
        select(LegacyTagDefinitionRecord, GovernanceTagRecord)
        .join(GovernanceTagRecord, GovernanceTagRecord.id == LegacyTagDefinitionRecord.normalized_tag_id)
        .where(
            GovernanceTagRecord.project_id == project_id,
            LegacyTagDefinitionRecord.source_system == "datara_meta",
            LegacyTagDefinitionRecord.source_table == "t_meta_tag",
        )
    ).all()
    for definition, tag in tag_rows:
        if not definition.source_id or definition.source_id in tag_targets:
            raise LegacyImportRejected("ambiguous I19 tag identity in target project")
        identity = ("t_meta_tag", definition.source_id)
        target_ids[identity] = definition.id
        tag_targets[definition.source_id] = I19TagTarget(tag.id, project_id, definition.id)

    tagging_asset_targets: dict[tuple[str, str], I19ScopedTarget] = {}
    tagging_key_candidates: dict[tuple[str, str], list[I19ScopedTarget]] = {}
    reference_rows = session.execute(
        select(LegacyTagReferenceRecord, AssetRecord)
        .join(GovernanceTagRecord, GovernanceTagRecord.id == LegacyTagReferenceRecord.tag_id)
        .outerjoin(AssetRecord, AssetRecord.id == LegacyTagReferenceRecord.resolved_asset_id)
        .where(
            LegacyTagReferenceRecord.project_id == project_id,
            GovernanceTagRecord.project_id == project_id,
            LegacyTagReferenceRecord.source_system == "datara_meta",
            LegacyTagReferenceRecord.source_table == "t_meta_tagging",
        )
    ).all()
    reference_sources: dict[str, list[int]] = {}
    for reference, asset in reference_rows:
        if reference.source_id:
            reference_sources.setdefault(reference.source_id, []).append(reference.id)
        if asset is not None and asset.project_id == project_id:
            tagging_key_candidates.setdefault((reference.target_type, reference.target_key), []).append(
                I19ScopedTarget(asset.id, project_id)
            )
    if any(len(ids) != 1 for ids in reference_sources.values()):
        raise LegacyImportRejected("ambiguous I19 tagging identity in target project")
    for source_id, ids in reference_sources.items():
        target_ids[("t_meta_tagging", source_id)] = ids[0]
    for key, candidates in tagging_key_candidates.items():
        unique_ids = {candidate.target_id for candidate in candidates}
        if len(unique_ids) > 1:
            raise LegacyImportRejected("ambiguous I19 resolved tagging target in project")
        if unique_ids:
            tagging_asset_targets[key] = candidates[0]

    return LegacyI19MappingContext(
        target_project_id=project_id,
        target_ids=target_ids,
        asset_targets=asset_targets,
        tag_targets=tag_targets,
        tagging_asset_targets=tagging_asset_targets,
    )


def execute_i19_legacy_import(
    session_factory: sessionmaker[Session],
    *,
    project_id: int,
    actor_id: int,
    source_snapshot: LegacyI19SourceSnapshot,
    expected_source_digest: str,
    expected_target_digest: str,
    idempotency_key: str,
    mapping_context_factory: Callable[[Session, int], LegacyI19MappingContext] = build_i19_mapping_context,
    on_item_error: Callable[[str, Exception], None] | None = None,
) -> LegacyImportResult:
    """Import a freshly read I19 source snapshot against fresh target identities.

    The source and target digests are compared before the batch is created. The
    fresh context is built in the target transaction under a target-local lock.
    Every source row has one checkpoint; a legacy tag and its normalized tag are
    a single atomic checkpoint bundle.
    """

    engine = _assert_isolated_target(session_factory)
    if project_id <= 0 or actor_id <= 0:
        raise ValueError("project_id and actor_id must be positive")
    if _source_digest(source_snapshot) != expected_source_digest:
        raise LegacyImportRejected("source or target snapshot changed; run a fresh preview")
    if engine.dialect.name == "mysql":
        lock_name = _project_lock_name(project_id)
        with engine.connect() as connection:
            acquired = connection.scalar(text("SELECT GET_LOCK(:lock_name, 30)"), {"lock_name": lock_name})
            if acquired != 1:
                raise LegacyImportRejected("could not acquire the target migration lock")
            try:
                return _execute_i19_unlocked(
                    session_factory,
                    project_id=project_id,
                    actor_id=actor_id,
                    source_snapshot=source_snapshot,
                    expected_source_digest=expected_source_digest,
                    expected_target_digest=expected_target_digest,
                    idempotency_key=idempotency_key,
                    mapping_context_factory=mapping_context_factory,
                    on_item_error=on_item_error,
                )
            finally:
                connection.execute(text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": lock_name})
    with _LOCAL_IMPORT_LOCK:
        return _execute_i19_unlocked(
            session_factory,
            project_id=project_id,
            actor_id=actor_id,
            source_snapshot=source_snapshot,
            expected_source_digest=expected_source_digest,
            expected_target_digest=expected_target_digest,
            idempotency_key=idempotency_key,
            mapping_context_factory=mapping_context_factory,
            on_item_error=on_item_error,
        )


def _execute_i19_unlocked(
    session_factory: sessionmaker[Session],
    *,
    project_id: int,
    actor_id: int,
    source_snapshot: LegacyI19SourceSnapshot,
    expected_source_digest: str,
    expected_target_digest: str,
    idempotency_key: str,
    mapping_context_factory: Callable[[Session, int], LegacyI19MappingContext],
    on_item_error: Callable[[str, Exception], None] | None,
) -> LegacyImportResult:
    _assert_isolated_target(session_factory)
    if _source_digest(source_snapshot) != expected_source_digest:
        raise LegacyImportRejected("source snapshot digest changed before import under the target lock")
    with session_factory() as session, session.begin():
        actor = session.get(UserRecord, actor_id)
        if actor is None:
            raise LegacyImportRejected("project edit permission is required for legacy import")
        project, allowed = GovernanceService(session).project_access(
            project_id,
            {"user_id": actor_id, "role": actor.role},
            Permission.EDIT_DEFINITION,
        )
        if project is None or not allowed:
            raise LegacyImportRejected("project edit permission is required for legacy import")

        context = mapping_context_factory(session, project_id)
        actual_target_digest = i19_target_identity_digest(context)
        if source_snapshot.digest != expected_source_digest or actual_target_digest != expected_target_digest:
            raise LegacyImportRejected("source or target snapshot changed; run a fresh preview")
        mapped = map_i19_snapshot(source_snapshot, context)
        if not mapped.ready_to_import:
            raise LegacyImportRejected("latest I19 mapping contains conflicts or blocked rows")

        units = _units(mapped.extensions, mapped.tags, mapped.tag_references, source_snapshot)
        payload_sha256 = _batch_digest(project_id, expected_source_digest, units)
        checkpoints = MigrationCheckpointRepository(session)
        batch = checkpoints.get_or_create_batch(
            source_system=f"datara_meta:i19:{project_id}",
            idempotency_key=idempotency_key,
            payload_sha256=payload_sha256,
            expected_count=len(units),
        )
        checkpoints.seed_items(
            batch.id,
            tuple(CheckpointItem(unit.source_table, unit.source_id, unit.fingerprint) for unit in units),
        )
        checkpoints.reopen_failed_items(batch.id)
        session.add(
            AuditEventRecord(
                actor_id=actor_id,
                project_id=project_id,
                action="legacy_i19_import_requested",
                resource_type="migration_batch",
                resource_id=str(batch.id),
                after_json=json.dumps(
                    {"source_digest": expected_source_digest, "target_digest": expected_target_digest},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        )
        batch_id = batch.id

        target_ids: dict[tuple[str, str], int] = dict(context.target_ids)
        # Existing and newly inserted tag identities are needed by source references.
        for source_id, target in context.tag_targets.items():
            target_ids[("i19_normalized_tag", source_id)] = target.normalized_tag_id

    for unit in units:
        try:
            target_id, aliases = _apply_unit(
                session_factory,
                batch_id=batch_id,
                unit=unit,
                target_ids=target_ids,
            )
            if target_id is not None:
                target_ids[(unit.source_table, unit.source_id)] = target_id
            target_ids.update(aliases)
        except Exception as error:
            if on_item_error is not None:
                on_item_error(unit.source_table, error)
            with session_factory() as session, session.begin():
                repository = MigrationCheckpointRepository(session)
                checkpoint = _get_item(session, batch_id, unit.external_id)
                if checkpoint.status in {"pending", "failed"}:
                    repository.mark_item(
                        batch_id,
                        checkpoint.external_id,
                        status="failed",
                        error_message=type(error).__name__,
                    )
            break

    with session_factory() as session:
        batch = session.get(MigrationBatchRecord, batch_id)
        if batch is None:
            raise RuntimeError("migration batch disappeared")
        return LegacyImportResult(
            batch_id=batch.id,
            status=batch.status,
            expected_count=batch.expected_count,
            imported_count=batch.imported_count,
            skipped_count=batch.skipped_count,
            error_count=batch.error_count,
        )


def _project_lock_name(project_id: int) -> str:
    """Serialize every I19 import for a project, regardless of request key."""

    return "datara_i19_" + hashlib.sha256(str(project_id).encode("ascii")).hexdigest()[:52]


def _source_digest(snapshot: LegacyI19SourceSnapshot) -> str:
    if snapshot.schema != "datara_meta":
        raise LegacyImportRejected("I19 source snapshot schema must be datara_meta")
    rows = snapshot.rows
    counts = snapshot.counts
    if not isinstance(rows, Mapping) or set(rows) != set(I19_SOURCE_COLUMNS):
        raise LegacyImportRejected("I19 source snapshot rows are invalid")
    if not isinstance(counts, Mapping) or set(counts) != set(I19_SOURCE_COLUMNS):
        raise LegacyImportRejected("I19 source snapshot counts are invalid")
    for table in I19_SOURCE_COLUMNS:
        if counts[table] != len(rows[table]) or any(not isinstance(row, Mapping) for row in rows[table]):
            raise LegacyImportRejected("I19 source snapshot counts do not match row payload")
    payload = {
        "schema": snapshot.schema,
        "rows": {table: [_json_safe(row) for row in rows[table]] for table in I19_SOURCE_COLUMNS},
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    if snapshot.digest != digest:
        raise LegacyImportRejected("I19 source snapshot digest does not match its row payload")
    return digest


def _units(
    extensions: tuple[MappedLegacyRow, ...],
    tags: tuple[MappedI19TagBundle, ...],
    references: tuple[MappedLegacyRow, ...],
    source_snapshot: LegacyI19SourceSnapshot,
) -> tuple[_ImportUnit, ...]:
    units = [_ImportUnit(row.source_table, row.source_id, semantic_fingerprint(row), row=row) for row in extensions]
    for bundle in tags:
        definition_values = dict(bundle.definition.values)
        definition_values["normalized_tag_id"] = TargetIdentityReference("i19_normalized_tag", bundle.source_id)
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "normalized_tag_values": _canonical(bundle.normalized_tag_values),
                    "definition": _row_fingerprint(bundle.definition, definition_values),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        units.append(_ImportUnit(bundle.definition.source_table, bundle.source_id, fingerprint, tag_bundle=bundle))
    tag_id_by_reference = {
        str(row.get("id")): str(row.get("tag_id"))
        for row in source_snapshot.rows["t_meta_tagging"]
        if row.get("id") is not None and row.get("tag_id") is not None
    }
    for row in references:
        values = dict(row.values)
        source_tag_id = tag_id_by_reference.get(row.source_id)
        if source_tag_id is not None:
            values["tag_id"] = TargetIdentityReference("i19_normalized_tag", source_tag_id)
            values["legacy_tag_definition_id"] = TargetIdentityReference("t_meta_tag", source_tag_id)
        if values.get("resolved_asset_id") is not None:
            values["resolved_asset_id"] = TargetIdentityReference(
                "i19_tagging_asset", f"{values.get('target_type')}:{values.get('target_key')}"
            )
        units.append(_ImportUnit(row.source_table, row.source_id, _row_fingerprint(row, values), row=row))
    return tuple(sorted(units, key=lambda unit: _unit_order(unit)))


def _row_fingerprint(row: MappedLegacyRow, values: Mapping[str, object]) -> str:
    canonical = {
        "target_table": row.target_table,
        "values": _canonical(values),
        "child_rows": _canonical(row.child_rows),
    }
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _unit_order(unit: _ImportUnit) -> tuple[int, str, str]:
    order = {"t_meta_table_ext": 0, "t_meta_tag": 1, "t_meta_tagging": 2}
    return (order.get(unit.source_table, 9), unit.source_table, unit.source_id)


def _batch_digest(project_id: int, source_digest: str, units: tuple[_ImportUnit, ...]) -> str:
    payload = {
        "project_id": project_id,
        "source_digest": source_digest,
        "units": sorted((unit.source_table, unit.source_id, unit.fingerprint) for unit in units),
    }
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode("utf-8")).hexdigest()


def _apply_unit(
    session_factory: sessionmaker[Session],
    *,
    batch_id: int,
    unit: _ImportUnit,
    target_ids: Mapping[tuple[str, str], int],
) -> tuple[int | None, dict[tuple[str, str], int]]:
    aliases: dict[tuple[str, str], int] = {}
    integrity_conflict = False
    replay_result: tuple[int | None, dict[tuple[str, str], int]] | None = None
    with session_factory() as session, session.begin():
        checkpoints = MigrationCheckpointRepository(session)
        checkpoint = _get_item(session, batch_id, unit.external_id)
        if checkpoint.status in {"imported", "skipped"}:
            if checkpoint.source_payload_sha256 != unit.fingerprint:
                raise CheckpointConflict(f"source payload changed for {unit.external_id}")
            if not _integrity_matches(session, checkpoint, batch_id, unit, target_ids):
                checkpoints.mark_target_integrity_conflict(batch_id, checkpoint.external_id)
                integrity_conflict = True
            else:
                replay_result = _checkpoint_target_ids(session, checkpoint, unit)
        elif checkpoint.status == "conflict":
            raise CheckpointConflict(f"checkpoint conflict requires review: {unit.external_id}")
        if integrity_conflict:
            pass
        elif replay_result is not None:
            pass
        elif unit.tag_bundle is not None:
            tag_id, definition_id = _insert_tag_bundle(session, batch_id, checkpoint, unit.tag_bundle)
            checkpoints.mark_item(
                batch_id,
                checkpoint.external_id,
                status="imported",
                target_type="i19_tag_bundle",
                target_id=f"{tag_id}:{definition_id}",
            )
            aliases[("i19_normalized_tag", unit.source_id)] = tag_id
            aliases[("t_meta_tag", unit.source_id)] = definition_id
            return definition_id, aliases
        else:
            assert unit.row is not None
            entity = _insert_row(session, batch_id, unit.row, target_ids)
            checkpoints.mark_item(
                batch_id,
                checkpoint.external_id,
                status="imported",
                target_type=unit.row.target_table,
                target_id=str(entity.id),
            )
            if unit.source_table == "t_meta_tagging":
                aliases[("t_meta_tagging", unit.source_id)] = entity.id
            return entity.id, aliases
    if integrity_conflict:
        raise CheckpointConflict("target integrity mismatch")
    assert replay_result is not None
    return replay_result


def _insert_tag_bundle(
    session: Session,
    batch_id: int,
    checkpoint: MigrationItemRecord,
    bundle: MappedI19TagBundle,
) -> tuple[int, int]:
    tag = GovernanceTagRecord(**dict(bundle.normalized_tag_values))
    session.add(tag)
    session.flush()
    definition_values = _resolve_values(
        session,
        batch_id,
        bundle.definition,
        {("i19_normalized_tag", bundle.source_id): tag.id},
    )
    definition = LegacyTagDefinitionRecord(
        **definition_values,
        source_system=bundle.definition.source_system,
        source_table=bundle.definition.source_table,
        source_id=bundle.definition.source_id,
        migration_batch_id=batch_id,
    )
    session.add(definition)
    session.flush()
    return tag.id, definition.id


def _insert_row(session: Session, batch_id: int, row: MappedLegacyRow, target_ids: Mapping[tuple[str, str], int]):
    model = _TARGET_MODELS.get(row.target_table)
    if model is None:
        raise CheckpointConflict(f"unsupported I19 target entity: {row.target_table}")
    values = _resolve_values(session, batch_id, row, target_ids)
    entity = model(
        **values,
        source_system=row.source_system,
        source_table=row.source_table,
        source_id=row.source_id,
        migration_batch_id=batch_id,
    )
    session.add(entity)
    session.flush()
    return entity


def _resolve_values(session: Session, batch_id: int, row: MappedLegacyRow, target_ids: Mapping[tuple[str, str], int]):
    values = dict(row.values)
    for key, value in tuple(values.items()):
        if not isinstance(value, TargetIdentityReference):
            continue
        identity = (value.source_table, value.source_id)
        resolved_id = target_ids.get(identity)
        if resolved_id is None:
            checkpoint = session.scalar(
                select(MigrationItemRecord).where(
                    MigrationItemRecord.batch_id == batch_id,
                    MigrationItemRecord.external_id == f"{identity[0]}:{identity[1]}",
                )
            )
            if checkpoint and checkpoint.status == "imported" and checkpoint.target_id:
                parts = checkpoint.target_id.split(":", 1)
                resolved_id = int(parts[1] if identity[0] == "t_meta_tag" and len(parts) == 2 else parts[0])
        if resolved_id is None and value.source_table == "i19_normalized_tag":
            tag_checkpoint = session.scalar(
                select(MigrationItemRecord).where(
                    MigrationItemRecord.batch_id == batch_id,
                    MigrationItemRecord.external_id == f"t_meta_tag:{value.source_id}",
                )
            )
            if tag_checkpoint and tag_checkpoint.status == "imported":
                resolved_id = int(tag_checkpoint.target_id.split(":", 1)[0])
        if resolved_id is None:
            raise CheckpointConflict(f"unresolved I19 target identity {value.source_table}:{value.source_id}")
        values[key] = resolved_id
    return values


def _integrity_matches(
    session: Session,
    checkpoint: MigrationItemRecord,
    batch_id: int,
    unit: _ImportUnit,
    target_ids: Mapping[tuple[str, str], int],
) -> bool:
    if unit.tag_bundle is not None:
        try:
            tag_id_text, definition_id_text = checkpoint.target_id.split(":", 1)
            tag_id, definition_id = int(tag_id_text), int(definition_id_text)
        except (AttributeError, ValueError):
            return False
        tag = session.get(GovernanceTagRecord, tag_id)
        definition = session.get(LegacyTagDefinitionRecord, definition_id)
        if tag is None or definition is None or definition.normalized_tag_id != tag.id:
            return False
        if not _has_provenance(definition, unit.tag_bundle.definition, batch_id):
            return False
        expected_definition = dict(unit.tag_bundle.definition.values)
        if isinstance(expected_definition.get("normalized_tag_id"), TargetIdentityReference):
            expected_definition["normalized_tag_id"] = tag.id
        tag_matches = all(
            getattr(tag, name, object()) == value
            for name, value in unit.tag_bundle.normalized_tag_values.items()
        )
        definition_matches = all(
            getattr(definition, name, object()) == value
            for name, value in expected_definition.items()
        )
        return tag_matches and definition_matches
    row = unit.row
    assert row is not None
    model = _TARGET_MODELS.get(row.target_table)
    if model is None or checkpoint.target_type != row.target_table:
        return False
    try:
        entity = session.get(model, int(checkpoint.target_id))
    except (TypeError, ValueError):
        return False
    if entity is None or not _has_provenance(entity, row, batch_id):
        return False
    try:
        expected = _resolve_values(session, batch_id, row, target_ids)
    except CheckpointConflict:
        return False
    return all(getattr(entity, key, object()) == value for key, value in expected.items())


def _checkpoint_target_ids(
    session: Session, checkpoint: MigrationItemRecord, unit: _ImportUnit
) -> tuple[int | None, dict[tuple[str, str], int]]:
    if unit.tag_bundle:
        tag_id, definition_id = (int(part) for part in checkpoint.target_id.split(":", 1))
        return definition_id, {
            ("i19_normalized_tag", unit.source_id): tag_id,
            ("t_meta_tag", unit.source_id): definition_id,
        }
    try:
        target_id = int(checkpoint.target_id)
    except (TypeError, ValueError):
        return None, {}
    aliases = {(unit.source_table, unit.source_id): target_id}
    return target_id, aliases


def _has_provenance(entity: object, row: MappedLegacyRow, batch_id: int) -> bool:
    return (
        getattr(entity, "source_system", None) == row.source_system
        and getattr(entity, "source_table", None) == row.source_table
        and getattr(entity, "source_id", None) == row.source_id
        and getattr(entity, "migration_batch_id", None) == batch_id
    )


def _get_item(session: Session, batch_id: int, external_id: str) -> MigrationItemRecord:
    item = session.scalar(
        select(MigrationItemRecord).where(
            MigrationItemRecord.batch_id == batch_id,
            MigrationItemRecord.external_id == external_id,
        )
    )
    if item is None:
        raise KeyError(f"migration checkpoint not found: {external_id}")
    return item


def _canonical(value: object) -> object:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, TargetIdentityReference):
        return {"source_table": value.source_table, "source_id": value.source_id}
    return value
