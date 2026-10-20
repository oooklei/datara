"""Persistence records for the new-Backend workflow domain (大盘缺口 #2/#12).

Design source (frozen): docs/increments/2026-10-14-datara-platform-rebuild-design.md
§3.1 (项目/工作流领域模型) + §4 (试运行/正式运行).

- workflow_definition owns the editing draft; draft nodes/edges are
  workflow_node / workflow_edge rows with version_id = NULL.
- Publishing copies the current draft into an immutable workflow_version
  snapshot: version row (status PUBLISHED, snapshot_digest = sha256 over the
  canonical node/edge JSON) + version-scoped node/edge copies + one
  workflow_publish_record row. 正式运行必须绑定 workflow_version_id (§4.2),
  so published version rows are frozen after publish (WF_VERSION_IMMUTABLE).
- Version status enum per §3.1: DRAFT / PUBLISHED / RUNNING / DISABLED /
  ARCHIVED. publish() creates PUBLISHED rows; the DRAFT slot is reserved for
  the §4.1 结果转正式版本 path.
- §3.1 layout notes: workflow_variable is owned by the existing variables
  domain (rebuild/variables); workflow_draft_snapshot lands with the trial-run
  domain (§4.1); schedule firing and latest-published-version resolution are
  the scheduler domain's (T33) responsibility — workflow_schedule is modeled
  here only.
- created_at/updated_at are DB-generated (design §9 convention).
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base


class WorkflowDefinitionRecord(Base):
    """workflow_definition — per project workflow with editing draft metadata."""

    __tablename__ = "workflow_definition"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_workflow_definition_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Latest published version number; NULL = never published.
    current_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )


class WorkflowVersionRecord(Base):
    """workflow_version — immutable published snapshot of one definition draft."""

    __tablename__ = "workflow_version"
    __table_args__ = (UniqueConstraint("definition_id", "version", name="uq_workflow_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    definition_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # §3.1: DRAFT | PUBLISHED | RUNNING | DISABLED | ARCHIVED.
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PUBLISHED")
    remark: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # sha256 over the canonical snapshot node/edge JSON (immutability anchor).
    snapshot_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    published_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )


class WorkflowNodeRecord(Base):
    """workflow_node — draft node (version_id NULL) or published snapshot copy."""

    __tablename__ = "workflow_node"
    __table_args__ = (
        UniqueConstraint("definition_id", "version_id", "node_code", name="uq_workflow_node_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    definition_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # NULL = editing draft row; set = immutable copy inside that version snapshot.
    version_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # Stable node code inside the definition (upsert key for the draft).
    node_code: Mapped[str] = mapped_column(String(128), nullable=False)
    # §3.2 first-phase Palette (task types + flow components), validated in the
    # repository against VALID_NODE_TYPES.
    node_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    # Node parameters verbatim (JSON object); DEPENDENCY-group configs live in
    # the dependency domain (dependency_config), not here.
    params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    position_x: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position_y: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )


class WorkflowEdgeRecord(Base):
    """workflow_edge — directed connection between node codes (draft or snapshot copy)."""

    __tablename__ = "workflow_edge"
    __table_args__ = (
        UniqueConstraint("definition_id", "version_id", "from_node", "to_node", name="uq_workflow_edge_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    definition_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    version_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    from_node: Mapped[str] = mapped_column(String(128), nullable=False)
    to_node: Mapped[str] = mapped_column(String(128), nullable=False)
    # Branch label (e.g. conditional branch name); empty for plain edges.
    name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )


class WorkflowScheduleRecord(Base):
    """workflow_schedule — configurable schedule bound to a definition."""

    __tablename__ = "workflow_schedule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    definition_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="默认定时")
    cron_expr: Mapped[str] = mapped_column(String(64), nullable=False)
    start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    worker_group: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fail_retry_times: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fail_retry_interval: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    misfire_policy: Mapped[str] = mapped_column(String(24), nullable=False, default="FIRE_ONCE")
    concurrency_policy: Mapped[str] = mapped_column(String(16), nullable=False, default="ALLOW")
    max_running_instances: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )


class WorkflowPublishRecord(Base):
    """workflow_publish_record — append-only publish event log (one row per publish)."""

    __tablename__ = "workflow_publish_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    definition_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    version_id: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    published_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remark: Mapped[str] = mapped_column(Text, nullable=False, default="")
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )
