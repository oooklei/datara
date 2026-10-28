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
from rebuild.sql_ide.errors import map_connection_error, map_driver_error
from rebuild.sql_ide.readonly_preflight import (
    ReadonlyBatchPreflightError,
    classify_sql_batch,
    preflight_readonly_batch,
)
from rebuild.run_sql import (
    SqlDependencyUnavailable,
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
        allow_mutating: bool = False,
    ) -> Mapping[str, Any]:
        dialect_name = dialect or "mysql"
        # 1. Look up datasource record
        record = self._lookup_datasource(project_id, datasource_id)
        if record is None:
            raise SqlDependencyUnavailable(
                f"datasource {datasource_id} not found in project {project_id}"
            )

        # 2. Preflight: if allow_mutating=False enforce strict read-only gate;
        #    otherwise apply a lighter parse-only validation + classify the batch.
        if not allow_mutating:
            statements = preflight_readonly_batch(sql, dialect=dialect_name)
            if len(statements) != 1:
                raise ReadonlyBatchPreflightError(
                    "multi-statement execution is not available on this port"
                )
        else:
            verdict = classify_sql_batch(sql, dialect=dialect_name)
            if verdict == "UNKNOWN":
                # Parse failure — still permit (e.g. raw SHOW statements), but
                # callers should be aware classification was indeterminate.
                pass

        draft = DataSourceDraft(
            name=record.name,
            kind=record.kind,
            host=record.host,
            port=record.port,
            database=record.database_name,
            username=record.username,
            password=record.password,
        )

        # 3. Get connection from registry
        try:
            connection = self._connection_provider(project_id, datasource_id, draft)
        except Exception as exc:
            raise map_connection_error(exc) from None

        # 4. Execute — read-only path applies SET TRANSACTION READ ONLY;
        #    mutating path runs in normal auto-commit / explicit commit mode.
        if not allow_mutating:
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
        else:
            try:
                return self._execute_writable(connection, record.kind, sql, row_limit)
            except Exception:
                try:
                    connection.rollback()
                except Exception:
                    pass
                raise
            finally:
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
        except SqlDependencyUnavailable:
            raise
        except Exception as exc:
            raise map_driver_error(exc) from None
        finally:
            cursor.close()

    def _execute_writable(
        self,
        connection: Any,
        kind: str,
        sql: str,
        row_limit: int,
    ) -> Mapping[str, Any]:
        """Execute DDL / DML in a normal (non-read-only) transaction.

        Unlike ``_execute_readonly`` this does NOT SET TRANSACTION READ ONLY,
        and issues an explicit COMMIT after successful execution so side effects
        (CREATE TABLE, INSERT, etc.) persist.  The result envelope mirrors the
        read-only path so consumers can treat both uniformly.
        """
        cursor = connection.cursor()
        try:
            # No SET TRANSACTION READ ONLY — run in default mode.
            # MySQL: DDL is auto-committed; DML inside explicit transaction.
            # PostgreSQL: explicit BEGIN + COMMIT.
            if kind.lower() == "postgresql":
                cursor.execute("BEGIN")
            # MySQL uses autocommit by default for DDL; DML runs in implicit tx.

            cursor.execute(sql)

            # Commit regardless — DDL needs it on some drivers, DML always needs it.
            try:
                connection.commit()
            except Exception:
                # Some drivers (e.g. MySQL) may auto-commit DDL; a second commit
                # can raise "no transaction in progress" — silently ignore.
                pass

            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            if cursor.description is not None:
                all_rows = cursor.fetchall()
            else:
                all_rows = []

            truncated = len(all_rows) > row_limit
            rows = all_rows[:row_limit]

            return {
                "execution_id": uuid4().hex,
                "columns": columns,
                "rows": [list(row) for row in rows],
                "row_count": len(rows),
                "total_rows": len(all_rows),
                "truncated": truncated,
                "allow_mutating": True,
            }
        except SqlDependencyUnavailable:
            raise
        except Exception as exc:
            # Rollback on failure — execute() outer handler also attempts rollback
            # but being defensive here for driver-specific commit-after-fail quirks.
            try:
                connection.rollback()
            except Exception:
                pass
            raise map_driver_error(exc) from None
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
