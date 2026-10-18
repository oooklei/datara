"""R5-B 依赖查询接口（C6 = R5B-02）。

依 P2-3 v3 设计 §3.3：
- IDependencyQuery: information_schema 依赖查询接口
- MockDependencyQuery: 测试用 Mock 实现

接口用于查询 information_schema 获取对象依赖关系，
补充 sqlglot AST 解析无法覆盖的动态依赖。
"""
from __future__ import annotations

from typing import Protocol


class IDependencyQuery(Protocol):
    """information_schema 依赖查询接口。

    用于查询数据库 information_schema 获取对象依赖关系。
    实现类应连接真实数据库或提供 Mock 数据。
    """

    def get_dependencies(
        self,
        *,
        datasource_id: int,
        schema: str,
        table: str,
    ) -> list[dict]:
        """查询指定表的依赖关系。

        Args:
            datasource_id: 数据源 ID
            schema: schema 名
            table: 表名

        Returns:
            依赖列表，每项包含 schema/table/relation_type 等字段
        """
        ...


class MockDependencyQuery:
    """IDependencyQuery 的 Mock 实现（测试用）。"""

    def __init__(self, dependencies: list[dict] | None = None):
        self._dependencies = dependencies or []

    def get_dependencies(
        self,
        *,
        datasource_id: int,
        schema: str,
        table: str,
    ) -> list[dict]:
        return list(self._dependencies)
