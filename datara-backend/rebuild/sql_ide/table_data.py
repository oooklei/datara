"""Table data operations backing the SQL IDE floating menu (B4-d).

Four server-side operations support the table context menu in the IDE view
(parity audit §6.2-6.5):

- ``read_table_rows`` — paged ``SELECT *`` with a ``COUNT(*)`` total and
  primary key discovery for the edit-data dialog.
- ``apply_table_changes`` — transactional insert/update/delete batch with a
  hard 1000-row cap and all-or-nothing rollback.
- ``import_csv_rows`` — batch ``INSERT`` of frontend-parsed CSV rows with a
  100k row cap.
- ``audit_table_op`` — pre-flight ``DROP``/``TRUNCATE`` audit: existence
  check plus a row-count scale warning. The pass/block verdict gates the
  frontend confirm dialog (S6 hard-block interaction).

All functions receive an open DBAPI connection plus a ``dialect`` of
``"postgres"`` or ``"mysql"`` and own their transaction (commit on success,
rollback before re-raising). The caller owns closing the connection.
Statements interpolate only identifiers validated by :func:`safe_identifier`;
every value travels through bound parameters.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from decimal import Decimal
from typing import Any, Mapping, Sequence

MAX_ROW_LIMIT = 1000
MAX_BATCH_CHANGES = 1000
MAX_IMPORT_ROWS = 100_000
AUDIT_ROW_WARNING = 10_000

_AUDIT_OPS = frozenset({"drop", "truncate"})

_POSTGRES = "postgres"


class TableDataError(Exception):
    """Domain failure translated to a SQL IDE error code at the adapter layer."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message


def safe_identifier(value: object) -> bool:
    """Reject anything that is not a plain SQL identifier."""
    if not isinstance(value, str):
        return False
    if not value or not (value[0].isalpha() or value[0] == "_"):
        return False
    return all(ch.isalnum() or ch in {"_", "$"} for ch in value)


def _require_identifier(value: object, label: str) -> str:
    if not safe_identifier(value):
        raise ValueError(f"a valid {label} is required")
    return str(value)


def _require_schema_table(payload: Mapping[str, object]) -> tuple[str, str]:
    schema = _require_identifier(
        payload.get("schema", payload.get("database")), "schema"
    )
    table = _require_identifier(
        payload.get("table", payload.get("object", payload.get("name"))), "table"
    )
    return schema, table


def _quote(dialect: str, *parts: str) -> str:
    open_q, close_q = ('"', '"') if dialect == _POSTGRES else ("`", "`")
    return ".".join(f"{open_q}{part}{close_q}" for part in parts)


def _json_safe(value: Any) -> Any:
    """Convert DBAPI values into JSON-serializable primitives."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        # NaN/Infinity are invalid JSON; degrade to text instead of emitting
        # a body FastAPI would serialize as bare NaN.
        return value if value == value and abs(value) != float("inf") else str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, _dt.datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, (_dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, _dt.timedelta):
        seconds = int(value.total_seconds())
        sign = "-" if seconds < 0 else ""
        seconds = abs(seconds)
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{sign}{hours:02d}:{minutes:02d}:{secs:02d}"
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


def _primary_keys(connection: Any, dialect: str, schema: str, table: str) -> list[str]:
    cursor = connection.cursor()
    try:
        if dialect == _POSTGRES:
            cursor.execute(
                """
                SELECT a.attname
                FROM pg_index i
                JOIN pg_class c ON c.oid = i.indrelid
                JOIN pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(i.indkey)
                WHERE n.nspname = %s AND c.relname = %s AND i.indisprimary
                ORDER BY a.attnum
                """,
                (schema, table),
            )
        else:
            cursor.execute(
                """
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND CONSTRAINT_NAME = 'PRIMARY'
                ORDER BY ORDINAL_POSITION
                """,
                (schema, table),
            )
        return [str(row[0]) for row in cursor.fetchall() if row[0] is not None]
    finally:
        try:
            cursor.close()
        except Exception:
            pass


def _table_exists(connection: Any, schema: str, table: str) -> bool:
    cursor = connection.cursor()
    try:
        cursor.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = %s LIMIT 1",
            (schema, table),
        )
        return cursor.fetchone() is not None
    finally:
        try:
            cursor.close()
        except Exception:
            pass


def read_table_rows(
    connection: Any,
    *,
    dialect: str,
    payload: Mapping[str, object],
) -> dict[str, Any]:
    """Read one page of table rows plus total count and primary keys."""
    if dialect not in {_POSTGRES, "mysql"}:
        raise ValueError("unsupported dialect")
    schema, table = _require_schema_table(payload)
    limit = int(payload.get("limit", 200) or 200)
    offset = int(payload.get("offset", 0) or 0)
    if limit < 1 or limit > MAX_ROW_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_ROW_LIMIT}")
    if offset < 0:
        raise ValueError("offset must not be negative")

    qualified = _quote(dialect, schema, table)
    cursor = connection.cursor()
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {qualified}")
        total = int(cursor.fetchone()[0])
        cursor.execute(
            f"SELECT * FROM {qualified} LIMIT %s OFFSET %s",
            (limit, offset),
        )
        columns = [str(desc[0]) for desc in cursor.description or ()]
        # Rows travel as arrays aligned with ``columns`` (mirroring the
        # executeSql payload shape). Object-keyed rows would have their column
        # names rewritten by the adapter's snake→camel normalizer, corrupting
        # every apply/import round-trip for snake_case columns.
        rows = [[_json_safe(value) for value in row] for row in cursor.fetchall()]
    except TableDataError:
        raise
    except Exception as exc:
        connection.rollback()
        raise TableDataError("STATEMENT_EXECUTION_FAILED", str(exc)) from exc
    finally:
        try:
            cursor.close()
        except Exception:
            pass
    try:
        primary_keys = _primary_keys(connection, dialect, schema, table)
    except Exception as exc:  # pragma: no cover - driver specific failures
        connection.rollback()
        raise TableDataError("STATEMENT_EXECUTION_FAILED", str(exc)) from exc
    return {
        "columns": columns,
        "rows": rows,
        "total": total,
        "primaryKeys": primary_keys,
        "offset": offset,
        "capability": "supported",
        "constraints": ["read-only"],
    }


def _normalise_key_values(
    record: Mapping[str, object], primary_keys: Sequence[str], label: str
) -> list[tuple[str, Any]]:
    if not isinstance(record, Mapping):
        raise ValueError(f"{label} entries must be objects keyed by primary key")
    keys = set(record)
    if keys != set(primary_keys):
        raise ValueError(f"{label} entries must supply exactly the primary keys {list(primary_keys)}")
    return [(str(k), _json_safe(record[k])) for k in primary_keys]


def apply_table_changes(
    connection: Any,
    *,
    dialect: str,
    payload: Mapping[str, object],
) -> dict[str, Any]:
    """Apply a bounded insert/update/delete batch in a single transaction."""
    if dialect not in {_POSTGRES, "mysql"}:
        raise ValueError("unsupported dialect")
    schema, table = _require_schema_table(payload)
    primary_keys = payload.get("primaryKeys", payload.get("primary_keys"))
    if (
        not isinstance(primary_keys, (list, tuple))
        or not primary_keys
        or len(primary_keys) > 16
        or not all(safe_identifier(pk) for pk in primary_keys)
    ):
        raise ValueError("primaryKeys must list the table primary key columns")
    inserts = payload.get("inserts") or []
    updates = payload.get("updates") or []
    deletes = payload.get("deletes") or []
    for label, batch in (("inserts", inserts), ("updates", updates), ("deletes", deletes)):
        if not isinstance(batch, (list, tuple)):
            raise ValueError(f"{label} must be an array")
    total = len(inserts) + len(updates) + len(deletes)
    if total < 1:
        raise ValueError("at least one change is required")
    if total > MAX_BATCH_CHANGES:
        raise ValueError(f"a single apply is capped at {MAX_BATCH_CHANGES} rows")

    pks = [str(pk) for pk in primary_keys]
    qualified = _quote(dialect, schema, table)
    # Compile and validate the whole batch before opening the transaction so
    # caller mistakes raise ValueError instead of masking as driver failures.
    plan: list[tuple[str, list[Any]]] = []
    for record in inserts:
        if not isinstance(record, Mapping) or not record:
            raise ValueError("insert entries must be non-empty objects")
        columns = [_require_identifier(col, "column name") for col in record]
        placeholders = ", ".join("%s" for _ in columns)
        plan.append(
            (
                f"INSERT INTO {qualified} ({', '.join(_quote(dialect, c) for c in columns)}) "
                f"VALUES ({placeholders})",
                [_json_safe(record[col]) for col in record],
            )
        )
    for record in updates:
        if not isinstance(record, Mapping):
            raise ValueError("update entries must be objects")
        keys = record.get("keys")
        changes = record.get("set")
        if not isinstance(keys, Mapping) or not isinstance(changes, Mapping) or not changes:
            raise ValueError("update entries need keys and a non-empty set")
        key_values = _normalise_key_values(keys, pks, "update.keys")
        for column in changes:
            if str(column) in pks:
                raise ValueError("primary key columns cannot be updated")
        assignments = ", ".join(
            f"{_quote(dialect, _require_identifier(col, 'column name'))} = %s"
            for col in changes
        )
        where = " AND ".join(f"{_quote(dialect, col)} = %s" for col, _ in key_values)
        plan.append(
            (
                f"UPDATE {qualified} SET {assignments} WHERE {where}",
                [_json_safe(changes[col]) for col in changes]
                + [value for _, value in key_values],
            )
        )
    for record in deletes:
        key_values = _normalise_key_values(record, pks, "delete")
        where = " AND ".join(f"{_quote(dialect, col)} = %s" for col, _ in key_values)
        plan.append(
            (f"DELETE FROM {qualified} WHERE {where}", [value for _, value in key_values])
        )

    try:
        cursor = connection.cursor()
        try:
            for statement, params in plan:
                cursor.execute(statement, params)
        finally:
            try:
                cursor.close()
            except Exception:
                pass
        connection.commit()
    except Exception as exc:
        connection.rollback()
        raise TableDataError("STATEMENT_EXECUTION_FAILED", str(exc)) from exc
    return {
        "inserted": len(inserts),
        "updated": len(updates),
        "deleted": len(deletes),
    }


def import_csv_rows(
    connection: Any,
    *,
    dialect: str,
    payload: Mapping[str, object],
) -> dict[str, Any]:
    """Insert frontend-parsed CSV rows in one transaction (audit §6.5)."""
    if dialect not in {_POSTGRES, "mysql"}:
        raise ValueError("unsupported dialect")
    schema, table = _require_schema_table(payload)
    columns = payload.get("columns")
    rows = payload.get("rows")
    if not isinstance(columns, (list, tuple)) or not columns:
        raise ValueError("columns must be a non-empty array")
    if not all(safe_identifier(col) for col in columns):
        raise ValueError("column names must be valid identifiers")
    if len(columns) > 512:
        raise ValueError("too many columns")
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ValueError("rows must be a non-empty array")
    if len(rows) > MAX_IMPORT_ROWS:
        raise ValueError(f"CSV import is capped at {MAX_IMPORT_ROWS} rows")

    qualified = _quote(dialect, schema, table)
    names = [str(col) for col in columns]
    placeholders = ", ".join("%s" for _ in names)
    statement = (
        f"INSERT INTO {qualified} ({', '.join(_quote(dialect, name) for name in names)}) "
        f"VALUES ({placeholders})"
    )
    # Validate row shapes before opening the transaction (see apply above).
    batch = []
    for index, row in enumerate(rows):
        if not isinstance(row, (list, tuple)) or len(row) != len(names):
            raise ValueError(f"row {index} must align with the {len(names)} mapped columns")
        batch.append([_json_safe(value) for value in row])

    try:
        cursor = connection.cursor()
        try:
            for params in batch:
                cursor.execute(statement, params)
        finally:
            try:
                cursor.close()
            except Exception:
                pass
        connection.commit()
    except Exception as exc:
        connection.rollback()
        raise TableDataError("STATEMENT_EXECUTION_FAILED", str(exc)) from exc
    return {"imported": len(rows)}


def audit_table_op(
    connection: Any,
    *,
    dialect: str,
    payload: Mapping[str, object],
) -> dict[str, Any]:
    """Pre-flight a destructive table operation (drop/truncate).

    Returns a ``pass``/``block`` verdict: unknown tables block hard, and an
    oversized row count adds a warning finding the confirm dialog surfaces.
    """
    op = str(payload.get("op", "")).strip().lower()
    if op not in _AUDIT_OPS:
        raise ValueError("op must be drop or truncate")
    schema, table = _require_schema_table(payload)

    findings: list[dict[str, str]] = [
        {
            "severity": "warning",
            "code": "DESTRUCTIVE_OP",
            "message": f"{op.upper()} {schema}.{table} permanently destroys data",
        }
    ]
    row_count: int | None = None
    if not _table_exists(connection, schema, table):
        findings.append(
            {
                "severity": "block",
                "code": "TABLE_NOT_FOUND",
                "message": f"table {schema}.{table} does not exist",
            }
        )
    else:
        qualified = _quote(dialect, schema, table)
        cursor = connection.cursor()
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {qualified}")
            row_count = int(cursor.fetchone()[0])
        except Exception as exc:
            connection.rollback()
            raise TableDataError("STATEMENT_EXECUTION_FAILED", str(exc)) from exc
        finally:
            try:
                cursor.close()
            except Exception:
                pass
        if row_count > AUDIT_ROW_WARNING:
            findings.append(
                {
                    "severity": "warning",
                    "code": "ROW_COUNT_LARGE",
                    "message": (
                        f"table holds {row_count} rows (>{AUDIT_ROW_WARNING}); "
                        "the operation may take a long time"
                    ),
                }
            )
    status = "block" if any(f["severity"] == "block" for f in findings) else "pass"
    return {
        "status": status,
        "op": op,
        "schema": schema,
        "table": table,
        "row_count": row_count,
        "findings": findings,
    }
