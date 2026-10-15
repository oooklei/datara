from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
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


class LegacySourceMixin(RuntimeTimestampMixin):
    """Stable source identity and original business timestamps for carried-forward records."""

    source_system: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_table: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    migration_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("rebuild_governance_migration_batch.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    source_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


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


class GovernanceDomainRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_domain"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_gov_domain_project_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("rebuild_project.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class WarehouseLayerRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_warehouse_layer"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_gov_warehouse_layer_code"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("rebuild_project.id"), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    naming_rule: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="#64748b")
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ModelEngineRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_model_engine"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_gov_model_engine_project_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("rebuild_project.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    ddl_dialect: Mapped[str] = mapped_column(String(32), nullable=False)
    vendor_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class WarehouseModelRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_warehouse_model"
    __table_args__ = (
        Index("ix_gov_warehouse_model_project_status", "project_id", "status"),
        UniqueConstraint("project_id", "code", name="uq_gov_warehouse_model_project_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    layer_id: Mapped[int | None] = mapped_column(ForeignKey("rebuild_governance_warehouse_layer.id"), nullable=True)
    model_type: Mapped[str] = mapped_column(String(16), nullable=False, default="明细表")
    domain_id: Mapped[int | None] = mapped_column(ForeignKey("rebuild_governance_domain.id"), nullable=True)
    engine_id: Mapped[int | None] = mapped_column(ForeignKey("rebuild_governance_model_engine.id"), nullable=True)
    legacy_datasource_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    database_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    er_position_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    last_ddl_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    security_level: Mapped[str] = mapped_column(String(16), nullable=False, default="鍐呴儴")
    built_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    built_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    owner_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")


class WarehouseModelFieldRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_warehouse_model_field"
    __table_args__ = (
        UniqueConstraint("model_id", "field_name", name="uq_gov_warehouse_field_name"),
        CheckConstraint("ordinal_position > 0", name="ck_gov_warehouse_field_ordinal"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("rebuild_governance_warehouse_model.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False)
    field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    data_type: Mapped[str] = mapped_column(String(64), nullable=False, default="VARCHAR")
    length: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    precision: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    nullable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    default_value: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    is_primary_key: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_partition_key: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dictionary_reference: Mapped[str] = mapped_column(String(128), nullable=False, default="")


class WarehouseModelRelationRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_warehouse_model_relation"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    source_model_id: Mapped[int] = mapped_column(
        ForeignKey("rebuild_governance_warehouse_model.id", ondelete="RESTRICT"), nullable=False
    )
    target_model_id: Mapped[int] = mapped_column(
        ForeignKey("rebuild_governance_warehouse_model.id", ondelete="RESTRICT"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(8), nullable=False, default="1:N")
    join_description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="")


class WarehouseModelRelationFieldRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_warehouse_model_relation_field"
    __table_args__ = (
        UniqueConstraint("relation_id", "ordinal_position", name="uq_gov_model_relation_field_position"),
        CheckConstraint("ordinal_position > 0", name="ck_gov_model_relation_field_ordinal"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    relation_id: Mapped[int] = mapped_column(
        ForeignKey("rebuild_governance_warehouse_model_relation.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False)
    source_field_name: Mapped[str] = mapped_column(String(128), nullable=False)
    target_field_name: Mapped[str] = mapped_column(String(128), nullable=False)


class WarehouseModelVersionRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_warehouse_model_version"
    __table_args__ = (UniqueConstraint("model_id", "version", name="uq_gov_warehouse_model_version"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    model_id: Mapped[int] = mapped_column(
        ForeignKey("rebuild_governance_warehouse_model.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    change_note: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="")


class AssetMetadataExtensionRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_asset_metadata_extension"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("rebuild_governance_asset.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    legacy_datasource_id: Mapped[int] = mapped_column(Integer, nullable=False)
    database_name: Mapped[str] = mapped_column(String(128), nullable=False)
    table_name: Mapped[str] = mapped_column(String(128), nullable=False)
    business_domain: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    security_level: Mapped[str] = mapped_column(String(16), nullable=False, default="鍐呴儴")
    owner_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    remark: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class LegacyTagDefinitionRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_legacy_tag_definition"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    normalized_tag_id: Mapped[int] = mapped_column(
        ForeignKey("rebuild_governance_tag.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    tag_category: Mapped[str] = mapped_column(String(16), nullable=False, default="鐢ㄩ€?")
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="#1677ff")
    tag_description: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class LegacyTagReferenceRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_legacy_tag_reference"
    __table_args__ = (UniqueConstraint("tag_id", "target_type", "target_key", name="uq_gov_legacy_tag_reference"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("rebuild_governance_tag.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    legacy_tag_definition_id: Mapped[int | None] = mapped_column(
        ForeignKey("rebuild_governance_legacy_tag_definition.id", ondelete="RESTRICT"), nullable=True
    )
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_key: Mapped[str] = mapped_column(String(255), nullable=False)
    resolved_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("rebuild_governance_asset.id", ondelete="RESTRICT"), nullable=True
    )
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="")


class AssetTagUnresolvedRecord(LegacySourceMixin, Base):
    """Keep an unbound legacy tag target available for later identity resolution."""

    __tablename__ = "rebuild_governance_asset_tag_unresolved"
    __table_args__ = (
        UniqueConstraint("source_system", "source_table", "source_id", name="uq_gov_asset_tag_unresolved_source"),
        UniqueConstraint("tag_id", "target_type", "target_key", name="uq_gov_asset_tag_unresolved_target"),
        Index("ix_gov_asset_tag_unresolved_target", "target_type", "target_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("rebuild_governance_tag.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_key: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="")


class SemanticMetricProfileRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_semantic_metric_profile"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    metric_id: Mapped[int] = mapped_column(
        ForeignKey("rebuild_governance_semantic_metric.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    base_metric_id: Mapped[int | None] = mapped_column(
        ForeignKey("rebuild_governance_semantic_metric.id", ondelete="RESTRICT"), nullable=True
    )
    legacy_base_metric_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metric_type: Mapped[str] = mapped_column(String(16), nullable=False, default="原子")
    business_domain: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    business_definition: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    technical_definition: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False, default="table")
    source_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    source_field: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    output_table: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    output_task: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    period: Mapped[str] = mapped_column(String(16), nullable=False, default="日")
    unit: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    aggregation_function: Mapped[str | None] = mapped_column(String(16), nullable=True)
    numerator_field: Mapped[str | None] = mapped_column(String(128), nullable=True)
    time_field: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dimension_field: Mapped[str | None] = mapped_column(String(128), nullable=True)
    filter_condition: Mapped[str | None] = mapped_column(String(255), nullable=True)
    legacy_dimensions: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    legacy_status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    legacy_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    owner_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")


class SemanticMetricDimensionRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_semantic_metric_dimension"
    __table_args__ = (UniqueConstraint("metric_id", "ordinal_position", name="uq_gov_metric_dimension_position"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    metric_id: Mapped[int] = mapped_column(
        ForeignKey("rebuild_governance_semantic_metric.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False)
    dimension_name: Mapped[str] = mapped_column(String(128), nullable=False)


class MetricDimensionRecord(LegacySourceMixin, Base):
    """Queryable I20 dimension attributes while preserving a legacy source key when present."""

    __tablename__ = "rebuild_governance_metric_dimension"
    __table_args__ = (
        UniqueConstraint("source_system", "source_table", "source_id", name="uq_gov_metric_dimension_source"),
        UniqueConstraint("metric_id", "dimension_key", name="uq_gov_metric_dimension_key"),
        CheckConstraint("ordinal_position > 0", name="ck_gov_metric_dimension_ordinal"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    metric_id: Mapped[int] = mapped_column(
        ForeignKey("rebuild_governance_semantic_metric.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False)
    dimension_key: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    source_field: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")


class SemanticMetricVersionRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_semantic_metric_version"
    __table_args__ = (UniqueConstraint("metric_id", "version", name="uq_gov_metric_version"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    metric_id: Mapped[int] = mapped_column(
        ForeignKey("rebuild_governance_semantic_metric.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    change_note: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="")


class QualityTaskRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_quality_task"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(64), nullable=False, default="0 0 * * * *")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="idle")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_result: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    owner_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    remark: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class QualityRuleDefinitionRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_quality_rule_definition"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    quality_rule_id: Mapped[int | None] = mapped_column(
        ForeignKey("rebuild_governance_quality_rule.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    dimension: Mapped[str] = mapped_column(String(32), nullable=False, default="完整性")
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    legacy_datasource_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_database: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    target_table: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    target_column: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="warning")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="enabled")
    owner_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    remark: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class QualityTaskRuleRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_quality_task_rule"
    __table_args__ = (UniqueConstraint("task_id", "ordinal_position", name="uq_gov_quality_task_rule_position"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("rebuild_governance_quality_task.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    rule_definition_id: Mapped[int] = mapped_column(
        ForeignKey("rebuild_governance_quality_rule_definition.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False)


class QualityRunLegacyDetailsRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_quality_run_legacy_details"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    quality_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("rebuild_governance_quality_run.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    legacy_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trigger_source: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    legacy_result: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    stats_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class QualityExceptionRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_quality_exception"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    run_details_id: Mapped[int | None] = mapped_column(
        ForeignKey("rebuild_governance_quality_run_legacy_details.id", ondelete="RESTRICT"), nullable=True
    )
    rule_definition_id: Mapped[int | None] = mapped_column(
        ForeignKey("rebuild_governance_quality_rule_definition.id", ondelete="RESTRICT"), nullable=True
    )
    legacy_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    sample_sql: Mapped[str] = mapped_column(Text, nullable=False, default="")
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    fix_note: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    handled_by: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class QualityReportRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_quality_report"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    period: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    content_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="")


class QualityAlarmPolicyRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_quality_alarm_policy"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    metric: Mapped[str] = mapped_column(String(32), nullable=False, default="score")
    operator: Mapped[str] = mapped_column(String(4), nullable=False, default="<")
    threshold: Mapped[float] = mapped_column(Float, nullable=False, default=90)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class StandardElementRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_standard_element"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_gov_standard_element_project_code"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    chinese_name: Mapped[str] = mapped_column(String(128), nullable=False)
    english_name: Mapped[str] = mapped_column(String(128), nullable=False)
    data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    owner_name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    remark: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class StandardCodeSetRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_standard_code_set"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_gov_standard_codeset_project_code"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    remark: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class StandardCodeValueRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_standard_code_value"
    __table_args__ = (UniqueConstraint("code_set_id", "code_value", name="uq_gov_standard_code_value"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code_set_id: Mapped[int] = mapped_column(
        ForeignKey("rebuild_governance_standard_code_set.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    code_value: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remark: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class StandardNamingRuleRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_standard_naming_rule"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(16), nullable=False)
    pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, default="field")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class StandardMappingRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_standard_mapping"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    element_id: Mapped[int | None] = mapped_column(
        ForeignKey("rebuild_governance_standard_element.id", ondelete="RESTRICT"), nullable=True
    )
    code_set_id: Mapped[int | None] = mapped_column(
        ForeignKey("rebuild_governance_standard_code_set.id", ondelete="RESTRICT"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    difference: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class StandardApprovalRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_standard_approval"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    standard_id: Mapped[int | None] = mapped_column(
        ForeignKey("rebuild_governance_standard.id", ondelete="RESTRICT"), nullable=True
    )
    business_type: Mapped[str] = mapped_column(String(16), nullable=False)
    legacy_business_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="review")
    opinion: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class StandardCheckReportRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_standard_check_report"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("rebuild_project.id"), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    issues_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="done")


class LegacyIdentityMappingRecord(LegacySourceMixin, Base):
    __tablename__ = "rebuild_governance_legacy_identity_mapping"
    __table_args__ = (UniqueConstraint("source_username", name="uq_gov_legacy_identity_username"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("rebuild_user.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_username: Mapped[str] = mapped_column(String(64), nullable=False)
    source_role: Mapped[str] = mapped_column(String(32), nullable=False)
    mapped_role: Mapped[str] = mapped_column(String(32), nullable=False)
    mapping_status: Mapped[str] = mapped_column(String(16), nullable=False, default="mapped")


LEGACY_CARRY_FORWARD_TABLES = (
    GovernanceDomainRecord.__table__,
    WarehouseLayerRecord.__table__,
    ModelEngineRecord.__table__,
    WarehouseModelRecord.__table__,
    WarehouseModelFieldRecord.__table__,
    WarehouseModelRelationRecord.__table__,
    WarehouseModelRelationFieldRecord.__table__,
    WarehouseModelVersionRecord.__table__,
    AssetMetadataExtensionRecord.__table__,
    LegacyTagDefinitionRecord.__table__,
    LegacyTagReferenceRecord.__table__,
    SemanticMetricProfileRecord.__table__,
    SemanticMetricDimensionRecord.__table__,
    SemanticMetricVersionRecord.__table__,
    QualityTaskRecord.__table__,
    QualityTaskRuleRecord.__table__,
    QualityRuleDefinitionRecord.__table__,
    QualityRunLegacyDetailsRecord.__table__,
    QualityExceptionRecord.__table__,
    QualityReportRecord.__table__,
    QualityAlarmPolicyRecord.__table__,
    StandardElementRecord.__table__,
    StandardCodeSetRecord.__table__,
    StandardCodeValueRecord.__table__,
    StandardNamingRuleRecord.__table__,
    StandardMappingRecord.__table__,
    StandardApprovalRecord.__table__,
    StandardCheckReportRecord.__table__,
    LegacyIdentityMappingRecord.__table__,
)

GOVERNANCE_I19_I20_TABLES = (
    AssetTagUnresolvedRecord.__table__,
    MetricDimensionRecord.__table__,
)

for _carry_forward_table in LEGACY_CARRY_FORWARD_TABLES:
    Index(
        f"uq_gov_carry_{_carry_forward_table.name.removeprefix('rebuild_governance_')}_source",
        _carry_forward_table.c.source_system,
        _carry_forward_table.c.source_table,
        _carry_forward_table.c.source_id,
        unique=True,
    )


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
