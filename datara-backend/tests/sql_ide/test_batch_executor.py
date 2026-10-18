from __future__ import annotations

from unittest.mock import Mock

import pytest

from rebuild.sql_ide.batch_executor import BatchSqlExecutor
from rebuild.sql_ide.readonly_preflight import ReadonlyBatchPreflightError


class ResultStore:
    def __init__(self, *, fail_on_index: int | None = None) -> None:
        self.saved = []
        self.fail_on_index = fail_on_index

    def save_snapshot(self, **kwargs):
        if kwargs["stmt_index"] == self.fail_on_index:
            raise RuntimeError("snapshot store failed")
        self.saved.append(kwargs)
        return f"result-{kwargs['stmt_index']}"


def _session(*, fail_on_sql: str | None = None) -> Mock:
    session = Mock()

    def execute(**kwargs):
        if kwargs["sql"] == fail_on_sql:
            raise RuntimeError("driver failed")
        return {
            "columns": ["value"],
            "rows": [[kwargs["sql"]]],
            "row_count": 1,
            "total_rows": 1,
            "truncated": False,
        }

    session.execute.side_effect = execute
    return session


def _executor(session: Mock, store: ResultStore) -> BatchSqlExecutor:
    return BatchSqlExecutor(execution_session=session, result_page_store=store)


def _run(executor: BatchSqlExecutor, sql: str, *, mode: str = "auto"):
    return executor.execute_batch(
        project_id=7,
        user_id=11,
        datasource_id=13,
        history_id="history-1",
        sql=sql,
        dialect="sqlite",
        mode=mode,
        row_limit=100,
        timeout_ms=5000,
    )


def test_auto_batch_preflights_every_statement_before_executing_any():
    session = _session()
    store = ResultStore()

    with pytest.raises(ReadonlyBatchPreflightError):
        _run(_executor(session, store), "SELECT 1; DELETE FROM accounts")

    session.execute.assert_not_called()
    assert store.saved == []


def test_auto_batch_executes_sequentially_and_persists_each_result_snapshot():
    session = _session()
    store = ResultStore()

    result = _run(_executor(session, store), "SELECT 1; SELECT 2")

    assert [call.kwargs["sql"] for call in session.execute.call_args_list] == [
        "SELECT 1",
        "SELECT 2",
    ]
    assert [snapshot["stmt_index"] for snapshot in store.saved] == [0, 1]
    assert [snapshot["history_id"] for snapshot in store.saved] == [
        "history-1",
        "history-1",
    ]
    assert result["status"] == "succeeded"
    assert [item["result_set_id"] for item in result["statements"]] == [
        "result-0",
        "result-1",
    ]


def test_failure_after_success_is_partial_failure_and_stops_later_statements():
    session = _session(fail_on_sql="SELECT 2")
    store = ResultStore()

    result = _run(_executor(session, store), "SELECT 1; SELECT 2; SELECT 3")

    assert result["status"] == "partial_failure"
    assert result["failed_statement_index"] == 1
    assert [item["status"] for item in result["statements"]] == [
        "succeeded",
        "failed",
    ]
    assert [call.kwargs["sql"] for call in session.execute.call_args_list] == [
        "SELECT 1",
        "SELECT 2",
    ]
    assert len(store.saved) == 1


def test_first_statement_failure_is_failed_not_partial_failure():
    session = _session(fail_on_sql="SELECT 1")
    store = ResultStore()

    result = _run(_executor(session, store), "SELECT 1; SELECT 2")

    assert result["status"] == "failed"
    assert result["failed_statement_index"] == 0
    assert [item["status"] for item in result["statements"]] == ["failed"]
    assert session.execute.call_count == 1
    assert store.saved == []


def test_snapshot_persistence_failure_stops_batch_and_reports_failure_location():
    session = _session()
    store = ResultStore(fail_on_index=1)

    result = _run(_executor(session, store), "SELECT 1; SELECT 2; SELECT 3")

    assert result["status"] == "partial_failure"
    assert result["failed_statement_index"] == 1
    assert [item["status"] for item in result["statements"]] == [
        "succeeded",
        "failed",
    ]
    assert result["statements"][1]["error_code"] == "RESULT_SNAPSHOT_FAILED"
    assert session.execute.call_count == 2
    assert len(store.saved) == 1


def test_only_auto_mode_is_supported_and_fails_before_execution():
    session = _session()
    store = ResultStore()

    with pytest.raises(ValueError, match="mode=auto"):
        _run(_executor(session, store), "SELECT 1", mode="transaction")

    session.execute.assert_not_called()
    assert store.saved == []
