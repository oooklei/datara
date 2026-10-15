"""Checkpointed I20 importer for the isolated rebuild governance schema.

This module deliberately has no HTTP endpoint. A caller must re-read its source
snapshot and obtain the current target identity digest before invoking it.
"""

from __future__ import annotations

from dataclasses import dataclass, is_dataclass, asdict
from datetime import date, datetime
import hashlib
import json
from threading import RLock
from typing import Callable, Mapping

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from rebuild.governance.contracts import is_sha256_digest
from rebuild.governance.legacy_importer import _assert_isolated_target
from rebuild.governance.legacy_i20_mapping import MappedI20MetricBundle, map_i20_snapshot
from rebuild.governance.legacy_mapping import LegacyMappingContext, MappedLegacyRow, TargetIdentityReference
from rebuild.governance.migration_checkpoints import (
    CheckpointConflict,
    CheckpointItem,
    MigrationCheckpointRepository,
)
from rebuild.governance.models import (
    AuditEventRecord,
    MigrationBatchRecord,
    MigrationItemRecord,
    SemanticMetricProfileRecord,
    SemanticMetricRecord,
    SemanticMetricVersionRecord,
)
from rebuild.governance.legacy_source_reader import I20_SOURCE_COLUMNS, _json_safe
from rebuild.governance.service import GovernanceService
from rebuild.identity.contracts import Permission
from rebuild.identity.models import UserRecord


_TARGET_METRIC = "rebuild_governance_semantic_metric"
_TARGET_PROFILE = "rebuild_governance_semantic_metric_profile"
_TARGET_VERSION = "rebuild_governance_semantic_metric_version"
_LOCAL_IMPORT_LOCK = RLock()


class I20ImportRejected(ValueError):
    """Raised when a current I20 import snapshot is unsafe to apply."""


@dataclass(frozen=True)
class I20ImportResult:
    batch_id: int
    status: str
    expected_count: int
    imported_count: int
    skipped_count: int
    error_count: int


def execute_i20_legacy_import(
    session_factory: sessionmaker[Session],
    *,
    project_id: int,
    actor_id: int,
    source_snapshot: object,
    expected_source_digest: str,
    expected_target_digest: str,
    idempotency_key: str,
    on_item_error: Callable[[str, Exception], None] | None = None,
) -> I20ImportResult:
    """Import a fresh, digest-bound I20 snapshot with row-level resumable checkpoints."""

    if not isinstance(project_id, int) or isinstance(project_id, bool) or project_id <= 0:
        raise ValueError("project_id must be positive")
    if not isinstance(actor_id, int) or isinstance(actor_id, bool) or actor_id <= 0:
        raise ValueError("actor_id must be positive")
    if not idempotency_key or len(idempotency_key) > 128:
        raise ValueError("idempotency_key must contain 1..128 characters")
    if not is_sha256_digest(expected_source_digest) or not is_sha256_digest(expected_target_digest):
        raise ValueError("expected source and target digests must be lowercase SHA-256 digests")
    source_digest = getattr(source_snapshot, "digest", None)
    if source_digest != expected_source_digest:
        raise I20ImportRejected("source digest does not match the freshly read source snapshot")
    if not is_sha256_digest(source_digest):
        raise I20ImportRejected("source snapshot digest is invalid")

    engine = _assert_isolated_target(session_factory)
    if engine.dialect.name == "mysql":
        lock_name = "datara_i20_" + hashlib.sha256(str(project_id).encode("ascii")).hexdigest()[:52]
        with engine.connect() as connection:
            acquired = connection.scalar(text("SELECT GET_LOCK(:lock_name, 30)"), {"lock_name": lock_name})
            if acquired != 1:
                raise I20ImportRejected("could not acquire the project I20 migration lock")
            try:
                return _execute_locked(
                    session_factory,
                    engine,
                    project_id=project_id,
                    actor_id=actor_id,
                    source_snapshot=source_snapshot,
                    expected_source_digest=expected_source_digest,
                    expected_target_digest=expected_target_digest,
                    idempotency_key=idempotency_key,
                    on_item_error=on_item_error,
                )
            finally:
                connection.execute(text("SELECT RELEASE_LOCK(:lock_name)"), {"lock_name": lock_name})

    with _LOCAL_IMPORT_LOCK:
        return _execute_locked(
            session_factory,
            engine,
            project_id=project_id,
            actor_id=actor_id,
            source_snapshot=source_snapshot,
            expected_source_digest=expected_source_digest,
            expected_target_digest=expected_target_digest,
            idempotency_key=idempotency_key,
            on_item_error=on_item_error,
        )


def _execute_locked(
    session_factory: sessionmaker[Session],
    engine: Engine,
    *,
    project_id: int,
    actor_id: int,
    source_snapshot: object,
    expected_source_digest: str,
    expected_target_digest: str,
    idempotency_key: str,
    on_item_error: Callable[[str, Exception], None] | None,
) -> I20ImportResult:
    if getattr(source_snapshot, "schema", None) != "datara_meta":
        raise I20ImportRejected("source snapshot schema must be datara_meta")
    locked_source_digest = _source_digest(source_snapshot)
    if (
        locked_source_digest != expected_source_digest
        or getattr(source_snapshot, "digest", None) != locked_source_digest
    ):
        raise I20ImportRejected("source digest changed before import under the target lock")

    with session_factory() as session, session.begin():
        actor = session.get(UserRecord, actor_id)
        if actor is None:
            raise I20ImportRejected("project edit permission is required for legacy import")
        project, allowed = GovernanceService(session).project_access(
            project_id,
            {"user_id": actor_id, "role": actor.role},
            Permission.EDIT_DEFINITION,
        )
        if project is None or not allowed:
            raise I20ImportRejected("project edit permission is required for legacy import")

        target_ids = _current_target_ids(session, project_id)
        current_target_digest = _target_digest(target_ids)
        if current_target_digest != expected_target_digest:
            raise I20ImportRejected("target digest does not match the current project source identities")

        mapping = map_i20_snapshot(
            source_snapshot,
            LegacyMappingContext(
                target_project_id=project_id,
                target_ids=target_ids,
                pending_identities=frozenset(
                    ("t_indicator", str(row["id"]))
                    for row in source_snapshot.rows.get("t_indicator", ())
                    if isinstance(row, Mapping)
                    and isinstance(row.get("id"), int)
                    and not isinstance(row.get("id"), bool)
                ),
            ),
        )
        if (
            mapping.mapping_issues
            or mapping.orphan_versions
            or any(not bundle.ready_to_import for bundle in mapping.metrics)
        ):
            raise I20ImportRejected("I20 mapping issues prevent import")
        counts = getattr(source_snapshot, "counts", None)
        source_rows = source_snapshot.rows
        if not isinstance(counts, Mapping) or set(counts) != set(I20_SOURCE_COLUMNS):
            raise I20ImportRejected("source snapshot counts must include both I20 tables")
        if any(counts[table] != len(source_rows[table]) for table in I20_SOURCE_COLUMNS):
            raise I20ImportRejected("source snapshot counts do not match row payload")
        if not mapping.metrics and not source_snapshot.rows.get("t_indicator_version", ()):
            # An empty source snapshot is valid and still produces a durable batch.
            pass
        rows = _flatten(mapping.metrics)
        if len(rows) != sum(source_snapshot.counts.values()):
            raise I20ImportRejected("I20 mapped row count differs from source snapshot counts")

        row_by_identity = {(row.source_table, row.source_id): row for row, _profile, _parent in rows}
        if len(row_by_identity) != len(rows):
            raise I20ImportRejected("I20 source identities are duplicated")
        checkpoint_items = tuple(
            CheckpointItem(
                row.source_table,
                row.source_id,
                _item_fingerprint(row, profile_values, parent_source_id),
            )
            for row, profile_values, parent_source_id in rows
        )
        payload_digest = _batch_digest(project_id, expected_source_digest, checkpoint_items)
        batch = MigrationCheckpointRepository(session).get_or_create_batch(
            source_system=f"datara_meta:i20:{project_id}",
            idempotency_key=idempotency_key,
            payload_sha256=payload_digest,
            expected_count=len(checkpoint_items),
        )
        checkpoints = MigrationCheckpointRepository(session)
        checkpoints.seed_items(batch.id, checkpoint_items)
        checkpoints.reopen_failed_items(batch.id)

        # A target identity from an unrelated batch is never silently treated as
        # an unchanged row. Existing identities are accepted only for this batch's
        # verified replay checkpoint.
        for row, _profile, _parent in rows:
            existing_id = target_ids.get((row.source_table, row.source_id))
            if existing_id is None:
                continue
            item = _get_item(session, batch.id, _external_id((row.source_table, row.source_id)))
            if item.status not in {"imported", "skipped"} or item.target_id != str(existing_id):
                raise I20ImportRejected("target source identity already exists outside this import checkpoint")

        session.add(
            AuditEventRecord(
                actor_id=actor_id,
                project_id=project_id,
                action="legacy_i20_import_requested",
                resource_type="migration_batch",
                resource_id=str(batch.id),
                after_json=json.dumps(
                    {
                        "source_digest": expected_source_digest,
                        "target_digest": current_target_digest,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        )
        batch_id = batch.id

    target_ids = dict(target_ids)
    stopped = False
    for bundle in _ordered_bundles(mapping.metrics):
        try:
            metric_id = _apply_metric(
                session_factory,
                batch_id=batch_id,
                bundle=bundle,
                target_ids=target_ids,
            )
            target_ids[("t_indicator", bundle.metric.source_id)] = metric_id
        except Exception as error:
            _mark_failed(session_factory, batch_id, ("t_indicator", bundle.metric.source_id), error)
            if on_item_error is not None:
                on_item_error("t_indicator", error)
            stopped = True
            break

    if not stopped:
        for bundle in _ordered_bundles(mapping.metrics):
            metric_identity = ("t_indicator", bundle.metric.source_id)
            metric_id = target_ids.get(metric_identity)
            if metric_id is None:
                stopped = True
                break
            for version in bundle.versions:
                try:
                    _apply_version(
                        session_factory,
                        batch_id=batch_id,
                        row=version,
                        metric_id=metric_id,
                        parent_source_id=bundle.metric.source_id,
                    )
                except Exception as error:
                    _mark_failed(session_factory, batch_id, ("t_indicator_version", version.source_id), error)
                    if on_item_error is not None:
                        on_item_error("t_indicator_version", error)
                    stopped = True
                    break
            if stopped:
                break

    with session_factory() as session:
        batch = session.get(MigrationBatchRecord, batch_id)
        if batch is None:
            raise RuntimeError("I20 migration batch disappeared")
        return I20ImportResult(
            batch_id=batch.id,
            status=batch.status,
            expected_count=batch.expected_count,
            imported_count=batch.imported_count,
            skipped_count=batch.skipped_count,
            error_count=batch.error_count,
        )


def _current_target_ids(session: Session, project_id: int) -> dict[tuple[str, str], int]:
    identities: dict[tuple[str, str], int] = {}
    profiles = session.scalars(
        select(SemanticMetricProfileRecord)
        .join(SemanticMetricRecord, SemanticMetricRecord.id == SemanticMetricProfileRecord.metric_id)
        .where(SemanticMetricRecord.project_id == project_id)
    ).all()
    for profile in profiles:
        if profile.source_system == "datara_meta" and profile.source_table == "t_indicator" and profile.source_id:
            _record_identity(identities, ("t_indicator", profile.source_id), profile.metric_id)

    versions = session.scalars(
        select(SemanticMetricVersionRecord)
        .join(SemanticMetricRecord, SemanticMetricRecord.id == SemanticMetricVersionRecord.metric_id)
        .where(SemanticMetricRecord.project_id == project_id)
    ).all()
    for version in versions:
        if (
            version.source_system == "datara_meta"
            and version.source_table == "t_indicator_version"
            and version.source_id
        ):
            _record_identity(identities, ("t_indicator_version", version.source_id), version.id)
    return identities


def _record_identity(identities: dict[tuple[str, str], int], identity: tuple[str, str], target_id: int) -> None:
    if identity in identities:
        raise I20ImportRejected("duplicate target source identity")
    identities[identity] = target_id


def _target_digest(target_ids: Mapping[tuple[str, str], int]) -> str:
    payload = sorted((table, source_id, target_id) for (table, source_id), target_id in target_ids.items())
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode("utf-8")).hexdigest()


def _source_digest(source_snapshot: object) -> str:
    rows = getattr(source_snapshot, "rows", None)
    if not isinstance(rows, Mapping):
        raise I20ImportRejected("source snapshot rows are invalid")
    payload = {
        "schema": getattr(source_snapshot, "schema", None),
        "rows": {table: [_json_safe(row) for row in rows[table]] for table in I20_SOURCE_COLUMNS if table in rows},
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _flatten(
    bundles: tuple[MappedI20MetricBundle, ...],
) -> list[tuple[MappedLegacyRow, Mapping[str, object] | None, str | None]]:
    rows: list[tuple[MappedLegacyRow, Mapping[str, object] | None, str | None]] = []
    for bundle in bundles:
        rows.append((bundle.metric, bundle.profile_values, None))
        rows.extend((version, None, bundle.metric.source_id) for version in bundle.versions)
    return rows


def _item_fingerprint(
    row: MappedLegacyRow,
    profile_values: Mapping[str, object] | None,
    parent_source_id: str | None = None,
) -> str:
    row_values = dict(row.values)
    if row.source_table == "t_indicator_version":
        if parent_source_id is None:
            raise ValueError("version fingerprint requires its parent source identity")
        row_values["metric_id"] = TargetIdentityReference("t_indicator", parent_source_id)
    stable_row = {
        "target_table": row.target_table,
        "values": _canonicalize(row_values),
        "child_rows": _canonicalize(row.child_rows),
    }
    stable_profile = dict(profile_values) if profile_values is not None else None
    if stable_profile is not None:
        stable_profile["metric_id"] = TargetIdentityReference("t_indicator", row.source_id)
        base_source_id = stable_profile.get("legacy_base_metric_id")
        stable_profile["base_metric_id"] = (
            TargetIdentityReference("t_indicator", str(base_source_id)) if base_source_id is not None else None
        )
    semantic = {
        "mapped_row": stable_row,
        "profile_values": _canonicalize(stable_profile),
    }
    encoded = json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _canonicalize(value: object) -> object:
    if isinstance(value, TargetIdentityReference):
        return {"source_table": value.source_table, "source_id": value.source_id}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if is_dataclass(value):
        return _canonicalize(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonicalize(item) for item in value]
    return value


def _batch_digest(project_id: int, source_digest: str, items: tuple[CheckpointItem, ...]) -> str:
    payload = {
        "project_id": project_id,
        "source_digest": source_digest,
        "items": sorted((item.entity_type, item.source_id, item.payload_sha256) for item in items),
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _ordered_bundles(bundles: tuple[MappedI20MetricBundle, ...]) -> tuple[MappedI20MetricBundle, ...]:
    by_id = {bundle.metric.source_id: bundle for bundle in bundles}
    ordered: list[MappedI20MetricBundle] = []
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(source_id: str) -> None:
        if source_id in visited:
            return
        if source_id in visiting:
            raise I20ImportRejected("cyclic I20 metric dependency")
        visiting.add(source_id)
        base_ref = by_id[source_id].profile_values.get("base_metric_id")
        if isinstance(base_ref, TargetIdentityReference) and base_ref.source_table == "t_indicator":
            if base_ref.source_id in by_id:
                visit(base_ref.source_id)
        visiting.remove(source_id)
        visited.add(source_id)
        ordered.append(by_id[source_id])

    for source_id in sorted(by_id, key=lambda item: (int(item), item)):
        visit(source_id)
    return tuple(ordered)


def _apply_metric(
    session_factory: sessionmaker[Session],
    *,
    batch_id: int,
    bundle: MappedI20MetricBundle,
    target_ids: Mapping[tuple[str, str], int],
) -> int:
    row = bundle.metric
    identity = (row.source_table, row.source_id)
    target_id: int | None = None
    replay_conflict = False
    with session_factory() as session, session.begin():
        checkpoints = MigrationCheckpointRepository(session)
        checkpoint = _get_item(session, batch_id, _external_id(identity))
        if checkpoint.status in {"imported", "skipped"}:
            if checkpoint.source_payload_sha256 != _item_fingerprint(row, bundle.profile_values):
                raise CheckpointConflict(f"source payload changed for {checkpoint.external_id}")
            if not checkpoint.target_id:
                return 0
            target_id = int(checkpoint.target_id)
            if _metric_integrity_matches(session, checkpoint, batch_id, bundle, target_id, target_ids):
                return target_id
            checkpoints.mark_target_integrity_conflict(batch_id, checkpoint.external_id)
            replay_conflict = True
        elif checkpoint.status == "conflict":
            raise CheckpointConflict(f"checkpoint conflict requires review: {checkpoint.external_id}")

        if not replay_conflict:
            if row.target_id is not None:
                raise CheckpointConflict("metric target identity exists without a matching import checkpoint")
            values = {
                name: row.values[name]
                for name in ("project_id", "code", "name", "formula", "description", "status")
            }
            values["project_id"] = int(values["project_id"])
            metric = SemanticMetricRecord(**values)
            session.add(metric)
            session.flush()

            profile_values = dict(bundle.profile_values)
            profile_values.pop("metric_id", None)
            profile_values["metric_id"] = metric.id
            profile = SemanticMetricProfileRecord(
                **profile_values,
                source_system=row.source_system,
                source_table=row.source_table,
                source_id=row.source_id,
                migration_batch_id=batch_id,
            )
            session.add(profile)
            session.flush()
            checkpoints.mark_item(
                batch_id,
                checkpoint.external_id,
                status="imported",
                target_type=_TARGET_METRIC,
                target_id=str(metric.id),
            )
            target_id = metric.id

    if replay_conflict:
        raise CheckpointConflict("metric/profile target integrity mismatch")
    if target_id is None:
        raise CheckpointConflict("metric checkpoint has no target identity")
    return target_id


def _metric_integrity_matches(
    session: Session,
    checkpoint: MigrationItemRecord,
    batch_id: int,
    bundle: MappedI20MetricBundle,
    target_id: int,
    target_ids: Mapping[tuple[str, str], int],
) -> bool:
    row = bundle.metric
    if checkpoint.target_type != _TARGET_METRIC:
        return False
    metric = session.get(SemanticMetricRecord, target_id)
    profile = session.scalar(
        select(SemanticMetricProfileRecord).where(SemanticMetricProfileRecord.metric_id == target_id)
    )
    if metric is None or profile is None or metric.project_id != row.values.get("project_id"):
        return False
    expected_metric = dict(row.values)
    expected_metric.pop("project_id", None)
    expected_metric.pop("source_created_at", None)
    expected_metric.pop("source_updated_at", None)
    if any(getattr(metric, field, object()) != value for field, value in expected_metric.items()):
        return False
    expected_profile = dict(bundle.profile_values)
    expected_profile.pop("metric_id", None)
    expected_profile.pop("project_id", None)
    for name, value in expected_profile.items():
        if isinstance(value, TargetIdentityReference):
            value = _resolve_reference(session, batch_id, value, target_ids)
            if value is None:
                return False
        if getattr(profile, name, object()) != value:
            return False
    return _has_profile_provenance(profile, row, batch_id)


def _apply_version(
    session_factory: sessionmaker[Session],
    *,
    batch_id: int,
    row: MappedLegacyRow,
    metric_id: int,
    parent_source_id: str,
) -> int:
    identity = (row.source_table, row.source_id)
    replay_conflict = False
    target_id: int | None = None
    with session_factory() as session, session.begin():
        checkpoints = MigrationCheckpointRepository(session)
        checkpoint = _get_item(session, batch_id, _external_id(identity))
        if checkpoint.status in {"imported", "skipped"}:
            if checkpoint.source_payload_sha256 != _item_fingerprint(row, None, parent_source_id):
                raise CheckpointConflict(f"source payload changed for {checkpoint.external_id}")
            if not checkpoint.target_id:
                return 0
            target_id = int(checkpoint.target_id)
            if _version_integrity_matches(session, checkpoint, batch_id, row, metric_id, target_id):
                return target_id
            checkpoints.mark_target_integrity_conflict(batch_id, checkpoint.external_id)
            replay_conflict = True
        elif checkpoint.status == "conflict":
            raise CheckpointConflict(f"checkpoint conflict requires review: {checkpoint.external_id}")

        if not replay_conflict:
            if row.target_id is not None:
                raise CheckpointConflict("version target identity exists without a matching import checkpoint")
            values = dict(row.values)
            values["metric_id"] = metric_id
            version = SemanticMetricVersionRecord(
                **values,
                source_system=row.source_system,
                source_table=row.source_table,
                source_id=row.source_id,
                migration_batch_id=batch_id,
            )
            session.add(version)
            session.flush()
            checkpoints.mark_item(
                batch_id,
                checkpoint.external_id,
                status="imported",
                target_type=_TARGET_VERSION,
                target_id=str(version.id),
            )
            target_id = version.id

    if replay_conflict:
        raise CheckpointConflict("metric version target integrity mismatch")
    if target_id is None:
        raise CheckpointConflict("version checkpoint has no target identity")
    return target_id


def _version_integrity_matches(
    session: Session,
    checkpoint: MigrationItemRecord,
    batch_id: int,
    row: MappedLegacyRow,
    metric_id: int,
    target_id: int,
) -> bool:
    if checkpoint.target_type != _TARGET_VERSION:
        return False
    version = session.get(SemanticMetricVersionRecord, target_id)
    if version is None or version.metric_id != metric_id or not _has_provenance(version, row, batch_id):
        return False
    return all(getattr(version, name, object()) == value for name, value in row.values.items() if name != "metric_id")


def _resolve_reference(
    session: Session,
    batch_id: int,
    reference: TargetIdentityReference,
    target_ids: Mapping[tuple[str, str], int],
) -> int | None:
    identity = (reference.source_table, reference.source_id)
    if identity in target_ids:
        return target_ids[identity]
    checkpoint = _get_item(session, batch_id, _external_id(identity))
    if checkpoint.status != "imported" or not checkpoint.target_id:
        return None
    return int(checkpoint.target_id)


def _has_profile_provenance(profile: SemanticMetricProfileRecord, row: MappedLegacyRow, batch_id: int) -> bool:
    return _has_provenance(profile, row, batch_id)


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
        raise KeyError(f"I20 migration checkpoint not found: {external_id}")
    return item


def _external_id(identity: tuple[str, str]) -> str:
    return f"{identity[0]}:{identity[1]}"


def _mark_failed(
    session_factory: sessionmaker[Session],
    batch_id: int,
    identity: tuple[str, str],
    error: Exception,
) -> None:
    with session_factory() as session, session.begin():
        checkpoints = MigrationCheckpointRepository(session)
        checkpoint = _get_item(session, batch_id, _external_id(identity))
        if checkpoint.status in {"pending", "failed"}:
            checkpoints.mark_item(
                batch_id,
                checkpoint.external_id,
                status="failed",
                error_message=type(error).__name__,
            )
