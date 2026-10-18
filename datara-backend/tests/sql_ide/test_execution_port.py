"""Tests for R5-A production SqlExecutionPort assembly (Track A Gap 1+2).

Covers:
- Factory wiring (session_factory + engine_registry → port)
- Datasource lookup and draft construction
- Layer-2 read-only enforcement (SET TRANSACTION READ ONLY / BEGIN READ ONLY)
- Result snapshot shape (columns, rows, truncated, row_count, execution_id)
- Row limit enforcement
- Error mapping (not found, connection failure, SQL error, timeout)
"""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock, patch, call

import pytest

from rebuild.sql_ide.execution import (
    ProductionSqlExecutionPort,
    build_execution_port,
)
from rebuild.run_sql import (
    SqlExecutionFailed,
    SqlDependencyUnavailable,
    SqlExecutionTimeout,
    SqlExecutionCancelled,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_datasource_record(
    *,
    kind: str = "mysql",
    host: str = "localhost",
    port: int = 3306,
    database: str = "testdb",
    username: str = "testuser",
    password: str = "testpass",
) -> MagicMock:
    record = MagicMock()
    record.kind = kind
    record.host = host
    record.port = port
    record.database_name = database
    record.username = username
    record.password = password
    return record


@contextmanager
def _mock_session(record=None):
    """Yield a context-manager mock that acts as session_factory()."""
    session = MagicMock()
    if record is not None:
        session.scalar.return_value = record
    else:
        session.scalar.return_value = None
    factory = MagicMock()
    factory.return_value.__enter__.return_value = session
    factory.return_value.__exit__.return_value = False
    yield factory


def _make_connection(
    *,
    columns: list[str] | None = None,
    rows: list[tuple] | None = None,
    raise_on_execute: Exception | None = None,
) -> MagicMock:
    """Build a mock DBAPI connection with cursor."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    if columns is not None:
        cursor.description = [(col,) for col in columns]
    else:
        cursor.description = None
    if rows is not None:
        cursor.fetchall.return_value = rows
    else:
        cursor.fetchall.return_value = []
    if raise_on_execute is not None:
        cursor.execute.side_effect = raise_on_execute
    return conn


# ---------------------------------------------------------------------------
# factory tests
# ---------------------------------------------------------------------------


class TestBuildExecutionPort:
    """Factory creates a properly wired port."""

    def test_build_returns_production_port(self):
        session_factory = MagicMock()
        registry = MagicMock()
        port = build_execution_port(session_factory=session_factory, engine_registry=registry)
        assert isinstance(port, ProductionSqlExecutionPort)

    def test_build_passes_session_factory_through(self):
        session_factory = MagicMock()
        registry = MagicMock()
        port = build_execution_port(session_factory=session_factory, engine_registry=registry)
        assert port._session_factory is session_factory

    def test_build_passes_engine_registry_as_connection_provider(self):
        session_factory = MagicMock()
        registry = MagicMock()
        port = build_execution_port(session_factory=session_factory, engine_registry=registry)
        assert port._connection_provider is registry.connect


# ---------------------------------------------------------------------------
# execute: happy path
# ---------------------------------------------------------------------------


class TestExecuteSnapshot:
    """Port.execute returns a well-formed result snapshot."""

    def test_returns_columns_rows_and_metadata(self):
        record = _make_datasource_record()
        conn = _make_connection(columns=["id", "name"], rows=[(1, "alice"), (2, "bob")])
        registry = MagicMock()
        registry.connect.return_value = conn

        with _mock_session(record) as sf:
            port = build_execution_port(session_factory=sf, engine_registry=registry)
            result = port.execute(
                project_id=1,
                datasource_id=1,
                sql="SELECT id, name FROM users",
                row_limit=200,
                timeout_ms=30000,
            )

        assert result["columns"] == ["id", "name"]
        assert result["rows"] == [[1, "alice"], [2, "bob"]]
        assert result["row_count"] == 2
        assert result["truncated"] is False
        assert "execution_id" in result
        assert isinstance(result["execution_id"], str)
        assert len(result["execution_id"]) > 0

    def test_row_limit_truncates_results(self):
        record = _make_datasource_record()
        big_rows = [(i,) for i in range(1000)]
        conn = _make_connection(columns=["id"], rows=big_rows)
        registry = MagicMock()
        registry.connect.return_value = conn

        with _mock_session(record) as sf:
            port = build_execution_port(session_factory=sf, engine_registry=registry)
            result = port.execute(
                project_id=1,
                datasource_id=1,
                sql="SELECT id FROM big_table",
                row_limit=50,
                timeout_ms=30000,
            )

        assert result["row_count"] == 50
        assert len(result["rows"]) == 50
        assert result["truncated"] is True

    def test_empty_result(self):
        record = _make_datasource_record()
        conn = _make_connection(columns=["id"], rows=[])
        registry = MagicMock()
        registry.connect.return_value = conn

        with _mock_session(record) as sf:
            port = build_execution_port(session_factory=sf, engine_registry=registry)
            result = port.execute(
                project_id=1,
                datasource_id=1,
                sql="SELECT id FROM empty_table",
                row_limit=200,
                timeout_ms=30000,
            )

        assert result["columns"] == ["id"]
        assert result["rows"] == []
        assert result["row_count"] == 0
        assert result["truncated"] is False

    def test_exact_limit_not_truncated(self):
        record = _make_datasource_record()
        rows = [(i,) for i in range(100)]
        conn = _make_connection(columns=["id"], rows=rows)
        registry = MagicMock()
        registry.connect.return_value = conn

        with _mock_session(record) as sf:
            port = build_execution_port(session_factory=sf, engine_registry=registry)
            result = port.execute(
                project_id=1,
                datasource_id=1,
                sql="SELECT id FROM t",
                row_limit=100,
                timeout_ms=30000,
            )

        assert result["row_count"] == 100
        assert result["truncated"] is False


# ---------------------------------------------------------------------------
# layer-2 read-only
# ---------------------------------------------------------------------------


class TestLayer2Readonly:
    """Port applies DB-side read-only before executing the user SQL."""

    def test_mysql_sets_transaction_read_only(self):
        record = _make_datasource_record(kind="mysql")
        conn = _make_connection(columns=["id"], rows=[(1,)])
        registry = MagicMock()
        registry.connect.return_value = conn

        with _mock_session(record) as sf:
            port = build_execution_port(session_factory=sf, engine_registry=registry)
            port.execute(
                project_id=1,
                datasource_id=1,
                sql="SELECT id FROM t",
                row_limit=200,
                timeout_ms=30000,
            )

        cursor = conn.cursor.return_value
        execute_calls = [c.args[0] for c in cursor.execute.call_args_list]
        assert "SET TRANSACTION READ ONLY" in execute_calls

    def test_mysql_begins_transaction(self):
        record = _make_datasource_record(kind="mysql")
        conn = _make_connection(columns=["id"], rows=[(1,)])
        registry = MagicMock()
        registry.connect.return_value = conn

        with _mock_session(record) as sf:
            port = build_execution_port(session_factory=sf, engine_registry=registry)
            port.execute(
                project_id=1,
                datasource_id=1,
                sql="SELECT id FROM t",
                row_limit=200,
                timeout_ms=30000,
            )

        conn.begin.assert_called_once()

    def test_postgresql_begins_read_only(self):
        record = _make_datasource_record(kind="postgresql")
        conn = _make_connection(columns=["id"], rows=[(1,)])
        registry = MagicMock()
        registry.connect.return_value = conn

        with _mock_session(record) as sf:
            port = build_execution_port(session_factory=sf, engine_registry=registry)
            port.execute(
                project_id=1,
                datasource_id=1,
                sql="SELECT id FROM t",
                row_limit=200,
                timeout_ms=30000,
            )

        cursor = conn.cursor.return_value
        execute_calls = [c.args[0] for c in cursor.execute.call_args_list]
        assert "BEGIN READ ONLY" in execute_calls

    def test_connection_always_closed(self):
        record = _make_datasource_record()
        conn = _make_connection(columns=["id"], rows=[(1,)])
        registry = MagicMock()
        registry.connect.return_value = conn

        with _mock_session(record) as sf:
            port = build_execution_port(session_factory=sf, engine_registry=registry)
            port.execute(
                project_id=1,
                datasource_id=1,
                sql="SELECT id FROM t",
                row_limit=200,
                timeout_ms=30000,
            )

        conn.close.assert_called_once()

    def test_connection_closed_on_error(self):
        record = _make_datasource_record()
        conn = _make_connection(raise_on_execute=RuntimeError("boom"))
        registry = MagicMock()
        registry.connect.return_value = conn

        with _mock_session(record) as sf:
            port = build_execution_port(session_factory=sf, engine_registry=registry)
            with pytest.raises(SqlExecutionFailed):
                port.execute(
                    project_id=1,
                    datasource_id=1,
                    sql="SELECT id FROM t",
                    row_limit=200,
                    timeout_ms=30000,
                )

        conn.close.assert_called_once()

    def test_rollback_called_after_execution(self):
        record = _make_datasource_record()
        conn = _make_connection(columns=["id"], rows=[(1,)])
        registry = MagicMock()
        registry.connect.return_value = conn

        with _mock_session(record) as sf:
            port = build_execution_port(session_factory=sf, engine_registry=registry)
            port.execute(
                project_id=1,
                datasource_id=1,
                sql="SELECT id FROM t",
                row_limit=200,
                timeout_ms=30000,
            )

        conn.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# error mapping
# ---------------------------------------------------------------------------


class TestErrorMapping:
    """Port maps failures to SqlExecutionError hierarchy."""

    def test_datasource_not_found_raises_dependency_unavailable(self):
        registry = MagicMock()
        with _mock_session(None) as sf:
            port = build_execution_port(session_factory=sf, engine_registry=registry)
            with pytest.raises(SqlDependencyUnavailable):
                port.execute(
                    project_id=999,
                    datasource_id=999,
                    sql="SELECT 1",
                    row_limit=200,
                    timeout_ms=30000,
                )

    def test_connection_failure_raises_dependency_unavailable(self):
        record = _make_datasource_record()
        registry = MagicMock()
        registry.connect.side_effect = RuntimeError("connection refused; password=secret")

        with _mock_session(record) as sf:
            port = build_execution_port(session_factory=sf, engine_registry=registry)
            with pytest.raises(SqlDependencyUnavailable) as error:
                port.execute(
                    project_id=1,
                    datasource_id=1,
                    sql="SELECT 1",
                    row_limit=200,
                    timeout_ms=30000,
                )

        assert str(error.value) == "Datasource connection unavailable"
        assert error.value.details == {"errorCode": "DATASOURCE_UNAVAILABLE"}
        assert error.value.__cause__ is None
        assert error.value.__suppress_context__ is True

    def test_driver_timeout_maps_to_stable_timeout_error(self):
        record = _make_datasource_record()
        conn = _make_connection(raise_on_execute=TimeoutError("server detail"))
        registry = MagicMock()
        registry.connect.return_value = conn

        with _mock_session(record) as sf:
            port = build_execution_port(session_factory=sf, engine_registry=registry)
            with pytest.raises(SqlExecutionTimeout) as error:
                port.execute(
                    project_id=1,
                    datasource_id=1,
                    sql="SELECT 1",
                    row_limit=200,
                    timeout_ms=30000,
                )

        assert str(error.value) == "SQL execution timed out"
        assert error.value.details == {"errorCode": "EXECUTION_TIMEOUT"}
        assert error.value.__cause__ is None
        assert error.value.__suppress_context__ is True

    def test_sql_error_raises_execution_failed(self):
        record = _make_datasource_record()
        conn = _make_connection(raise_on_execute=RuntimeError("syntax error; password=secret"))
        registry = MagicMock()
        registry.connect.return_value = conn

        with _mock_session(record) as sf:
            port = build_execution_port(session_factory=sf, engine_registry=registry)
            with pytest.raises(SqlExecutionFailed) as error:
                port.execute(
                    project_id=1,
                    datasource_id=1,
                    sql="SELECT BROKEN",
                    row_limit=200,
                    timeout_ms=30000,
                )

        assert str(error.value) == "SQL execution failed"
        assert error.value.details == {"errorCode": "DRIVER_ERROR"}
        assert error.value.__cause__ is None
        assert error.value.__suppress_context__ is True

    def test_unsupported_kind_raises_dependency_unavailable(self):
        record = _make_datasource_record(kind="oracle")
        registry = MagicMock()
        registry.connect.side_effect = ValueError("pooled datasource connections do not support kind: oracle")

        with _mock_session(record) as sf:
            port = build_execution_port(session_factory=sf, engine_registry=registry)
            with pytest.raises(SqlDependencyUnavailable):
                port.execute(
                    project_id=1,
                    datasource_id=1,
                    sql="SELECT 1",
                    row_limit=200,
                    timeout_ms=30000,
                )


# ---------------------------------------------------------------------------
# datasource lookup
# ---------------------------------------------------------------------------


class TestDatasourceLookup:
    """Port looks up the datasource record from the session factory."""

    def test_session_scalar_called_with_project_and_datasource_id(self):
        record = _make_datasource_record()
        conn = _make_connection(columns=["id"], rows=[(1,)])
        registry = MagicMock()
        registry.connect.return_value = conn

        sf_session = MagicMock()
        sf_session.scalar.return_value = record
        sf = MagicMock()
        sf.return_value.__enter__.return_value = sf_session
        sf.return_value.__exit__.return_value = False

        port = build_execution_port(session_factory=sf, engine_registry=registry)
        port.execute(
            project_id=42,
            datasource_id=7,
            sql="SELECT id FROM t",
            row_limit=200,
            timeout_ms=30000,
        )

        sf_session.scalar.assert_called_once()

    def test_draft_passed_to_connection_provider(self):
        record = _make_datasource_record(
            kind="mysql",
            host="db.example.com",
            port=3307,
            database="analytics",
            username="reader",
            password="secret",
        )
        conn = _make_connection(columns=["id"], rows=[(1,)])
        registry = MagicMock()
        registry.connect.return_value = conn

        with _mock_session(record) as sf:
            port = build_execution_port(session_factory=sf, engine_registry=registry)
            port.execute(
                project_id=1,
                datasource_id=1,
                sql="SELECT id FROM t",
                row_limit=200,
                timeout_ms=30000,
            )

        registry.connect.assert_called_once()
        args, kwargs = registry.connect.call_args
        # positional: project_id, datasource_id
        assert args[0] == 1
        assert args[1] == 1
        # draft keyword
        draft = kwargs.get("draft") or (args[2] if len(args) > 2 else None)
        assert draft is not None
        assert draft.kind == "mysql"
        assert draft.host == "db.example.com"
        assert draft.port == 3307
        assert draft.database == "analytics"
        assert draft.username == "reader"
        assert draft.password == "secret"
