"""Focused tests for the project-scoped R5-B execution-record list service."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from rebuild.rb.ledger.list_execution_records import ListExecutionRecordsService
from rebuild.rb.models.rb_models import ObjectRef


class Repository:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def list_records(self, **kwargs):
        self.calls.append(kwargs)
        return self.rows[: kwargs["fetch_limit"]]


def _row(number: int, *, object_ref=None):
    return SimpleNamespace(
        record_id=f"record-{number}",
        datasource_id=7,
        object_ref=object_ref or {
            "datasource_id": 7,
            "database": "warehouse",
            "catalog": None,
            "schema": "public",
            "kind": "table",
            "name": "orders",
            "parent": None,
        },
        action="ALTER_TABLE",
        script_hash="a" * 64,
        executed_at=datetime(2026, 10, 20, 8, number, tzinfo=timezone.utc),
        status="success",
        failure_summary=None,
        policy_snapshot_id="policy-1",
        impact_snapshot_id="impact-1",
        compensation_refs=[],
        actor_id=11,
    )


def test_list_records_is_project_scoped_and_serializes_wire_shape():
    repository = Repository([_row(1, object_ref=ObjectRef(7, "warehouse", None, "public", "table", "orders", None))])
    service = ListExecutionRecordsService(repository)

    result = service(
        project_id=3,
        datasource_id=7,
        object_ref={"database": "warehouse", "schema": "public", "kind": "table", "name": "orders"},
        page=1,
        page_size=50,
    )

    call = repository.calls[0]
    assert call["project_id"] == 3
    assert call["datasource_id"] == 7
    assert call["object_ref"].name == "orders"
    assert call["fetch_limit"] == 51
    assert result["items"][0]["objectRef"] == {
        "datasourceId": 7,
        "database": "warehouse",
        "catalog": None,
        "schema": "public",
        "kind": "table",
        "name": "orders",
        "parent": None,
    }
    assert result["items"][0]["executedAt"] == "2026-10-20T08:01:00Z"
    assert result["page"] == {"number": 1, "pageSize": 50, "nextCursor": None, "hasMore": False}


def test_list_records_fetches_one_extra_row_for_exact_has_more():
    repository = Repository([_row(1), _row(2), _row(3)])
    service = ListExecutionRecordsService(repository)

    result = service(project_id=3, datasource_id=7, page=1, page_size=2)

    assert [item["recordId"] for item in result["items"]] == ["record-1", "record-2"]
    assert result["page"] == {"number": 1, "pageSize": 2, "nextCursor": "2", "hasMore": True}


@pytest.mark.parametrize(
    "values",
    [
        {"project_id": 0, "datasource_id": 7},
        {"project_id": 3, "datasource_id": 0},
        {"project_id": 3, "datasource_id": 7, "page": 0},
        {"project_id": 3, "datasource_id": 7, "page_size": 201},
    ],
)
def test_list_records_rejects_invalid_scope_or_pagination(values):
    service = ListExecutionRecordsService(Repository([]))

    with pytest.raises(ValueError):
        service(**values)


def test_list_records_rejects_incomplete_object_filter():
    service = ListExecutionRecordsService(Repository([]))

    with pytest.raises(ValueError, match="database, kind, and name"):
        service(project_id=3, datasource_id=7, object_ref={"name": "orders"})
