"""R5-B DDL 专用执行记录服务（G-B5）。

依 P2-3 v3 设计 §3.4：
- ExecutionLedger 薄封装委托给 ExecutionLedgerRepository
- record_execution: 记录 DDL 执行结果（append-only）
- record_compensation: 记录补偿动作
- list_records: 分页查询执行记录

append-only 语义：ExecutionRecord 一旦写入不可修改。
"""
from __future__ import annotations

from rebuild.rb.ledger.ledger_repository import ExecutionLedgerRepository
from rebuild.rb.models.rb_models import ExecutionRecord, ObjectRef


class ExecutionLedger:
    """R5-B DDL 专用执行记录服务。

    薄封装委托给 ExecutionLedgerRepository。
    """

    def __init__(self, repository: ExecutionLedgerRepository):
        self._repository = repository

    def record_execution(self, record: ExecutionRecord) -> str:
        """记录 DDL 执行结果。append-only。

        Args:
            record: 执行记录

        Returns:
            记录 ID
        """
        return self._repository.record_execution(record)

    def record_compensation(self, original_record_id: str, compensation_record: ExecutionRecord) -> str:
        """记录补偿动作。关联原始 record。

        Args:
            original_record_id: 原始执行记录 ID
            compensation_record: 补偿执行记录

        Returns:
            补偿记录 ID
        """
        return self._repository.record_compensation(original_record_id, compensation_record)

    def list_records(
        self,
        project_id: int,
        datasource_id: int,
        object_ref: ObjectRef | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> list:
        """分页查询执行记录。只读。

        Args:
            project_id: 项目 ID
            datasource_id: 数据源 ID
            object_ref: 对象引用过滤（可选）
            page: 页码（从 1 开始）
            page_size: 每页条数

        Returns:
            RbExecutionRecordRecord 列表
        """
        return self._repository.list_records(
            project_id=project_id,
            datasource_id=datasource_id,
            object_ref=object_ref,
            page=page,
            page_size=page_size,
        )
