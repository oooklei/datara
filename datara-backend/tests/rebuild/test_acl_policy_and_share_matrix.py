"""ACL 策略与分享矩阵测试（P2）。

设计依据：docs/designs/2026-11-01-identity-resource-governance-design.md §7.4.7 / §10。
覆盖：effective_permission 四象限、expires_at 过期回收、grantee_type=project/role 批量授权、
      PolicyService.decide_resource / can_share 行为矩阵。
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from rebuild.acl.models import ACL_TABLES, IdentityAuditRecord, ResourceAclRecord
from rebuild.acl.policy import (
    ALLOW_ACL,
    ALLOW_ADMIN,
    ALLOW_OWNER,
    ALLOW_PROJECT_ROLE,
    DENY_ACL_EXPIRED,
    DENY_ACL_INSUFFICIENT,
    DENY_ACL_MISSING,
    DENY_NOT_MEMBER,
    DENY_PLATFORM_ROLE,
    DENY_PROJECT_NOT_FOUND,
    DENY_PROJECT_ROLE,
    PolicyService,
    Subject,
    reason_text,
)
from rebuild.acl.service import (
    ACL_PERMISSION_RANK,
    AclService,
    AuditWriter,
    role_acl_ceiling,
)
from rebuild.common.db import Base
from rebuild.identity.contracts import Permission, Role, authorize
from rebuild.identity.models import ProjectMemberRecord, UserRecord
from rebuild.project.models import ProjectRecord


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[UserRecord.__table__, ProjectRecord.__table__, ProjectMemberRecord.__table__, *ACL_TABLES],
    )
    factory = sessionmaker(bind=engine)
    with Session(engine) as s:
        # 三用户：admin(1) / developer(2) / viewer(3)；两项目；viewer 只在项目 2
        s.add_all([
            UserRecord(id=1, username="admin", password_hash="x", role="admin"),
            UserRecord(id=2, username="dev", password_hash="x", role="developer"),
            UserRecord(id=3, username="viewer", password_hash="x", role="viewer"),
            UserRecord(id=4, username="operator", password_hash="x", role="operator"),
            ProjectRecord(id=1, name="p1", owner_id=1),
            ProjectRecord(id=2, name="p2", owner_id=2),
            ProjectMemberRecord(project_id=1, user_id=2, role="inherit"),
            ProjectMemberRecord(project_id=2, user_id=2, role="inherit"),
            ProjectMemberRecord(project_id=2, user_id=3, role="inherit"),
            ProjectMemberRecord(project_id=2, user_id=4, role="operator"),
        ])
        s.flush()
        yield s
        s.rollback()
        s.close()


# ---------------------------------------------------------------------------
# 角色权限基础（验证 role_acl_ceiling + 不产生提权路径）
# ---------------------------------------------------------------------------


def test_role_acl_ceiling_no_escalation():
    """平台角色到 ACL 级别的上限映射：任何平台角色都不产生 manage。"""
    assert role_acl_ceiling(Role.ADMIN) == "manage"
    assert role_acl_ceiling(Role.DEVELOPER) == "manage"
    assert role_acl_ceiling(Role.OPERATOR) == "use"
    assert role_acl_ceiling(Role.VIEWER) == "view"
    # 未知角色 → view（fail-closed 下限）
    assert role_acl_ceiling("unknown") == "view"


def test_acl_permission_rank_triangle_inequality():
    assert ACL_PERMISSION_RANK["view"] < ACL_PERMISSION_RANK["use"]
    assert ACL_PERMISSION_RANK["use"] < ACL_PERMISSION_RANK["manage"]


def test_authorize_does_not_allow_viewer_to_manage_user():
    """平台 viewer 不应该拥有任何管理权限。"""
    assert not authorize(Role.VIEWER, Permission.MANAGE_USER)
    assert not authorize(Role.VIEWER, Permission.DATASOURCE_MANAGE)
    assert authorize(Role.ADMIN, Permission.MANAGE_USER)


# ---------------------------------------------------------------------------
# §7.4.7 分享上限 × 角色上限 四象限
# ---------------------------------------------------------------------------


class TestSharePermissionIntersection:
    """effective_permission = min(分享上限, 平台角色上限) 矩阵。"""

    def test_view_share_on_view_role(self, session):
        """view 分享 × viewer 角色 → view（默认情形）。"""
        acl = AclService(session)
        acl.claim_owner(resource_kind="dbx_connection", resource_id="c1", owner_id=1, project_id=1)
        acl.grant(
            resource_kind="dbx_connection", resource_id="c1",
            grantee_type="user", grantee_id="3",  # viewer
            permission="view", granted_by=1, project_id=1, owner_id=1,
        )
        session.flush()
        effective = acl.effective_permission(
            user_id=3, platform_role="viewer",
            resource_kind="dbx_connection", resource_id="c1",
        )
        assert effective == "view"

    def test_view_share_on_manager_role_still_view(self, session):
        """view 分享 × admin(manage) 角色 → view（分享是上限）。"""
        acl = AclService(session)
        acl.claim_owner(resource_kind="dbx_connection", resource_id="c2", owner_id=1, project_id=1)
        acl.grant(
            resource_kind="dbx_connection", resource_id="c2",
            grantee_type="user", grantee_id="1",
            permission="view", granted_by=1, project_id=1, owner_id=1,
        )
        session.flush()
        effective = acl.effective_permission(
            user_id=1, platform_role="admin",
            resource_kind="dbx_connection", resource_id="c2",
        )
        assert effective == "view"

    def test_manage_share_on_view_role_still_view(self, session):
        """manage 分享 × viewer 角色 → view（角色是上限，分享不构成提权）。"""
        acl = AclService(session)
        acl.claim_owner(resource_kind="dbx_connection", resource_id="c3", owner_id=1, project_id=1)
        acl.grant(
            resource_kind="dbx_connection", resource_id="c3",
            grantee_type="user", grantee_id="3",  # viewer
            permission="manage", granted_by=1, project_id=1, owner_id=1,
        )
        session.flush()
        effective = acl.effective_permission(
            user_id=3, platform_role="viewer",
            resource_kind="dbx_connection", resource_id="c3",
        )
        assert effective == "view"

    def test_manage_share_on_developer_role_is_manage(self, session):
        """manage 分享 × developer(manage) 角色 → manage（developer 是平台级 manage holder）。"""
        acl = AclService(session)
        acl.claim_owner(resource_kind="dbx_connection", resource_id="c4", owner_id=1, project_id=1)
        acl.grant(
            resource_kind="dbx_connection", resource_id="c4",
            grantee_type="user", grantee_id="2",  # developer
            permission="manage", granted_by=1, project_id=1, owner_id=1,
        )
        session.flush()
        effective = acl.effective_permission(
            user_id=2, platform_role="developer",
            resource_kind="dbx_connection", resource_id="c4",
        )
        assert effective == "manage"

    def test_manager_share_on_operator_role_is_use(self, session):
        """manage 分享 × operator(use) 角色 → use（角色是上限）。"""
        acl = AclService(session)
        acl.claim_owner(resource_kind="dbx_connection", resource_id="c4b", owner_id=1, project_id=1)
        acl.grant(
            resource_kind="dbx_connection", resource_id="c4b",
            grantee_type="user", grantee_id="4",  # operator
            permission="manage", granted_by=1, project_id=1, owner_id=1,
        )
        session.flush()
        effective = acl.effective_permission(
            user_id=4, platform_role="operator",
            resource_kind="dbx_connection", resource_id="c4b",
        )
        assert effective == "use"

    def test_manage_share_on_admin_role_is_manage(self, session):
        """manage 分享 × admin(manage) 角色 → manage（两边都允许）。"""
        acl = AclService(session)
        acl.claim_owner(resource_kind="dbx_connection", resource_id="c5", owner_id=1, project_id=1)
        acl.grant(
            resource_kind="dbx_connection", resource_id="c5",
            grantee_type="user", grantee_id="1",
            permission="manage", granted_by=1, project_id=1, owner_id=1,
        )
        session.flush()
        effective = acl.effective_permission(
            user_id=1, platform_role="admin",
            resource_kind="dbx_connection", resource_id="c5",
        )
        assert effective == "manage"

    def test_use_share_on_manager_role_is_use(self, session):
        """use 分享 × admin(manage) 角色 → use（中间档）。"""
        acl = AclService(session)
        acl.claim_owner(resource_kind="dbx_connection", resource_id="c6", owner_id=1, project_id=1)
        acl.grant(
            resource_kind="dbx_connection", resource_id="c6",
            grantee_type="user", grantee_id="1",
            permission="use", granted_by=1, project_id=1, owner_id=1,
        )
        session.flush()
        effective = acl.effective_permission(
            user_id=1, platform_role="admin",
            resource_kind="dbx_connection", resource_id="c6",
        )
        assert effective == "use"


# ---------------------------------------------------------------------------
# expires_at 过期回收
# ---------------------------------------------------------------------------


def test_expired_share_yields_none_for_effective(session):
    """expires_at 已过 → effective_permission 返回 None。"""
    acl = AclService(session)
    acl.claim_owner(resource_kind="dbx_connection", resource_id="c7", owner_id=1, project_id=1)
    acl.grant(
        resource_kind="dbx_connection", resource_id="c7",
        grantee_type="user", grantee_id="3",
        permission="view", project_id=1, owner_id=1, granted_by=1,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1),
    )
    session.flush()
    effective = acl.effective_permission(
        user_id=3, platform_role="viewer",
        resource_kind="dbx_connection", resource_id="c7",
    )
    assert effective is None


def test_future_expiry_still_valid(session):
    """expires_at 未来 → 正常生效。"""
    acl = AclService(session)
    acl.claim_owner(resource_kind="dbx_connection", resource_id="c8", owner_id=1, project_id=1)
    acl.grant(
        resource_kind="dbx_connection", resource_id="c8",
        grantee_type="user", grantee_id="3",
        permission="view", project_id=1, owner_id=1, granted_by=1,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
    )
    session.flush()
    effective = acl.effective_permission(
        user_id=3, platform_role="viewer",
        resource_kind="dbx_connection", resource_id="c8",
    )
    assert effective == "view"


# ---------------------------------------------------------------------------
# grantee_type = project / role 批量授权（查询时实时展开）
# ---------------------------------------------------------------------------


class TestGranteeTypeExpansion:
    def test_project_grant_includes_all_members(self, session):
        """grantee_type=project → 该项目所有成员自动继承资格。"""
        acl = AclService(session)
        acl.claim_owner(resource_kind="dbx_connection", resource_id="c9", owner_id=1, project_id=1)
        acl.grant(
            resource_kind="dbx_connection", resource_id="c9",
            grantee_type="project", grantee_id="1",
            permission="view", project_id=1, owner_id=1, granted_by=1,
        )
        session.flush()
        # project 1 里只有 user 2(developer) 是成员
        effective = acl.effective_permission(
            user_id=2, platform_role="developer",
            resource_kind="dbx_connection", resource_id="c9",
            project_ids={1},
        )
        assert effective == "view"

    def test_project_grant_non_member_not_included(self, session):
        acl = AclService(session)
        acl.claim_owner(resource_kind="dbx_connection", resource_id="c10", owner_id=1, project_id=1)
        acl.grant(
            resource_kind="dbx_connection", resource_id="c10",
            grantee_type="project", grantee_id="1",
            permission="manage", project_id=1, owner_id=1, granted_by=1,
        )
        session.flush()
        viewer_not_in_p1 = acl.effective_permission(
            user_id=3, platform_role="viewer",
            resource_kind="dbx_connection", resource_id="c10",
            project_ids={2},  # viewer 只在项目 2
        )
        assert viewer_not_in_p1 is None

    def test_role_grant_matches_all_members_with_same_role(self, session):
        """grantee_type=role → 平台角色 = 该值的所有用户。"""
        acl = AclService(session)
        acl.claim_owner(resource_kind="dbx_connection", resource_id="c11", owner_id=1, project_id=1)
        acl.grant(
            resource_kind="dbx_connection", resource_id="c11",
            grantee_type="role", grantee_id="developer",
            permission="use", project_id=1, owner_id=1, granted_by=1,
        )
        session.flush()
        # user 2 是 developer
        effective_dev = acl.effective_permission(
            user_id=2, platform_role="developer",
            resource_kind="dbx_connection", resource_id="c11",
        )
        assert effective_dev == "use"
        # user 3 是 viewer，角色不匹配 → 收不到
        effective_viewer = acl.effective_permission(
            user_id=3, platform_role="viewer",
            resource_kind="dbx_connection", resource_id="c11",
        )
        assert effective_viewer is None


# ---------------------------------------------------------------------------
# PolicyService.decide_resource 端到端（含 expired + insufficient + allow）
# ---------------------------------------------------------------------------


class TestPolicyServiceResourceDecisions:
    def test_admin_passes_resource_decide_without_acl(self, session):
        """admin 无 ACL 表也应直通（穿透保留，需审计）。"""
        policy = PolicyService(session)
        decision = policy.decide_resource(
            Subject(user_id=1, platform_role="admin"),
            resource_kind="dbx_connection", resource_id="c-any",
            required_permission="manage",
        )
        assert decision.allowed is True
        assert decision.reason == ALLOW_ADMIN

    def test_owner_can_share_privately_owned_resource(self, session):
        """owner 对 ACL 表首行对应资源 can_share = True。"""
        acl = AclService(session)
        acl.claim_owner(resource_kind="dbx_connection", resource_id="c-owner", owner_id=2, project_id=1)
        session.flush()
        policy = PolicyService(session)
        assert policy.can_share(
            Subject(user_id=2, platform_role="developer"),
            resource_kind="dbx_connection", resource_id="c-owner",
        )

    def test_non_owner_non_admin_cannot_share(self, session):
        acl = AclService(session)
        acl.claim_owner(resource_kind="dbx_connection", resource_id="c-owner-2", owner_id=2, project_id=1)
        session.flush()
        policy = PolicyService(session)
        assert not policy.can_share(
            Subject(user_id=3, platform_role="viewer"),
            resource_kind="dbx_connection", resource_id="c-owner-2",
        )

    def test_decide_resource_expired_yields_deny_expired(self, session):
        """有过期分享记录 → DENY_ACL_EXPIRED（不是 DENY_ACL_MISSING）。"""
        acl = AclService(session)
        acl.claim_owner(resource_kind="dbx_connection", resource_id="c-expired", owner_id=1, project_id=1)
        acl.grant(
            resource_kind="dbx_connection", resource_id="c-expired",
            grantee_type="user", grantee_id="3",
            permission="view", project_id=1, owner_id=1, granted_by=1,
            expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1),
        )
        session.flush()
        policy = PolicyService(session)
        decision = policy.decide_resource(
            Subject(user_id=3, platform_role="viewer"),
            resource_kind="dbx_connection", resource_id="c-expired",
            required_permission="view",
        )
        assert decision.allowed is False
        assert decision.reason == DENY_ACL_EXPIRED

    def test_decide_resource_insufficient_permission_yields_deny(self, session):
        """有效权限 view，需要 manage → DENY_ACL_INSUFFICIENT。"""
        acl = AclService(session)
        acl.claim_owner(resource_kind="dbx_connection", resource_id="c-limited", owner_id=1, project_id=1)
        acl.grant(
            resource_kind="dbx_connection", resource_id="c-limited",
            grantee_type="user", grantee_id="3",
            permission="view", project_id=1, owner_id=1, granted_by=1,
        )
        session.flush()
        policy = PolicyService(session)
        decision = policy.decide_resource(
            Subject(user_id=3, platform_role="viewer"),
            resource_kind="dbx_connection", resource_id="c-limited",
            required_permission="manage",
        )
        assert decision.allowed is False
        assert decision.reason == DENY_ACL_INSUFFICIENT

    def test_decide_resource_missing_share_denied(self, session):
        policy = PolicyService(session)
        decision = policy.decide_resource(
            Subject(user_id=3, platform_role="viewer"),
            resource_kind="dbx_connection", resource_id="c-nope",
            required_permission="view",
        )
        assert decision.allowed is False
        assert decision.reason == DENY_ACL_MISSING


# ---------------------------------------------------------------------------
# PolicyService.decide_project（保持原判定顺序）
# ---------------------------------------------------------------------------


class TestPolicyServiceProjectDecisions:
    def test_admin_passes_project_without_acl(self, session):
        policy = PolicyService(session)
        decision = policy.decide_project(
            Subject(user_id=1, platform_role="admin"),
            project_id=1, permission=Permission.DATASOURCE_MANAGE,
        )
        assert decision.allowed and decision.reason == ALLOW_ADMIN

    def test_platform_role_not_permitted_hard_deny(self, session):
        """viewer 平台角色申请 DATASOURCE_MANAGE → DENY_PLATFORM_ROLE。"""
        policy = PolicyService(session)
        decision = policy.decide_project(
            Subject(user_id=3, platform_role="viewer"),
            project_id=2, permission=Permission.DATASOURCE_MANAGE,
        )
        assert decision.allowed is False
        assert decision.reason == DENY_PLATFORM_ROLE

    def test_non_member_denied(self, session):
        """user 1(admin) 外没人在 project 1；user 4 也不在 project 1。"""
        policy = PolicyService(session)
        decision = policy.decide_project(
            Subject(user_id=4, platform_role="operator"),
            project_id=1, permission=Permission.PROJECT_READ,
        )
        assert decision.allowed is False
        assert decision.reason == DENY_NOT_MEMBER

    def test_project_not_found(self, session):
        policy = PolicyService(session)
        decision = policy.decide_project(
            Subject(user_id=1, platform_role="admin"),
            project_id=999, permission=Permission.PROJECT_READ,
        )
        assert decision.allowed is False
        assert decision.reason == DENY_PROJECT_NOT_FOUND


# ---------------------------------------------------------------------------
# AuditWriter 业务审计
# ---------------------------------------------------------------------------


def test_audit_writer_identity_writes_append_only_row(session):
    AuditWriter(session).identity(
        actor_id=1, actor_name="admin", action="user_login",
        target_user_id=2, target_username="dev",
        result="allow", after={"role": "developer"},
        ip="127.0.0.1", user_agent="test",
    )
    session.flush()
    row = session.scalar(select(IdentityAuditRecord).limit(1))
    assert row is not None
    assert row.action == "user_login"
    assert row.result == "allow"
    assert row.after_json == '{"role": "developer"}'


def test_audit_writer_acl_writes_append_only_row(session):
    AuditWriter(session).acl(
        actor_id=1, actor_name="admin",
        object_kind="dbx_connection", object_id="c1",
        action="grant", after={"grantee_id": "3", "permission": "view"},
        result="allow",
        ip="127.0.0.1", user_agent="test",
    )
    session.flush()
    from rebuild.acl.models import AclAuditRecord
    row = session.scalar(select(AclAuditRecord).limit(1))
    assert row is not None
    assert row.action == "grant"
    assert row.after_json is not None


# ---------------------------------------------------------------------------
# AclService 幂等性
# ---------------------------------------------------------------------------


def test_grant_is_idempotent(session):
    """同一 (resource_kind, resource_id, grantee_type, grantee_id) 第二次 grant 应 upsert。"""
    acl = AclService(session)
    acl.claim_owner(resource_kind="dbx_connection", resource_id="c-idem", owner_id=1, project_id=1)
    first = acl.grant(
        resource_kind="dbx_connection", resource_id="c-idem",
        grantee_type="user", grantee_id="3",
        permission="view", granted_by=1, project_id=1, owner_id=1,
    )
    session.flush()
    first_id = first.id
    second = acl.grant(
        resource_kind="dbx_connection", resource_id="c-idem",
        grantee_type="user", grantee_id="3",
        permission="use",  # 升级，应该被覆盖
        granted_by=1, project_id=1, owner_id=1,
    )
    session.flush()
    assert second.id == first_id
    assert second.permission == "use"


def test_revoke_grantee_user_does_not_touch_owner_rows(session):
    """revoke_grantee_user 只删 granted_by IS NOT NULL 的分享行，保留 owner 首行。"""
    acl = AclService(session)
    acl.claim_owner(resource_kind="dbx_connection", resource_id="c-keep-owner", owner_id=2, project_id=1)
    acl.grant(
        resource_kind="dbx_connection", resource_id="c-keep-owner",
        grantee_type="user", grantee_id="3",
        permission="view", granted_by=2, project_id=1, owner_id=2,
    )
    session.flush()
    acl.revoke_grantee_user(3)
    session.flush()
    rows = acl.rows_for_resource("dbx_connection", "c-keep-owner")
    grantees = [r.grantee_id for r in rows]
    assert "3" not in grantees
    assert "2" in grantees  # owner 行保留


# ---------------------------------------------------------------------------
# reason_text 可解释性（§7.1 决策理由返回前端）
# ---------------------------------------------------------------------------


def test_reason_text_is_cn_explainable():
    assert reason_text(DENY_PLATFORM_ROLE)
    assert reason_text(DENY_PROJECT_NOT_FOUND)
    assert reason_text(DENY_NOT_MEMBER)
    assert reason_text(DENY_ACL_EXPIRED)
    assert reason_text(DENY_ACL_INSUFFICIENT)
    assert reason_text(DENY_ACL_MISSING)
    assert reason_text(ALLOW_ADMIN)
    assert reason_text(ALLOW_OWNER)
