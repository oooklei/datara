from __future__ import annotations

import pytest

from rebuild.sql_ide.statement_splitter import (
    StatementSplitError,
    split_sql_statements,
)


def test_splits_only_on_delimiters_outside_comments_and_quoted_text():
    sql = """SELECT 'one; two', `semi;colon` /* ; ignored */;
-- ; ignored too
SELECT \"semi;column\" FROM t;"""

    statements = split_sql_statements(sql, dialect="mysql")

    assert [statement.sql for statement in statements] == [
        "SELECT 'one; two', `semi;colon` /* ; ignored */",
        '-- ; ignored too\nSELECT "semi;column" FROM t',
    ]


def test_keeps_postgres_dollar_quoted_function_body_as_one_statement():
    sql = """CREATE FUNCTION f() RETURNS text AS $body$
BEGIN
  RETURN 'a;b';
END
$body$ LANGUAGE plpgsql;
SELECT 1;"""

    statements = split_sql_statements(sql, dialect="postgres")

    assert len(statements) == 2
    assert statements[0].sql.startswith("CREATE FUNCTION f()")
    assert "RETURN 'a;b';" in statements[0].sql
    assert statements[1].sql == "SELECT 1"


def test_honors_mysql_delimiter_directive_for_compound_routine_body():
    sql = """DELIMITER //
CREATE PROCEDURE p()
BEGIN
  SELECT 'inside;body';
  SELECT 2;
END//
DELIMITER ;
SELECT 3;"""

    statements = split_sql_statements(sql, dialect="mysql")

    assert [statement.sql for statement in statements] == [
        "CREATE PROCEDURE p()\nBEGIN\n  SELECT 'inside;body';\n  SELECT 2;\nEND",
        "SELECT 3",
    ]


@pytest.mark.parametrize(
    ("sql", "dialect"),
    [
        ("SELECT 'unfinished; SELECT 2", "mysql"),
        ("SELECT 1 /* unfinished", "mysql"),
        ("SELECT $$unfinished; SELECT 2", "postgres"),
        ("SELECT 1;\nDELIMITER", "mysql"),
    ],
)
def test_fails_closed_for_malformed_input_without_returning_partial_batch(sql: str, dialect: str):
    with pytest.raises(StatementSplitError):
        split_sql_statements(sql, dialect=dialect)


def test_rejects_unclosed_compound_block_with_custom_delimiter():
    with pytest.raises(StatementSplitError):
        split_sql_statements(
            "DELIMITER //\nCREATE PROCEDURE p() BEGIN SELECT 1; //",
            dialect="mysql",
        )
