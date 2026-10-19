from collections.abc import Mapping, Sequence
from typing import Any

from rebuild.sync.executor import (
    SyncBatchWriteResult,
    SyncExecutionSpec,
    execute_sync,
)
from rebuild.sync.repository import SyncDomainError


class FakeAdapter:
    def __init__(self):
        self.stats = None
        self.edges = None
        self.writes = []

    def read_rows(self, spec: SyncExecutionSpec, *, batch_size: int):
        assert batch_size == 2
        yield {"id": 1, "name": "Ada", "active": True}
        yield {"id": 2, "name": "Lin", "active": False}
        yield {"id": 3, "name": "Bo", "active": True}

    def include_row(self, condition: str, row: Mapping[str, Any]) -> bool:
        assert condition == "active = true"
        return bool(row["active"])

    def transform_value(self, expression: str, row: Mapping[str, Any]) -> Any:
        assert expression == "upper(name)"
        return str(row["name"]).upper()

    def write_batch(self, spec: SyncExecutionSpec, rows: Sequence[Mapping[str, Any]]) -> SyncBatchWriteResult:
        self.writes.extend(rows)
        return SyncBatchWriteResult(inserted=len(rows), success=len(rows))

    def write_statistics(self, context: Mapping[str, Any], metrics: Mapping[str, int]) -> None:
        self.stats = dict(metrics)

    def write_lineage(self, context: Mapping[str, Any], edges) -> None:
        self.edges = tuple(edges)


def _snapshot():
    return {
        "project_id": 1,
        "workflow_id": 2,
        "workflow_version": 3,
        "task_id": "sync-users",
        "source": {"datasource_id": 4, "schema": "src", "object": "users"},
        "target": {"datasource_id": 5, "schema": "dw", "object": "users"},
        "mappings": [
            {
                "source_column": "id", "target_column": "user_id", "source_type": "int", "target_type": "int",
                "transform_expression": "", "nullable": False, "default_value": None, "mapping_status": "AUTO",
            },
            {
                "source_column": "name", "target_column": "display_name", "source_type": "text", "target_type": "text",
                "transform_expression": "upper(name)", "nullable": True, "default_value": None, "mapping_status": "ADJUSTED",
            },
        ],
        "transform_config": {"filter_condition": "active = true"},
        "target_properties": {"batch_concurrency": {"batch_size": 2, "concurrency": 1}},
    }


def test_sync_executor_maps_filters_batches_and_reports_all_metrics_and_lineage():
    adapter = FakeAdapter()
    metrics = execute_sync(_snapshot(), adapter=adapter, run_context={"instance_id": "run-1"})
    assert metrics.as_dict() == {
        "read_rows": 3,
        "write_rows": 2,
        "inserted": 2,
        "updated": 0,
        "success": 2,
        "failed": 0,
        "skipped": 0,
        "filtered": 1,
    }
    assert adapter.writes == [
        {"user_id": 1, "display_name": "ADA"},
        {"user_id": 3, "display_name": "BO"},
    ]
    assert adapter.stats == metrics.as_dict()
    assert adapter.edges[0].source_entity == "4:src.users"
    assert adapter.edges[0].target_entity == "5:dw.users"
    assert adapter.edges[0].field_mappings == (("id", "user_id"), ("name", "display_name"))


def test_sync_executor_rejects_invalid_snapshot_before_runtime_io():
    adapter = FakeAdapter()
    snapshot = _snapshot()
    snapshot["target_properties"] = {"batch_concurrency": {"batch_size": 10001}}
    try:
        execute_sync(snapshot, adapter=adapter, run_context={})
    except SyncDomainError as error:
        assert error.code == "SYNC_INVALID_TARGET_PROPS"
    else:
        raise AssertionError("invalid target batch size was accepted")
    assert adapter.writes == []
    assert adapter.stats is None
