from __future__ import annotations

from rebuild.sql_ide.diagnostics import (
    from_linter_result,
    from_preflight_error,
    from_split_error,
)


def test_linter_diagnostic_is_mapped_to_the_shared_envelope() -> None:
    result = {
        "valid": False,
        "diagnostics": [
            {
                "stmtIndex": 2,
                "line": 4,
                "column": 9,
                "severity": "error",
                "code": "SQL_SYNTAX_ERROR",
                "message": "SQL syntax is invalid",
            }
        ],
    }

    assert from_linter_result(result) == [
        {
            "severity": "error",
            "code": "SQL_SYNTAX_ERROR",
            "location": {"statement_index": 2, "line": 4, "column": 9},
            "rule": None,
            "message": "SQL syntax is invalid",
        }
    ]


def test_linter_diagnostic_without_position_keeps_location_empty() -> None:
    result = {
        "valid": False,
        "diagnostics": [
            {"severity": "error", "code": "SQL_EMPTY", "message": "SQL text is required"}
        ],
    }

    assert from_linter_result(result)[0]["location"] is None


def test_preflight_and_split_failures_use_the_same_envelope_shape() -> None:
    preflight = from_preflight_error(ValueError("SQL batch cannot be classified as read-only"))
    split = from_split_error(ValueError("unterminated quoted string"))

    assert preflight == {
        "severity": "error",
        "code": "SQL_READONLY_PREFLIGHT_REJECTED",
        "location": None,
        "rule": "readonly_preflight",
        "message": "SQL batch cannot be classified as read-only",
    }
    assert split == {
        "severity": "error",
        "code": "SQL_STATEMENT_SPLIT_FAILED",
        "location": None,
        "rule": "statement_splitter",
        "message": "unterminated quoted string",
    }
