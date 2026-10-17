"""R5-A production SqlExecutionPort assembly (Track A Gap 1+2).

Replaces the PoC wiring with real datasource mapping and connection management.
The seam (SqlExecutionPort Protocol in rebuild.run_sql) is unchanged.

Layer-2 read-only: before executing user SQL, the port applies DB-side read-only:
- MySQL: SET TRANSACTION READ ONLY + BEGIN (matches probe_datasource pattern)
- PostgreSQL: BEGIN READ ONLY

After execution, the connection is rolled back and closed — no persistent state.

Design input: docs/increments/2026-10-18-P2-2-R5-A-SQL-IDE后端设计草案.md §9.
Supervisor dispatch: #263 Track A / #265 domain boundary ruling.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping
from uuid import uuid4

from rebuild.datasource.contracts import DataSourceDraft
from rebuild.datasource.repository import ProjectDatasourceRepository
from rebuild.run_sql import (
    SqlDependencyUnavailable,
    SqlExecutionFailed,
    SqlExecutionPort,
)


class ProductionSqlExecutionPort:
    """Production SqlExecutionPort backed by real datasource registry.

    Looks up the datasource record via session_factory, obtains a raw DBAPI
    connection from the engine registry, applies layer-2 read-only, executes
    the user SQL within row_limit, and returns a result snapshot.
    """

    def __init__(
        self,
        *,
        session_factory: Callable[[], Any],
        connection_provider: Callable[..., Any],
    ) -> None:
        self._session_factory = session_factory
        self._connection_provider = connection_provider

    def execute(
        self,
        *,
        project_id: int,
        datasource_id: int,
        sql: str,
        row_limit: int,
        timeout_ms: int,
        dialect: str | None = None,
    ) -> Mapping[str, Any]:
        # 1. Look up datasource record
        record = self._lookup_datasource(project_id, datasource_id)
        if record is None:
            raise SqlDependencyUnavailable(
                f"datasource {datasource_id} not found in project {project_id}"
            )
        draft = DataSourceDraft(
            name=record.name,
            kind=record.kind,
            host=record.host,
            port=record.port,
            database=record.database_name,
            username=record.username,
            password=record.password,
        )

        # 2. Get connection from registry
        try:
            connection = self._connection_provider(project_id, datasource_id, draft)
        except Exception as exc:
            raise SqlDependencyUnavailable(
                f"connection to datasource {datasource_id} failed"
            ) from exc

        # 3. Apply layer-2 read-only + execute
        try:
            return self._execute_readonly(connection, record.kind, sql, row_limit)
        finally:
            try:
                connection.rollback()
            except Exception:
                pass
            try:
                connection.close()
            except Exception:
                pass

    def _lookup_datasource(self, project_id: int, datasource_id: int):
        with self._session_factory() as session:
            return ProjectDatasourceRepository(session).get(project_id, datasource_id)

    def _execute_readonly(
        self,
        connection: Any,
        kind: str,
        sql: str,
        row_limit: int,
    ) -> Mapping[str, Any]:
        cursor = connection.cursor()
        try:
            if kind.lower() == "mysql":
                cursor.execute("SET TRANSACTION READ ONLY")
                connection.begin()
            elif kind.lower() == "postgresql":
                cursor.execute("BEGIN READ ONLY")
            else:
                raise SqlDependencyUnavailable(
                    f"layer-2 read-only not supported for kind: {kind}"
                )

            cursor.execute(sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            all_rows = cursor.fetchall()

            truncated = len(all_rows) > row_limit
            rows = all_rows[:row_limit]

            return {
                "execution_id": uuid4().hex,
                "columns": columns,
                "rows": [list(row) for row in rows],
                "row_count": len(rows),
                "total_rows": len(all_rows),
                "truncated": truncated,
            }
        except Exception as exc:
            raise SqlExecutionFailed(
                f"SQL execution failed: {exc}"
            ) from exc
        finally:
            cursor.close()


def build_execution_port(
    *,
    session_factory: Callable[[], Any],
    engine_registry: Any,
) -> SqlExecutionPort:
    """Factory: assemble production SqlExecutionPort from app services.

    session_factory: callable returning a SQLAlchemy Session context manager.
    engine_registry: DatasourceEngineRegistry (or compatible) with .connect().
    """
    return ProductionSqlExecutionPort(
        session_factory=session_factory,
        connection_provider=engine_registry.connect,
    )
