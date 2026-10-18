"""Read-only SQL syntax and dialect diagnostics backed by sqlglot."""

from __future__ import annotations

from typing import Any

import sqlglot

_DIALECT_ALIASES = {"postgresql": "postgres"}


def _diagnostic(
    code: str,
    message: str,
    *,
    stmt_index: int | None = None,
    line: int | None = None,
    column: int | None = None,
) -> dict[str, Any]:
    return {
        "stmtIndex": stmt_index,
        "line": line,
        "column": column,
        "severity": "error",
        "code": code,
        "message": message,
    }


def _statement_spans(sql: str, dialect_name: str) -> list[tuple[int, str]]:
    """Split on sqlglot semicolon tokens, never on semicolons inside literals/comments."""

    dialect_type = sqlglot.Dialect.get_or_raise(dialect_name)
    tokens = dialect_type.tokenize(sql)
    spans: list[tuple[int, str]] = []
    start = 0
    for token in tokens:
        if token.token_type.name != "SEMICOLON":
            continue
        spans.append((start, sql[start : token.start]))
        start = token.end + 1
    spans.append((start, sql[start:]))
    return spans


def _global_position(
    sql: str, start: int, line: int | None, column: int | None
) -> tuple[int | None, int | None]:
    if line is None or column is None:
        return line, column
    prefix = sql[:start]
    global_line = prefix.count("\n") + line
    if line == 1:
        column += len(prefix.rsplit("\n", 1)[-1])
    return global_line, column


def lint_sql(sql: str, *, dialect: str) -> dict[str, Any]:
    """Parse SQL for the requested dialect without executing or connecting.

    The function is intentionally limited to static syntax diagnostics. It does
    not consult a datasource, execute statements, or apply read-only policy.
    """

    if not isinstance(sql, str) or not sql.strip():
        return {
            "valid": False,
            "diagnostics": [_diagnostic("SQL_EMPTY", "SQL text is required")],
        }
    if not isinstance(dialect, str) or not dialect.strip():
        return {
            "valid": False,
            "diagnostics": [
                _diagnostic("SQL_UNSUPPORTED_DIALECT", "A supported SQL dialect is required")
            ],
        }

    requested_dialect = dialect.strip().lower()
    dialect_name = _DIALECT_ALIASES.get(requested_dialect, requested_dialect)
    try:
        spans = _statement_spans(sql, dialect_name)
    except sqlglot.errors.TokenError as exc:
        offset = exc.start if exc.start is not None else len(sql)
        prefix = sql[:offset]
        try:
            prefix_tokens = sqlglot.Dialect.get_or_raise(dialect_name).tokenize(prefix)
            stmt_index = sum(token.token_type.name == "SEMICOLON" for token in prefix_tokens)
        except sqlglot.errors.TokenError:
            stmt_index = 0
        line = prefix.count("\n") + 1
        column = len(prefix.rsplit("\n", 1)[-1]) + 1
        return {
            "valid": False,
            "diagnostics": [
                _diagnostic(
                    "SQL_SYNTAX_ERROR",
                    "SQL syntax is invalid for the requested dialect",
                    stmt_index=stmt_index,
                    line=line,
                    column=column,
                )
            ],
        }
    except ValueError:
        return {
            "valid": False,
            "diagnostics": [
                _diagnostic("SQL_UNSUPPORTED_DIALECT", "The requested SQL dialect is unsupported")
            ],
        }

    diagnostics: list[dict[str, Any]] = []
    stmt_index = 0
    for start, statement in spans:
        if not statement.strip():
            continue
        try:
            parsed = sqlglot.parse(statement, read=dialect_name)
        except sqlglot.errors.ParseError as exc:
            details = getattr(exc, "errors", ())
            first = details[0] if details else {}
            line = first.get("line") if isinstance(first, dict) else None
            column = first.get("col") if isinstance(first, dict) else None
            line, column = _global_position(sql, start, line, column)
            diagnostics.append(
                _diagnostic(
                    "SQL_SYNTAX_ERROR",
                    "SQL syntax is invalid for the requested dialect",
                    stmt_index=stmt_index,
                    line=line,
                    column=column,
                )
            )
            stmt_index += 1
        else:
            if any(item is not None for item in parsed):
                stmt_index += 1

    if not diagnostics and stmt_index == 0:
        return {
            "valid": False,
            "diagnostics": [_diagnostic("SQL_EMPTY", "SQL text is required")],
        }
    if not diagnostics:
        return {"valid": True, "diagnostics": []}
    return {"valid": False, "diagnostics": diagnostics}
