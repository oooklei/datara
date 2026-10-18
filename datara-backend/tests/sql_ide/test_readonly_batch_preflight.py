from __future__ import annotations

import pytest

from rebuild.sql_ide.readonly_preflight import ReadonlyBatchPreflightError, preflight_readonly_batch


def test_accepts_read_only_select_batch():
    statements = preflight_readonly_batch(
        "SELECT id FROM users; SELECT count(*) FROM orders",
        dialect="mysql",
    )

    assert len(statements) == 2
    assert all(statement.sql for statement in statements)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id FROM users; DELETE FROM users",
        "SELECT id FROM users; UPDATE users SET active = 0",
        "SELECT id FROM users; CREATE TABLE x (id INT)",
        "SELECT id FROM users; nonsense ???",
    ],
)
def test_rejects_entire_batch_before_returning_any_statement(sql: str):
    with pytest.raises(ReadonlyBatchPreflightError):
        preflight_readonly_batch(sql, dialect="mysql")


def test_rejects_locking_select():
    with pytest.raises(ReadonlyBatchPreflightError):
        preflight_readonly_batch("SELECT id FROM users FOR UPDATE", dialect="mysql")


def test_rejects_unclassified_function_calls():
    with pytest.raises(ReadonlyBatchPreflightError):
        preflight_readonly_batch("SELECT application_side_effect()", dialect="mysql")


def test_rejects_empty_or_comment_only_batch():
    with pytest.raises(ReadonlyBatchPreflightError):
        preflight_readonly_batch("-- no statement", dialect="mysql")
