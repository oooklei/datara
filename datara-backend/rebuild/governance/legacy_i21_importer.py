"""Checkpointed import executor for the allowlisted I21 quality snapshot."""

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
from rebuild.governance.legacy_i21_mapping import (
    MappedI21Snapshot,
    MappedI21TaskBundle,
    map_i21_snapshot,
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
    QualityAlarmPolicyRecord,
    QualityExceptionRecord,
    QualityReportRecord,
    QualityRuleDefinitionRecord,
    QualityRunLegacyDetailsRecord,
    QualityTaskRecord,
    QualityTaskRuleRecord,
)
from rebuild.governance.service import GovernanceService
from rebuild.governance.legacy_source_reader import LegacyI21SourceSnapshot, _json_safe
from rebuild.identity.contracts import Permission
from rebuild.identity.models import UserRecord


_LOCAL_IMPORT_LOCK = RLock()
_TARGET_MODELS = {
    "rebuild_governance_quality_rule_definition": QualityRuleDefinitionRecord,
    "rebuild_governance_quality_task": QualityTaskRecord,
    "rebuild_governance_quality_task_rule": QualityTaskRuleRecord,
    "rebuild_governance_quality_run_legacy_details": QualityRunLegacyDetailsRecord,
    "rebuild_governance_quality_exception": QualityExceptionRecord,
    "rebuild_governance_quality_report": QualityReportRecord,
    "rebuild_governance_quality_alarm_policy": QualityAlarmPolicyRecord,
}


@dataclass(frozen=True)
class _ImportUnit:
    source_table: str
    source_id: str
    fingerprint: str
    row: MappedLegacyRow | None = None
    task_bundle: MappedI21TaskBundle | None = None

    @property
    def external_id(self) -> str:
        return f"{self.source_table}:{self.source_id}"


def i21_target_identity_digest(context: object) -> str:
    """Hash the exact project-scoped identity payload exposed by I21 preview."""

    payload = {
        "source_identities": sorted(
            (table, identity, target_id) for (table, identity), target_id in context.target_ids.items()
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_i21_mapping_context(session: Session, project_id: int) -> object:
    """Build a fresh I21 identity map from the current project-scoped target rows."""

    if project_id <= 0:
        raise ValueError("project_id must be positive")

    target_ids: dict[tuple[str, str], int] = {}

    rule_rows = session.execute(
        select(QualityRuleDefinitionRecord).where(
            QualityRuleDefinitionRecord.project_id == project_id,
        )
    ).all()
    for row in rule_rows:
        if row.source_id:
            target_ids[("t_qc_rule", row.source_id)] = row.id

    task_rows = session.execute(
        select(QualityTaskRecord).where(
            QualityTaskRecord.project_id == project_id,
        )
    ).all()
    for row in task_rows:
        if row.source_id:
            target_ids[("t_qc_task", row.source_id)] = row.id

    run_rows = session.execute(
        select(QualityRunLegacyDetailsRecord).where(
            QualityRunLegacyDetailsRecord.project_id == project_id,
        )
    ).all()
    for row in run_rows:
        if row.source_id:
            target_ids[("t_qc_run", row.source_id)] = row.id

    exception_rows = session.execute(
        select(QualityExceptionRecord).where(
            QualityExceptionRecord.project_id == project_id,
        )
    ).all()
    for row in exception_rows:
        if row.source_id:
            target_ids[("t_qc_exception", row.source_id)] = row.id

    report_rows = session.execute(
        select(QualityReportRecord).where(
            QualityReportRecord.project_id == project_id,
        )
    ).all()
    for row in report_rows:
        if row.source_id:
            target_ids[("t_qc_report", row.source_id)] = row.id

    alarm_rows = session.execute(
        select(QualityAlarmPolicyRecord).where(
            QualityAlarmPolicyRecord.project_id == project_id,
        )
    ).all()
    for row in alarm_rows:
        if row.source_id:
            target_ids[("t_qc_alarm_policy", row.source_id)] = row.id

    from rebuild.governance.legacy_mapping import LegacyMappingContext

    return LegacyMappingContext(
        target_project_id=project_id,
        target_ids=target_ids,
        pending_identities=frozenset(),
    )


def execute_i21_legacy_import(
    session_factory: sessionmaker[Session],
    *,
    project_id: int,
    actor_id: int,
    source_snapshot: LegacyI21SourceSnapshot,
    expected_source_digest: str,
    expected_target_digest: str,
    idempotency_key: str,
    mapping_context_factory: Callable[[Session, int], object] = build_i21_mapping_context,
    on_item_error: Callable[[str, Exception], None] | None = None,
) -> LegacyImportResult:
    """Import a freshly read I21 source snapshot against fresh target identities."""

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
                return _execute_i21_unlocked(
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
        return _execute_i21_unlocked(
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


def _execute_i21_unlocked(
    session_factory: sessionmaker[Session],
    *,
    project_id: int,
    actor_id: int,
    source_snapshot: LegacyI21SourceSnapshot,
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
        actual_target_digest = i21_target_identity_digest(context)
        if source_snapshot.digest != expected_source_digest or actual_target_digest != expected_target_digest:
            raise LegacyImportRejected("source or target snapshot changed; run a fresh preview")
        mapped = map_i21_snapshot(source_snapshot, context)
        if not mapped.ready_to_import:
            raise LegacyImportRejected("latest I21 mapping contains conflicts or blocked rows")

        units = _units(mapped, source_snapshot)
        payload_sha256 = _batch_digest(project_id, expected_source_digest, units)
        checkpoints = MigrationCheckpointRepository(session)
        batch = checkpoints.get_or_create_batch(
            source_system=f"datara_meta:i21:{project_id}",
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
                action="legacy_i21_import_requested",
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
    return "datara_i21_" + hashlib.sha256(str(project_id).encode("ascii")).hexdigest()[:52]


def _source_digest(snapshot: LegacyI21SourceSnapshot) -> str:
    if snapshot.schema != "datara_meta":
        raise LegacyImportRejected("I21 source snapshot schema must be datara_meta")
    rows = snapshot.rows
    counts = snapshot.counts
    if not isinstance(rows, Mapping) or set(rows) != set(I21_SOURCE_COLUMNS):
        raise LegacyImportRejected("I21 source snapshot rows are invalid")
    if not isinstance(counts, Mapping) or set(counts) != set(I21_SOURCE_COLUMNS):
        raise LegacyImportRejected("I21 source snapshot counts are invalid")
    for table in I21_SOURCE_COLUMNS:
        if counts[table] != len(rows[table]) or any(not isinstance(row, Mapping) for row in rows[table]):
            raise LegacyImportRejected("I21 source snapshot counts do not match row payload")
    payload = {
        "schema": snapshot.schema,
        "rows": {table: [_json_safe(row) for row in rows[table]] for table in I21_SOURCE_COLUMNS},
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    if snapshot.digest != digest:
        raise LegacyImportRejected("I21 source snapshot digest does not match its row payload")
    return digest


def _units(
    mapped: MappedI21Snapshot,
    source_snapshot: LegacyI21SourceSnapshot,
) -> tuple[_ImportUnit, ...]:
    units = [_ImportUnit(row.source_table, row.source_id, semantic_fingerprint(row), row=row) for row in mapped.rules]
    for bundle in mapped.tasks:
        task_values = dict(bundle.task.values)
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "task_values": _canonical(task_values),
                    "rule_links": [
                        {
                            "ordinal_position": link.ordinal_position,
                            "rule_definition_id": str(link.rule_definition_id),
                        }
                        for link in bundle.rule_links
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        units.append(_ImportUnit(bundle.task.source_table, bundle.task.source_id, fingerprint, task_bundle=bundle))
    units.extend(_ImportUnit(row.source_table, row.source_id, semantic_fingerprint(row), row=row) for row in mapped.runs)
    units.extend(_ImportUnit(row.source_table, row.source_id, semantic_fingerprint(row), row=row) for row in mapped.exceptions)
    units.extend(_ImportUnit(row.source_table, row.source_id, semantic_fingerprint(row), row=row) for row in mapped.reports)
    units.extend(_ImportUnit(row.source_table, row.source_id, semantic_fingerprint(row), row=row) for row in mapped.alarm_policies)
    return tuple(sorted(units, key=lambda unit: _unit_order(unit)))


def _unit_order(unit: _ImportUnit) -> tuple[int, str, str]:
    order = {"t_qc_rule": 0, "t_qc_task": 1, "t_qc_run": 2, "t_qc_exception": 3, "t_qc_report": 4, "t_qc_alarm_policy": 5}
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
        elif unit.task_bundle is not None:
            task_id = _insert_task_bundle(session, batch_id, checkpoint, unit.task_bundle, target_ids)
            checkpoints.mark_item(
                batch_id,
                checkpoint.external_id,
                status="imported",
                target_type=unit.task_bundle.task.target_table,
                target_id=str(task_id),
            )
            aliases[("t_qc_task", unit.source_id)] = task_id
            return task_id, aliases
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


def _insert_task_bundle(
    session: Session,
    batch_id: int,
    checkpoint: MigrationItemRecord,
    bundle: MappedI21TaskBundle,
    target_ids: Mapping[tuple[str, str], int],
) -> int:
    task_values = dict(bundle.task.values)
    for key, value in tuple(task_values.items()):
        if isinstance(value, TargetIdentityReference):
            identity = (value.source_table, value.source_id)
            resolved_id = target_ids.get(identity)
            if resolved_id is None:
                checkpoint_ref = session.scalar(
                    select(MigrationItemRecord).where(
                        MigrationItemRecord.batch_id == batch_id,
                        MigrationItemRecord.external_id == f"{identity[0]}:{identity[1]}",
                    )
                )
                if checkpoint_ref and checkpoint_ref.status == "imported" and checkpoint_ref.target_id:
                    resolved_id = int(checkpoint_ref.target_id)
            if resolved_id is None:
                raise CheckpointConflict(f"unresolved I21 target identity {value.source_table}:{value.source_id}")
            task_values[key] = resolved_id
    task = QualityTaskRecord(
        **task_values,
        source_system=bundle.task.source_system,
        source_table=bundle.task.source_table,
        source_id=bundle.task.source_id,
        migration_batch_id=batch_id,
    )
    session.add(task)
    session.flush()
    for link in bundle.rule_links:
        rule_ref = link.rule_definition_id
        if isinstance(rule_ref, TargetIdentityReference):
            identity = (rule_ref.source_table, rule_ref.source_id)
            resolved_id = target_ids.get(identity)
            if resolved_id is None:
                checkpoint_ref = session.scalar(
                    select(MigrationItemRecord).where(
                        MigrationItemRecord.batch_id == batch_id,
                        MigrationItemRecord.external_id == f"{identity[0]}:{identity[1]}",
                    )
                )
                if checkpoint_ref and checkpoint_ref.status == "imported" and checkpoint_ref.target_id:
                    resolved_id = int(checkpoint_ref.target_id)
            if resolved_id is None:
                raise CheckpointConflict(f"unresolved I21 rule identity {identity[0]}:{identity[1]}")
            rule_ref = resolved_id
        session.add(
            QualityTaskRuleRecord(
                task_id=task.id,
                rule_definition_id=rule_ref,
                ordinal_position=link.ordinal_position,
                source_system="datara_meta",
                source_table="t_qc_task_rule",
                source_id=f"{bundle.task.source_id}:{link.ordinal_position}",
                migration_batch_id=batch_id,
            )
        )
    return task.id


def _insert_row(session: Session, batch_id: int, row: MappedLegacyRow, target_ids: Mapping[tuple[str, str], int]):
    model = _TARGET_MODELS.get(row.target_table)
    if model is None:
        raise CheckpointConflict(f"unsupported I21 target entity: {row.target_table}")
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
            raise CheckpointConflict(f"unresolved I21 target identity {value.source_table}:{value.source_id}")
        values[key] = resolved_id
    return values


def _integrity_matches(
    session: Session,
    checkpoint: MigrationItemRecord,
    batch_id: int,
    unit: _ImportUnit,
    target_ids: Mapping[tuple[str, str], int],
) -> bool:
    if unit.task_bundle is not None:
        try:
            target_id = int(checkpoint.target_id)
        except (TypeError, ValueError):
            return False
        task = session.get(QualityTaskRecord, target_id)
        if task is None or not _has_provenance(task, unit.task_bundle.task, batch_id):
            return False
        expected_values = dict(unit.task_bundle.task.values)
        for key, value in tuple(expected_values.items()):
            if isinstance(value, TargetIdentityReference):
                expected_values[key] = target_id
        task_matches = all(
            getattr(task, name, object()) == value
            for name, value in expected_values.items()
        )
        actual_rules = session.scalars(
            select(QualityTaskRuleRecord)
            .where(QualityTaskRuleRecord.task_id == task.id)
            .order_by(QualityTaskRuleRecord.ordinal_position)
        ).all()
        expected_links = unit.task_bundle.rule_links
        if len(actual_rules) != len(expected_links):
            return False
        for actual, expected in zip(actual_rules, expected_links, strict=True):
            if actual.ordinal_position != expected.ordinal_position:
                return False
            rule_ref = expected.rule_definition_id
            if isinstance(rule_ref, TargetIdentityReference):
                identity = (rule_ref.source_table, rule_ref.source_id)
                resolved_id = target_ids.get(identity)
                if resolved_id is None:
                    checkpoint_ref = session.scalar(
                        select(MigrationItemRecord).where(
                            MigrationItemRecord.batch_id == batch_id,
                            MigrationItemRecord.external_id == f"{identity[0]}:{identity[1]}",
                        )
                    )
                    if checkpoint_ref and checkpoint_ref.status == "imported" and checkpoint_ref.target_id:
                        resolved_id = int(checkpoint_ref.target_id)
                if resolved_id is None:
                    return False
                rule_ref = resolved_id
            if actual.rule_definition_id != rule_ref:
                return False
        return task_matches
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
