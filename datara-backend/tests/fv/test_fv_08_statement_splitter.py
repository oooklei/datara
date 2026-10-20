"""FV-08 R5-A 语句切分与诊断 envelope 终验。

验收标准（草案）：
- 完整语句边界切分（注释/字符串/分隔符/方言块）
- 切分失败 fail-closed 拒绝整批
- 选区半条语句不得悄然独立执行
- 诊断统一 envelope severity/code/location/rule

测试策略：全部 mock/内存，禁真实写库。
"""

from __future__ import annotations

import pytest

from rebuild.sql_ide.diagnostics import (
    from_preflight_error,
    from_split_error,
    normalize_diagnostic,
)
from rebuild.sql_ide.readonly_preflight import ReadonlyBatchPreflightError
from rebuild.sql_ide.statement_splitter import (
    SqlStatement,
    StatementSplitError,
    split_sql_statements,
)


class TestStatementSplit:
    """split_sql_statements 语句边界切分。"""

    def test_simple_split(self):
        statements = split_sql_statements("SELECT 1; SELECT 2", dialect="mysql")
        assert len(statements) == 2
        assert statements[0].index == 0
        assert statements[1].index == 1

    def test_single_statement(self):
        statements = split_sql_statements("SELECT 1", dialect="mysql")
        assert len(statements) == 1

    def test_trailing_semicolon(self):
        statements = split_sql_statements("SELECT 1;", dialect="mysql")
        assert len(statements) == 1

    def test_multiple_semicolons(self):
        statements = split_sql_statements("SELECT 1;; SELECT 2", dialect="mysql")
        assert len(statements) == 2

    def test_string_literal_with_semicolon(self):
        """字符串内的分号不切分。"""
        statements = split_sql_statements("SELECT 'a;b'", dialect="mysql")
        assert len(statements) == 1
        assert "a;b" in statements[0].sql

    def test_double_quoted_string_with_semicolon(self):
        statements = split_sql_statements('SELECT "a;b"', dialect="mysql")
        assert len(statements) == 1

    def test_backtick_identifier_with_semicolon(self):
        statements = split_sql_statements("SELECT `a;b`", dialect="mysql")
        assert len(statements) == 1

    def test_line_comment_with_semicolon(self):
        statements = split_sql_statements("SELECT 1 -- comment; more\n", dialect="mysql")
        assert len(statements) == 1

    def test_hash_comment_mysql(self):
        statements = split_sql_statements("SELECT 1 # comment; more\n", dialect="mysql")
        assert len(statements) == 1

    def test_block_comment_with_semicolon(self):
        statements = split_sql_statements("SELECT /* comment; */ 1", dialect="mysql")
        assert len(statements) == 1

    def test_nested_block_comment(self):
        statements = split_sql_statements("SELECT /* outer /* inner */ still */ 1", dialect="mysql")
        assert len(statements) == 1

    def test_postgresql_dollar_quote(self):
        statements = split_sql_statements("SELECT $$hello; world$$", dialect="postgresql")
        assert len(statements) == 1

    def test_postgresql_dollar_tag(self):
        statements = split_sql_statements("SELECT $tag$hello; world$tag$", dialect="postgresql")
        assert len(statements) == 1

    def test_mysql_delimiter(self):
        """DELIMITER 指令单独一行时切换分隔符。"""
        sql = "SELECT 1;\n//\nSELECT 2\n//"
        statements = split_sql_statements(sql, dialect="mysql")
        assert len(statements) == 2

    def test_mysql_begin_end_block(self):
        """BEGIN...END 块内的分号不切分（需 DELIMITER 模式）。"""
        sql = "DELIMITER //\nBEGIN; SELECT 1; SELECT 2; END//"
        statements = split_sql_statements(sql, dialect="mysql")
        assert len(statements) == 1

    def test_empty_input(self):
        statements = split_sql_statements("", dialect="mysql")
        assert len(statements) == 0

    def test_whitespace_only(self):
        statements = split_sql_statements("   \n  ", dialect="mysql")
        assert len(statements) == 0


class TestStatementSplitFailClosed:
    """切分失败 fail-closed 拒绝整批。"""

    def test_unterminated_single_quote(self):
        with pytest.raises(StatementSplitError):
            split_sql_statements("SELECT 'unterminated", dialect="mysql")

    def test_unterminated_double_quote(self):
        with pytest.raises(StatementSplitError):
            split_sql_statements('SELECT "unterminated', dialect="mysql")

    def test_unterminated_backtick(self):
        with pytest.raises(StatementSplitError):
            split_sql_statements("SELECT `unterminated", dialect="mysql")

    def test_unterminated_block_comment(self):
        with pytest.raises(StatementSplitError):
            split_sql_statements("SELECT /* unterminated", dialect="mysql")

    def test_unterminated_dollar_quote(self):
        with pytest.raises(StatementSplitError):
            split_sql_statements("SELECT $$unterminated", dialect="postgresql")

    def test_invalid_sql_type(self):
        with pytest.raises(StatementSplitError):
            split_sql_statements(None, dialect="mysql")

    def test_invalid_dialect_type(self):
        with pytest.raises(StatementSplitError):
            split_sql_statements("SELECT 1", dialect=None)

    def test_empty_dialect(self):
        with pytest.raises(StatementSplitError):
            split_sql_statements("SELECT 1", dialect="")

    def test_unbalanced_compound_block(self):
        with pytest.raises(StatementSplitError):
            split_sql_statements("DELIMITER //\nSELECT 1; END", dialect="mysql")

    def test_delimiter_inside_statement(self):
        """DELIMITER 指令出现在未完成的语句中间 → 拒绝。"""
        # SELECT 1 未完成（无分号），DELIMITER 指令在行首但 buffer 不为空
        with pytest.raises(StatementSplitError):
            split_sql_statements("SELECT 1\nDELIMITER //\nSELECT 2", dialect="mysql")


class TestDiagnosticEnvelope:
    """诊断统一 envelope severity/code/location/rule。"""

    def test_normalize_diagnostic_full(self):
        source = {
            "severity": "error",
            "code": "SQL_SYNTAX_ERROR",
            "location": {"statement_index": 0, "line": 1, "column": 5},
            "rule": "syntax_check",
            "message": "bad syntax",
        }
        result = normalize_diagnostic(source)
        assert result["severity"] == "error"
        assert result["code"] == "SQL_SYNTAX_ERROR"
        assert result["location"]["line"] == 1
        assert result["rule"] == "syntax_check"
        assert result["message"] == "bad syntax"

    def test_normalize_diagnostic_minimal(self):
        result = normalize_diagnostic({"code": "SOME_CODE"})
        assert result["severity"] == "error"
        assert result["code"] == "SOME_CODE"
        assert result["location"] is None

    def test_normalize_diagnostic_stmt_index_alias(self):
        source = {"stmtIndex": 2}
        result = normalize_diagnostic(source)
        assert result["location"]["statement_index"] == 2

    def test_from_preflight_error(self):
        error = ReadonlyBatchPreflightError("cannot classify")
        diag = from_preflight_error(error)
        assert diag["severity"] == "error"
        assert diag["code"] == "SQL_READONLY_PREFLIGHT_REJECTED"
        assert diag["rule"] == "readonly_preflight"
        assert diag["location"] is None

    def test_from_split_error(self):
        error = StatementSplitError("unterminated")
        diag = from_split_error(error)
        assert diag["severity"] == "error"
        assert diag["code"] == "SQL_STATEMENT_SPLIT_FAILED"
        assert diag["rule"] == "statement_splitter"
        assert diag["location"] is None


class TestBatchExecutorPreflight:
    """BatchSqlExecutor 切分后 preflight 整批拒绝。"""

    def test_batch_rejects_write_statement(self):
        """批次含写语句 → 整批拒绝，不执行任何语句。"""
        from rebuild.sql_ide.batch_executor import BatchSqlExecutor

        class _FakeSession:
            def execute(self, **kwargs):
                raise AssertionError("should not execute")

        class _FakeStore:
            def save_snapshot(self, **kwargs):
                return "rs1"

        executor = BatchSqlExecutor(
            execution_session=_FakeSession(),
            result_page_store=_FakeStore(),
        )
        with pytest.raises(ReadonlyBatchPreflightError):
            executor.execute_batch(
                project_id=1,
                user_id=2,
                datasource_id=3,
                history_id="h1",
                sql="SELECT 1; INSERT INTO t VALUES (1)",
                dialect="mysql",
                mode="auto",
                row_limit=100,
                timeout_ms=5000,
            )

    def test_batch_rejects_empty_batch(self):
        from rebuild.sql_ide.batch_executor import BatchSqlExecutor
        from rebuild.sql_ide.readonly_preflight import ReadonlyBatchPreflightError

        class _FakeSession:
            def execute(self, **kwargs):
                raise AssertionError("should not execute")

        class _FakeStore:
            def save_snapshot(self, **kwargs):
                return "rs1"

        executor = BatchSqlExecutor(
            execution_session=_FakeSession(),
            result_page_store=_FakeStore(),
        )
        with pytest.raises(ReadonlyBatchPreflightError):
            executor.execute_batch(
                project_id=1,
                user_id=2,
                datasource_id=3,
                history_id="h1",
                sql="",
                dialect="mysql",
                mode="auto",
                row_limit=100,
                timeout_ms=5000,
            )

    def test_batch_rejects_non_auto_mode(self):
        from rebuild.sql_ide.batch_executor import BatchSqlExecutor

        class _FakeSession:
            def execute(self, **kwargs):
                raise AssertionError("should not execute")

        class _FakeStore:
            def save_snapshot(self, **kwargs):
                return "rs1"

        executor = BatchSqlExecutor(
            execution_session=_FakeSession(),
            result_page_store=_FakeStore(),
        )
        with pytest.raises(ValueError, match="mode=auto"):
            executor.execute_batch(
                project_id=1,
                user_id=2,
                datasource_id=3,
                history_id="h1",
                sql="SELECT 1",
                dialect="mysql",
                mode="manual",
                row_limit=100,
                timeout_ms=5000,
            )

    def test_batch_rejects_invalid_history_id(self):
        from rebuild.sql_ide.batch_executor import BatchSqlExecutor

        class _FakeSession:
            def execute(self, **kwargs):
                raise AssertionError("should not execute")

        class _FakeStore:
            def save_snapshot(self, **kwargs):
                return "rs1"

        executor = BatchSqlExecutor(
            execution_session=_FakeSession(),
            result_page_store=_FakeStore(),
        )
        with pytest.raises(ValueError, match="history_id"):
            executor.execute_batch(
                project_id=1,
                user_id=2,
                datasource_id=3,
                history_id="",
                sql="SELECT 1",
                dialect="mysql",
                mode="auto",
                row_limit=100,
                timeout_ms=5000,
            )
