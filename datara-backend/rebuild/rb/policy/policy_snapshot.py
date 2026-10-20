"""R5-B 策略快照服务（G-B6）。

依 P2-3 v3 设计 §3.1：
- evaluate_and_snapshot: 执行策略评估并创建持久 snapshot
- validate_snapshot: 验证 snapshot 仍然有效（版本/digest/过期）

snapshot 绑定 project/object/sourceVersion/DDL digest。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from hashlib import sha256

from rebuild.rb.errors.rb_errors import RbErrorCode
from rebuild.rb.models.rb_models import ObjectRef, PolicyFinding, PolicySnapshot
from rebuild.rb.policy.policy_evaluator import PolicyEvaluator

POLICY_TTL = timedelta(minutes=30)


class PolicySnapshotService:
    """R5-B 策略快照服务。"""

    def __init__(self, evaluator: PolicyEvaluator | None = None):
        self._evaluator = evaluator or PolicyEvaluator()
        self._snapshots: dict[str, PolicySnapshot] = {}

    def evaluate_and_snapshot(
        self,
        *,
        project_id: int,
        datasource_id: int,
        object_ref: ObjectRef,
        source_version: str,
        next_ddl_text: str,
        dialect: str = "mysql",
        current_definition: str | None = None,
        current_definition_digest: str | None = None,
    ) -> PolicySnapshot:
        """执行策略评估并创建持久 snapshot。

        Args:
            project_id: 项目 ID
            datasource_id: 数据源 ID
            object_ref: 完整对象引用
            source_version: 当前定义版本（ETag）
            next_ddl_text: 待提交的 DDL 文本
            dialect: 数据库方言（从 datasource.kind 获取）
            current_definition: 当前定义（可选）
            current_definition_digest: 当前定义的 SHA-256 digest（可选）

        Returns:
            PolicySnapshot 绑定 project/object/sourceVersion/DDL digest
        """
        eval_result = self._evaluator.evaluate(
            dialect=dialect,
            object_kind=object_ref.kind,
            current_definition=current_definition,
            current_definition_digest=current_definition_digest,
            expected_definition=next_ddl_text,
        )
        findings = [
            PolicyFinding(
                level=f.level,
                code=f.code,
                message=f.message,
                impacts=list(f.impacts),
            )
            for f in eval_result.findings
        ]
        snapshot = PolicySnapshot(
            snapshot_id=str(uuid.uuid4()),
            project_id=project_id,
            datasource_id=datasource_id,
            object_ref=object_ref,
            source_version=source_version,
            next_ddl_digest=eval_result.digest,
            policy_version="1.0",
            findings=findings,
            blocked=eval_result.blocked,
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + POLICY_TTL,
        )
        self._snapshots[snapshot.snapshot_id] = snapshot
        return snapshot

    def validate_snapshot(
        self,
        *,
        snapshot_id: str,
        project_id: int,
        datasource_id: int,
        object_ref: ObjectRef,
        source_version: str,
        next_ddl_text: str,
    ) -> PolicySnapshot:
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
            Exception: SOURCE_VERSION_CONFLICT / SNAPSHOT_MISMATCH / SNAPSHOT_EXPIRED
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
