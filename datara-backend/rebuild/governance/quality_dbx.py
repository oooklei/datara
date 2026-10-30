"""Compile a bounded quality predicate into a read-only DBX count query."""

from __future__ import annotations

import re
from typing import Any

import sqlglot
from sqlglot import exp


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ALLOWED_NODES = (
    exp.And, exp.Or, exp.Not, exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE,
    exp.Is, exp.Between, exp.In, exp.Column, exp.Identifier, exp.Literal,
    exp.Null, exp.Length, exp.Trim, exp.RegexpLike, exp.Add, exp.Sub,
    exp.Mul, exp.Div, exp.Mod, exp.Paren, exp.Cast, exp.Lower, exp.Upper,
    exp.Coalesce, exp.Boolean,
)


class QualityPredicateError(ValueError):
    pass


def compile_quality_count_query(
    *, database: str, table: str, expression: str, fields: set[str],
) -> str:
    """Accept only simple predicates over declared columns; count every failed row."""
    if not _IDENTIFIER.fullmatch(database) or not _IDENTIFIER.fullmatch(table):
        raise QualityPredicateError("unsafe asset identifier")
    if not expression.strip() or not fields:
        raise QualityPredicateError("predicate and asset fields are required")
    try:
        statements = sqlglot.parse(expression, read="mysql")
    except sqlglot.errors.SqlglotError as exc:
        raise QualityPredicateError("invalid quality predicate") from exc
    if len(statements) != 1 or statements[0] is None:
        raise QualityPredicateError("one quality predicate is required")
    predicate = statements[0]
    allowed_fields = {name.lower() for name in fields}
    referenced_fields = 0
    for node in predicate.walk():
        if not isinstance(node, _ALLOWED_NODES):
            raise QualityPredicateError(f"unsupported predicate element: {type(node).__name__}")
        if isinstance(node, exp.Column):
            if node.table or node.db or node.name.lower() not in allowed_fields:
                raise QualityPredicateError("predicate references a field outside the asset")
            referenced_fields += 1
    if not referenced_fields:
        raise QualityPredicateError("predicate must reference an asset field")
    predicate_sql = predicate.sql(dialect="mysql")
    return (
        "SELECT COUNT(*) AS checked_rows, "
        f"COALESCE(SUM(CASE WHEN ({predicate_sql}) THEN 0 ELSE 1 END), 0) AS failed_rows "
        f"FROM `{database}`.`{table}`"
    )


def parse_quality_counts(result: dict[str, Any]) -> tuple[int, int]:
    if result.get("truncated") or result.get("columns") != ["checked_rows", "failed_rows"]:
        raise QualityPredicateError("DBX returned an unexpected quality count result")
    rows = result.get("rows")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], list) or len(rows[0]) != 2:
        raise QualityPredicateError("DBX returned an unexpected quality count result")
    try:
        checked, failed = (int(value) for value in rows[0])
    except (TypeError, ValueError) as exc:
        raise QualityPredicateError("DBX returned invalid quality counts") from exc
    if checked < 0 or failed < 0 or failed > checked:
        raise QualityPredicateError("DBX returned inconsistent quality counts")
    return checked, failed
