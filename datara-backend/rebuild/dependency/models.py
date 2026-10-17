"""Persistence records for the R4-DEPENDENCY domain.

Contract source (frozen, A2 v2.1): docs/increments/2026-10-17-R4-DEP-RES-API-contract-pending.md
§2/§3.1/§7 (double-line signoff; see handoff heartbeat #72/#74) + B2 §2.

- One saved object = "workflow version × task" dependency configuration
  (``saveDependency`` semantics). Re-saving the same slot replaces the draft
  configuration; published-version immutability enforcement is deferred until
  the workflow-registry domain lands on main (narrow-scope disclosure).
- The groups snapshot (conditions incl. v2.1 kind/selector/sentinel/depend_result/
  parameter_passing, dual time input) is stored verbatim as JSON: the run-time
  judgment consumes the snapshot saved with the workflow version, not later edits.
- Config-level policy fields (§7.3/§7.9) sit at the dependency-config top level,
  next to groups (DS ``Dependence`` field placement).
- created_at/updated_at are DB-generated (design §9 convention).
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base


class DependencyConfigRecord(Base):
    """dependency_config — per (project, workflow version, task) dependency snapshot."""

    __tablename__ = "dependency_config"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "workflow_id",
            "workflow_version",
            "task_id",
            name="uq_dependency_config_slot",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    workflow_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    workflow_version: Mapped[int] = mapped_column(Integer, nullable=False)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # Full groups snapshot verbatim (list of groups; each group {join, conditions[]}).
    groups_json: Mapped[str] = mapped_column(Text, nullable=False)
    # Between-groups relation (§7.8): AND|OR, default AND (v1 wire back-compat).
    group_relation: Mapped[str] = mapped_column(String(8), nullable=False, default="AND")
    # Config-level policies (§7.3/§7.9), nullable = not configured.
    check_interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_policy: Mapped[str] = mapped_column(String(16), nullable=False, default="fail")
    failure_waiting_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dependent_wait_timeout_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dependent_wait_timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dependent_wait_timeout_strategies_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )
