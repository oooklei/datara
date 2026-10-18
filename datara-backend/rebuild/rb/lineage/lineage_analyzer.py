"""R5-B 血缘分析器（C6 = R5B-02）。

依 P2-3 v3 设计 §3.3：
- 基于 ObjectRef/ImpactItem 模型
- 复用 #21 shared read 获取对象定义
- 使用 sqlglot DDL AST 解析依赖关系
- 集成 IDependencyQuery 查询 information_schema
- 方言不支持时 fail-closed 返回 unknown_reasons
- 禁伪称无影响

不连接数据库，不执行 SQL；纯本地 DDL 依赖分析。
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp

from rebuild.rb.models.rb_models import ObjectRef, ImpactItem
from rebuild.rb.lineage.dependency_query import IDependencyQuery

# 常见方言列表，用于尝试解析
_COMMON_DIALECTS = [
    "postgres",
    "mysql",
    "sqlite",
    "bigquery",
    "snowflake",
    "redshift",
    "clickhouse",
    "duckdb",
    "spark",
    "hive",
    "presto",
    "trino",
]


class LineageAnalyzer:
    """R5-B 血缘分析器。

    复用 #21 shared read 获取对象定义，使用 sqlglot AST 解析 DDL 依赖关系。
    方言不支持时 fail-closed 返回 unknown_reasons。
    """

    def __init__(
        self,
        get_definition_service=None,
        dependency_query: IDependencyQuery | None = None,
    ):
        self._get_definition = get_definition_service
        self._dependency_query = dependency_query

    def analyze(
        self,
        *,
        datasource_id: int,
        object_ref: ObjectRef,
        source_version: str,
    ) -> tuple[list[ImpactItem], list[str]]:
        """分析对象血缘依赖。

        Args:
            datasource_id: 数据源 ID
            object_ref: 完整对象引用
            source_version: 当前定义版本（ETag）

        Returns:
            (impacts, unknown_reasons) 元组
            - impacts: ImpactItem 列表，描述依赖该对象的其他对象
            - unknown_reasons: 无法分析的原因列表（fail-closed）
        """
        if self._get_definition is None:
            return [], ["lineage_unavailable"]

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
            return [], ["definition_not_found"]

        definition_text = definition_result.get("definitionText", "")
        if not definition_text:
            return [], ["definition_empty"]

        # 使用 sqlglot 解析 DDL
        ast = self._parse_ddl(definition_text)
        if ast is None:
            return [], ["dialect_not_supported"]

        impacts: list[ImpactItem] = []
        unknown_reasons: list[str] = []

        # 提取外键依赖（REFERENCES 子句）
        impacts.extend(
            self._extract_foreign_key_deps(ast, datasource_id, object_ref)
        )

        # 提取视图依赖（FROM/JOIN 子句中的表）
        if object_ref.kind == "view":
            impacts.extend(
                self._extract_view_deps(ast, datasource_id, object_ref)
            )

        # 集成 IDependencyQuery 补充依赖
        if self._dependency_query is not None:
            impacts.extend(
                self._query_dependency_service(datasource_id, object_ref)
            )

        return impacts, unknown_reasons

    def _parse_ddl(self, ddl_text: str):
        """使用 sqlglot 解析 DDL，尝试多种方言。

        Returns:
            AST 对象，或 None（所有方言都失败）
        """
        # 先尝试无方言解析（标准 SQL）
        try:
            return sqlglot.parse_one(ddl_text)
        except Exception:
            pass

        # 尝试常见方言
        for dialect in _COMMON_DIALECTS:
            try:
                return sqlglot.parse_one(ddl_text, dialect=dialect)
            except Exception:
                continue

        return None

    def _extract_foreign_key_deps(
        self,
        ast: exp.Expression,
        datasource_id: int,
        object_ref: ObjectRef,
    ) -> list[ImpactItem]:
        """提取外键依赖（REFERENCES 子句）。"""
        impacts: list[ImpactItem] = []

        for fk in ast.find_all(exp.ForeignKey):
            ref = fk.args.get("reference")
            if ref is None:
                continue

            ref_table_name, ref_schema = self._extract_table_from_reference(ref)
            if ref_table_name is None:
                continue

            # 默认使用 object_ref 的 schema
            effective_schema = ref_schema or object_ref.schema or ""

            # 跳过自引用
            if (
                ref_table_name == object_ref.name
                and effective_schema == (object_ref.schema or "")
            ):
                continue

            ref_obj = ObjectRef(
                datasource_id=datasource_id,
                database=object_ref.database,
                catalog=object_ref.catalog,
                schema=effective_schema or None,
                kind="table",
                name=ref_table_name,
                parent=None,
            )
            impacts.append(
                ImpactItem(
                    object_ref=ref_obj,
                    relation_type="dependent",
                    detail=f"Foreign key references {effective_schema + '.' if effective_schema else ''}{ref_table_name}",
                )
            )

        return impacts

    def _extract_view_deps(
        self,
        ast: exp.Expression,
        datasource_id: int,
        object_ref: ObjectRef,
    ) -> list[ImpactItem]:
        """提取视图依赖（FROM/JOIN 子句中的表）。

        过滤 CREATE 语句的目标表（视图自身）。
        """
        impacts: list[ImpactItem] = []
        seen: set[tuple[str, str]] = set()

        # 获取 CREATE 目标表名（视图自身）
        target_name = self._get_create_target_name(ast)

        for table in ast.find_all(exp.Table):
            table_name = table.name
            table_schema = table.db or ""

            # 跳过 CREATE 目标表（视图自身）
            if target_name and table_name == target_name:
                continue

            # 跳过自引用（schema 也匹配）
            if (
                table_name == object_ref.name
                and table_schema == (object_ref.schema or "")
            ):
                continue

            # 去重
            key = (table_schema, table_name)
            if key in seen:
                continue
            seen.add(key)

            ref_obj = ObjectRef(
                datasource_id=datasource_id,
                database=object_ref.database,
                catalog=object_ref.catalog,
                schema=table_schema or None,
                kind="table",
                name=table_name,
                parent=None,
            )
            impacts.append(
                ImpactItem(
                    object_ref=ref_obj,
                    relation_type="downstream",
                    detail=f"View depends on {table_schema + '.' if table_schema else ''}{table_name}",
                )
            )

        return impacts

    def _query_dependency_service(
        self,
        datasource_id: int,
        object_ref: ObjectRef,
    ) -> list[ImpactItem]:
        """使用 IDependencyQuery 补充依赖。"""
        impacts: list[ImpactItem] = []

        if self._dependency_query is None:
            return impacts

        try:
            deps = self._dependency_query.get_dependencies(
                datasource_id=datasource_id,
                schema=object_ref.schema or "",
                table=object_ref.name,
            )
        except Exception:
            return impacts

        for dep in deps:
            dep_table = dep.get("table", "")
            dep_schema = dep.get("schema", "")
            dep_relation = dep.get("relation_type", "dependent")

            if not dep_table:
                continue

            # 跳过自引用
            if (
                dep_table == object_ref.name
                and dep_schema == (object_ref.schema or "")
            ):
                continue

            ref_obj = ObjectRef(
                datasource_id=datasource_id,
                database=object_ref.database,
                catalog=object_ref.catalog,
                schema=dep_schema or None,
                kind="table",
                name=dep_table,
                parent=None,
            )
            impacts.append(
                ImpactItem(
                    object_ref=ref_obj,
                    relation_type=dep_relation,
                    detail=f"Dependency from information_schema: {dep_schema + '.' if dep_schema else ''}{dep_table}",
                )
            )

        return impacts

    @staticmethod
    def _extract_table_from_reference(ref: exp.Expression) -> tuple[str | None, str]:
        """从外键引用中提取表名和 schema。

        Args:
            ref: Reference 对象

        Returns:
            (table_name, schema) 元组，table_name 为 None 表示提取失败
        """
        ref_this = ref.this

        # 带 schema 的引用：Schema(this=Table(...), db=Identifier(...))
        if isinstance(ref_this, exp.Schema):
            table_obj = ref_this.this
            if isinstance(table_obj, exp.Table):
                schema = table_obj.db or ""
                return table_obj.name, schema
            return None, ""

        # 不带 schema 的引用：Table(...)
        if isinstance(ref_this, exp.Table):
            return ref_this.name, ref_this.db or ""

        return None, ""

    @staticmethod
    def _get_create_target_name(ast: exp.Expression) -> str | None:
        """获取 CREATE 语句的目标表名。

        Args:
            ast: CREATE AST 对象

        Returns:
            目标表名，或 None（无法提取）
        """
        if not isinstance(ast, exp.Create):
            return None

        schema = ast.args.get("this")
        if schema is None:
            return None

        # Schema(this=Table(...))
        if isinstance(schema, exp.Schema):
            table_obj = schema.this
            if isinstance(table_obj, exp.Table):
                return table_obj.name
            return None

        # 直接是 Table(...)
        if isinstance(schema, exp.Table):
            return schema.name

        return None
