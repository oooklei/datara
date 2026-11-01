"""把四套 ownership/share 旧表的数据回填到统一 ACL 表（P2 步骤）。

设计依据：docs/designs/2026-11-01-identity-resource-governance-design.md §7.3 / §8 P2。
幂等：已存在（resource_kind, resource_id, grantee_type, grantee_id）的行不重复插入。
只在 ACL 表为空或部分为空时运行；已填满则跳过，避免无谓开销。
"""

from __future__ import annotations

import logging

from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from rebuild.common.db import Base

from .models import ResourceAclRecord

logger = logging.getLogger(__name__)


# ---- 旧表名集合（回填前必须存在）----

_OLD_TABLES_REQUIRED = (
    "dbx_connection_ownership",
    "dbx_connection_share",
    "dbx_object_ownership",
    "dbx_object_share",
    "rebuild_orchestration_resource_ownership",
    "rebuild_orchestration_resource_share",
    "rebuild_ssh_node_governance",
    "rebuild_ssh_node_share",
)


def apply_acl_backfill(engine, session_factory) -> dict[str, int]:
    """把四套旧 ownership/share 表回填到 rebuild_resource_acl；幂等。

    返回各 resource_kind 的写入计数（仅本次新插入；已存在的不计）。
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    # 1. ACL 表必须存在（已由 create_all 保证）
    if "rebuild_resource_acl" not in existing_tables:
        raise RuntimeError("rebuild_resource_acl must exist before backfill")

    # 2. 若无任何旧表，直接跳过（全新库）
    old_present = [t for t in _OLD_TABLES_REQUIRED if t in existing_tables]
    if not old_present:
        return {}

    counts: dict[str, int] = {}

    # --- dbx_connection ---
    if "dbx_connection_ownership" in existing_tables:
        counts["dbx_connection"] = _backfill_dbx_connection(session_factory)

    # --- dbx_object ---
    if "dbx_object_ownership" in existing_tables:
        counts["dbx_object"] = _backfill_dbx_object(session_factory)

    # --- orchestration_resource ---
    if "rebuild_orchestration_resource_ownership" in existing_tables:
        counts["orchestration_resource"] = _backfill_orchestration(session_factory)

    # --- ssh_node ---
    if "rebuild_ssh_node_governance" in existing_tables:
        counts["ssh_node"] = _backfill_ssh_node(session_factory)

    total = sum(counts.values())
    if total:
        logger.info("acl_backfill inserted=%d breakdown=%s", total, counts)
    return counts


# ---------------------------------------------------------------------------
# dbx_connection
# ---------------------------------------------------------------------------


def _backfill_dbx_connection(session_factory) -> int:
    """dbx_connection_ownership + dbx_connection_share → rebuild_resource_acl(dbx_connection)。"""
    inserted = 0
    with session_factory() as session:
        # ownership → owner 行
        ownership = session.execute(
            text("SELECT connection_id, project_id, owner_id FROM dbx_connection_ownership")
        ).fetchall()
        for row in ownership:
            cid, pid, oid = row[0], row[1], row[2]
            n = _upsert_acl(
                session,
                resource_kind="dbx_connection",
                resource_id=str(cid),
                project_id=int(pid) if pid is not None else None,
                owner_id=int(oid),
                grantee_type="user",
                grantee_id=str(oid),
                permission="manage",
                granted_by=None,
            )
            inserted += n

        # share → 分享行（permission=view）
        # 先构建 connection_id → (project_id, owner_id) 映射
        conn_meta: dict[str, tuple[int | None, int | None]] = {}
        for row in ownership:
            conn_meta[str(row[0])] = (
                int(row[1]) if row[1] is not None else None,
                int(row[2]) if row[2] is not None else None,
            )

        shares = session.execute(
            text("SELECT connection_id, user_id FROM dbx_connection_share")
        ).fetchall()
        for row in shares:
            cid, uid = str(row[0]), int(row[1])
            pid, oid = conn_meta.get(cid, (None, None))
            n = _upsert_acl(
                session,
                resource_kind="dbx_connection",
                resource_id=cid,
                project_id=pid,
                owner_id=oid,
                grantee_type="user",
                grantee_id=str(uid),
                permission="view",
                granted_by=oid,  # share 发起者默认认 owner
            )
            inserted += n

        session.commit()
    return inserted


# ---------------------------------------------------------------------------
# dbx_object
# ---------------------------------------------------------------------------


def _backfill_dbx_object(session_factory) -> int:
    """dbx_object_ownership + dbx_object_share → rebuild_resource_acl(dbx_object)。

    ACL resource_id = f"{kind}:{object_id}"，因为 dbx_object 以 (kind, object_id) 唯一。
    """
    inserted = 0
    with session_factory() as session:
        ownership = session.execute(
            text("SELECT kind, object_id, project_id, owner_id FROM dbx_object_ownership")
        ).fetchall()
        obj_meta: dict[str, tuple[int | None, int | None]] = {}
        for row in ownership:
            kind, oid, pid, owner_id = str(row[0]), str(row[1]), row[2], row[3]
            resource_id = f"{kind}:{oid}"
            obj_meta[resource_id] = (
                int(pid) if pid is not None else None,
                int(owner_id) if owner_id is not None else None,
            )
            n = _upsert_acl(
                session,
                resource_kind="dbx_object",
                resource_id=resource_id,
                project_id=int(pid) if pid is not None else None,
                owner_id=int(owner_id),
                grantee_type="user",
                grantee_id=str(owner_id),
                permission="manage",
                granted_by=None,
            )
            inserted += n

        shares = session.execute(
            text("SELECT kind, object_id, user_id FROM dbx_object_share")
        ).fetchall()
        for row in shares:
            kind, oid, uid = str(row[0]), str(row[1]), int(row[2])
            resource_id = f"{kind}:{oid}"
            pid, owner_id = obj_meta.get(resource_id, (None, None))
            n = _upsert_acl(
                session,
                resource_kind="dbx_object",
                resource_id=resource_id,
                project_id=pid,
                owner_id=owner_id,
                grantee_type="user",
                grantee_id=str(uid),
                permission="view",
                granted_by=owner_id,
            )
            inserted += n

        session.commit()
    return inserted


# ---------------------------------------------------------------------------
# orchestration_resource
# ---------------------------------------------------------------------------


def _backfill_orchestration(session_factory) -> int:
    """rebuild_orchestration_resource_ownership/share → rebuild_resource_acl(orchestration_resource)。

    ACL resource_id = f"{kind}:{resource_key}"（与 dbx_object 同理）。
    project_id 在 orchestration 域无登记，留空（各路由自行关联）。
    """
    inserted = 0
    with session_factory() as session:
        ownership = session.execute(
            text(
                "SELECT kind, resource_key, owner_id "
                "FROM rebuild_orchestration_resource_ownership"
            )
        ).fetchall()
        key_to_owner: dict[str, int | None] = {}
        for row in ownership:
            kind, resource_key, owner_id = str(row[0]), str(row[1]), row[2]
            resource_id = f"{kind}:{resource_key}"
            key_to_owner[resource_id] = int(owner_id) if owner_id is not None else None
            n = _upsert_acl(
                session,
                resource_kind="orchestration_resource",
                resource_id=resource_id,
                project_id=None,
                owner_id=int(owner_id),
                grantee_type="user",
                grantee_id=str(owner_id),
                permission="manage",
                granted_by=None,
            )
            inserted += n

        shares = session.execute(
            text(
                "SELECT kind, resource_key, user_id "
                "FROM rebuild_orchestration_resource_share"
            )
        ).fetchall()
        for row in shares:
            kind, resource_key, uid = str(row[0]), str(row[1]), int(row[2])
            resource_id = f"{kind}:{resource_key}"
            owner_id = key_to_owner.get(resource_id)
            n = _upsert_acl(
                session,
                resource_kind="orchestration_resource",
                resource_id=resource_id,
                project_id=None,
                owner_id=owner_id,
                grantee_type="user",
                grantee_id=str(uid),
                permission="view",
                granted_by=owner_id,
            )
            inserted += n

        session.commit()
    return inserted


# ---------------------------------------------------------------------------
# ssh_node
# ---------------------------------------------------------------------------


def _backfill_ssh_node(session_factory) -> int:
    """rebuild_ssh_node_governance + rebuild_ssh_node_share → rebuild_resource_acl(ssh_node)。

    node_id 是整数，ACL resource_id 存其字符串化值。
    """
    inserted = 0
    with session_factory() as session:
        governance = session.execute(
            text("SELECT node_id, owner_id FROM rebuild_ssh_node_governance")
        ).fetchall()
        node_to_owner: dict[str, int | None] = {}
        for row in governance:
            node_id, owner_id = int(row[0]), row[1]
            node_to_owner[str(node_id)] = int(owner_id) if owner_id is not None else None
            n = _upsert_acl(
                session,
                resource_kind="ssh_node",
                resource_id=str(node_id),
                project_id=None,
                owner_id=int(owner_id),
                grantee_type="user",
                grantee_id=str(owner_id),
                permission="manage",
                granted_by=None,
            )
            inserted += n

        shares = session.execute(
            text("SELECT node_id, user_id FROM rebuild_ssh_node_share")
        ).fetchall()
        for row in shares:
            node_id, uid = int(row[0]), int(row[1])
            owner_id = node_to_owner.get(str(node_id))
            n = _upsert_acl(
                session,
                resource_kind="ssh_node",
                resource_id=str(node_id),
                project_id=None,
                owner_id=owner_id,
                grantee_type="user",
                grantee_id=str(uid),
                permission="view",
                granted_by=owner_id,
            )
            inserted += n

        session.commit()
    return inserted


# ---------------------------------------------------------------------------
# 通用 upsert（纯 INSERT + 唯一约束冲突则跳过 → 幂等）
# ---------------------------------------------------------------------------


def _upsert_acl(
    session: Session,
    *,
    resource_kind: str,
    resource_id: str,
    project_id: int | None,
    owner_id: int | None,
    grantee_type: str,
    grantee_id: str,
    permission: str,
    granted_by: int | None,
) -> int:
    """幂等插入 ACL 行；已存在则跳过。返回 0 或 1。"""
    existing = session.scalar(
        select(ResourceAclRecord).where(
            ResourceAclRecord.resource_kind == resource_kind,
            ResourceAclRecord.resource_id == resource_id,
            ResourceAclRecord.grantee_type == grantee_type,
            ResourceAclRecord.grantee_id == grantee_id,
        )
    )
    if existing is not None:
        return 0
    session.add(
        ResourceAclRecord(
            resource_kind=resource_kind,
            resource_id=resource_id,
            project_id=project_id,
            owner_id=owner_id,
            grantee_type=grantee_type,
            grantee_id=grantee_id,
            permission=permission,
            granted_by=granted_by,
        )
    )
    session.flush()
    return 1
