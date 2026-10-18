"""R5-B 血缘分析器（G-B4）。

依 P2-3 v3 设计 §3.3：
- 基于 ObjectRef/ImpactItem 模型
- 复用 #21 shared read 获取对象定义
- 分析 DDL 依赖关系，返回 ImpactItem 列表

不连接数据库，不执行 SQL；纯本地 DDL 依赖分析。
"""
from __future__ import annotations

import re

from rebuild.rb.models.rb_models import ObjectRef, ImpactItem


class LineageAnalyzer:
    """R5-B 血缘分析器。

    复用 #21 shared read 获取对象定义，分析 DDL 依赖关系。
    """

    def __init__(self, get_definition_service=None):
        self._get_definition = get_definition_service

    def analyze(
        self,
        *,
        datasource_id: int,
        object_ref: ObjectRef,
        source_version: str,
    ) -> list[ImpactItem]:
        """分析对象血缘依赖。

        Args:
            datasource_id: 数据源 ID
            object_ref: 完整对象引用
            source_version: 当前定义版本（ETag）

        Returns:
            ImpactItem 列表，描述依赖该对象的其他对象
        """
        if self._get_definition is None:
            return []

        # 复用 #21 shared read 获取当前定义
        definition_result = self._get_definition(
            datasource_id=datasource_id,
            object_ref={
                "database": object_ref.database,
                "catalog": object_ref.catalog,
                "schema": object_ref.schema,
                "kind": object_ref.kind,
                "name": object_ref.name,
                "parent": object_ref.parent,
            },
        )
        if definition_result is None:
            return []

        definition_text = definition_result.get("definitionText", "")
        if not definition_text:
            return []

        impacts: list[ImpactItem] = []

        # 分析外键依赖（REFERENCES 子句）
        fk_pattern = re.compile(
            r"REFERENCES\s+(?:(?P<schema>\w+)\.)?(?P<table>\w+)",
            re.IGNORECASE,
        )
        for match in fk_pattern.finditer(definition_text):
            ref_schema = match.group("schema") or object_ref.schema or ""
            ref_table = match.group("table")
            # 跳过自引用
            if ref_table == object_ref.name and ref_schema == (object_ref.schema or ""):
                continue
            ref_obj = ObjectRef(
                datasource_id=datasource_id,
                database=object_ref.database,
                catalog=object_ref.catalog,
                schema=ref_schema,
                kind="table",
                name=ref_table,
                parent=None,
            )
            impacts.append(
                ImpactItem(
                    object_ref=ref_obj,
                    relation_type="dependent",
                    detail=f"Foreign key references {ref_schema + '.' if ref_schema else ''}{ref_table}",
                )
            )

        # 分析视图依赖（FROM/JOIN 子句中的表）
        from_pattern = re.compile(
            r"(?:FROM|JOIN)\s+(?:(?P<schema>\w+)\.)?(?P<table>\w+)",
            re.IGNORECASE,
        )
        for match in from_pattern.finditer(definition_text):
            ref_schema = match.group("schema") or object_ref.schema or ""
            ref_table = match.group("table")
            # 跳过自引用
            if ref_table == object_ref.name and ref_schema == (object_ref.schema or ""):
                continue
            ref_obj = ObjectRef(
                datasource_id=datasource_id,
                database=object_ref.database,
                catalog=object_ref.catalog,
                schema=ref_schema,
                kind="table",
                name=ref_table,
                parent=None,
            )
            impacts.append(
                ImpactItem(
                    object_ref=ref_obj,
                    relation_type="downstream",
                    detail=f"View depends on {ref_schema + '.' if ref_schema else ''}{ref_table}",
                )
            )

        return impacts
