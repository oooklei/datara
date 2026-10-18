"""R5-B 影响面快照服务（G-B7）。

依 P2-3 v3 设计 §3.2：
- preview_and_snapshot: 执行影响面分析并创建持久 snapshot
- get_snapshot: 读取已有 snapshot
- validate_snapshot: 验证 snapshot 仍然有效（版本/digest/过期）

snapshot 绑定 project/object/sourceVersion/DDL digest，
并可关联同一 policy_snapshot_id。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from hashlib import sha256

from rebuild.rb.errors.rb_errors import RbErrorCode
from rebuild.rb.models.rb_models import ObjectRef, ImpactItem, ImpactSnapshot

IMPACT_TTL = timedelta(minutes=30)


class ImpactSnapshotService:
    """R5-B 影响面快照服务。"""

    def __init__(self, analyzer=None):
        self._analyzer = analyzer
        self._snapshots: dict[str, ImpactSnapshot] = {}

    def preview_and_snapshot(
        self,
        *,
        project_id: int,
        datasource_id: int,
        object_ref: ObjectRef,
        source_version: str,
        next_ddl_text: str,
        policy_snapshot_id: str | None = None,
    ) -> ImpactSnapshot:
        """执行影响面分析并创建持久 snapshot。

        Args:
            project_id: 项目 ID
            datasource_id: 数据源 ID
            object_ref: 完整对象引用
            source_version: 当前定义版本（ETag）
            next_ddl_text: 待提交的 DDL 文本
            policy_snapshot_id: 关联的策略快照 ID（可选）

        Returns:
            ImpactSnapshot 绑定 project/object/sourceVersion/DDL digest
        """
        if self._analyzer is not None:
            impacts = self._analyzer.analyze(
                datasource_id=datasource_id,
                object_ref=object_ref,
                source_version=source_version,
            )
            impact_items = [
                ImpactItem(
                    object_ref=imp.object_ref,
                    relation_type=imp.relation_type,
                    detail=imp.detail,
                )
                for imp in impacts
            ]
            unknown_reasons: list[str] = []
        else:
            # 无 analyzer 时返回空 impacts + unknown reason
            impact_items = []
            unknown_reasons = ["lineage_unavailable"]

        digest = sha256(next_ddl_text.encode("utf-8")).hexdigest()
        snapshot = ImpactSnapshot(
            snapshot_id=str(uuid.uuid4()),
            project_id=project_id,
            datasource_id=datasource_id,
            object_ref=object_ref,
            source_version=source_version,
            next_ddl_digest=digest,
            policy_snapshot_id=policy_snapshot_id or "",
            impacts=impact_items,
            unknown_reasons=unknown_reasons,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + IMPACT_TTL,
        )
        self._snapshots[snapshot.snapshot_id] = snapshot
        return snapshot

    def get_snapshot(self, snapshot_id: str) -> ImpactSnapshot | None:
        """读取已有 snapshot。

        Args:
            snapshot_id: 快照 ID

        Returns:
            ImpactSnapshot 或 None（未找到）
        """
        return self._snapshots.get(snapshot_id)

    def validate_snapshot(
        self,
        *,
        snapshot_id: str,
        project_id: int,
        datasource_id: int,
        object_ref: ObjectRef,
        source_version: str,
        next_ddl_text: str,
    ) -> ImpactSnapshot:
        """验证 snapshot 仍然有效。

        Args:
            snapshot_id: 快照 ID
            project_id: 项目 ID
            datasource_id: 数据源 ID
            object_ref: 完整对象引用
            source_version: 当前定义版本
            next_ddl_text: 待提交的 DDL 文本

        Returns:
            原 snapshot 供 audit 重读

        Raises:
            ValueError: SOURCE_VERSION_CONFLICT / SNAPSHOT_MISMATCH / SNAPSHOT_EXPIRED
        """
        snapshot = self._snapshots.get(snapshot_id)
        if snapshot is None:
            raise ValueError(f"Snapshot not found: {snapshot_id}")

        # 检查过期
        if datetime.now(timezone.utc) > snapshot.expires_at:
            raise ValueError(RbErrorCode.SNAPSHOT_EXPIRED)

        # 检查版本漂移
        if snapshot.source_version != source_version:
            raise ValueError(RbErrorCode.SOURCE_VERSION_CONFLICT)

        # 检查 DDL 变更
        digest = sha256(next_ddl_text.encode("utf-8")).hexdigest()
        if snapshot.next_ddl_digest != digest:
            raise ValueError(RbErrorCode.SNAPSHOT_MISMATCH)

        return snapshot
