from __future__ import annotations

from rebuild.sql_ide.linter import lint_sql


def test_lint_sql_accepts_valid_sql_for_requested_dialect() -> None:
    result = lint_sql("SELECT `name` FROM users", dialect="mysql")

    assert result == {"valid": True, "diagnostics": []}


def test_lint_sql_accepts_driver_postgresql_dialect_name() -> None:
    result = lint_sql("SELECT 1", dialect="postgresql")

    assert result == {"valid": True, "diagnostics": []}


def test_lint_sql_reports_syntax_errors_without_throwing() -> None:
    result = lint_sql("SELECT FROM", dialect="postgres")

    assert result["valid"] is False
    assert result["diagnostics"] == [
        {
            "stmtIndex": 0,
            "line": 1,
            "column": 11,
            "severity": "error",
            "code": "SQL_SYNTAX_ERROR",
            "message": "SQL syntax is invalid for the requested dialect",
        }
    ]


def test_lint_sql_reports_each_invalid_statement_with_statement_index() -> None:
    result = lint_sql("SELECT 1;\nSELECT FROM;\nSELECT (", dialect="postgres")

    assert result["valid"] is False
    diagnostics = result["diagnostics"]
    assert [item["stmtIndex"] for item in diagnostics] == [1, 2]
    assert [item["line"] for item in diagnostics] == [2, 3]
    assert all(item["severity"] == "error" for item in diagnostics)
    assert all(item["line"] is not None and item["column"] is not None for item in diagnostics)
    assert all(item["code"] == "SQL_SYNTAX_ERROR" for item in diagnostics)


def test_lint_sql_reports_tokenization_errors_as_static_diagnostics() -> None:
    result = lint_sql("SELECT 'unterminated", dialect="postgres")

    assert result["valid"] is False
    assert result["diagnostics"][0]["code"] == "SQL_SYNTAX_ERROR"
    assert result["diagnostics"][0]["stmtIndex"] == 0
    assert result["diagnostics"][0]["line"] == 1


def test_lint_sql_reports_empty_input() -> None:
    result = lint_sql("  ", dialect="postgres")

    assert result == {
        "valid": False,
        "diagnostics": [
            {
                "stmtIndex": None,
                "code": "SQL_EMPTY",
                "message": "SQL text is required",
                "line": None,
                "column": None,
                "severity": "error",
            }
        ],
    }


def test_lint_sql_reports_delimiter_only_input_as_empty() -> None:
    result = lint_sql(";;;", dialect="postgres")

    assert result["valid"] is False
    assert result["diagnostics"][0]["code"] == "SQL_EMPTY"


def test_lint_sql_reports_unsupported_dialect() -> None:
    result = lint_sql("SELECT 1", dialect="not-a-dialect")

    assert result["valid"] is False
    assert result["diagnostics"][0]["code"] == "SQL_UNSUPPORTED_DIALECT"
