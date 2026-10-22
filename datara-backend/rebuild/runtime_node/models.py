"""Persistence model for the rebuild-owned runtime node registry (B6).

All 17 columns are ported verbatim from common/models.py RuntimeNode
(t_runtime_node) so the future F53 registration UI can manage both sides
against one schema shape. B6 is read-only; writes come from the lifespan
seed and the future F53 ticket only.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base


class RuntimeNodeRecord(Base):
    __tablename__ = "rebuild_runtime_node"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16), default="本地")
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Legacy parity: plaintext password or PEM private key stays in one column;
    # it is never echoed by the B6 list endpoint (auth is not in the payload).
    auth: Mapped[str | None] = mapped_column(Text, nullable=True)
    runtime_dir: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tmp_dir: Mapped[str | None] = mapped_column(String(255), nullable=True)
    os: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="offline")
    cpu: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mem: Mapped[str | None] = mapped_column(String(32), nullable=True)
    disk: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tasks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)


RUNTIME_NODE_TABLES = (RuntimeNodeRecord.__table__,)
