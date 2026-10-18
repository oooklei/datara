"""Fail-closed SQL parsing and whole-batch read-only preflight for R5-A."""

from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp


class ReadonlyBatchPreflightError(ValueError):
    """Raised when any statement cannot be proven read-only."""


@dataclass(frozen=True)
class ReadonlyStatement:
    """A parsed statement approved for later execution by the caller."""

    index: int
    sql: str


_READ_QUERY_TYPES = (exp.Select, exp.Union, exp.Intersect, exp.Except)
_SAFE_FUNCTION_TYPES = {
    "Abs",
    "Avg",
    "Ceil",
    "CharLength",
    "Coalesce",
    "Concat",
    "ConcatWs",
    "Count",
    "CurrentDate",
    "CurrentTime",
    "CurrentTimestamp",
    "Date",
    "DateAdd",
    "DateDiff",
    "DateSub",
    "Extract",
    "Floor",
    "Greatest",
    "If",
    "IfNull",
    "Least",
    "Length",
    "Lower",
    "LTrim",
    "Max",
    "Min",
    "Month",
    "Nullif",
    "OctetLength",
    "Round",
    "RTrim",
    "Substring",
    "Sum",
    "Trim",
    "Upper",
    "Year",
}
_DIALECT_ALIASES = {"postgresql": "postgres"}


def _is_readonly_query(statement: exp.Expression) -> bool:
    if not isinstance(statement, _READ_QUERY_TYPES):
        return False

    for node in statement.walk():
        if isinstance(node, exp.Select):
            # SELECT ... INTO and locking clauses can mutate state or acquire
            # locks even though the top-level AST node is a Select.
            if node.args.get("into") is not None or node.args.get("locks"):
                return False
        # Unknown and user-defined functions cannot be assumed side-effect free.
        if isinstance(node, exp.Func) and type(node).__name__ not in _SAFE_FUNCTION_TYPES:
            return False
    return True


def preflight_readonly_batch(sql: str, *, dialect: str) -> tuple[ReadonlyStatement, ...]:
    """Parse and validate every statement before returning any executable item.

    A failed parse, empty batch, unsupported dialect, non-query statement, or
    query containing a locking/unknown-function construct rejects the entire
    batch. Callers must not execute incrementally while this function runs.
    """

    if not isinstance(sql, str) or not sql.strip() or not isinstance(dialect, str) or not dialect.strip():
        raise ReadonlyBatchPreflightError("SQL batch and dialect are required")
    dialect_name = _DIALECT_ALIASES.get(dialect.lower(), dialect.lower())
    try:
        parsed = sqlglot.parse(sql, read=dialect_name)
    except (sqlglot.errors.ParseError, ValueError) as exc:
        raise ReadonlyBatchPreflightError("SQL batch cannot be classified as read-only") from exc

    statements = [statement for statement in parsed if statement is not None]
    if not statements or any(not _is_readonly_query(statement) for statement in statements):
        raise ReadonlyBatchPreflightError("SQL batch cannot be classified as read-only")

    return tuple(
        ReadonlyStatement(index=index, sql=statement.sql(dialect=dialect_name))
        for index, statement in enumerate(statements)
    )
