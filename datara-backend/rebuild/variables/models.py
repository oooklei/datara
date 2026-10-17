"""Persistence records for the R2 unified variable domain (design §5).

Two tables only:

- ``rebuild_variable_definition``: persisted definitions for scopes that own
  stored values (global/project/tmp). ``workflow``/``task`` values belong to
  workflow/task execution contexts and ``run``/``env``/``builtin`` are system
  or transient layers, so none of those are persisted here.
- ``task_instance_variable_runtime``: per-execution variable snapshot rows
  (design §5: expression, scope, name, resolved value, type, source, resolved
  time, attempt number).

Sensitive values are returned to the client in plaintext by design decision
(declaration §5 Q11: no redaction layer is introduced).
"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base


class VariableDefinitionRecord(Base):
    """Persisted variable definition for a storeable scope."""

    __tablename__ = "rebuild_variable_definition"
    __table_args__ = (
        UniqueConstraint("owner_key", "name", name="uq_variable_owner_name"),
        CheckConstraint("scope IN ('global', 'project', 'tmp')", name="ck_variable_scope"),
        CheckConstraint(
            "(scope = 'global' AND project_id IS NULL) OR "
            "(scope = 'project' AND project_id IS NOT NULL) OR "
            "(scope = 'tmp' AND project_id IS NOT NULL)",
            name="ck_variable_owner_scope",
        ),
        Index("ix_variable_project_name", "project_id", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    # Null means the global scope; project/tmp records always name one project.
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Non-null uniqueness key avoids databases treating NULLs as distinct in UNIQUE constraints.
    owner_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False, default="string")
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp(), server_onupdate=func.current_timestamp()
    )


class TaskInstanceVariableRuntimeRecord(Base):
    """Variable snapshot row produced per task-instance execution attempt."""

    __tablename__ = "task_instance_variable_runtime"
    __table_args__ = (
        UniqueConstraint("instance_id", "attempt_no", "name", name="uq_variable_runtime_instance_attempt_name"),
        Index("ix_variable_runtime_instance_attempt", "instance_id", "attempt_no"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Owning project of the execution attempt (P0-7 security patch: enables
    # project-level authorization on GET /run-snapshot). NULL rows are legacy
    # and unreadable from every project (fail-closed).
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    resolved_value: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False, default="string")
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())
