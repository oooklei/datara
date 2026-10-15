from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from rebuild.governance.migrations import (
    GovernanceMigration,
    MigrationApplyError,
    MigrationChecksumConflict,
    MigrationRunner,
    R3_GOVERNANCE_MIGRATIONS,
)
from rebuild.governance.models import (
    AssetRecord,
    AssetTagUnresolvedRecord,
    GOVERNANCE_I19_I20_TABLES,
    GOVERNANCE_TABLES,
    LEGACY_CARRY_FORWARD_TABLES,
    MetricDimensionRecord,
)
from rebuild.project.models import ProjectRecord
from rebuild.identity.models import UserRecord
from rebuild.governance.revisions import (
    v0001_governance_catalog,
    v0002_legacy_governance_carryforward,
    v0003_metadata_metric_carry_forward,
)


def isolated_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ProjectRecord.__table__.create(engine)
    UserRecord.__table__.create(engine)
    return engine


def test_migration_registry_applies_once_and_records_database_timestamps():
    engine = isolated_engine()
    calls = []

    def upgrade(target_engine):
        calls.append("upgrade")
        AssetRecord.__table__.create(target_engine, checkfirst=True)

    migration = GovernanceMigration("r3-test-0001", "a" * 64, upgrade)
    runner = MigrationRunner(engine, [migration])

    first = runner.apply()
    second = runner.apply()

    assert first.applied == ("r3-test-0001",)
    assert second.skipped == ("r3-test-0001",)
    assert calls == ["upgrade"]
    assert "rebuild_governance_asset" in inspect(engine).get_table_names()
    with Session(engine) as session:
        record = runner.get_revision(session, "r3-test-0001")
        assert record is not None
        assert record.status == "completed"
        assert record.attempt_count == 1
        assert isinstance(record.created_at, datetime)
        assert isinstance(record.updated_at, datetime)
        assert isinstance(record.generated_at, datetime)
        assert isinstance(record.finished_at, datetime)


def test_real_r3_revisions_are_additive_and_create_all_normalized_legacy_tables():
    engine = isolated_engine()
    result = MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS).apply()
    table_names = set(inspect(engine).get_table_names())
    expected_v1 = {table.name for table in GOVERNANCE_TABLES}
    expected_v2 = {table.name for table in LEGACY_CARRY_FORWARD_TABLES}
    expected_v3 = {table.name for table in GOVERNANCE_I19_I20_TABLES}

    assert result.applied == (
        "r3_0001_governance_catalog",
        "r3_0002_legacy_governance_carryforward",
        "r3_0003_metadata_metric_carry_forward",
    )
    assert expected_v1 | expected_v2 | expected_v3 <= table_names
    assert R3_GOVERNANCE_MIGRATIONS[0].checksum == v0001_governance_catalog.checksum
    assert R3_GOVERNANCE_MIGRATIONS[1].checksum == v0002_legacy_governance_carryforward.checksum
    assert R3_GOVERNANCE_MIGRATIONS[2].checksum == v0003_metadata_metric_carry_forward.checksum
    assert MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS).apply().skipped == result.applied
    assert "rebuild_user" in table_names
    assert "qc_task" not in table_names


def test_i19_i20_tables_follow_main_legacy_source_contract_without_rewriting_v2():
    engine = isolated_engine()
    MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS).apply()
    inspector = inspect(engine)

    for record in (AssetTagUnresolvedRecord, MetricDimensionRecord):
        columns = {item["name"]: item for item in inspector.get_columns(record.__tablename__)}
        assert columns["source_id"]["nullable"]
        assert columns["source_system"]["nullable"]
        assert columns["migration_batch_id"]["nullable"]
        assert columns["source_id"]["type"].length == 256
        batch_fk = next(
            item for item in inspector.get_foreign_keys(record.__tablename__)
            if item["constrained_columns"] == ["migration_batch_id"]
        )
        assert batch_fk["referred_table"] == "rebuild_governance_migration_batch"
        assert batch_fk["options"]["ondelete"] == "RESTRICT"

    tag_fks = inspector.get_foreign_keys(AssetTagUnresolvedRecord.__tablename__)
    assert any(
        item["constrained_columns"] == ["tag_id"] and item["options"]["ondelete"] == "RESTRICT"
        for item in tag_fks
    )
    assert any(item["constrained_columns"] == ["project_id"] for item in tag_fks)
    dimension_fks = inspector.get_foreign_keys(MetricDimensionRecord.__tablename__)
    assert any(
        item["constrained_columns"] == ["metric_id"] and item["options"]["ondelete"] == "RESTRICT"
        for item in dimension_fks
    )


def test_failed_revision_is_audited_and_same_checksum_can_resume_after_partial_ddl():
    engine = isolated_engine()
    calls = 0

    def upgrade(target_engine):
        nonlocal calls
        calls += 1
        if calls == 1:
            AssetRecord.__table__.create(target_engine, checkfirst=True)
            raise RuntimeError("synthetic migration detail")
        AssetRecord.__table__.create(target_engine, checkfirst=True)

    migration = GovernanceMigration("r3-test-0002", "b" * 64, upgrade)
    runner = MigrationRunner(engine, [migration])
    with pytest.raises(MigrationApplyError, match="RuntimeError") as raised:
        runner.apply()
    assert "synthetic migration detail" not in str(raised.value)
    with Session(engine) as session:
        failed = runner.get_revision(session, "r3-test-0002")
        assert failed is not None and failed.status == "failed"
        assert failed.last_error == "RuntimeError"
        assert isinstance(failed.generated_at, datetime)
        assert isinstance(failed.finished_at, datetime)

    result = runner.apply()
    assert result.applied == ("r3-test-0002",)
    with Session(engine) as session:
        completed = runner.get_revision(session, "r3-test-0002")
        assert completed is not None
        assert completed.status == "completed"
        assert completed.attempt_count == 2


def test_revision_checksum_change_fails_closed_without_overwriting_completed_state():
    engine = isolated_engine()
    first = GovernanceMigration(
        "r3-test-0003", "c" * 64, lambda target_engine: AssetRecord.__table__.create(target_engine, checkfirst=True)
    )
    MigrationRunner(engine, [first]).apply()
    changed = GovernanceMigration(
        "r3-test-0003", "d" * 64, lambda _target_engine: pytest.fail("checksum conflict must block before execution")
    )

    with pytest.raises(MigrationChecksumConflict):
        MigrationRunner(engine, [changed]).apply()
    with Session(engine) as session:
        record = MigrationRunner(engine, []).get_revision(session, "r3-test-0003")
        assert record is not None
        assert record.status == "completed"
        assert record.checksum == "c" * 64
