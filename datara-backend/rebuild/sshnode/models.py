"""Persistence model for the rebuild-owned SSH node registry."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base


class SshNodeRecord(Base):
    __tablename__ = "rebuild_ssh_node"
    __table_args__ = (Index("ix_rebuild_ssh_node_state", "enabled", "heartbeat_state"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
    ssh_user: Mapped[str] = mapped_column(String(128), nullable=False, default="root")
    # R-34 migration compatibility: plaintext password or PEM private key is
    # intentionally retained. Returning it is a frozen security debt until the
    # separate masking/encryption ticket replaces the legacy contract.
    cred: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    heartbeat_state: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        server_onupdate=func.current_timestamp(),
    )


SSH_NODE_TABLES = (SshNodeRecord.__table__,)
