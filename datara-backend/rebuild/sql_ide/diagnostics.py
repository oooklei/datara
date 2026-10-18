"""Shared diagnostic envelope for SQL IDE analysis and preflight stages."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _location(source: Mapping[str, Any]) -> dict[str, Any] | None:
    value = source.get("location")
    if isinstance(value, Mapping):
        location = {
            "statement_index": value.get("statement_index", value.get("stmtIndex")),
            "line": value.get("line"),
            "column": value.get("column"),
        }
    else:
        location = {
            "statement_index": source.get("statement_index", source.get("stmtIndex")),
            "line": source.get("line"),
            "column": source.get("column"),
        }
    location = {key: item for key, item in location.items() if item is not None}
    return location or None


def normalize_diagnostic(source: Mapping[str, Any]) -> dict[str, Any]:
    """Convert a linter, preflight, or splitter diagnostic to the shared shape."""

    result = {
        "severity": source.get("severity", "error"),
        "code": source.get("code"),
        "location": _location(source),
        "rule": source.get("rule"),
    }
    if "message" in source:
        result["message"] = source["message"]
    return result


def from_linter_result(result: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Adapt the existing ``lint_sql`` result without changing its producer."""

    diagnostics = result.get("diagnostics", ())
    return [normalize_diagnostic(item) for item in diagnostics if isinstance(item, Mapping)]


def _stage_error(error: BaseException, *, code: str, rule: str) -> dict[str, Any]:
    return normalize_diagnostic(
        {
            "severity": "error",
            "code": code,
            "location": None,
            "rule": rule,
            "message": str(error),
        }
    )


def from_preflight_error(error: BaseException) -> dict[str, Any]:
    """Represent a fail-closed read-only preflight rejection."""

    return _stage_error(
        error,
        code="SQL_READONLY_PREFLIGHT_REJECTED",
        rule="readonly_preflight",
    )


def from_split_error(error: BaseException) -> dict[str, Any]:
    """Represent a statement splitting failure that rejects the whole batch."""

    return _stage_error(
        error,
        code="SQL_STATEMENT_SPLIT_FAILED",
        rule="statement_splitter",
    )
