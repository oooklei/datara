"""Tests for rebuild.sql_ide.ddl_policy — conservative DDL preview policy.

These are non-production tests (P2-2 partial unfreeze #257): they test the
existing conservative tokenizer and DDL policy, not the future R5-A backend.
"""

from __future__ import annotations

import pytest

from rebuild.sql_ide.ddl_policy import (
    DdlPolicyResult,
    evaluate_ddl_policy,
    sql_tokens_and_statement_count,
)


class TestSqlTokensAndStatementCount:
    """Conservative tokenizer: words outside comments/quoted values."""

    def test_simple_select(self):
        tokens, count, errors = sql_tokens_and_statement_count("SELECT 1")
        assert tokens == ["SELECT", "1"]
        assert count == 1
        assert errors == ()

    def test_multiple_statements(self):
        tokens, count, errors = sql_tokens_and_statement_count("SELECT 1; SELECT 2;")
        assert count == 2
        assert errors == ()

    def test_quoted_value_ignored(self):
        tokens, count, errors = sql_tokens_and_statement_count("SELECT 'hello world'")
        assert "HELLO" not in tokens
        assert "WORLD" not in tokens
        assert count == 1

    def test_block_comment_ignored(self):
        tokens, count, errors = sql_tokens_and_statement_count("SELECT /* comment */ 1")
        assert "COMMENT" not in tokens
        assert count == 1

    def test_unterminated_quoted_value(self):
        _, _, errors = sql_tokens_and_statement_count("SELECT 'unterminated")
        assert "unterminated_quoted_value" in errors

    def test_unterminated_block_comment(self):
        _, _, errors = sql_tokens_and_statement_count("SELECT /* unterminated")
        assert "unterminated_block_comment" in errors

    def test_backslash_escape_flagged(self):
        _, _, errors = sql_tokens_and_statement_count(r"SELECT 'a\b'")
        assert "backslash_escape_unclassified" in errors

    def test_executable_comment_flagged(self):
        _, _, errors = sql_tokens_and_statement_count("SELECT /*!50000 1 */")
        assert "executable_comment_unclassified" in errors


class TestEvaluateDdlPolicy:
    """DDL policy: block/warn findings, never opens a connection."""

    def test_create_table_passes_with_warnings(self):
        result = evaluate_ddl_policy(
            dialect="mysql",
            object_kind="table",
            current_definition=None,
            current_definition_digest=None,
            expected_definition="CREATE TABLE t (id INT)",
        )
        assert isinstance(result, DdlPolicyResult)
        assert not result.blocked
        assert any(f.code == "target_identity_unverified" for f in result.findings)

    def test_create_existing_object_blocked(self):
        result = evaluate_ddl_policy(
            dialect="mysql",
            object_kind="table",
            current_definition="CREATE TABLE t (id INT)",
            current_definition_digest="abc123",
            expected_definition="CREATE TABLE t (id INT)",
        )
        assert result.blocked
        assert any(f.code == "create_existing_object" for f in result.findings)

    def test_alter_missing_object_blocked(self):
        result = evaluate_ddl_policy(
            dialect="mysql",
            object_kind="table",
            current_definition=None,
            current_definition_digest=None,
            expected_definition="ALTER TABLE t ADD COLUMN c INT",
        )
        assert result.blocked
        assert any(f.code == "alter_missing_object" for f in result.findings)

    def test_destructive_ddl_blocked(self):
        result = evaluate_ddl_policy(
            dialect="mysql",
            object_kind="table",
            current_definition="CREATE TABLE t (id INT)",
            current_definition_digest="abc123",
            expected_definition="DROP TABLE t",
        )
        assert result.blocked
        assert any(f.code == "destructive_ddl" for f in result.findings)

    def test_unsupported_dialect_blocked(self):
        result = evaluate_ddl_policy(
            dialect="oracle",
            object_kind="table",
            current_definition=None,
            current_definition_digest=None,
            expected_definition="CREATE TABLE t (id INT)",
        )
        assert result.blocked
        assert any(f.code == "unsupported_dialect" for f in result.findings)

    def test_object_kind_mismatch_blocked(self):
        result = evaluate_ddl_policy(
            dialect="mysql",
            object_kind="table",
            current_definition=None,
            current_definition_digest=None,
            expected_definition="CREATE VIEW v AS SELECT 1",
        )
        assert result.blocked
        assert any(f.code == "object_kind_mismatch" for f in result.findings)

    def test_preimage_digest_mismatch_blocked(self):
        result = evaluate_ddl_policy(
            dialect="mysql",
            object_kind="table",
            current_definition="CREATE TABLE t (id INT)",
            current_definition_digest="wrong_digest",
            expected_definition="ALTER TABLE t ADD COLUMN c INT",
        )
        assert result.blocked
        assert any(f.code == "preimage_digest_mismatch" for f in result.findings)

    def test_drop_column_blocked(self):
        result = evaluate_ddl_policy(
            dialect="mysql",
            object_kind="table",
            current_definition="CREATE TABLE t (id INT)",
            current_definition_digest="abc123",
            expected_definition="ALTER TABLE t DROP COLUMN id",
        )
        assert result.blocked
        assert any(f.code == "drop_column" for f in result.findings)
