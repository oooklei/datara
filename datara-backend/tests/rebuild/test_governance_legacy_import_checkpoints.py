from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.governance.models import MigrationBatchRecord, MigrationItemRecord
from rebuild.governance.migration_checkpoints import (
    CheckpointConflict,
    CheckpointItem,
    MigrationCheckpointRepository,
)
from rebuild.identity.models import UserRecord  # noqa: F401
from rebuild.project.models import ProjectRecord  # noqa: F401


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_checkpoint_batch_is_idempotent_and_rejects_payload_drift():
    engine = _session_factory()
    try:
        with Session(engine) as session, session.begin():
            repository = MigrationCheckpointRepository(session)
            first = repository.get_or_create_batch(
                source_system="datara_meta:i18",
                idempotency_key="project-41:source-a",
                payload_sha256="a" * 64,
                expected_count=2,
            )
            repeated = repository.get_or_create_batch(
                source_system="datara_meta:i18",
                idempotency_key="project-41:source-a",
                payload_sha256="a" * 64,
                expected_count=2,
            )
            assert repeated.id == first.id
            try:
                repository.get_or_create_batch(
                    source_system="datara_meta:i18",
                    idempotency_key="project-41:source-a",
                    payload_sha256="b" * 64,
                    expected_count=2,
                )
            except CheckpointConflict:
                pass
            else:
                raise AssertionError("idempotency key reuse with a different payload must fail closed")
    finally:
        engine.dispose()


def test_checkpoint_records_terminal_outcomes_and_retry_without_duplicate_items():
    engine = _session_factory()
    try:
        with Session(engine) as session, session.begin():
            repository = MigrationCheckpointRepository(session)
            batch = repository.get_or_create_batch(
                source_system="datara_meta:i18",
                idempotency_key="project-41:source-b",
                payload_sha256="c" * 64,
                expected_count=2,
            )
            repository.seed_items(
                batch.id,
                (
                    CheckpointItem("t_biz_domain", "5", "d" * 64),
                    CheckpointItem("t_dw_model_version", "1", "e" * 64),
                ),
            )
            repository.mark_item(
                batch.id,
                "t_biz_domain:5",
                status="imported",
                target_type="rebuild_governance_domain",
                target_id="901",
            )
            repository.mark_item(
                batch.id,
                "t_dw_model_version:1",
                status="skipped",
                error_message="approved_missing_model_reference",
            )
            repository.mark_item(
                batch.id,
                "t_biz_domain:5",
                status="imported",
                target_type="rebuild_governance_domain",
                target_id="901",
            )

        with Session(engine) as session:
            stored_batch = session.scalar(select(MigrationBatchRecord))
            items = session.scalars(select(MigrationItemRecord).order_by(MigrationItemRecord.external_id)).all()
            assert stored_batch is not None
            assert stored_batch.status == "completed"
            assert stored_batch.imported_count == 1
            assert stored_batch.skipped_count == 1
            assert stored_batch.error_count == 0
            assert len(items) == 2
            assert {item.status for item in items} == {"imported", "skipped"}
            assert all(item.created_at and item.updated_at and item.generated_at for item in items)
    finally:
        engine.dispose()


def test_failed_checkpoint_can_be_reopened_for_recovery_but_terminal_conflict_cannot():
    engine = _session_factory()
    try:
        with Session(engine) as session, session.begin():
            repository = MigrationCheckpointRepository(session)
            batch = repository.get_or_create_batch(
                source_system="datara_meta:i18",
                idempotency_key="project-41:source-c",
                payload_sha256="f" * 64,
                expected_count=1,
            )
            repository.seed_items(batch.id, (CheckpointItem("t_biz_domain", "5", "1" * 64),))
            repository.mark_item(batch.id, "t_biz_domain:5", status="failed", error_message="IntegrityError")
            repository.reopen_failed_items(batch.id)
            item = session.scalar(select(MigrationItemRecord))
            assert item is not None and item.status == "pending" and item.error_message == ""
            repository.mark_item(batch.id, "t_biz_domain:5", status="conflict", error_message="fingerprint mismatch")
            try:
                repository.reopen_failed_items(batch.id)
            except CheckpointConflict:
                pass
            else:
                raise AssertionError("conflicts require review and must not be auto-retried")
    finally:
        engine.dispose()
