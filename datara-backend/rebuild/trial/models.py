"""Persistence record for the trial-run domain (大盘缺口 #2/#14).

Design source (frozen): docs/increments/2026-10-14-datara-platform-rebuild-design.md
§4.1 (试运行流程「生成草稿快照」) + §3.1 (草稿快照独立于已发布版本) + §9 (时间戳约定).

- workflow_draft_snapshot is the immutable input to a TRIAL run: it captures the
  editing draft (version_id NULL node/edge rows) at trial-creation time so the
  trial executor never races draft edits.  It is deliberately distinct from
  workflow_version.snapshot_digest (the publish path): the two mechanisms must
  never be mixed (WBS risk #2).
- snapshot_digest is sha256 over the canonical node/edge JSON (same algorithm as
  the publish path), enabling idempotent re-snapshot (same digest → no new row).
- created_at/updated_at are DB-generated per §9; created_by records the triggering
  principal for audit.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base


class WorkflowDraftSnapshotRecord(Base):
    """workflow_draft_snapshot — point-in-time capture of a definition editing draft."""

    __tablename__ = "workflow_draft_snapshot"
    __table_args__ = (
        UniqueConstraint("definition_id", "snapshot_digest", name="uq_wds_definition_digest"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    definition_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # sha256 over the canonical snapshot node/edge JSON (immutability anchor).
    snapshot_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    # Full draft graph payload (nodes + edges JSON); consumed by the trial executor.
    node_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    edge_snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    # §4.1 snapshot lifecycle: ACTIVE (usable for trial) | STALE (superseded by a newer digest).
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )
