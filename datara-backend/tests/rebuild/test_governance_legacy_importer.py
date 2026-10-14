from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from rebuild.common.db import Base
from rebuild.governance.legacy_dry_run import I18TargetSnapshot
from rebuild.governance.legacy_importer import (
    LegacyImportRejected,
    _assert_isolated_target,
    execute_i18_legacy_import,
)
from rebuild.governance.legacy_source_reader import LEGACY_SCHEMA, LegacyI18SourceSnapshot
from rebuild.governance.models import (
    GovernanceDomainRecord,
    MigrationBatchRecord,
    MigrationItemRecord,
)
from rebuild.identity.models import UserRecord
from rebuild.project.models import ProjectRecord


def _factories():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session, session.begin():
        session.add(UserRecord(id=1, username="operator", password_hash="hash", role="admin"))
        session.add(ProjectRecord(id=41, name="target", description="", owner_id=1))
    return engine, factory


def _snapshots(*, include_layer=False):
    tables = (
        "t_biz_domain",
        "t_dw_layer",
        "t_engine_type",
        "t_dw_model",
        "t_dw_model_field",
        "t_dw_model_relation",
        "t_dw_model_version",
    )
    rows = {table: () for table in tables}
    rows["t_biz_domain"] = ({"id": 5, "name": "交易域", "remark": "订单业务域"},)
    if include_layer:
        rows["t_dw_layer"] = ({"code": "DWD", "name": "明细层", "rule": "dwd_*", "seq": 2},)
    rows["t_dw_model_version"] = (
        {"id": 1, "model_id": 1, "version": 1, "snapshot_json": "{}"},
    )
    source = LegacyI18SourceSnapshot(
        schema=LEGACY_SCHEMA,
        captured_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        digest="a" * 64,
        counts={table: len(rows[table]) for table in tables},
        rows=rows,
    )
    target = I18TargetSnapshot(
        project_id=41,
        captured_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        digest="b" * 64,
        row_fingerprints={},
        target_ids={},
        model_fields={},
        unique_key_owners={},
    )
    return source, target


def test_i18_import_persists_row_checkpoints_and_replay_is_idempotent():
    engine, factory = _factories()
    source, target = _snapshots()
    try:
        first = execute_i18_legacy_import(
            factory,
            project_id=41,
            actor_id=1,
            source_snapshot=source,
            target_snapshot=target,
            idempotency_key="i18-project-41-source-a",
        )
        replay = execute_i18_legacy_import(
            factory,
            project_id=41,
            actor_id=1,
            source_snapshot=source,
            target_snapshot=target,
            idempotency_key="i18-project-41-source-a",
        )
        with Session(engine) as session:
            domain_count = session.scalar(select(func.count()).select_from(GovernanceDomainRecord))
            batch_count = session.scalar(select(func.count()).select_from(MigrationBatchRecord))
            domain = session.scalar(select(GovernanceDomainRecord))
            item = session.scalar(select(MigrationItemRecord))

        assert first.batch_id == replay.batch_id
        assert first.status == replay.status == "completed"
        assert first.imported_count == replay.imported_count == 1
        assert first.skipped_count == replay.skipped_count == 1
        assert domain_count == batch_count == 1
        assert domain is not None and domain.name == "交易域"
        assert domain.migration_batch_id == first.batch_id
        with Session(engine) as session:
            items = session.scalars(select(MigrationItemRecord).order_by(MigrationItemRecord.external_id)).all()
            batch = session.scalar(select(MigrationBatchRecord))
        assert item is not None and item.status == "imported"
        assert item.target_type == "rebuild_governance_domain"
        assert item.target_id == str(domain.id)
        skipped = next(row for row in items if row.entity_type == "t_dw_model_version")
        assert skipped.status == "skipped"
        assert skipped.error_message == "approved_missing_model_reference"
        assert batch is not None and batch.imported_count == 1 and batch.skipped_count == 1
        assert all(row.created_at and row.updated_at and row.generated_at for row in items)
    finally:
        engine.dispose()


def test_i18_import_recovers_failed_row_without_recreating_completed_rows():
    engine, factory = _factories()
    source, target = _snapshots(include_layer=True)
    from rebuild.governance.models import WarehouseLayerRecord

    calls = {"count": 0}

    def fail_once(_mapper, _connection, _target):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("simulated connection interruption")

    from sqlalchemy import event

    event.listen(WarehouseLayerRecord, "before_insert", fail_once)
    try:
        failed = execute_i18_legacy_import(
            factory,
            project_id=41,
            actor_id=1,
            source_snapshot=source,
            target_snapshot=target,
            idempotency_key="i18-project-41-source-recovery",
        )
        assert failed.status == "failed"
        with Session(engine) as session:
            failed_item = session.scalar(
                select(MigrationItemRecord).where(MigrationItemRecord.entity_type == "t_biz_domain")
            )
            assert failed_item is not None and failed_item.status == "imported"
            failed_layer = session.scalar(
                select(MigrationItemRecord).where(MigrationItemRecord.entity_type == "t_dw_layer")
            )
            assert failed_layer is not None and failed_layer.status == "failed"

        resumed = execute_i18_legacy_import(
            factory,
            project_id=41,
            actor_id=1,
            source_snapshot=source,
            target_snapshot=target,
            idempotency_key="i18-project-41-source-recovery",
        )
        with Session(engine) as session:
            domains = session.scalars(select(GovernanceDomainRecord)).all()
            layers = session.scalars(select(WarehouseLayerRecord)).all()
            batches = session.scalars(select(MigrationBatchRecord)).all()
            items = session.scalars(select(MigrationItemRecord)).all()
        assert resumed.status == "completed"
        assert len(domains) == len(layers) == len(batches) == 1
        assert len(items) == 3
        assert {row.status for row in items} == {"imported", "skipped"}
        assert batches[0].imported_count == 2 and batches[0].skipped_count == 1 and batches[0].error_count == 0
    finally:
        event.remove(WarehouseLayerRecord, "before_insert", fail_once)
        engine.dispose()


def test_i18_import_requires_project_edit_permission_before_creating_batch():
    engine, factory = _factories()
    source, target = _snapshots()
    try:
        try:
            execute_i18_legacy_import(
                factory,
                project_id=41,
                actor_id=999,
                source_snapshot=source,
                target_snapshot=target,
                idempotency_key="i18-project-41-denied",
            )
        except LegacyImportRejected as error:
            assert "permission" in str(error)
        else:
            raise AssertionError("import must require project edit permission")

        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(MigrationBatchRecord)) == 0
            assert session.scalar(select(func.count()).select_from(GovernanceDomainRecord)) == 0
    finally:
        engine.dispose()


def test_import_target_guard_rejects_file_sqlite_outside_test_memory(tmp_path):
    sqlite_path = tmp_path / "not-a-test-memory-database.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{sqlite_path.as_posix()}")
    try:
        with pytest.raises(LegacyImportRejected, match="isolated rebuild schema"):
            _assert_isolated_target(sessionmaker(engine))
        assert not sqlite_path.exists()
    finally:
        engine.dispose()
