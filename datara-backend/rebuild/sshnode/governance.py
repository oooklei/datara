"""Owner and trial permissions for the existing SSH host registry."""

from sqlalchemy import Boolean, ForeignKey, Integer, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from rebuild.common.db import Base


class SshNodeGovernanceRecord(Base):
    __tablename__ = "rebuild_ssh_node_governance"

    node_id: Mapped[int] = mapped_column(ForeignKey("rebuild_ssh_node.id", ondelete="CASCADE"), primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("rebuild_user.id"), nullable=False, index=True)
    allow_trial: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SshNodeShareRecord(Base):
    __tablename__ = "rebuild_ssh_node_share"
    __table_args__ = (UniqueConstraint("node_id", "user_id", name="uq_ssh_node_share"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("rebuild_ssh_node.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("rebuild_user.id"), nullable=False, index=True)


class SshNodeAccess:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, node_id: int) -> SshNodeGovernanceRecord | None:
        return self.session.get(SshNodeGovernanceRecord, node_id)

    def claim(self, node_id: int, owner_id: int, *, allow_trial: bool = False) -> SshNodeGovernanceRecord:
        record = self.get(node_id)
        if record is not None:
            if record.owner_id != owner_id:
                raise PermissionError("node already claimed")
            record.allow_trial = allow_trial
            return record
        record = SshNodeGovernanceRecord(node_id=node_id, owner_id=owner_id, allow_trial=allow_trial)
        self.session.add(record)
        return record

    def can_view(self, node_id: int, user_id: int, *, is_admin: bool = False) -> bool:
        if is_admin:
            return True
        record = self.get(node_id)
        if record is None:
            return False
        if record.owner_id == user_id:
            return True
        return self.session.scalar(select(SshNodeShareRecord.id).where(
            SshNodeShareRecord.node_id == node_id, SshNodeShareRecord.user_id == user_id,
        )) is not None

    def can_manage(self, node_id: int, user_id: int, *, is_admin: bool = False) -> bool:
        record = self.get(node_id)
        return is_admin or (record is not None and record.owner_id == user_id)

    def share(self, node_id: int, user_id: int) -> None:
        if self.session.scalar(select(SshNodeShareRecord.id).where(SshNodeShareRecord.node_id == node_id, SshNodeShareRecord.user_id == user_id)) is None:
            self.session.add(SshNodeShareRecord(node_id=node_id, user_id=user_id))
