from datetime import datetime, timezone
import hashlib
import json

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from rebuild.common.db import Base
from rebuild.governance.legacy_i20_importer import (
    I20ImportRejected,
    execute_i20_legacy_import,
)
from rebuild.governance.legacy_source_reader import I20_SOURCE_COLUMNS
from rebuild.governance.models import (
    AuditEventRecord,
    MigrationBatchRecord,
    MigrationItemRecord,
    SemanticMetricProfileRecord,
    SemanticMetricRecord,
    SemanticMetricVersionRecord,
)
from rebuild.governance.migration_checkpoints import CheckpointConflict
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


def _source(*, dimensions="country,region", digest=None, orphan=False):
    metric = {
        "id": 7,
        "code": "orders_total",
        "name": "订单总数",
        "type": "原子",
        "biz_domain": "交易",
        "biz_def": "订单数量",
        "tech_def": "count(order_id)",
        "src_kind": "table",
        "src_ref": "warehouse.orders",
        "src_field": "order_id",
        "out_table": "dws_orders",
        "out_task": "orders_daily",
        "period": "日",
        "dims": dimensions,
        "unit": "个",
        "status": "draft",
        "version": 2,
        "owner": "data-team",
        "base_metric_id": None,
        "agg_fn": "count",
        "num_field": None,
        "time_field": "created_at",
        "dim_field": "country",
        "filter_cond": "is_valid = 1",
        "create_time": None,
        "update_time": None,
    }
    versions = (
        {
            "id": 91,
            "indicator_id": 7,
            "version": 1,
            "snapshot_json": '{"legacy":"verbatim"}',
            "change_note": "initial",
            "created_by": "alice",
            "create_time": None,
        },
    )
    if orphan:
        versions = ({**versions[0], "indicator_id": 999},)
    rows = {"t_indicator": (metric,), "t_indicator_version": versions}
    payload = {"schema": "datara_meta", "rows": rows}
    source_digest = digest or hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return type("Snapshot", (), {
        "schema": "datara_meta",
        "captured_at": datetime(2026, 10, 16, tzinfo=timezone.utc),
        "digest": source_digest,
        "counts": {table: len(rows[table]) for table in I20_SOURCE_COLUMNS},
        "rows": rows,
    })()


def _target_digest(factory):
    with factory() as session:
        profiles = session.scalars(
            select(SemanticMetricProfileRecord).join(
                SemanticMetricRecord, SemanticMetricRecord.id == SemanticMetricProfileRecord.metric_id
            ).where(SemanticMetricRecord.project_id == 41)
        ).all()
        versions = session.scalars(
            select(SemanticMetricVersionRecord).join(
                SemanticMetricRecord, SemanticMetricRecord.id == SemanticMetricVersionRecord.metric_id
            ).where(SemanticMetricRecord.project_id == 41)
        ).all()
        identities = [
            (record.source_table, record.source_id, record.metric_id)
            for record in profiles
            if record.source_system == "datara_meta" and record.source_id
        ] + [
            (record.source_table, record.source_id, record.id)
            for record in versions
            if record.source_system == "datara_meta" and record.source_id
        ]
    identities.sort()
    return hashlib.sha256(json.dumps(identities, separators=(",", ":")).encode("utf-8")).hexdigest()


def _execute(factory, source, *, key="i20-project-41", target_digest=None, source_digest=None):
    return execute_i20_legacy_import(
        factory,
        project_id=41,
        actor_id=1,
        source_snapshot=source,
        expected_source_digest=source_digest or source.digest,
        expected_target_digest=target_digest or _target_digest(factory),
        idempotency_key=key,
    )


def test_i20_import_atomically_checkpoints_metric_profile_and_versions_and_replays():
    engine, factory = _factories()
    source = _source()
    try:
        first = _execute(factory, source)
        replay = _execute(factory, source, target_digest=_target_digest(factory))

        with Session(engine) as session:
            metric = session.scalar(select(SemanticMetricRecord))
            profile = session.scalar(select(SemanticMetricProfileRecord))
            version = session.scalar(select(SemanticMetricVersionRecord))
            batch = session.scalar(select(MigrationBatchRecord))
            items = session.scalars(select(MigrationItemRecord).order_by(MigrationItemRecord.external_id)).all()
            audit = session.scalar(
                select(AuditEventRecord).where(AuditEventRecord.action == "legacy_i20_import_requested")
            )
            metric_count = session.scalar(select(func.count()).select_from(SemanticMetricRecord))
            profile_count = session.scalar(select(func.count()).select_from(SemanticMetricProfileRecord))
            version_count = session.scalar(select(func.count()).select_from(SemanticMetricVersionRecord))

        assert first.batch_id == replay.batch_id
        assert first.status == replay.status == "completed"
        assert first.expected_count == first.imported_count == 2
        assert metric_count == profile_count == version_count == 1
        assert metric is not None and metric.project_id == 41 and metric.code == "orders_total"
        assert profile is not None and profile.metric_id == metric.id
        assert profile.legacy_dimensions == "country,region"
        assert version is not None and version.metric_id == metric.id
        assert version.snapshot_json == '{"legacy":"verbatim"}'
        assert batch is not None and batch.source_system == "datara_meta:i20:41"
        assert {item.external_id: item.status for item in items} == {
            "t_indicator:7": "imported",
            "t_indicator_version:91": "imported",
        }
        assert audit is not None and '"source_digest"' in audit.after_json
    finally:
        engine.dispose()


def test_i20_import_fails_closed_on_digest_drift_or_orphan_versions_before_batch_write():
    engine, factory = _factories()
    try:
        valid = _source()
        with pytest.raises(I20ImportRejected, match="source digest"):
            _execute(factory, valid, source_digest="f" * 64)
        with pytest.raises(I20ImportRejected, match="target digest"):
            _execute(factory, valid, target_digest="e" * 64)
        with pytest.raises(I20ImportRejected, match="mapping issues"):
            _execute(factory, _source(orphan=True))

        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(MigrationBatchRecord)) == 0
            assert session.scalar(select(func.count()).select_from(SemanticMetricRecord)) == 0
    finally:
        engine.dispose()


def test_i20_import_rejects_reused_idempotency_key_after_source_payload_changes():
    engine, factory = _factories()
    try:
        _execute(factory, _source())
        changed = _source(dimensions="country|region")
        with pytest.raises(CheckpointConflict, match="different migration payload|payload changed"):
            _execute(factory, changed, target_digest=_target_digest(factory))
    finally:
        engine.dispose()


def test_i20_import_resumes_a_failed_metric_checkpoint_without_duplicate_rows():
    engine, factory = _factories()
    source = _source()
    did_fail = False

    def fail_first_metric_insert(_connection, _cursor, statement, _parameters, _context, _many):
        nonlocal did_fail
        if not did_fail and statement.lstrip().upper().startswith("INSERT INTO REBUILD_GOVERNANCE_SEMANTIC_METRIC "):
            did_fail = True
            raise RuntimeError("transient target write failure")

    event.listen(engine, "before_cursor_execute", fail_first_metric_insert)
    try:
        failed = _execute(factory, source)
    finally:
        event.remove(engine, "before_cursor_execute", fail_first_metric_insert)

    try:
        resumed = _execute(factory, source)
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(SemanticMetricRecord)) == 1
            assert session.scalar(select(func.count()).select_from(SemanticMetricProfileRecord)) == 1
            assert session.scalar(select(func.count()).select_from(SemanticMetricVersionRecord)) == 1
            metric_checkpoint = session.scalar(
                select(MigrationItemRecord).where(MigrationItemRecord.external_id == "t_indicator:7")
            )
        assert failed.status == "failed" and failed.error_count == 1
        assert resumed.batch_id == failed.batch_id
        assert resumed.status == "completed" and resumed.imported_count == 2
        assert metric_checkpoint is not None and metric_checkpoint.status == "imported"
    finally:
        engine.dispose()


def test_i20_replay_checks_profile_integrity_and_marks_drift_as_conflict():
    engine, factory = _factories()
    source = _source()
    try:
        first = _execute(factory, source)
        with factory() as session, session.begin():
            profile = session.scalar(select(SemanticMetricProfileRecord))
            assert profile is not None
            profile.legacy_dimensions = "tampered"

        replay = _execute(factory, source, target_digest=_target_digest(factory))
        with Session(engine) as session:
            item = session.scalar(
                select(MigrationItemRecord).where(MigrationItemRecord.external_id == "t_indicator:7")
            )
        assert replay.batch_id == first.batch_id
        assert replay.status == "failed" and replay.error_count == 1
        assert item is not None and item.status == "conflict"
        assert item.error_message == "target_integrity_mismatch"
    finally:
        engine.dispose()
