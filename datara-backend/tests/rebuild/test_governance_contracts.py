from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.governance.contracts import (
    MigrationStatus,
    authorize_project_access,
    is_sha256_digest,
    migration_replay_decision,
    migration_transition_allowed,
)
from rebuild.governance.models import (
    AssetFieldRecord,
    AssetRecord,
    AssetTagRecord,
    AuditEventRecord,
    GovernanceTagRecord,
    LineageEdgeRecord,
    MigrationBatchRecord,
    MigrationItemRecord,
    QualityRunRecord,
    QualityRuleRecord,
    SemanticMetricRecord,
    StandardDefinitionRecord,
)
from rebuild.identity.contracts import Permission, Role
from rebuild.identity.models import ProjectMemberRecord, UserRecord  # noqa: F401
from rebuild.project.models import ProjectRecord  # noqa: F401


def sqlite_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return engine


def create_project(session):
    project = ProjectRecord(name="governance-test", description="", owner_id=1)
    session.add(project)
    session.flush()
    return project


def test_r3_governance_schema_has_the_authoritative_entity_set():
    expected = {
        "rebuild_governance_asset",
        "rebuild_governance_asset_field",
        "rebuild_governance_tag",
        "rebuild_governance_asset_tag",
        "rebuild_governance_lineage_edge",
        "rebuild_governance_quality_rule",
        "rebuild_governance_quality_run",
        "rebuild_governance_standard",
        "rebuild_governance_semantic_metric",
        "rebuild_governance_migration_batch",
        "rebuild_governance_migration_item",
        "rebuild_governance_audit_event",
    }
    assert expected <= set(Base.metadata.tables)


def test_database_generates_audit_and_runtime_timestamps():
    engine = sqlite_engine()
    with Session(engine) as session:
        project = create_project(session)
        asset = AssetRecord(
            project_id=project.id,
            source_system="mysql-src",
            database_name="ec_retail",
            schema_name="sales",
            asset_name="orders",
            asset_type="table",
        )
        batch = MigrationBatchRecord(
            source_system="legacy-i18",
            idempotency_key="batch-r3-test",
            payload_sha256="a" * 64,
            status=MigrationStatus.PLANNED.value,
            dry_run=True,
            expected_count=1,
        )
        session.add(asset)
        session.flush()
        session.add(batch)
        session.flush()
        run = QualityRunRecord(
            project_id=project.id,
            asset_id=asset.id,
            status="succeeded",
            checked_rows=1,
            success_rows=1,
            failed_rows=0,
            skipped_rows=0,
        )
        item = MigrationItemRecord(
            batch_id=batch.id,
            external_id="legacy-quality-11",
            entity_type="quality_rule",
            source_payload_sha256="d" * 64,
            status="imported",
        )
        audit = AuditEventRecord(
            actor_id=1,
            project_id=project.id,
            action="asset.create",
            resource_type="asset",
            resource_id=str(asset.id),
        )
        session.add_all([item, run, audit])
        session.commit()
        session.refresh(asset)
        session.refresh(batch)
        session.refresh(item)
        session.refresh(run)
        session.refresh(audit)

        assert isinstance(asset.created_at, datetime)
        assert isinstance(asset.updated_at, datetime)
        assert isinstance(batch.created_at, datetime)
        assert isinstance(batch.updated_at, datetime)
        assert isinstance(batch.generated_at, datetime)
        assert isinstance(item.generated_at, datetime)
        assert isinstance(run.generated_at, datetime)
        assert isinstance(audit.generated_at, datetime)


def test_governance_external_identity_and_field_identity_are_unique():
    engine = sqlite_engine()
    with Session(engine) as session:
        project = create_project(session)
        asset = AssetRecord(
            project_id=project.id,
            source_system="mysql-src",
            database_name="ec_retail",
            schema_name="sales",
            asset_name="orders",
            asset_type="table",
        )
        session.add(asset)
        session.flush()
        session.add(
            AssetFieldRecord(
                asset_id=asset.id,
                field_name="order_id",
                ordinal_position=1,
                data_type="bigint",
            )
        )
        session.commit()
        session.add(
            AssetRecord(
                project_id=project.id,
                source_system="mysql-src",
                database_name="ec_retail",
                schema_name="sales",
                asset_name="orders",
                asset_type="table",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(
            AssetFieldRecord(
                asset_id=asset.id,
                field_name="order_id",
                ordinal_position=2,
                data_type="bigint",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_quality_row_counters_are_non_negative_and_reconcile():
    engine = sqlite_engine()
    with Session(engine) as session:
        project = create_project(session)
        asset = AssetRecord(
            project_id=project.id,
            source_system="mysql-src",
            database_name="ec_retail",
            schema_name="sales",
            asset_name="orders",
            asset_type="table",
        )
        session.add(asset)
        session.flush()
        session.add(
            QualityRunRecord(
                project_id=project.id,
                asset_id=asset.id,
                status="succeeded",
                checked_rows=12,
                success_rows=10,
                failed_rows=1,
                skipped_rows=1,
            )
        )
        session.commit()
        session.add(
            QualityRunRecord(
                project_id=project.id,
                asset_id=asset.id,
                status="succeeded",
                checked_rows=12,
                success_rows=11,
                failed_rows=1,
                skipped_rows=1,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_project_access_is_scoped_and_denies_missing_membership():
    assert authorize_project_access(
        actor_id=10,
        owner_id=20,
        global_role=Role.DEV,
        member_role=None,
        permission=Permission.VIEW_ALL,
    ) is False
    assert authorize_project_access(
        actor_id=10,
        owner_id=20,
        global_role=Role.VIEWER,
        member_role=Role.VIEWER,
        permission=Permission.EDIT_DEFINITION,
    ) is False
    assert authorize_project_access(
        actor_id=20,
        owner_id=20,
        global_role=Role.DEV,
        member_role=None,
        permission=Permission.EDIT_DEFINITION,
    ) is True


def test_migration_replay_is_idempotent_but_payload_conflicts_are_not():
    payload = "b" * 64
    assert is_sha256_digest(payload)
    assert not is_sha256_digest("B" * 64)
    assert migration_replay_decision(None, payload) == "new"
    assert migration_replay_decision(payload, payload) == "replay"
    assert migration_replay_decision(payload, "c" * 64) == "conflict"
    assert migration_transition_allowed(MigrationStatus.PLANNED, MigrationStatus.RUNNING)
    assert migration_transition_allowed(MigrationStatus.RUNNING, MigrationStatus.COMPLETED)
    assert migration_transition_allowed(MigrationStatus.RUNNING, MigrationStatus.ROLLED_BACK)
    assert not migration_transition_allowed(MigrationStatus.COMPLETED, MigrationStatus.RUNNING)
    with pytest.raises(ValueError):
        migration_replay_decision(None, "not-a-digest")


def test_audit_and_governance_model_contracts_are_constructible():
    tag = GovernanceTagRecord(namespace="business", tag_key="finance", display_name="Finance")
    link = AssetTagRecord(asset_id=1, tag_id=1)
    edge = LineageEdgeRecord(
        project_id=7,
        external_id="edge-source-1",
        source_asset_id=1,
        target_asset_id=2,
        source_field_name="order_id",
        target_field_name="id",
        lineage_type="transformation",
    )
    rule = QualityRuleRecord(project_id=7, asset_id=1, name="not-null", expression="order_id IS NOT NULL")
    standard = StandardDefinitionRecord(project_id=7, code="ORDER_ID", name="Order identifier", data_type="bigint")
    metric = SemanticMetricRecord(project_id=7, code="ORDER_COUNT", name="Order count", formula="count(order_id)")
    audit = AuditEventRecord(actor_id=10, project_id=7, action="asset.tag", resource_type="asset", resource_id="1")
    assert all((tag, link, edge, rule, standard, metric, audit))
