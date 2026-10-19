"""SYNC execution orchestration and the runtime adapter boundary.

This module is intentionally owned by the SYNC domain. The shared execution
integration supplies a driver-backed adapter and invokes ``execute_sync``;
this module never opens datasource connections or imports worker internals.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from rebuild.sync.repository import validate_mappings, validate_target_properties, validate_transform_config


@dataclass(frozen=True)
class SyncExecutionSpec:
    project_id: int
    workflow_id: int
    workflow_version: int
    task_id: str
    source: Mapping[str, Any]
    target: Mapping[str, Any]
    mappings: tuple[Mapping[str, Any], ...]
    transform_config: Mapping[str, Any]
    target_properties: Mapping[str, Any]


@dataclass
class SyncExecutionMetrics:
    read_rows: int = 0
    write_rows: int = 0
    inserted: int = 0
    updated: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    filtered: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "read_rows": self.read_rows,
            "write_rows": self.write_rows,
            "inserted": self.inserted,
            "updated": self.updated,
            "success": self.success,
            "failed": self.failed,
            "skipped": self.skipped,
            "filtered": self.filtered,
        }


@dataclass(frozen=True)
class SyncBatchWriteResult:
    inserted: int = 0
    updated: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class SyncLineageEdge:
    source_entity: str
    target_entity: str
    field_mappings: tuple[tuple[str, str], ...]


class SyncRuntimeAdapter(Protocol):
    """Driver/runtime operations required from the shared integration layer."""

    def read_rows(self, spec: SyncExecutionSpec, *, batch_size: int) -> Iterable[Mapping[str, Any]]: ...

    def include_row(self, condition: str, row: Mapping[str, Any]) -> bool: ...

    def transform_value(self, expression: str, row: Mapping[str, Any]) -> Any: ...

    def write_batch(
        self, spec: SyncExecutionSpec, rows: Sequence[Mapping[str, Any]]
    ) -> SyncBatchWriteResult: ...

    def write_statistics(self, context: Mapping[str, Any], metrics: Mapping[str, int]) -> None: ...

    def write_lineage(self, context: Mapping[str, Any], edges: Sequence[SyncLineageEdge]) -> None: ...


def prepare_sync_execution(snapshot: Mapping[str, Any]) -> SyncExecutionSpec:
    """Validate and freeze the persisted plan snapshot before any I/O begins."""
    required_ints = ("project_id", "workflow_id", "workflow_version")
    for name in required_ints:
        value = snapshot.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be an integer >= 1")
    task_id = snapshot.get("task_id")
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id must be a non-empty string")
    source, target = snapshot.get("source"), snapshot.get("target")
    if not isinstance(source, Mapping) or not isinstance(target, Mapping):
        raise ValueError("source and target must be objects")
    for label, ref in (("source", source), ("target", target)):
        datasource_id = ref.get("datasource_id")
        if isinstance(datasource_id, bool) or not isinstance(datasource_id, int) or datasource_id < 1:
            raise ValueError(f"{label}.datasource_id must be an integer >= 1")
        for field in ("schema", "object"):
            value = ref.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > 255:
                raise ValueError(f"{label}.{field} must be a non-empty string of at most 255 characters")
    mappings = validate_mappings(snapshot.get("mappings"))
    transforms = validate_transform_config(snapshot.get("transform_config"))
    properties = validate_target_properties(snapshot.get("target_properties"))
    return SyncExecutionSpec(
        project_id=snapshot["project_id"],
        workflow_id=snapshot["workflow_id"],
        workflow_version=snapshot["workflow_version"],
        task_id=task_id,
        source=dict(source),
        target=dict(target),
        mappings=tuple(dict(mapping) for mapping in mappings),
        transform_config=dict(transforms),
        target_properties=dict(properties),
    )


def _batch_size(spec: SyncExecutionSpec) -> int:
    settings = spec.target_properties.get("batch_concurrency", {})
    return settings.get("batch_size", 1000) if isinstance(settings, Mapping) else 1000


def _entity(ref: Mapping[str, Any]) -> str:
    return f"{ref.get('datasource_id')}:{ref.get('schema')}.{ref.get('object')}"


def _mapped_row(spec: SyncExecutionSpec, row: Mapping[str, Any], adapter: SyncRuntimeAdapter) -> dict[str, Any] | None:
    output: dict[str, Any] = {}
    expressions = spec.transform_config.get("transform_expression", {})
    for mapping in spec.mappings:
        source_column = mapping.get("source_column")
        target_column = mapping.get("target_column")
        if not source_column or not target_column or mapping.get("mapping_status") == "UNMATCHED":
            continue
        value = row.get(source_column, mapping.get("default_value"))
        expression = str(mapping.get("transform_expression") or expressions.get(target_column) or "")
        output[target_column] = adapter.transform_value(expression, row) if expression else value
    return output or None


def execute_sync(
    snapshot: Mapping[str, Any],
    *,
    adapter: SyncRuntimeAdapter,
    run_context: Mapping[str, Any],
) -> SyncExecutionMetrics:
    """Stream a saved mapping snapshot through an injected, driver-backed adapter.

    ``include_row`` and ``transform_value`` are explicit adapter operations so
    SQL dialect/expression semantics stay in the runtime integration. Every
    count is accumulated from source rows or the adapter's actual write result;
    the executor does not infer inserted/updated from row arithmetic.
    """
    spec = prepare_sync_execution(snapshot)
    metrics = SyncExecutionMetrics()
    batch_size = _batch_size(spec)
    batch: list[Mapping[str, Any]] = []
    filter_condition = str(spec.transform_config.get("filter_condition", ""))

    def flush() -> None:
        if not batch:
            return
        result = adapter.write_batch(spec, tuple(batch))
        for name in ("inserted", "updated", "success", "failed", "skipped"):
            count = getattr(result, name)
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError(f"write result {name} must be a non-negative integer")
            setattr(metrics, name, getattr(metrics, name) + count)
        metrics.write_rows += result.success
        batch.clear()

    for source_row in adapter.read_rows(spec, batch_size=batch_size):
        metrics.read_rows += 1
        if filter_condition and not adapter.include_row(filter_condition, source_row):
            metrics.filtered += 1
            continue
        mapped = _mapped_row(spec, source_row, adapter)
        if mapped is None:
            metrics.skipped += 1
            continue
        batch.append(mapped)
        if len(batch) >= batch_size:
            flush()
    flush()

    lineage = SyncLineageEdge(
        source_entity=_entity(spec.source),
        target_entity=_entity(spec.target),
        field_mappings=tuple(
            (str(item["source_column"]), str(item["target_column"]))
            for item in spec.mappings
            if item.get("source_column") and item.get("target_column") and item.get("mapping_status") != "UNMATCHED"
        ),
    )
    adapter.write_statistics(run_context, metrics.as_dict())
    adapter.write_lineage(run_context, (lineage,))
    return metrics
