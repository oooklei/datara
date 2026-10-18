from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from rebuild.common.db import Base
from rebuild.sql_ide.batch_executor import BatchSqlExecutor
from rebuild.sql_ide.pagination import paginate_result
from rebuild.sql_ide.readonly_preflight import ReadonlyBatchPreflightError
from rebuild.sql_ide.result_store import PersistentResultPageStore


class _SqliteExecutionSession:
    """Execute the approved statements against the same in-memory SQLite DB."""

    def __init__(self, engine):
        self.engine = engine
        self.statements: list[str] = []

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        sql = kwargs["sql"]
        self.statements.append(sql)
        with self.engine.connect() as connection:
            result = connection.execute(text(sql))
            rows = [list(row) for row in result.fetchall()]
            columns = list(result.keys())
        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "total_rows": len(rows),
            "truncated": False,
        }


class _ScopedResultPageStore:
    """Bind the storage adapter's project/user scope to the pagination protocol."""

    def __init__(self, store, *, project_id: int, user_id: int):
        self.store = store
        self.project_id = project_id
        self.user_id = user_id

    def save_snapshot(self, **kwargs: Any) -> str:
        return self.store.save_snapshot(**kwargs)

    def get_snapshot_meta(self, *, history_id: str, stmt_index: int):
        return self.store.get_snapshot_meta(
            project_id=self.project_id,
            user_id=self.user_id,
            history_id=history_id,
            stmt_index=stmt_index,
        )

    def fetch_page(self, *, history_id: str, stmt_index: int, offset: int, limit: int):
        return self.store.fetch_page(
            project_id=self.project_id,
            user_id=self.user_id,
            history_id=history_id,
            stmt_index=stmt_index,
            offset=offset,
            limit=limit,
        )


def test_readonly_preflight_batch_snapshot_and_pagination_use_sqlite_memory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
        )
        connection.execute(
            text("INSERT INTO items (id, name) VALUES (1, 'one'), (2, 'two'), (3, 'three')")
        )

    execution = _SqliteExecutionSession(engine)
    persistent_store = PersistentResultPageStore(session_factory=sessions)
    page_store = _ScopedResultPageStore(persistent_store, project_id=7, user_id=11)
    executor = BatchSqlExecutor(execution_session=execution, result_page_store=page_store)
    args = {
        "project_id": 7,
        "user_id": 11,
        "datasource_id": 13,
        "history_id": "w2-history",
        "dialect": "sqlite",
        "mode": "auto",
        "row_limit": 100,
        "timeout_ms": 5000,
    }

    try:
        with pytest.raises(ReadonlyBatchPreflightError):
            executor.execute_batch(sql="SELECT id FROM items; DELETE FROM items", **args)
        assert execution.statements == []

        outcome = executor.execute_batch(
            sql="SELECT id, name FROM items ORDER BY id; SELECT COUNT(*) AS n FROM items",
            **args,
        )
        assert outcome["status"] == "succeeded", (outcome, execution.statements)
        assert [item["status"] for item in outcome["statements"]] == [
            "succeeded",
            "succeeded",
        ]
        assert [item["stmt_index"] for item in outcome["statements"]] == [0, 1]
        assert len(execution.statements) == 2

        first_page = paginate_result(
            page_store,
            history_id="w2-history",
            stmt_index=0,
            limit=2,
        )
        assert first_page["rows"] == [[1, "one"], [2, "two"]]
        assert first_page["page"]["hasMore"] is True
        assert first_page["nextCursor"]

        second_page = paginate_result(
            page_store,
            history_id="w2-history",
            stmt_index=0,
            cursor=first_page["nextCursor"],
            limit=2,
        )
        assert second_page["rows"] == [[3, "three"]]
        assert second_page["page"]["hasMore"] is False
        assert second_page["nextCursor"] is None
        # Paging reads persisted rows and does not execute the source SQL again.
        assert len(execution.statements) == 2
    finally:
        engine.dispose()
