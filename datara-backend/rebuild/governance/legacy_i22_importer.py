"""Checkpointed import executor for the allowlisted I22 standard snapshot."""

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
from rebuild.governance.legacy_i22_mapping import (
    MappedI22Snapshot,
    map_i22_snapshot,
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
    AuditEventRecord,
    MigrationBatchRecord,
    MigrationItemRecord,
    StandardApprovalRecord,
    StandardCheckReportRecord,
    StandardCodeSetRecord,
    StandardCodeValueRecord,
    StandardElementRecord,
    StandardMappingRecord,
    StandardNamingRuleRecord,
)
from rebuild.governance.service import GovernanceService
from rebuild.governance.legacy_source_reader import LegacyI22SourceSnapshot, _json_safe
from rebuild.identity.contracts import Permission
from rebuild.identity.models import UserRecord


_LOCAL_IMPORT_LOCK = RLock()
_TARGET_MODELS = {
    "rebuild_governance_standard_element": StandardElementRecord,
    "rebuild_governance_standard_code_set": StandardCodeSetRecord,
    "rebuild_governance_standard_code_value": StandardCodeValueRecord,
    "rebuild_governance_standard_naming_rule": StandardNamingRuleRecord,
    "rebuild_governance_standard_mapping": StandardMappingRecord,
    "rebuild_governance_standard_approval": StandardApprovalRecord,
    "rebuild_governance_standard_check_report": StandardCheckReportRecord,
}


@dataclass(frozen=True)
class _ImportUnit:
    source_table: str
    source_id: str
    fingerprint: str
    row: MappedLegacyRow | None = None

    @property
    def external_id(self) -> str:
        return f"{self.source_table}:{self.source_id}"


def i22_target_identity_digest(context: object) -> str:
    payload = {
        "source_identities": sorted(
            (table, identity, target_id) for (table, identity), target_id in context.target_ids.items()
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_i22_mapping_context(session: Session, project_id: int) -> object:
    if project_id <= 0:
        raise ValueError("project_id must be positive")

    target_ids: dict[tuple[str, str], int] = {}

    element_rows = session.execute(
        select(StandardElementRecord).where(StandardElementRecord.project_id == project_id)
    ).all()
    for row in element_rows:
        if row.source_id:
            target_ids[("t_std_element", row.source_id)] = row.id

    code_set_rows = session.execute(
        select(StandardCodeSetRecord).where(StandardCodeSetRecord.project_id == project_id)
    ).all()
    for row in code_set_rows:
        if row.source_id:
            target_ids[("t_std_code", row.source_id)] = row.id

    code_value_rows = session.execute(
        select(StandardCodeValueRecord).where(StandardCodeValueRecord.project_id == project_id)
    ).all()
    for row in code_value_rows:
        if row.source_id:
            target_ids[("t_std_code_value", row.source_id)] = row.id

    naming_rows = session.execute(
        select(StandardNamingRuleRecord).where(StandardNamingRuleRecord.project_id == project_id)
    ).all()
    for row in naming_rows:
        if row.source_id:
            target_ids[("t_std_naming_rule", row.source_id)] = row.id

    mapping_rows = session.execute(
        select(StandardMappingRecord).where(StandardMappingRecord.project_id == project_id)
    ).all()
    for row in mapping_rows:
        if row.source_id:
            target_ids[("t_std_mapping", row.source_id)] = row.id

    approval_rows = session.execute(
        select(StandardApprovalRecord).where(StandardApprovalRecord.project_id == project_id)
    ).all()
    for row in approval_rows:
        if row.source_id:
            target_ids[("t_std_approval", row.source_id)] = row.id

    check_rows = session.execute(
        select(StandardCheckReportRecord).where(StandardCheckReportRecord.project_id == project_id)
    ).all()
    for row in check_rows:
        if row.source_id:
            target_ids[("t_std_check_report", row.source_id)] = row.id

    from rebuild.governance.legacy_mapping import LegacyMappingContext

    return LegacyMappingContext(
        target_project_id=project_id,
        target_ids=target_ids,
        pending_identities=frozenset(),
    )


def execute_i22_legacy_import(
    session_factory: sessionmaker[Session],
    *,
    project_id: int,
    actor_id: int,
    source_snapshot: LegacyI22SourceSnapshot,
    expected_source_digest: str,
    expected_target_digest: str,
    idempotency_key: str,
    mapping_context_factory: Callable[[Session, int], object] = build_i22_mapping_context,
    on_item_error: Callable[[str, Exception], None] | None = None,
) -> LegacyImportResult:
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
                return _execute_i22_unlocked(
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
        return _execute_i22_unlocked(
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


def _execute_i22_unlocked(
    session_factory: sessionmaker[Session],
    *,
    project_id: int,
    actor_id: int,
    source_snapshot: LegacyI22SourceSnapshot,
    expected_source_digest: str,
    expected_target_digest: str,
    idempotency_key: str,
    mapping_context_factory: Callable[[Session, int], object],
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
        actual_target_digest = i22_target_identity_digest(context)
        if source_snapshot.digest != expected_source_digest or actual_target_digest != expected_target_digest:
            raise LegacyImportRejected("source or target snapshot changed; run a fresh preview")
        mapped = map_i22_snapshot(source_snapshot, context)
        if not mapped.ready_to_import:
            raise LegacyImportRejected("latest I22 mapping contains conflicts or blocked rows")

        units = _units(mapped)
        payload_sha256 = _batch_digest(project_id, expected_source_digest, units)
        checkpoints = MigrationCheckpointRepository(session)
        batch = checkpoints.get_or_create_batch(
            source_system=f"datara_meta:i22:{project_id}",
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
                action="legacy_i22_import_requested",
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
    return "datara_i22_" + hashlib.sha256(str(project_id).encode("ascii")).hexdigest()[:52]


def _source_digest(snapshot: LegacyI22SourceSnapshot) -> str:
    if snapshot.schema != "datara_meta":
        raise LegacyImportRejected("I22 source snapshot schema must be datara_meta")
    rows = snapshot.rows
    counts = snapshot.counts
    if not isinstance(rows, Mapping) or set(rows) != set(I22_SOURCE_COLUMNS):
        raise LegacyImportRejected("I22 source snapshot rows are invalid")
    if not isinstance(counts, Mapping) or set(counts) != set(I22_SOURCE_COLUMNS):
        raise LegacyImportRejected("I22 source snapshot counts are invalid")
    for table in I22_SOURCE_COLUMNS:
        if counts[table] != len(rows[table]) or any(not isinstance(row, Mapping) for row in rows[table]):
            raise LegacyImportRejected("I22 source snapshot counts do not match row payload")
    payload = {
        "schema": snapshot.schema,
        "rows": {table: [_json_safe(row) for row in rows[table]] for table in I22_SOURCE_COLUMNS},
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    if snapshot.digest != digest:
        raise LegacyImportRejected("I22 source snapshot digest does not match its row payload")
    return digest


def _units(mapped: MappedI22Snapshot) -> tuple[_ImportUnit, ...]:
    all_rows = (
        mapped.elements
        + mapped.code_sets
        + mapped.code_values
        + mapped.naming_rules
        + mapped.mappings
        + mapped.approvals
        + mapped.check_reports
    )
    units = [_ImportUnit(row.source_table, row.source_id, semantic_fingerprint(row), row=row) for row in all_rows]
    return tuple(sorted(units, key=lambda unit: _unit_order(unit)))


def _unit_order(unit: _ImportUnit) -> tuple[int, str, str]:
    order = {
        "t_std_element": 0,
        "t_std_code": 1,
        "t_std_code_value": 2,
        "t_std_naming_rule": 3,
        "t_std_mapping": 4,
        "t_std_approval": 5,
        "t_std_check_report": 6,
    }
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
            return entity.id, aliases
    if integrity_conflict:
        raise CheckpointConflict("target integrity mismatch")
    assert replay_result is not None
    return replay_result


def _insert_row(session: Session, batch_id: int, row: MappedLegacyRow, target_ids: Mapping[tuple[str, str], int]):
    model = _TARGET_MODELS.get(row.target_table)
    if model is None:
        raise CheckpointConflict(f"unsupported I22 target entity: {row.target_table}")
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
                resolved_id = int(checkpoint.target_id)
        if resolved_id is None:
            raise CheckpointConflict(f"unresolved I22 target identity {value.source_table}:{value.source_id}")
        values[key] = resolved_id
    return values


def _integrity_matches(
    session: Session,
    checkpoint: MigrationItemRecord,
    batch_id: int,
    unit: _ImportUnit,
    target_ids: Mapping[tuple[str, str], int],
) -> bool:
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
