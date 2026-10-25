"""Production datasource adapter used by API-triggered SYNC trial runs."""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from sqlalchemy.orm import Session

from rebuild.datasource.contracts import DataSourceDraft
from rebuild.datasource.repository import ProjectDatasourceRepository
from rebuild.sync.executor import SyncBatchWriteResult, SyncExecutionSpec, SyncLineageEdge


_EXPRESSION_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
    ast.In,
    ast.NotIn,
)


def _safe_expression(expression: str, row: Mapping[str, Any]) -> Any:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("SYNC expression is invalid") from exc
    if any(not isinstance(node, _EXPRESSION_NODES) for node in ast.walk(tree)):
        raise ValueError("SYNC expression contains unsupported operations")
    unknown = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} - set(row)
    if unknown:
        raise ValueError(f"SYNC expression references unknown columns: {', '.join(sorted(unknown))}")
    return eval(compile(tree, "<sync-expression>", "eval"), {"__builtins__": {}}, dict(row))


def _draft(record: Any) -> DataSourceDraft:
    return DataSourceDraft(
        name=record.name,
        kind=record.kind,
        host=record.host,
        port=record.port,
        database=record.database_name,
        username=record.username,
        password=record.password,
    )


def _identifier(value: Any, *, quote: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("SYNC object identifiers must be non-empty strings")
    return f"{quote}{value.replace(quote, quote * 2)}{quote}"


class DatasourceSyncRuntimeAdapter:
    """DB-API adapter backed by the application's bounded datasource pools."""

    def __init__(
        self,
        *,
        source_record: Any,
        target_record: Any,
        connector_factory: Callable[[int, int], Callable[[DataSourceDraft], Any]],
    ) -> None:
        self._source = source_record
        self._target = target_record
        self._connector_factory = connector_factory

    @staticmethod
    def _quote(kind: str) -> str:
        return "`" if kind.lower() == "mysql" else '"'

    @staticmethod
    def _placeholder(kind: str) -> str:
        return "%s"

    def _connect(self, record: Any):
        return self._connector_factory(record.project_id, record.id)(_draft(record))

    def read_rows(self, spec: SyncExecutionSpec, *, batch_size: int) -> Iterable[Mapping[str, Any]]:
        quote = self._quote(self._source.kind)
        table = ".".join(
            _identifier(spec.source[key], quote=quote) for key in ("schema", "object")
        )
        columns = tuple(
            dict.fromkeys(
                str(mapping["source_column"])
                for mapping in spec.mappings
                if mapping.get("source_column") and mapping.get("mapping_status") != "UNMATCHED"
            )
        )
        projection = ", ".join(_identifier(column, quote=quote) for column in columns) or "*"
        connection = self._connect(self._source)
        try:
            cursor = connection.cursor()
            try:
                cursor.execute(f"SELECT {projection} FROM {table}")
                names = [str(item[0]) for item in cursor.description or ()]
                while rows := cursor.fetchmany(batch_size):
                    for row in rows:
                        yield dict(zip(names, row, strict=True))
            finally:
                cursor.close()
        finally:
            connection.close()

    def include_row(self, condition: str, row: Mapping[str, Any]) -> bool:
        return bool(_safe_expression(condition, row))

    def transform_value(self, expression: str, row: Mapping[str, Any]) -> Any:
        return _safe_expression(expression, row)

    def write_batch(
        self, spec: SyncExecutionSpec, rows: Sequence[Mapping[str, Any]]
    ) -> SyncBatchWriteResult:
        if not rows:
            return SyncBatchWriteResult()
        columns = tuple(rows[0])
        if not columns or any(tuple(row) != columns for row in rows):
            raise ValueError("SYNC batch rows must share one non-empty column layout")
        quote = self._quote(self._target.kind)
        table = ".".join(
            _identifier(spec.target[key], quote=quote) for key in ("schema", "object")
        )
        names = ", ".join(_identifier(column, quote=quote) for column in columns)
        placeholders = ", ".join(self._placeholder(self._target.kind) for _ in columns)
        conflict = spec.target_properties.get("primary_key_conflict", {})
        strategy = str(conflict.get("conflict_strategy", "insert"))
        primary_key = tuple(str(value) for value in conflict.get("primary_key", ()))
        prefix = "INSERT IGNORE" if strategy == "ignore" and self._target.kind.lower() == "mysql" else "INSERT"
        suffix = ""
        if strategy == "ignore" and self._target.kind.lower() == "postgresql":
            suffix = " ON CONFLICT DO NOTHING"
        elif strategy in {"update", "upsert"}:
            if not primary_key:
                raise ValueError("SYNC update/upsert requires primary_key")
            mutable = tuple(column for column in columns if column not in primary_key)
            if self._target.kind.lower() == "mysql":
                assignments = ", ".join(
                    f"{_identifier(column, quote=quote)} = VALUES({_identifier(column, quote=quote)})"
                    for column in mutable
                )
                suffix = f" ON DUPLICATE KEY UPDATE {assignments}"
            else:
                keys = ", ".join(_identifier(column, quote=quote) for column in primary_key)
                assignments = ", ".join(
                    f"{_identifier(column, quote=quote)} = EXCLUDED.{_identifier(column, quote=quote)}"
                    for column in mutable
                )
                suffix = f" ON CONFLICT ({keys}) DO UPDATE SET {assignments}"
        sql = f"{prefix} INTO {table} ({names}) VALUES ({placeholders}){suffix}"
        connection = self._connect(self._target)
        try:
            cursor = connection.cursor()
            try:
                cursor.executemany(sql, [tuple(row[column] for column in columns) for row in rows])
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()
        finally:
            connection.close()
        count = len(rows)
        return SyncBatchWriteResult(
            inserted=count if strategy in {"insert", "ignore", "upsert"} else 0,
            updated=count if strategy == "update" else 0,
            success=count,
        )

    def write_statistics(self, context: Mapping[str, Any], metrics: Mapping[str, int]) -> None:
        del context, metrics

    def write_lineage(self, context: Mapping[str, Any], edges: Sequence[SyncLineageEdge]) -> None:
        del context, edges


def build_sync_driver_factory(
    session: Session,
    connector_factory: Callable[[int, int], Callable[[DataSourceDraft], Any]],
) -> Callable[[Mapping[str, Any]], DatasourceSyncRuntimeAdapter]:
    repository = ProjectDatasourceRepository(session)

    def factory(snapshot: Mapping[str, Any]) -> DatasourceSyncRuntimeAdapter:
        project_id = snapshot.get("project_id")
        source = snapshot.get("source")
        target = snapshot.get("target")
        if not isinstance(project_id, int) or not isinstance(source, Mapping) or not isinstance(target, Mapping):
            raise ValueError("SYNC runtime snapshot lacks project/source/target bindings")
        source_record = repository.get(project_id, source.get("datasource_id"))
        target_record = repository.get(project_id, target.get("datasource_id"))
        if source_record is None or target_record is None:
            raise ValueError("SYNC runtime datasource is missing or outside the project")
        return DatasourceSyncRuntimeAdapter(
            source_record=source_record,
            target_record=target_record,
            connector_factory=connector_factory,
        )

    return factory
