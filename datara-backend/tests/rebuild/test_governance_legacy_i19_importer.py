from datetime import datetime, timezone
import hashlib
import json

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from rebuild.common.db import Base
from rebuild.governance.legacy_i19_mapping import LegacyI19MappingContext
from rebuild.governance.legacy_importer import LegacyImportRejected
from rebuild.governance.migration_checkpoints import CheckpointConflict
from rebuild.governance.legacy_source_reader import I19_SOURCE_COLUMNS, LegacyI19SourceSnapshot
from rebuild.governance.models import (
    AuditEventRecord,
    GovernanceTagRecord,
    LegacyTagDefinitionRecord,
    LegacyTagReferenceRecord,
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


def _row(table, **values):
    columns = I19_SOURCE_COLUMNS[table][1]
    row = {column: None for column in columns}
    row.update(values)
    return row


def _snapshot(*, tag_name="核心数据", digest=None):
    rows = {table: () for table in I19_SOURCE_COLUMNS}
    rows["t_meta_tag"] = (
        _row(
            "t_meta_tag",
            id=3,
            name=tag_name,
            cat="用途",
            color="#1677ff",
            desc="important data",
            create_time="2026-01-01T00:00:00",
            update_time="2026-02-01T00:00:00",
        ),
    )
    rows["t_meta_tagging"] = (
        _row(
            "t_meta_tagging",
            id=5,
            tag_id=3,
            target_type="future",
            target_key="raw/key",
            created_by="operator",
            create_time="2026-02-02T00:00:00",
        ),
    )
    if digest is None:
        payload = {
            "schema": "datara_meta",
            "rows": {table: list(table_rows) for table, table_rows in rows.items()},
        }
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    return LegacyI19SourceSnapshot(
        schema="datara_meta",
        captured_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        digest=digest,
        counts={table: len(rows[table]) for table in I19_SOURCE_COLUMNS},
        rows=rows,
    )


def _context_factory(_session, project_id):
    return LegacyI19MappingContext(target_project_id=project_id)


def _target_digest():
    from rebuild.governance.legacy_i19_importer import i19_target_identity_digest

    return i19_target_identity_digest(LegacyI19MappingContext(target_project_id=41))


def test_i19_import_writes_tag_bundle_and_unresolved_reference_then_replays_idempotently():
    from rebuild.governance.legacy_i19_importer import execute_i19_legacy_import

    engine, factory = _factories()
    source = _snapshot()
    target_digest = _target_digest()
    try:
        first = execute_i19_legacy_import(
            factory,
            project_id=41,
            actor_id=1,
            source_snapshot=source,
            expected_source_digest=source.digest,
            expected_target_digest=target_digest,
            mapping_context_factory=_context_factory,
            idempotency_key="i19-project-41-source-1",
        )
        replay = execute_i19_legacy_import(
            factory,
            project_id=41,
            actor_id=1,
            source_snapshot=source,
            expected_source_digest=source.digest,
            expected_target_digest=target_digest,
            mapping_context_factory=_context_factory,
            idempotency_key="i19-project-41-source-1",
        )
        with Session(engine) as session:
            tag = session.scalar(select(GovernanceTagRecord))
            definition = session.scalar(select(LegacyTagDefinitionRecord))
            reference = session.scalar(select(LegacyTagReferenceRecord))
            batch = session.scalar(select(MigrationBatchRecord))
            items = session.scalars(select(MigrationItemRecord).order_by(MigrationItemRecord.external_id)).all()
            audits = session.scalars(select(AuditEventRecord)).all()

        assert first.status == replay.status == "completed"
        assert first.batch_id == replay.batch_id
        assert first.expected_count == first.imported_count == 2
        assert tag is not None and tag.namespace == "legacy_i19" and tag.tag_key == "legacy-3"
        assert definition is not None and definition.normalized_tag_id == tag.id
        assert definition.tag_category == "用途" and definition.color == "#1677ff"
        assert reference is not None and reference.tag_id == tag.id
        assert reference.target_type == "future" and reference.target_key == "raw/key"
        assert reference.resolved_asset_id is None
        assert batch is not None and batch.status == "completed" and batch.imported_count == 2
        assert {item.external_id for item in items} == {"t_meta_tag:3", "t_meta_tagging:5"}
        assert all(item.status == "imported" and item.target_id for item in items)
        assert len(audits) == 2 and all(row.action == "legacy_i19_import_requested" for row in audits)
    finally:
        engine.dispose()


def test_i19_import_rejects_stale_source_or_target_digest_before_creating_batch():
    from rebuild.governance.legacy_i19_importer import execute_i19_legacy_import

    engine, factory = _factories()
    source = _snapshot()
    try:
        with pytest.raises(LegacyImportRejected, match="snapshot changed"):
            execute_i19_legacy_import(
                factory,
                project_id=41,
                actor_id=1,
                source_snapshot=source,
                expected_source_digest="c" * 64,
                expected_target_digest="c" * 64,
                mapping_context_factory=_context_factory,
                idempotency_key="i19-stale-snapshot",
            )
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(MigrationBatchRecord)) == 0
            assert session.scalar(select(func.count()).select_from(GovernanceTagRecord)) == 0
    finally:
        engine.dispose()


def test_i19_import_rechecks_target_digest_from_fresh_context_inside_target_session():
    from rebuild.governance.legacy_i19_importer import execute_i19_legacy_import

    engine, factory = _factories()
    source = _snapshot()

    def changed_context(_session, project_id):
        return LegacyI19MappingContext(
            target_project_id=project_id,
            target_ids={("t_meta_tag", "99"): 700},
        )

    try:
        with pytest.raises(LegacyImportRejected, match="snapshot changed"):
            execute_i19_legacy_import(
                factory,
                project_id=41,
                actor_id=1,
                source_snapshot=source,
                expected_source_digest=source.digest,
                expected_target_digest=_target_digest(),
                mapping_context_factory=changed_context,
                idempotency_key="i19-stale-target",
            )
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(MigrationBatchRecord)) == 0
            assert session.scalar(select(func.count()).select_from(GovernanceTagRecord)) == 0
    finally:
        engine.dispose()


def test_i19_import_recomputes_digest_from_mutable_snapshot_rows_before_batch_write():
    from rebuild.governance.legacy_i19_importer import execute_i19_legacy_import

    engine, factory = _factories()
    source = _snapshot()
    source.rows["t_meta_tag"][0]["name"] = "changed after digest"
    try:
        with pytest.raises(LegacyImportRejected, match="source snapshot digest"):
            execute_i19_legacy_import(
                factory,
                project_id=41,
                actor_id=1,
                source_snapshot=source,
                expected_source_digest=source.digest,
                expected_target_digest=_target_digest(),
                mapping_context_factory=_context_factory,
                idempotency_key="i19-mutated-source",
            )
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(MigrationBatchRecord)) == 0
    finally:
        engine.dispose()


def test_i19_project_lock_identity_is_project_scoped():
    from rebuild.governance.legacy_i19_importer import _project_lock_name

    assert _project_lock_name(41) == _project_lock_name(41)
    assert _project_lock_name(41) != _project_lock_name(42)


def test_i19_tag_definition_failure_rolls_back_entire_bundle_and_checkpoint_can_resume():
    from sqlalchemy import event

    from rebuild.governance.legacy_i19_importer import execute_i19_legacy_import

    engine, factory = _factories()
    source = _snapshot()
    target_digest = _target_digest()
    calls = {"count": 0}

    def fail_once(_mapper, _connection, _target):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("simulated definition insert failure")

    event.listen(LegacyTagDefinitionRecord, "before_insert", fail_once)
    try:
        failed = execute_i19_legacy_import(
            factory,
            project_id=41,
            actor_id=1,
            source_snapshot=source,
            expected_source_digest=source.digest,
            expected_target_digest=target_digest,
            mapping_context_factory=_context_factory,
            idempotency_key="i19-bundle-recovery",
        )
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(GovernanceTagRecord)) == 0
            assert session.scalar(select(func.count()).select_from(LegacyTagDefinitionRecord)) == 0
            tag_item = session.scalar(
                select(MigrationItemRecord).where(MigrationItemRecord.external_id == "t_meta_tag:3")
            )
        assert failed.status == "failed"
        assert tag_item is not None and tag_item.status == "failed"

        resumed = execute_i19_legacy_import(
            factory,
            project_id=41,
            actor_id=1,
            source_snapshot=source,
            expected_source_digest=source.digest,
            expected_target_digest=target_digest,
            mapping_context_factory=_context_factory,
            idempotency_key="i19-bundle-recovery",
        )
        assert resumed.status == "completed"
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(GovernanceTagRecord)) == 1
            assert session.scalar(select(func.count()).select_from(LegacyTagDefinitionRecord)) == 1
            assert session.scalar(select(func.count()).select_from(LegacyTagReferenceRecord)) == 1
    finally:
        event.remove(LegacyTagDefinitionRecord, "before_insert", fail_once)
        engine.dispose()


def test_i19_import_resumes_after_partial_success_with_fresh_target_digest():
    from sqlalchemy import event

    from rebuild.governance.legacy_i19_importer import (
        build_i19_mapping_context,
        execute_i19_legacy_import,
        i19_target_identity_digest,
    )

    engine, factory = _factories()
    source = _snapshot()
    original_digest = _target_digest()
    did_fail = False

    def fail_reference_once(_mapper, _connection, _target):
        nonlocal did_fail
        if not did_fail:
            did_fail = True
            raise RuntimeError("simulated reference insert failure")

    event.listen(LegacyTagReferenceRecord, "before_insert", fail_reference_once)
    try:
        failed = execute_i19_legacy_import(
            factory,
            project_id=41,
            actor_id=1,
            source_snapshot=source,
            expected_source_digest=source.digest,
            expected_target_digest=original_digest,
            mapping_context_factory=build_i19_mapping_context,
            idempotency_key="i19-resume-after-partial-write",
        )
    finally:
        event.remove(LegacyTagReferenceRecord, "before_insert", fail_reference_once)

    with factory() as session:
        fresh_target_digest = i19_target_identity_digest(build_i19_mapping_context(session, 41))
    try:
        resumed = execute_i19_legacy_import(
            factory,
            project_id=41,
            actor_id=1,
            source_snapshot=source,
            expected_source_digest=source.digest,
            expected_target_digest=fresh_target_digest,
            mapping_context_factory=build_i19_mapping_context,
            idempotency_key="i19-resume-after-partial-write",
        )
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(GovernanceTagRecord)) == 1
            assert session.scalar(select(func.count()).select_from(LegacyTagDefinitionRecord)) == 1
            assert session.scalar(select(func.count()).select_from(LegacyTagReferenceRecord)) == 1
        assert failed.status == "failed" and failed.imported_count == 1
        assert resumed.batch_id == failed.batch_id
        assert resumed.status == "completed" and resumed.imported_count == 2
    finally:
        engine.dispose()


def test_i19_idempotency_key_rejects_changed_mapped_payload():
    from rebuild.governance.legacy_i19_importer import execute_i19_legacy_import

    engine, factory = _factories()
    target_digest = _target_digest()
    try:
        first = _snapshot(tag_name="核心数据")
        second = _snapshot(tag_name="关键数据")
        execute_i19_legacy_import(
            factory,
            project_id=41,
            actor_id=1,
            source_snapshot=first,
            expected_source_digest=first.digest,
            expected_target_digest=target_digest,
            mapping_context_factory=_context_factory,
            idempotency_key="i19-payload-change",
        )
        with pytest.raises(CheckpointConflict, match="different migration payload"):
            execute_i19_legacy_import(
                factory,
                project_id=41,
                actor_id=1,
                source_snapshot=second,
                expected_source_digest=second.digest,
                expected_target_digest=target_digest,
                mapping_context_factory=_context_factory,
                idempotency_key="i19-payload-change",
            )
    finally:
        engine.dispose()
