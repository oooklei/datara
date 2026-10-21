from __future__ import annotations

from types import SimpleNamespace

import pytest

from rebuild.ai_bridge import ToolError
from rebuild.ai_tools import (
    build_get_task_metrics_handler,
    build_inspect_workflow_run_handler,
    build_validate_sql_handler,
)
from rebuild.execution.models import WorkflowInstanceRecord
from rebuild.workflow.models import WorkflowVersionRecord


class _Session:
    def __init__(self, records=None):
        self.records = records or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def get(self, model, identity):
        return self.records.get((model, identity))


def _factory(records=None):
    return lambda: _Session(records)


def test_validate_sql_checks_datasource_project_even_with_explicit_dialect() -> None:
    from rebuild.datasource.models import ProjectDatasourceRecord

    datasource = SimpleNamespace(id=9, project_id=2, kind="mysql")
    handler = build_validate_sql_handler(_factory({(ProjectDatasourceRecord, 9): datasource}))

    with pytest.raises(ToolError) as raised:
        handler(
            {"datasource_id": 9, "sql": "select 1", "dialect": "mysql"},
            None,
            {"project_id": 1},
        )
    assert raised.value.code == "NOT_FOUND"


def test_inspect_run_fails_closed_when_version_or_definition_is_missing() -> None:
    run = SimpleNamespace(id=3, workflow_version_id=7)
    handler = build_inspect_workflow_run_handler(
        _factory({(WorkflowInstanceRecord, 3): run})
    )
    with pytest.raises(ToolError) as raised:
        handler({"run_id": 3}, None, {"project_id": 1})
    assert raised.value.code == "NOT_FOUND"

    version = SimpleNamespace(id=7, definition_id=11)
    handler = build_inspect_workflow_run_handler(
        _factory({
            (WorkflowInstanceRecord, 3): run,
            (WorkflowVersionRecord, 7): version,
        })
    )
    with pytest.raises(ToolError) as raised:
        handler({"run_id": 3}, None, {"project_id": 1})
    assert raised.value.code == "NOT_FOUND"


def test_task_metrics_never_synthesizes_missing_frozen_bucket_fields() -> None:
    handler = build_get_task_metrics_handler(_factory())
    with pytest.raises(ToolError) as raised:
        handler(
            {"time_window": {"from": "2026-10-01", "to": "2026-10-02"}, "group_by": "day"},
            None,
            {"project_id": 1},
        )
    assert raised.value.code == "DEPENDENCY_UNAVAILABLE"
    assert raised.value.retryable is True
