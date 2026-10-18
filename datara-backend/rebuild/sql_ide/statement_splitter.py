"""Lexical SQL statement splitting before policy validation or execution."""

from __future__ import annotations

import re
from dataclasses import dataclass


class StatementSplitError(ValueError):
    """Raised when SQL boundaries cannot be determined safely."""


@dataclass(frozen=True)
class SqlStatement:
    """One complete SQL statement, retaining its original internal syntax."""

    index: int
    sql: str


_DIALECT_ALIASES = {"postgresql": "postgres", "mariadb": "mysql"}
_DOLLAR_QUOTE = re.compile(r"\$[A-Za-z_][A-Za-z_0-9]*\$|\$\$")
_DELIMITER_DIRECTIVE = re.compile(r"\s*DELIMITER\s+(\S+)\s*", re.IGNORECASE)


def split_sql_statements(sql: str, *, dialect: str) -> tuple[SqlStatement, ...]:
    """Split a SQL batch at lexical statement boundaries.

    Quoted text, identifiers, comments, PostgreSQL dollar-quoted bodies and
    MySQL client delimiters are respected. Malformed lexical or compound-block
    input raises before any partial statement collection is returned.
    Read-only policy remains the responsibility of ``readonly_preflight``.
    """

    if not isinstance(sql, str) or not isinstance(dialect, str) or not dialect.strip():
        raise StatementSplitError("SQL and dialect are required")

    dialect_name = _DIALECT_ALIASES.get(dialect.lower(), dialect.lower())
    mysql = dialect_name == "mysql"
    postgres = dialect_name == "postgres"
    delimiter = ";"
    custom_delimiter = False
    statements: list[SqlStatement] = []
    buffer: list[str] = []
    state: str | None = None
    dollar_tag: str | None = None
    block_comment_depth = 0
    compound_depth = 0
    token: list[str] = []
    i = 0

    def flush_token() -> None:
        nonlocal compound_depth
        if not token:
            return
        word = "".join(token).upper()
        token.clear()
        if mysql and custom_delimiter:
            if word == "BEGIN":
                compound_depth += 1
            elif word == "END":
                compound_depth -= 1
                if compound_depth < 0:
                    raise StatementSplitError("unbalanced compound block")

    def emit_statement() -> None:
        flush_token()
        content = "".join(buffer).strip()
        buffer.clear()
        if content:
            statements.append(SqlStatement(index=len(statements), sql=content))

    while i < len(sql):
        char = sql[i]

        if state is None and block_comment_depth == 0:
            line_start = sql.rfind("\n", 0, i) + 1
            if i == line_start or not sql[line_start:i].strip():
                line_end = sql.find("\n", i)
                if line_end < 0:
                    line_end = len(sql)
                line = sql[i:line_end]
                directive = _DELIMITER_DIRECTIVE.fullmatch(line)
                if mysql and directive:
                    flush_token()
                    if "".join(buffer).strip():
                        raise StatementSplitError("DELIMITER directive inside unfinished statement")
                    delimiter = directive.group(1)
                    if any(ch.isspace() for ch in delimiter):
                        raise StatementSplitError("invalid delimiter")
                    custom_delimiter = delimiter != ";"
                    compound_depth = 0
                    i = line_end + (line_end < len(sql))
                    continue
                if mysql and line.strip().upper() == "DELIMITER":
                    raise StatementSplitError("invalid DELIMITER directive")

        if state is None and block_comment_depth == 0 and sql.startswith(delimiter, i):
            flush_token()
            if custom_delimiter and compound_depth:
                raise StatementSplitError("unclosed compound block")
            emit_statement()
            i += len(delimiter)
            continue

        if state == "line_comment":
            buffer.append(char)
            i += 1
            if char == "\n":
                state = None
            continue

        if block_comment_depth:
            if sql.startswith("/*", i):
                block_comment_depth += 1
                buffer.append("/*")
                i += 2
            elif sql.startswith("*/", i):
                block_comment_depth -= 1
                buffer.append("*/")
                i += 2
                if block_comment_depth == 0:
                    state = None
            else:
                buffer.append(char)
                i += 1
            continue

        if state in {"single", "double", "backtick", "bracket", "dollar"}:
            if state == "dollar":
                if sql.startswith(dollar_tag or "", i):
                    buffer.append(dollar_tag or "")
                    i += len(dollar_tag or "")
                    state = None
                    dollar_tag = None
                else:
                    buffer.append(char)
                    i += 1
                continue

            closing = {"single": "'", "double": '"', "backtick": "`", "bracket": "]"}[state]
            buffer.append(char)
            i += 1
            if char == "\\" and mysql and state in {"single", "double"} and i < len(sql):
                buffer.append(sql[i])
                i += 1
            elif char == closing:
                if i < len(sql) and sql[i] == closing:
                    buffer.append(sql[i])
                    i += 1
                else:
                    state = None
            continue

        if sql.startswith("--", i):
            flush_token()
            buffer.append("--")
            i += 2
            state = "line_comment"
            continue
        if mysql and char == "#":
            flush_token()
            buffer.append(char)
            i += 1
            state = "line_comment"
            continue
        if sql.startswith("/*", i):
            flush_token()
            buffer.append("/*")
            i += 2
            block_comment_depth = 1
            state = "block_comment"
            continue

        if postgres and char == "$":
            match = _DOLLAR_QUOTE.match(sql, i)
            if match:
                flush_token()
                dollar_tag = match.group(0)
                buffer.append(dollar_tag)
                i = match.end()
                state = "dollar"
                continue

        if char == "'":
            flush_token()
            buffer.append(char)
            i += 1
            state = "single"
            continue
        if char == '"':
            flush_token()
            buffer.append(char)
            i += 1
            state = "double"
            continue
        if mysql and char == "`":
            flush_token()
            buffer.append(char)
            i += 1
            state = "backtick"
            continue
        if dialect_name in {"tsql", "sqlserver", "mssql"} and char == "[":
            flush_token()
            buffer.append(char)
            i += 1
            state = "bracket"
            continue

        if char.isalpha() or char == "_":
            token.append(char)
        else:
            flush_token()
        buffer.append(char)
        i += 1

    if state in {"single", "double", "backtick", "bracket", "dollar"} or block_comment_depth:
        raise StatementSplitError("unterminated quoted text or comment")
    flush_token()
    if custom_delimiter and compound_depth:
        raise StatementSplitError("unclosed compound block")
    if "".join(buffer).strip():
        emit_statement()
    return tuple(statements)
