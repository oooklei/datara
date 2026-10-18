"""R5-B 策略评估器（G-B6）。

包装 ddl_policy.py 的纯函数 evaluate_ddl_policy，
返回包含 findings + digest 的可持久化结果。
不连接数据库，不执行 SQL。
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from rebuild.sql_ide.ddl_policy import evaluate_ddl_policy


@dataclass(frozen=True)
class PolicyEvaluationResult:
    """策略评估结果。"""
    findings: list
    blocked: bool
    digest: str


class PolicyEvaluator:
    """R5-B 策略评估器。

    包装 ddl_policy.py 的纯函数，返回可持久化的评估结果。
    """

    def evaluate(
        self,
        *,
        dialect: str,
        object_kind: str,
        current_definition: str | None,
        current_definition_digest: str | None,
        expected_definition: str,
    ) -> PolicyEvaluationResult:
        """执行策略评估。

        Args:
            dialect: SQL 方言（mysql/postgresql/sqlite）
            object_kind: 对象类型（table/view/function/procedure/trigger）
            current_definition: 当前定义（可选）
            current_definition_digest: 当前定义的 SHA-256 digest（可选，但缺失会导致 block）
            expected_definition: 待提交的 DDL 文本

        Returns:
            PolicyEvaluationResult 包含 findings、blocked 状态和 DDL digest
        """
        result = evaluate_ddl_policy(
            dialect=dialect,
            object_kind=object_kind,
            current_definition=current_definition,
            current_definition_digest=current_definition_digest,
            expected_definition=expected_definition,
        )
        digest = sha256(expected_definition.encode("utf-8")).hexdigest()
        return PolicyEvaluationResult(
            findings=list(result.findings),
            blocked=result.blocked,
            digest=digest,
        )
