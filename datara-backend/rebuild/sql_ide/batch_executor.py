"""Sequential, read-only SQL batch execution for the R5-A ``auto`` mode."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from rebuild.sql_ide.contracts import ResultPageStore, SqlExecutionSession
from rebuild.sql_ide.readonly_preflight import preflight_readonly_batch


class BatchSqlExecutor:
    """Preflight a complete batch, then execute and snapshot statements in order.

    A batch is never executed incrementally during policy validation. Once the
    complete batch is approved, statements execute serially. A failed
    statement stops the batch; successful earlier result snapshots remain
    addressable and the terminal status is ``partial_failure``.
    """

    def __init__(
        self,
        *,
        execution_session: SqlExecutionSession,
        result_page_store: ResultPageStore,
        preflight: Callable[..., tuple[Any, ...]] = preflight_readonly_batch,
    ) -> None:
        self._execution_session = execution_session
        self._result_page_store = result_page_store
        self._preflight = preflight

    def execute_batch(
        self,
        *,
        project_id: int,
        user_id: int,
        datasource_id: int,
        history_id: str,
        sql: str,
        dialect: str,
        mode: str,
        row_limit: int,
        timeout_ms: int,
        catalog: str | None = None,
        schema: str | None = None,
    ) -> Mapping[str, Any]:
        if mode != "auto":
            raise ValueError("only mode=auto is supported")
        if not history_id:
            raise ValueError("history_id is required")
        if row_limit <= 0 or timeout_ms <= 0:
            raise ValueError("row_limit and timeout_ms must be positive")

        # This call validates every parsed statement before the first session
        # call. Do not move it inside the execution loop.
        statements = self._preflight(sql, dialect=dialect)
        if not statements:
            raise ValueError("SQL batch must contain at least one statement")

        snapshot_writer = getattr(self._result_page_store, "save_snapshot", None)
        if not callable(snapshot_writer):
            raise TypeError("result page store must provide save_snapshot")

        results: list[dict[str, Any]] = []
        for statement in statements:
            statement_index = int(statement.index)
            try:
                execution = self._execution_session.execute(
                    project_id=project_id,
                    datasource_id=datasource_id,
                    sql=statement.sql,
                    row_limit=row_limit,
                    timeout_ms=timeout_ms,
                    dialect=dialect,
                    catalog=catalog,
                    schema=schema,
                )
            except Exception:
                results.append(
                    {
                        "stmt_index": statement_index,
                        "status": "failed",
                        "error_code": "STATEMENT_EXECUTION_FAILED",
                    }
                )
                return {
                    "status": "partial_failure" if len(results) > 1 else "failed",
                    "failed_statement_index": statement_index,
                    "statements": results,
                }

            columns = list(execution.get("columns", ()))
            rows = list(execution.get("rows", ()))
            total_rows = int(execution.get("total_rows", len(rows)))
            try:
                result_set_id = snapshot_writer(
                    project_id=project_id,
                    user_id=user_id,
                    history_id=history_id,
                    stmt_index=statement_index,
                    columns=columns,
                    rows=rows,
                    total_rows=total_rows,
                )
            except Exception:
                results.append(
                    {
                        "stmt_index": statement_index,
                        "status": "failed",
                        "error_code": "RESULT_SNAPSHOT_FAILED",
                    }
                )
                return {
                    "status": "partial_failure" if len(results) > 1 else "failed",
                    "failed_statement_index": statement_index,
                    "statements": results,
                }
            results.append(
                {
                    "stmt_index": statement_index,
                    "status": "succeeded",
                    "result_set_id": result_set_id,
                    "columns": columns,
                    "row_count": int(execution.get("row_count", len(rows))),
                    "total_rows": total_rows,
                    "truncated": bool(execution.get("truncated", False)),
                }
            )

        return {"status": "succeeded", "statements": results}
