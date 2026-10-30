"""Datara ownership metadata for connections whose configuration lives in dbx."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from rebuild.common.db import Base


class DbxConnectionOwnershipRecord(Base):
    __tablename__ = "dbx_connection_ownership"

    connection_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("rebuild_user.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class DbxConnectionShareRecord(Base):
    __tablename__ = "dbx_connection_share"
    __table_args__ = (UniqueConstraint("connection_id", "user_id", name="uq_dbx_connection_share"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("rebuild_user.id"), nullable=False, index=True)


class DbxObjectOwnershipRecord(Base):
    """Datara owner for dbx objects stored in dbx's single-user database."""

    __tablename__ = "dbx_object_ownership"

    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    object_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("rebuild_user.id"), nullable=False, index=True)
    connection_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.current_timestamp())


class DbxObjectShareRecord(Base):
    __tablename__ = "dbx_object_share"
    __table_args__ = (UniqueConstraint("kind", "object_id", "user_id", name="uq_dbx_object_share"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    object_id: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("rebuild_user.id"), nullable=False, index=True)
