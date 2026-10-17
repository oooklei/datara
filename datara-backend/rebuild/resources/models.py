"""Persistence records for the R4-RESOURCE domain.

Contract source (frozen, A2 v2.1): docs/increments/2026-10-17-R4-DEP-RES-API-contract-pending.md
§2/§4 + B2 §3 + FE resourceApi.ts.

- Resource = named upload with a monotonic, immutable version chain
  (version 1, 2, ...; uploaded content never rewritten).
- Version content is stored on disk (REBUILD_RESOURCE_STORAGE_DIR, default
  ./resource_storage — gitignored) keyed by resource id + version; the DB row
  keeps size/digest(sha256 lowercase hex)/storage path for verification.
- Binding = explicit (workflow version × task) → concrete resource version slot;
  re-binding the same slot with the same payload is idempotent, a different
  payload is RES_BINDING_CONFLICT (409). Published-version rejection is
  deferred until the workflow-registry domain lands (narrow-scope disclosure).
- created_at/updated_at are DB-generated (design §9 convention).
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base


class ResourceRecord(Base):
    """resources — per project named resource with kind and latest version."""

    __tablename__ = "resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # Size of the latest uploaded version (FE ResourceMeta.sizeBytes semantics).
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )


class ResourceVersionRecord(Base):
    """resource_version — immutable uploaded version (content on disk)."""

    __tablename__ = "resource_version"
    __table_args__ = (UniqueConstraint("resource_id", "version", name="uq_resource_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resource_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # sha256 lowercase hex digest of the stored content.
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(256), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )


class ResourceBindingRecord(Base):
    """resource_binding — explicit workflow-version×task → resource-version slot."""

    __tablename__ = "resource_binding"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "workflow_id",
            "workflow_version",
            "task_id",
            name="uq_resource_binding_slot",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    workflow_id: Mapped[int] = mapped_column(Integer, nullable=False)
    workflow_version: Mapped[int] = mapped_column(Integer, nullable=False)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    resource_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )
