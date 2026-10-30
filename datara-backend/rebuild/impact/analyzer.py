"""Extract table read/write effects from a dbx history entry.

This is a post-execution report. Failed statements never produce write effects.
Unsupported SQL is reported as unknown instead of guessing an impact.
"""

from __future__ import annotations

from typing import Any

import sqlglot
from sqlglot import exp


_WRITE_TYPES = (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter, exp.TruncateTable)


def _table_name(table: exp.Table, database: str) -> str:
    parts = [part for part in (table.catalog, table.db, table.name) if part]
    if len(parts) == 1 and database:
        parts.insert(0, database)
    return ".".join(parts)


def _write_target(statement: exp.Expression) -> exp.Table | None:
    if not isinstance(statement, _WRITE_TYPES):
        return None
    target = statement.this
    if isinstance(target, exp.Table):
        return target
    if isinstance(target, exp.Schema) and isinstance(target.this, exp.Table):
        return target.this
    return None


def analyze_history_entry(entry: dict[str, Any], *, dialect: str | None = None) -> dict[str, Any]:
    """Return a stable result row for one dbx ``HistoryEntry``.

    ``reads`` and ``writes`` are fully qualified with the history database when
    the SQL uses an unqualified table. The original SQL is deliberately omitted
    from this result; dbx remains its history source of truth.
    """
    result: dict[str, Any] = {
        "history_id": str(entry.get("id", "")),
        "connection_id": str(entry.get("connection_id", "") or ""),
        "database": str(entry.get("database", "") or ""),
        "executed_at": str(entry.get("executed_at", "") or ""),
        "success": bool(entry.get("success", False)),
        "reads": [],
        "writes": [],
        "status": "ok",
    }
    sql = str(entry.get("sql", "") or "").strip()
    if not sql:
        result["status"] = "no_sql"
        return result
    if not result["success"]:
        result["status"] = "failed_execution"
        return result
    try:
        statements = sqlglot.parse(sql, read=dialect)
    except (sqlglot.errors.ParseError, ValueError):
        result["status"] = "unparsed"
        return result
    reads: set[str] = set()
    writes: set[str] = set()
    for statement in statements:
        if statement is None:
            continue
        cte_names = {cte.alias.lower() for cte in statement.find_all(exp.CTE) if cte.alias}
        target = _write_target(statement)
        target_name = _table_name(target, result["database"]) if target is not None else None
        if target_name:
            writes.add(target_name)
        for table in statement.find_all(exp.Table):
            if not table.db and not table.catalog and table.name.lower() in cte_names:
                continue
            name = _table_name(table, result["database"])
            if name != target_name:
                reads.add(name)
    result["reads"] = sorted(reads)
    result["writes"] = sorted(writes)
    return result
