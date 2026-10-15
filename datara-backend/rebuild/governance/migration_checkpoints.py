"""Durable, resumable checkpoints for isolated legacy migration batches."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.governance.contracts import is_sha256_digest
from rebuild.governance.models import MigrationBatchRecord, MigrationItemRecord


_ITEM_STATUSES = {"pending", "imported", "skipped", "conflict", "failed"}
_TERMINAL_STATUSES = {"imported", "skipped", "conflict"}


class CheckpointConflict(ValueError):
    """Raised when an idempotency key or source item is reused with changed content."""


@dataclass(frozen=True)
class CheckpointItem:
    entity_type: str
    source_id: str
    payload_sha256: str

    @property
    def external_id(self) -> str:
        return f"{self.entity_type}:{self.source_id}"


class MigrationCheckpointRepository:
    """Persists one batch and its row-level outcomes in the caller's transaction."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_or_create_batch(
        self,
        *,
        source_system: str,
        idempotency_key: str,
        payload_sha256: str,
        expected_count: int,
    ) -> MigrationBatchRecord:
        if not source_system or len(source_system) > 64:
            raise ValueError("source_system must contain 1..64 characters")
        if not idempotency_key or len(idempotency_key) > 128:
            raise ValueError("idempotency_key must contain 1..128 characters")
        if not is_sha256_digest(payload_sha256):
            raise ValueError("payload_sha256 must be a lowercase SHA-256 digest")
        if expected_count < 0:
            raise ValueError("expected_count must be non-negative")

        batch = self.session.scalar(
            select(MigrationBatchRecord)
            .where(
                MigrationBatchRecord.source_system == source_system,
                MigrationBatchRecord.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        if batch is not None:
            if batch.payload_sha256 != payload_sha256 or batch.expected_count != expected_count:
                raise CheckpointConflict("idempotency key was already used for a different migration payload")
            return batch

        batch = MigrationBatchRecord(
            source_system=source_system,
            idempotency_key=idempotency_key,
            payload_sha256=payload_sha256,
            status="running",
            dry_run=False,
            expected_count=expected_count,
        )
        self.session.add(batch)
        self.session.flush()
        return batch

    def seed_items(self, batch_id: int, items: tuple[CheckpointItem, ...]) -> None:
        batch = self._batch(batch_id)
        identities = [item.external_id for item in items]
        if len(identities) != len(set(identities)):
            raise CheckpointConflict("migration payload contains duplicate source identities")
        if batch.expected_count != len(items):
            raise CheckpointConflict("checkpoint item count does not match the batch expected_count")

        current = {
            item.external_id: item
            for item in self.session.scalars(
                select(MigrationItemRecord)
                .where(MigrationItemRecord.batch_id == batch_id)
                .with_for_update()
            ).all()
        }
        for item in items:
            if not item.entity_type or len(item.entity_type) > 64:
                raise ValueError("entity_type must contain 1..64 characters")
            if not item.source_id or len(item.external_id) > 256:
                raise ValueError("source identity must contain 1..256 characters")
            if not is_sha256_digest(item.payload_sha256):
                raise ValueError("item payload_sha256 must be a lowercase SHA-256 digest")
            existing = current.get(item.external_id)
            if existing is not None:
                if existing.source_payload_sha256 != item.payload_sha256:
                    raise CheckpointConflict(f"source payload changed for {item.external_id}")
                continue
            self.session.add(
                MigrationItemRecord(
                    batch_id=batch_id,
                    external_id=item.external_id,
                    entity_type=item.entity_type,
                    source_payload_sha256=item.payload_sha256,
                    status="pending",
                )
            )
        self.session.flush()
        self._refresh_batch(batch)

    def mark_item(
        self,
        batch_id: int,
        external_id: str,
        *,
        status: str,
        target_type: str = "",
        target_id: str = "",
        error_message: str = "",
    ) -> MigrationItemRecord:
        if status not in _ITEM_STATUSES:
            raise ValueError(f"unsupported migration item status: {status}")
        batch = self._batch(batch_id)
        item = self.session.scalar(
            select(MigrationItemRecord)
            .where(
                MigrationItemRecord.batch_id == batch_id,
                MigrationItemRecord.external_id == external_id,
            )
            .with_for_update()
        )
        if item is None:
            raise KeyError(f"migration checkpoint not found: {external_id}")

        if item.status in _TERMINAL_STATUSES:
            if (
                item.status == status
                and item.target_type == target_type
                and item.target_id == target_id
                and item.error_message == error_message
            ):
                return item
            raise CheckpointConflict(f"terminal checkpoint cannot be changed: {external_id}")
        if item.status == "failed" and status != "failed":
            raise CheckpointConflict(f"failed checkpoint must be explicitly reopened: {external_id}")

        item.status = status
        item.target_type = target_type
        item.target_id = target_id
        item.error_message = error_message
        self.session.flush()
        self._refresh_batch(batch)
        return item

    def reopen_failed_items(self, batch_id: int) -> int:
        batch = self._batch(batch_id)
        items = self.session.scalars(
            select(MigrationItemRecord)
            .where(MigrationItemRecord.batch_id == batch_id)
            .with_for_update()
        ).all()
        if any(item.status == "conflict" for item in items):
            raise CheckpointConflict("batch contains conflicts requiring review; automatic recovery is refused")
        reopened = 0
        for item in items:
            if item.status == "failed":
                item.status = "pending"
                item.error_message = ""
                reopened += 1
        self.session.flush()
        self._refresh_batch(batch)
        return reopened

    def mark_target_integrity_conflict(self, batch_id: int, external_id: str) -> MigrationItemRecord:
        """Promote a previously successful item to a terminal conflict on replay drift."""

        batch = self._batch(batch_id)
        item = self.session.scalar(
            select(MigrationItemRecord)
            .where(
                MigrationItemRecord.batch_id == batch_id,
                MigrationItemRecord.external_id == external_id,
            )
            .with_for_update()
        )
        if item is None:
            raise KeyError(f"migration checkpoint not found: {external_id}")
        if item.status == "conflict" and item.error_message == "target_integrity_mismatch":
            return item
        if item.status not in {"imported", "skipped"} or not item.target_type or not item.target_id:
            raise CheckpointConflict(f"checkpoint cannot be integrity-checked: {external_id}")

        item.status = "conflict"
        item.error_message = "target_integrity_mismatch"
        self.session.flush()
        self._refresh_batch(batch)
        return item

    def _batch(self, batch_id: int) -> MigrationBatchRecord:
        batch = self.session.scalar(
            select(MigrationBatchRecord).where(MigrationBatchRecord.id == batch_id).with_for_update()
        )
        if batch is None:
            raise KeyError(f"migration batch not found: {batch_id}")
        return batch

    def _refresh_batch(self, batch: MigrationBatchRecord) -> None:
        statuses = self.session.scalars(
            select(MigrationItemRecord.status).where(MigrationItemRecord.batch_id == batch.id)
        ).all()
        if len(statuses) > batch.expected_count:
            raise CheckpointConflict("checkpoint count exceeds batch expected_count")
        batch.imported_count = statuses.count("imported")
        batch.skipped_count = statuses.count("skipped")
        batch.error_count = statuses.count("failed") + statuses.count("conflict")
        if batch.error_count:
            batch.status = "failed"
        elif statuses and len(statuses) == batch.expected_count and all(
            status in _TERMINAL_STATUSES for status in statuses
        ):
            batch.status = "completed"
        else:
            batch.status = "running"
        batch.error_summary = f"{batch.error_count} migration item(s) require review" if batch.error_count else ""

