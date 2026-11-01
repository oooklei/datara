"""Owner and trial permissions for the existing SSH host registry.

P2 双写：claim / share 同时写 rebuild_resource_acl（若表存在）。
"""

import logging

from sqlalchemy import Boolean, ForeignKey, Integer, UniqueConstraint, inspect, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from rebuild.common.db import Base

logger = logging.getLogger(__name__)


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


def _acl_service(session: Session):
    try:
        from rebuild.acl.service import AclService  # noqa: PLC0415
    except Exception:  # pragma: no cover
        return None
    try:
        if "rebuild_resource_acl" not in inspect(session.connection()).get_table_names():
            return None
    except Exception:  # pragma: no cover
        return None
    return AclService(session)


def _policy_decision(session, user_id: int, role: str, resource_kind: str, resource_id: str, required: str) -> bool | None:
    """PolicyService.decide_resource 判定；ACL 表不可用或返回 DENY_ACL_MISSING 时返回 None 让调用方 fallback 旧表。"""
    try:
        from rebuild.acl.policy import PolicyService, Subject  # noqa: PLC0415
        policy = PolicyService(session)
        decision = policy.decide_resource(
            Subject(user_id=user_id, platform_role=role),
            resource_kind=resource_kind,
            resource_id=resource_id,
            required_permission=required,
        )
        if decision.allowed:
            return True
        # ACL 表有记录但级别不够 / 过期 → 明确拒绝
        if decision.reason in {"deny:acl_insufficient", "deny:acl_expired"}:
            return False
        return None  # 让调用方 fallback 旧表
    except Exception:  # noqa: BLE001
        return None


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
        self.session.flush()
        # --- P2 ACL 双写 ---
        acl = _acl_service(self.session)
        if acl is not None:
            try:
                acl.claim_owner(
                    resource_kind="ssh_node",
                    resource_id=str(node_id),
                    owner_id=owner_id,
                )
                self.session.flush()
            except Exception:  # noqa: BLE001
                logger.exception("acl_claim failed for ssh_node %d", node_id)
        return record

    def can_view(self, node_id: int, user_id: int, *, is_admin: bool = False) -> bool:
        if is_admin:
            return True
        policy = _policy_decision(self.session, user_id, "viewer", "ssh_node", str(node_id), "view")
        if policy is not None:
            return policy
        record = self.get(node_id)
        if record is None:
            return False
        if record.owner_id == user_id:
            return True
        return self.session.scalar(select(SshNodeShareRecord.id).where(
            SshNodeShareRecord.node_id == node_id, SshNodeShareRecord.user_id == user_id,
        )) is not None

    def can_manage(self, node_id: int, user_id: int, *, is_admin: bool = False) -> bool:
        if is_admin:
            return True
        policy = _policy_decision(self.session, user_id, "developer", "ssh_node", str(node_id), "manage")
        if policy is not None:
            return policy
        record = self.get(node_id)
        return record is not None and record.owner_id == user_id

    def share(self, node_id: int, user_id: int) -> None:
        if self.session.scalar(select(SshNodeShareRecord.id).where(SshNodeShareRecord.node_id == node_id, SshNodeShareRecord.user_id == user_id)) is None:
            self.session.add(SshNodeShareRecord(node_id=node_id, user_id=user_id))
            self.session.flush()
        # --- P2 ACL 双写 ---
        owner = self.get(node_id)
        acl = _acl_service(self.session)
        if acl is not None:
            try:
                acl.grant(
                    resource_kind="ssh_node",
                    resource_id=str(node_id),
                    grantee_type="user",
                    grantee_id=str(user_id),
                    permission="view",
                    owner_id=owner.owner_id if owner is not None else None,
                    granted_by=owner.owner_id if owner is not None else None,
                )
                self.session.flush()
            except Exception:  # noqa: BLE001
                logger.exception("acl_grant failed for ssh_node %d → user %d", node_id, user_id)
