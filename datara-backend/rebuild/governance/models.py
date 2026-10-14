from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base


class GovernanceTimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


class RuntimeTimestampMixin(GovernanceTimestampMixin):
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())


class AssetRecord(GovernanceTimestampMixin, Base):
    __tablename__ = "rebuild_governance_asset"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "source_system", "database_name", "schema_name", "asset_name", name="uq_gov_asset_identity"
        ),
        Index("ix_gov_asset_project_type", "project_id", "asset_type"),
        CheckConstraint("row_count IS NULL OR row_count >= 0", name="ck_gov_asset_row_count"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    database_name: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    asset_name: Mapped[str] = mapped_column(String(256), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    domain_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    properties_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_collected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AssetFieldRecord(GovernanceTimestampMixin, Base):
    __tablename__ = "rebuild_governance_asset_field"
    __table_args__ = (
        UniqueConstraint("asset_id", "field_name", name="uq_gov_asset_field_name"),
        CheckConstraint("ordinal_position > 0", name="ck_gov_asset_field_ordinal"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("rebuild_governance_asset.id", ondelete="CASCADE"), nullable=False)
    field_name: Mapped[str] = mapped_column(String(256), nullable=False)
    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False)
    data_type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    nullable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")


class GovernanceTagRecord(GovernanceTimestampMixin, Base):
    __tablename__ = "rebuild_governance_tag"
    __table_args__ = (UniqueConstraint("project_id", "namespace", "tag_key", name="uq_gov_tag_identity"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    namespace: Mapped[str] = mapped_column(String(64), nullable=False, default="business")
    tag_key: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")


class AssetTagRecord(GovernanceTimestampMixin, Base):
    __tablename__ = "rebuild_governance_asset_tag"
    __table_args__ = (UniqueConstraint("asset_id", "tag_id", name="uq_gov_asset_tag"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("rebuild_governance_asset.id", ondelete="CASCADE"), nullable=False)
    tag_id: Mapped[int] = mapped_column(ForeignKey("rebuild_governance_tag.id", ondelete="CASCADE"), nullable=False)


class LineageEdgeRecord(GovernanceTimestampMixin, Base):
    __tablename__ = "rebuild_governance_lineage_edge"
    __table_args__ = (UniqueConstraint("project_id", "external_id", name="uq_gov_lineage_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(256), nullable=False)
    source_asset_id: Mapped[int] = mapped_column(ForeignKey("rebuild_governance_asset.id"), nullable=False)
    target_asset_id: Mapped[int] = mapped_column(ForeignKey("rebuild_governance_asset.id"), nullable=False)
    source_field_name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    target_field_name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    lineage_type: Mapped[str] = mapped_column(String(32), nullable=False)
    process_ref: Mapped[str] = mapped_column(String(256), nullable=False, default="")


class QualityRuleRecord(GovernanceTimestampMixin, Base):
    __tablename__ = "rebuild_governance_quality_rule"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_gov_quality_rule_name"),
        CheckConstraint("severity IN ('info', 'warning', 'error')", name="ck_gov_quality_rule_severity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("rebuild_governance_asset.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="warning")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class QualityRunRecord(RuntimeTimestampMixin, Base):
    __tablename__ = "rebuild_governance_quality_run"
    __table_args__ = (
        CheckConstraint(
            "checked_rows >= 0 AND success_rows >= 0 AND failed_rows >= 0 AND skipped_rows >= 0",
            name="ck_gov_quality_rows_nonnegative",
        ),
        CheckConstraint(
            "checked_rows = success_rows + failed_rows + skipped_rows", name="ck_gov_quality_rows_reconcile"
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')", name="ck_gov_quality_run_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("rebuild_governance_asset.id"), nullable=False, index=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("rebuild_governance_quality_rule.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    checked_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class StandardDefinitionRecord(GovernanceTimestampMixin, Base):
    __tablename__ = "rebuild_governance_standard"
    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_gov_standard_code"),
        CheckConstraint("status IN ('draft', 'active', 'retired')", name="ck_gov_standard_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    data_type: Mapped[str] = mapped_column(String(128), nullable=False)
    expression: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")


class SemanticMetricRecord(GovernanceTimestampMixin, Base):
    __tablename__ = "rebuild_governance_semantic_metric"
    __table_args__ = (
        UniqueConstraint("project_id", "code", name="uq_gov_semantic_metric_code"),
        CheckConstraint("status IN ('draft', 'active', 'retired')", name="ck_gov_semantic_metric_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    formula: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")


class MigrationBatchRecord(RuntimeTimestampMixin, Base):
    __tablename__ = "rebuild_governance_migration_batch"
    __table_args__ = (
        UniqueConstraint("source_system", "idempotency_key", name="uq_gov_migration_idempotency"),
        CheckConstraint(
            "expected_count >= 0 AND imported_count >= 0 AND skipped_count >= 0 AND error_count >= 0",
            name="ck_gov_migration_counts_nonnegative",
        ),
        CheckConstraint(
            "imported_count + skipped_count + error_count <= expected_count",
            name="ck_gov_migration_counts_within_expected",
        ),
        CheckConstraint("length(payload_sha256) = 64", name="ck_gov_migration_sha256_length"),
        CheckConstraint(
            "status IN ('planned', 'running', 'completed', 'failed', 'rolled_back')",
            name="ck_gov_migration_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")


class MigrationItemRecord(RuntimeTimestampMixin, Base):
    __tablename__ = "rebuild_governance_migration_item"
    __table_args__ = (
        UniqueConstraint("batch_id", "external_id", name="uq_gov_migration_item_external_id"),
        CheckConstraint(
            "status IN ('pending', 'imported', 'skipped', 'conflict', 'failed', 'rolled_back')",
            name="ck_gov_migration_item_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(
        ForeignKey("rebuild_governance_migration_batch.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(256), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    target_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    target_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")


class AuditEventRecord(RuntimeTimestampMixin, Base):
    __tablename__ = "rebuild_governance_audit_event"
    __table_args__ = (Index("ix_gov_audit_project_generated", "project_id", "generated_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor_id: Mapped[int] = mapped_column(nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("rebuild_project.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    before_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    after_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class SchemaMigrationRecord(RuntimeTimestampMixin, Base):
    __tablename__ = "rebuild_schema_migration"
    __table_args__ = (
        UniqueConstraint("revision", name="uq_rebuild_schema_migration_revision"),
        CheckConstraint("status IN ('running', 'completed', 'failed')", name="ck_rebuild_schema_migration_status"),
        CheckConstraint("attempt_count > 0", name="ck_rebuild_schema_migration_attempts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    revision: Mapped[str] = mapped_column(String(128), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str] = mapped_column(String(128), nullable=False, default="")


GOVERNANCE_TABLES = (
    AssetRecord.__table__,
    AssetFieldRecord.__table__,
    GovernanceTagRecord.__table__,
    AssetTagRecord.__table__,
    LineageEdgeRecord.__table__,
    QualityRuleRecord.__table__,
    QualityRunRecord.__table__,
    StandardDefinitionRecord.__table__,
    SemanticMetricRecord.__table__,
    MigrationBatchRecord.__table__,
    MigrationItemRecord.__table__,
    AuditEventRecord.__table__,
)
