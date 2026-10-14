"""Checkpointed I18 importer for the isolated rebuild governance schema.

This service is deliberately not exposed as an HTTP write route yet. A caller
must separately obtain the import approval and re-run the full remote gates.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from threading import RLock
from typing import Callable, Mapping

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from rebuild.governance.legacy_dry_run import I18TargetSnapshot, semantic_fingerprint
from rebuild.governance.legacy_mapping import (
    LegacyMappingContext,
    MappedLegacyRow,
    TargetIdentityReference,
    map_legacy_row,
)
from rebuild.governance.legacy_migration_service import build_i18_legacy_dry_run
from rebuild.governance.legacy_source_reader import I18_SOURCE_COLUMNS, LegacyI18SourceSnapshot
from rebuild.governance.migration_checkpoints import (
    CheckpointConflict,
    CheckpointItem,
    MigrationCheckpointRepository,
)
from rebuild.governance.service import GovernanceService
from rebuild.identity.contracts import Permission
from rebuild.identity.models import UserRecord
from rebuild.governance.models import (
    AuditEventRecord,
    GovernanceDomainRecord,
    MigrationBatchRecord,
    MigrationItemRecord,
    ModelEngineRecord,
    WarehouseLayerRecord,
    WarehouseModelFieldRecord,
    WarehouseModelRecord,
    WarehouseModelRelationFieldRecord,
    WarehouseModelRelationRecord,
    WarehouseModelVersionRecord,
)


_TARGET_MODELS = {
    "rebuild_governance_domain": GovernanceDomainRecord,
    "rebuild_governance_warehouse_layer": WarehouseLayerRecord,
    "rebuild_governance_model_engine": ModelEngineRecord,
    "rebuild_governance_warehouse_model": WarehouseModelRecord,
    "rebuild_governance_warehouse_model_field": WarehouseModelFieldRecord,
    "rebuild_governance_warehouse_model_relation": WarehouseModelRelationRecord,
    "rebuild_governance_warehouse_model_version": WarehouseModelVersionRecord,
}
_LOCAL_IMPORT_LOCK = RLock()


class LegacyImportRejected(ValueError):
    """Raised when the latest dry-run is not safe for an import attempt."""


@dataclass(frozen=True)
class LegacyImportResult:
    batch_id: int
    status: str
    expected_count: int
    imported_count: int
    skipped_count: int
    error_count: int


def execute_i18_legacy_import(
    session_factory: sessionmaker[Session],
    *,
    project_id: int,
    actor_id: int,
    source_snapshot: LegacyI18SourceSnapshot,
    target_snapshot: I18TargetSnapshot,
    idempotency_key: str,
    on_item_error: Callable[[str, Exception], None] | None = None,
) -> LegacyImportResult:
    """Serialize same-process and MySQL import attempts before touching target rows."""

    engine = _assert_isolated_target(session_factory)
    if engine.dialect.name == "mysql":
        lock_name = "datara_i18_" + hashlib.sha256(
            f"{project_id}:{idempotency_key}".encode("utf-8")
        ).hexdigest()[:52]
        with engine.connect() as connection:
            acquired = connection.scalar(text("SELECT GET_LOCK(:lock_name, 30)"), {"lock_name": lock_name})
            if acquired != 1:
                raise LegacyImportRejected("could not acquire the target migration lock")
            try:
                return _execute_i18_legacy_import_unlocked(
                    session_factory,
                    project_id=project_id,
                    actor_id=actor_id,
                    source_snapshot=source_snapshot,
                    target_snapshot=target_snapshot,
                    idempotency_key=idempotency_key,
                    on_item_error=on_item_error,
                )
            finally:
                connection.execute(text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": lock_name})
    with _LOCAL_IMPORT_LOCK:
        return _execute_i18_legacy_import_unlocked(
            session_factory,
            project_id=project_id,
            actor_id=actor_id,
            source_snapshot=source_snapshot,
            target_snapshot=target_snapshot,
            idempotency_key=idempotency_key,
            on_item_error=on_item_error,
        )


def _execute_i18_legacy_import_unlocked(
    session_factory: sessionmaker[Session],
    *,
    project_id: int,
    actor_id: int,
    source_snapshot: LegacyI18SourceSnapshot,
    target_snapshot: I18TargetSnapshot,
    idempotency_key: str,
    on_item_error: Callable[[str, Exception], None] | None = None,
) -> LegacyImportResult:
    """Apply one prevalidated snapshot using one transaction per source row.

    `on_item_error` is an optional operational callback; exceptions stored in
    the database are class names only, never driver messages or SQL payloads.
    """

    if actor_id <= 0:
        raise ValueError("actor_id must be positive")
    if target_snapshot.project_id != project_id:
        raise LegacyImportRejected("target snapshot project does not match requested project")
    _assert_isolated_target(session_factory)

    dry_run = build_i18_legacy_dry_run(project_id, source_snapshot, target_snapshot)
    if not dry_run.plan.ready_to_import:
        raise LegacyImportRejected("latest I18 dry-run contains conflicts or blocked rows")

    mapped_rows = _map_rows(project_id, source_snapshot, target_snapshot)
    mapped_by_identity = {(row.source_table, row.source_id): row for row in mapped_rows}
    entry_by_identity = {(entry.source_table, entry.source_id): entry for entry in dry_run.plan.entries}
    payload_sha256 = _batch_digest(project_id, source_snapshot.digest, mapped_rows)
    source_system = f"datara_meta:i18:{project_id}"

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
        checkpoints = MigrationCheckpointRepository(session)
        batch = checkpoints.get_or_create_batch(
            source_system=source_system,
            idempotency_key=idempotency_key,
            payload_sha256=payload_sha256,
            expected_count=len(mapped_rows),
        )
        checkpoints.seed_items(
            batch.id,
            tuple(
                CheckpointItem(row.source_table, row.source_id, semantic_fingerprint(row))
                for row in mapped_rows
            ),
        )
        checkpoints.reopen_failed_items(batch.id)
        session.add(
            AuditEventRecord(
                actor_id=actor_id,
                project_id=project_id,
                action="legacy_i18_import_requested",
                resource_type="migration_batch",
                resource_id=str(batch.id),
                after_json=json.dumps(
                    {"source_digest": source_snapshot.digest, "target_digest": target_snapshot.digest},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        )
        batch_id = batch.id

    # Persist approved skip/unchanged dispositions before importing parents.
    for identity, entry in entry_by_identity.items():
        if entry.disposition not in {"skipped", "unchanged"}:
            continue
        with session_factory() as session, session.begin():
            repo = MigrationCheckpointRepository(session)
            checkpoint = _get_item(session, batch_id, _external_id(identity))
            if checkpoint.status in {"pending", "failed"}:
                if checkpoint.status == "failed":
                    repo.reopen_failed_items(batch_id)
                target_id = target_snapshot.target_ids.get(identity)
                reason = entry.disposition_reason or "unchanged_target_identity_and_fingerprint"
                repo.mark_item(
                    batch_id,
                    checkpoint.external_id,
                    status="skipped",
                    target_type=mapped_by_identity[identity].target_table if target_id else "",
                    target_id=str(target_id) if target_id else "",
                    error_message=reason,
                )

    # Respect the frozen topological import order from the exact dry-run.
    for identity in dry_run.plan.import_order:
        row = mapped_by_identity[identity]
        try:
            _apply_one(
                session_factory,
                batch_id=batch_id,
                row=row,
                target_ids=target_snapshot.target_ids,
            )
        except Exception as error:
            if on_item_error is not None:
                on_item_error(row.source_table, error)
            with session_factory() as session, session.begin():
                repo = MigrationCheckpointRepository(session)
                checkpoint = _get_item(session, batch_id, _external_id(identity))
                if checkpoint.status in {"pending", "failed"}:
                    repo.mark_item(
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


def _apply_one(
    session_factory: sessionmaker[Session],
    *,
    batch_id: int,
    row: MappedLegacyRow,
    target_ids: Mapping[tuple[str, str], int],
) -> None:
    with session_factory() as session, session.begin():
        checkpoints = MigrationCheckpointRepository(session)
        checkpoint = _get_item(session, batch_id, _external_id((row.source_table, row.source_id)))
        if checkpoint.status in {"imported", "skipped"}:
            if checkpoint.source_payload_sha256 != semantic_fingerprint(row):
                raise CheckpointConflict(f"source payload changed for {checkpoint.external_id}")
            return
        if checkpoint.status == "conflict":
            raise CheckpointConflict(f"checkpoint conflict requires review: {checkpoint.external_id}")

        values = dict(row.values)
        for name, value in tuple(values.items()):
            if isinstance(value, TargetIdentityReference):
                resolved_id = _resolve_reference(session, batch_id, value, target_ids)
                if resolved_id is None:
                    raise CheckpointConflict(
                        f"unresolved target identity {value.source_table}:{value.source_id}"
                    )
                values[name] = resolved_id
        if isinstance(values.get("er_position_json"), (dict, list)):
            values["er_position_json"] = json.dumps(values["er_position_json"], ensure_ascii=False, sort_keys=True)

        model = _TARGET_MODELS.get(row.target_table)
        if model is None:
            raise CheckpointConflict(f"unsupported target entity: {row.target_table}")
        entity = model(
            **values,
            source_system=row.source_system,
            source_table=row.source_table,
            source_id=row.source_id,
            migration_batch_id=batch_id,
        )
        session.add(entity)
        session.flush()
        if isinstance(entity, WarehouseModelRelationRecord):
            for child in row.child_rows:
                session.add(
                    WarehouseModelRelationFieldRecord(
                        relation_id=entity.id,
                        ordinal_position=int(child["ordinal_position"]),
                        source_field_name=str(child["source_field_name"]),
                        target_field_name=str(child["target_field_name"]),
                        source_system=row.source_system,
                        source_table="t_dw_model_relation_field",
                        source_id=f"{row.source_id}:{child['ordinal_position']}",
                        migration_batch_id=batch_id,
                    )
                )
        checkpoints.mark_item(
            batch_id,
            checkpoint.external_id,
            status="imported",
            target_type=row.target_table,
            target_id=str(entity.id),
        )


def _resolve_reference(
    session: Session,
    batch_id: int,
    reference: TargetIdentityReference,
    target_ids: Mapping[tuple[str, str], int],
) -> int | None:
    identity = (reference.source_table, reference.source_id)
    if identity in target_ids:
        return target_ids[identity]
    checkpoint = session.scalar(
        select(MigrationItemRecord).where(
            MigrationItemRecord.batch_id == batch_id,
            MigrationItemRecord.external_id == _external_id(identity),
        )
    )
    if checkpoint is None or checkpoint.status != "imported" or not checkpoint.target_id:
        return None
    return int(checkpoint.target_id)


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


def _external_id(identity: tuple[str, str]) -> str:
    return f"{identity[0]}:{identity[1]}"


def _batch_digest(project_id: int, source_digest: str, rows: list[MappedLegacyRow]) -> str:
    payload = {
        "project_id": project_id,
        "source_digest": source_digest,
        "rows": sorted(
            (
                row.source_table,
                row.source_id,
                semantic_fingerprint(row),
            )
            for row in rows
        ),
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _map_rows(
    project_id: int,
    source_snapshot: LegacyI18SourceSnapshot,
    target_snapshot: I18TargetSnapshot,
) -> list[MappedLegacyRow]:
    pending: set[tuple[str, str]] = set()
    for table_name, (identity_field, _columns) in I18_SOURCE_COLUMNS.items():
        for source_row in source_snapshot.rows[table_name]:
            source_id = source_row.get(identity_field)
            if source_id is None:
                raise ValueError(f"source row in {table_name} is missing its identity")
            pending.add((table_name, str(source_id)))
            if table_name == "t_biz_domain" and source_row.get("name"):
                pending.add((table_name, str(source_row["name"])))

    from rebuild.governance.legacy_migration_service import (
        I18_APPROVED_REFERENCE_ALIASES,
        I18_APPROVED_RELATION_FIELD_ALIASES,
    )

    context = LegacyMappingContext(
        target_project_id=project_id,
        target_ids=target_snapshot.target_ids,
        pending_identities=frozenset(pending),
        approved_reference_aliases=I18_APPROVED_REFERENCE_ALIASES,
        approved_relation_field_aliases=I18_APPROVED_RELATION_FIELD_ALIASES,
    )
    rows = [
        map_legacy_row(table, source_row, context)
        for table in I18_SOURCE_COLUMNS
        for source_row in source_snapshot.rows[table]
    ]
    versions = [row for row in source_snapshot.rows["t_dw_model_version"] if str(row.get("id")) == "1"]
    if versions and (
        len(versions) != 1
        or str(versions[0].get("model_id")) != "1"
        or any(str(row.get("id")) == "1" for row in source_snapshot.rows["t_dw_model"])
    ):
        raise ValueError("approved skip precondition changed for t_dw_model_version#1")
    return rows


def _assert_isolated_target(session_factory: sessionmaker[Session]) -> Engine:
    bind = session_factory.kw.get("bind")
    if bind is None:
        raise LegacyImportRejected("migration target engine is unavailable")
    url = bind.url
    backend = url.get_backend_name()
    if backend == "mysql" and url.database == "datara_rebuild_i0":
        return bind
    if backend == "sqlite" and url.database == ":memory:":
        return bind
    raise LegacyImportRejected("migration target is not the isolated rebuild schema")
