"""Tests for rebuild.run_sql PoC read-only gate.

These are non-production tests (P2-2 partial unfreeze #257): they test the
existing conservative read-only gate, not the future R5-A backend.
"""

from __future__ import annotations

import pytest

from rebuild.run_sql import (
    SqlExecutionError,
    SqlExecutionFailed,
    SqlExecutionTimeout,
    SqlDependencyUnavailable,
    SqlExecutionCancelled,
    evaluate_readonly_sql,
)


class TestEvaluateReadonlySql:
    """PoC read-only gate: only single SELECT statements pass."""

    def test_simple_select_passes(self):
        allowed, violations = evaluate_readonly_sql("SELECT 1")
        assert allowed
        assert violations == []

    def test_select_from_table_passes(self):
        allowed, violations = evaluate_readonly_sql("SELECT id, name FROM users WHERE id = 1")
        assert allowed
        assert violations == []

    def test_insert_rejected(self):
        allowed, violations = evaluate_readonly_sql("INSERT INTO users (name) VALUES ('test')")
        assert not allowed
        assert any(v["code"] == "not_readonly_select" for v in violations)

    def test_update_rejected(self):
        allowed, violations = evaluate_readonly_sql("UPDATE users SET name = 'test' WHERE id = 1")
        assert not allowed
        assert any(v["code"] == "not_readonly_select" for v in violations)

    def test_delete_rejected(self):
        allowed, violations = evaluate_readonly_sql("DELETE FROM users WHERE id = 1")
        assert not allowed
        assert any(v["code"] == "not_readonly_select" for v in violations)

    def test_create_table_rejected(self):
        allowed, violations = evaluate_readonly_sql("CREATE TABLE t (id INT)")
        assert not allowed
        assert any(v["code"] == "not_readonly_select" for v in violations)

    def test_multiple_statements_rejected(self):
        allowed, violations = evaluate_readonly_sql("SELECT 1; SELECT 2")
        assert not allowed
        assert any(v["code"] == "statement_count_invalid" for v in violations)

    def test_dangerous_into_rejected(self):
        allowed, violations = evaluate_readonly_sql("SELECT * INTO new_table FROM users")
        assert not allowed
        assert any(v["code"] == "dangerous_pattern" for v in violations)

    def test_dangerous_for_update_rejected(self):
        allowed, violations = evaluate_readonly_sql("SELECT * FROM users WHERE id = 1 FOR UPDATE")
        assert not allowed
        assert any(v["code"] == "dangerous_pattern" for v in violations)

    def test_dangerous_pragma_rejected(self):
        allowed, violations = evaluate_readonly_sql("PRAGMA table_info(users)")
        assert not allowed
        assert any(v["code"] == "dangerous_pattern" for v in violations)

    def test_unterminated_quote_rejected(self):
        allowed, violations = evaluate_readonly_sql("SELECT * FROM users WHERE name = 'unterminated")
        assert not allowed
        assert any(v["code"] == "unterminated_quoted_value" for v in violations)

    def test_select_with_passes(self):
        """WITH CTE passes only if it starts with SELECT."""
        allowed, violations = evaluate_readonly_sql("SELECT * FROM (SELECT 1) t")
        assert allowed

    def test_explain_rejected(self):
        """EXPLAIN does not start with SELECT."""
        allowed, violations = evaluate_readonly_sql("EXPLAIN SELECT * FROM users")
        assert not allowed
        assert any(v["code"] == "not_readonly_select" for v in violations)


class TestRunSqlErrorTypes:
    """Error type hierarchy for run_sql execution."""

    def test_sql_execution_error_base(self):
        err = SqlExecutionError("test error", details={"key": "value"})
        assert str(err) == "test error"
        assert err.details == {"key": "value"}

    def test_timeout_is_sql_execution_error(self):
        assert issubclass(SqlExecutionTimeout, SqlExecutionError)

    def test_cancelled_is_sql_execution_error(self):
        assert issubclass(SqlExecutionCancelled, SqlExecutionError)

    def test_dependency_unavailable_is_sql_execution_error(self):
        assert issubclass(SqlDependencyUnavailable, SqlExecutionError)

    def test_failed_is_sql_execution_error(self):
        assert issubclass(SqlExecutionFailed, SqlExecutionError)
