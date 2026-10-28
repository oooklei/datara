"""Unit tests for the B4-d table data operations (rows/apply/import/audit)."""

import datetime as _dt
from decimal import Decimal

import pytest

from rebuild.sql_ide.routes import build_sql_ide_router
from rebuild.sql_ide.table_data import (
    MAX_BATCH_CHANGES,
    MAX_IMPORT_ROWS,
    MAX_ROW_LIMIT,
    TableDataError,
    apply_table_changes,
    audit_table_op,
    import_csv_rows,
    read_table_rows,
    safe_identifier,
)


class StubCursor:
    def __init__(self, handler):
        self._handler = handler
        self.executed = []
        self._rows = []
        self._description = ()
        self.closed = False

    @property
    def description(self):
        return self._description

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        rows, description = self._handler(sql, params)
        self._rows = list(rows)
        self._description = description or ()

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def close(self):
        self.closed = True


class StubConnection:
    def __init__(self, handler=None):
        self.cursor_obj = StubCursor(handler or (lambda sql, params: ([], [])))
        self.committed = 0
        self.rolled_back = 0
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        self.closed = True


def counting_handler(rows=0):
    def handler(sql, params):
        if sql.startswith("SELECT COUNT(*)"):
            return [(rows,), (("count",),)]
        return ([], [])
    return handler


def mysql_pk_handler(total=3, data_rows=None):
    rows = data_rows if data_rows is not None else [(1, "a"), (2, "b")]

    def handler(sql, params):
        if sql.startswith("SELECT COUNT(*)"):
            return [(total,)], (("COUNT(*)",),)
        if sql.startswith("SELECT * FROM"):
            return rows, (("id",), ("name",), ("ts",), ("amount",), ("blob",))
        if "KEY_COLUMN_USAGE" in sql:
            return [("id",)], (("COLUMN_NAME",),)
        return ([], [])
    return handler


def postgres_pk_handler():
    def handler(sql, params):
        if "pg_index" in sql:
            return [("id",)], (("attname",),)
        return ([], [])
    return handler


# ---------------------------------------------------------------- identifiers


def test_safe_identifier_rejects_quotes_and_empty_parts():
    assert safe_identifier("users")
    assert safe_identifier("_t1$x")
    assert not safe_identifier("")
    assert not safe_identifier("1abc")
    assert not safe_identifier('a"; DROP TABLE x')
    assert not safe_identifier("a b")
    assert not safe_identifier(None)


# ------------------------------------------------------------- read_table_rows


def test_read_table_rows_returns_json_safe_rows_totals_and_primary_keys():
    connection = StubConnection(
        mysql_pk_handler(
            total=2,
            data_rows=[
                (1, "a", _dt.datetime(2026, 10, 28, 8, 0, 0), Decimal("1.50"), b"\x01"),
            ],
        )
    )
    result = read_table_rows(
        connection,
        dialect="mysql",
        payload={"schema": "app", "table": "users", "limit": 200, "offset": 0},
    )
    assert result["columns"] == ["id", "name", "ts", "amount", "blob"]
    # Rows stay as arrays aligned with columns: the HTTP adapter rewrites
    # object keys snake→camel, which would corrupt snake_case column names.
    assert result["rows"][0] == [1, "a", "2026-10-28 08:00:00", "1.50", "01"]
    assert result["total"] == 2
    assert result["primaryKeys"] == ["id"]
    executed = connection.cursor_obj.executed
    assert executed[0][0].startswith("SELECT COUNT(*) FROM `app`.`users`")
    assert executed[1][0].startswith("SELECT * FROM `app`.`users` LIMIT %s OFFSET %s")
    assert executed[1][1] == (200, 0)


def test_read_table_rows_quotes_postgres_identifiers_and_finds_primary_key():
    connection = StubConnection(postgres_pk_handler())
    connection.cursor_obj._handler = _combined_postgres_handler(connection.cursor_obj._handler)
    result = read_table_rows(
        connection,
        dialect="postgres",
        payload={"schema": "app", "table": "users"},
    )
    assert result["primaryKeys"] == ["id"]
    assert '"app"."users"' in connection.cursor_obj.executed[1][0]


def _combined_postgres_handler(pk_handler):
    def handler(sql, params):
        if sql.startswith("SELECT COUNT(*)"):
            return [(0,)], (("count",),)
        if sql.startswith("SELECT * FROM"):
            return [], (("id",),)
        return pk_handler(sql, params)
    return handler


def test_read_table_rows_validates_limit_and_identifiers():
    connection = StubConnection()
    with pytest.raises(ValueError):
        read_table_rows(
            connection, dialect="mysql",
            payload={"schema": "app", "table": "users", "limit": MAX_ROW_LIMIT + 1},
        )
    with pytest.raises(ValueError):
        read_table_rows(connection, dialect="mysql", payload={"schema": "app", "table": "users; DROP", "limit": 10})
    with pytest.raises(ValueError):
        read_table_rows(connection, dialect="mysql", payload={"schema": "", "table": "users"})


def test_read_table_rows_maps_driver_failure_to_domain_error():
    def handler(sql, params):
        raise RuntimeError("boom")

    connection = StubConnection(handler)
    with pytest.raises(TableDataError) as excinfo:
        read_table_rows(connection, dialect="mysql", payload={"schema": "app", "table": "users"})
    assert excinfo.value.error_code == "STATEMENT_EXECUTION_FAILED"
    assert connection.rolled_back == 1


# ---------------------------------------------------------- apply_table_changes


def test_apply_table_changes_runs_insert_update_delete_in_one_transaction():
    connection = StubConnection()
    result = apply_table_changes(
        connection,
        dialect="mysql",
        payload={
            "schema": "app",
            "table": "users",
            "primaryKeys": ["id"],
            "inserts": [{"id": 3, "name": "c"}],
            "updates": [{"keys": {"id": 1}, "set": {"name": "aa"}}],
            "deletes": [{"id": 2}],
        },
    )
    assert result == {"inserted": 1, "updated": 1, "deleted": 1}
    assert connection.committed == 1
    executed = connection.cursor_obj.executed
    assert executed[0][0] == "INSERT INTO `app`.`users` (`id`, `name`) VALUES (%s, %s)"
    assert executed[0][1] == [3, "c"]
    assert executed[1][0] == "UPDATE `app`.`users` SET `name` = %s WHERE `id` = %s"
    assert executed[1][1] == ["aa", 1]
    assert executed[2][0] == "DELETE FROM `app`.`users` WHERE `id` = %s"
    assert executed[2][1] == [2]


def test_apply_table_changes_requires_primary_keys_and_rejects_pk_updates():
    connection = StubConnection()
    base = {"schema": "app", "table": "users"}
    with pytest.raises(ValueError):
        apply_table_changes(connection, dialect="mysql", payload={**base, "primaryKeys": [], "inserts": [{"a": 1}]})
    with pytest.raises(ValueError):
        apply_table_changes(
            connection,
            dialect="mysql",
            payload={**base, "primaryKeys": ["id"], "updates": [{"keys": {"id": 1}, "set": {"id": 9}}]},
        )
    with pytest.raises(ValueError):
        apply_table_changes(
            connection,
            dialect="mysql",
            payload={**base, "primaryKeys": ["id"], "deletes": [{"other": 1}]},
        )


def test_apply_table_changes_caps_batch_size_and_requires_changes():
    connection = StubConnection()
    with pytest.raises(ValueError):
        apply_table_changes(
            connection,
            dialect="mysql",
            payload={
                "schema": "app", "table": "users", "primaryKeys": ["id"],
                "inserts": [], "updates": [], "deletes": [],
            },
        )
    with pytest.raises(ValueError):
        apply_table_changes(
            connection,
            dialect="mysql",
            payload={
                "schema": "app",
                "table": "users",
                "primaryKeys": ["id"],
                "inserts": [{"id": i} for i in range(MAX_BATCH_CHANGES + 1)],
            },
        )


def test_apply_table_changes_rolls_back_and_reports_execution_failure():
    def handler(sql, params):
        if sql.startswith("INSERT"):
            raise RuntimeError("constraint violated")
        return ([], [])

    connection = StubConnection(handler)
    with pytest.raises(TableDataError) as excinfo:
        apply_table_changes(
            connection,
            dialect="postgres",
            payload={
                "schema": "app",
                "table": "users",
                "primaryKeys": ["id"],
                "inserts": [{"id": 3}],
            },
        )
    assert excinfo.value.error_code == "STATEMENT_EXECUTION_FAILED"
    assert connection.rolled_back == 1
    assert connection.committed == 0


# -------------------------------------------------------------- import_csv_rows


def test_import_csv_rows_inserts_mapped_columns_and_commits_once():
    connection = StubConnection()
    result = import_csv_rows(
        connection,
        dialect="mysql",
        payload={
            "schema": "app",
            "table": "users",
            "columns": ["id", "name"],
            "rows": [[1, "a"], [2, "b"]],
        },
    )
    assert result == {"imported": 2}
    assert connection.committed == 1
    executed = connection.cursor_obj.executed
    assert len(executed) == 2
    assert executed[0][0] == "INSERT INTO `app`.`users` (`id`, `name`) VALUES (%s, %s)"
    assert executed[0][1] == [1, "a"]
    assert executed[1][1] == [2, "b"]


def test_import_csv_rows_validates_columns_rows_and_cap():
    connection = StubConnection()
    base_csv = {"schema": "app", "table": "users"}
    with pytest.raises(ValueError):
        import_csv_rows(connection, dialect="mysql", payload={**base_csv, "columns": [], "rows": [[1]]})
    with pytest.raises(ValueError):
        import_csv_rows(connection, dialect="mysql", payload={**base_csv, "columns": ["a;"], "rows": [[1]]})
    with pytest.raises(ValueError):
        import_csv_rows(connection, dialect="mysql", payload={**base_csv, "columns": ["a"], "rows": []})
    with pytest.raises(ValueError):
        import_csv_rows(
            connection,
            dialect="mysql",
            payload={**base_csv, "columns": ["a"], "rows": [[1]] * (MAX_IMPORT_ROWS + 1)},
        )
    with pytest.raises(ValueError):
        import_csv_rows(
            connection,
            dialect="mysql",
            payload={**base_csv, "columns": ["a", "b"], "rows": [[1]]},
        )


# ---------------------------------------------------------------- audit_table_op


def test_audit_table_op_passes_small_existing_table_with_destructive_warning():
    def exists_handler(sql, params):
        if sql.startswith("SELECT 1 FROM information_schema.tables"):
            return [(1,)], (("?column?",),)
        if sql.startswith("SELECT COUNT(*)"):
            return [(42,)], (("count",),)
        return ([], [])

    connection = StubConnection(exists_handler)
    result = audit_table_op(connection, dialect="mysql", payload={"schema": "app", "table": "users", "op": "TRUNCATE"})
    assert result["status"] == "pass"
    assert result["row_count"] == 42
    assert result["op"] == "truncate"
    codes = {f["code"]: f["severity"] for f in result["findings"]}
    assert codes["DESTRUCTIVE_OP"] == "warning"
    assert "ROW_COUNT_LARGE" not in codes


def test_audit_table_op_warns_on_large_row_count():
    def handler(sql, params):
        if sql.startswith("SELECT 1 FROM information_schema.tables"):
            return [(1,)], None
        if sql.startswith("SELECT COUNT(*)"):
            return [(50001,)], None
        return ([], [])

    connection = StubConnection(handler)
    result = audit_table_op(connection, dialect="postgres", payload={"schema": "app", "table": "users", "op": "drop"})
    assert result["status"] == "pass"
    assert result["row_count"] == 50001
    assert any(f["code"] == "ROW_COUNT_LARGE" for f in result["findings"])


def test_audit_table_op_blocks_missing_table():
    connection = StubConnection()
    result = audit_table_op(connection, dialect="mysql", payload={"schema": "app", "table": "ghost", "op": "drop"})
    assert result["status"] == "block"
    assert result["row_count"] is None
    assert any(f["code"] == "TABLE_NOT_FOUND" and f["severity"] == "block" for f in result["findings"])


def test_audit_table_op_rejects_unknown_operations():
    connection = StubConnection()
    with pytest.raises(ValueError):
        audit_table_op(connection, dialect="mysql", payload={"schema": "app", "table": "users", "op": "delete"})


# ------------------------------------------------------------------- wiring


def test_router_registers_table_data_routes_with_frozen_permissions():
    from fastapi import FastAPI

    app = FastAPI()
    router = build_sql_ide_router(
        dispatch=lambda operation, **kwargs: {},
        authenticate=lambda token, authorization: {"user_id": 7},
        authorize=lambda *args: None,
    )
    app.include_router(router)
    registered = {(route.path, route.name) for route in router.routes}
    assert ("/api/v1/projects/{project_id}/sql-ide/rows", "listTableRows") in registered
    assert ("/api/v1/projects/{project_id}/sql-ide/rows/apply", "applyTableRows") in registered
    assert ("/api/v1/projects/{project_id}/sql-ide/import-csv", "importCsv") in registered
    assert ("/api/v1/projects/{project_id}/sql-ide/audit", "auditTable") in registered
