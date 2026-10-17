"""Sample SQL queries for P2-2 testing.

Non-production fixtures (P2-2 partial unfreeze #257): these are test inputs
for the PoC read-only gate and future R5-A backend tests.
"""

from __future__ import annotations


class SampleQueries:
    """Valid and invalid SQL samples for read-only gate testing."""

    VALID_SINGLE_SELECT = "SELECT 1"
    VALID_SELECT_FROM_TABLE = "SELECT id, name FROM users WHERE id = 1"
    VALID_SELECT_WITH_JOIN = "SELECT u.id, u.name FROM users u JOIN orders o ON u.id = o.user_id"
    VALID_SELECT_WITH_SUBQUERY = "SELECT * FROM (SELECT 1) t"
    VALID_SELECT_STAR = "SELECT * FROM users"

    INVALID_INSERT = "INSERT INTO users (name) VALUES ('test')"
    INVALID_UPDATE = "UPDATE users SET name = 'test' WHERE id = 1"
    INVALID_DELETE = "DELETE FROM users WHERE id = 1"
    INVALID_CREATE_TABLE = "CREATE TABLE t (id INT)"
    INVALID_DROP_TABLE = "DROP TABLE users"
    INVALID_ALTER_TABLE = "ALTER TABLE users ADD COLUMN email VARCHAR(255)"
    INVALID_TRUNCATE = "TRUNCATE TABLE users"

    DANGEROUS_INTO = "SELECT * INTO new_table FROM users"
    DANGEROUS_FOR_UPDATE = "SELECT * FROM users WHERE id = 1 FOR UPDATE"
    DANGEROUS_PRAGMA = "PRAGMA table_info(users)"
    DANGEROUS_SLEEP = "SELECT SLEEP(5)"
    DANGEROUS_BENCHMARK = "SELECT BENCHMARK(1000000, MD5('test'))"

    MULTIPLE_STATEMENTS = "SELECT 1; SELECT 2"
    UNTERMINATED_QUOTE = "SELECT * FROM users WHERE name = 'unterminated"
    UNTERMINATED_COMMENT = "SELECT /* unterminated"
    BACKSLASH_ESCAPE = r"SELECT 'a\b'"
    EXECUTABLE_COMMENT = "SELECT /*!50000 1 */"


class ExpectedGates:
    """Expected gate results for sample queries."""

    VALID_COUNT = 5
    INVALID_COUNT = 10
    DANGEROUS_COUNT = 5
    SPECIAL_COUNT = 5

    ALL_VALID = [
        SampleQueries.VALID_SINGLE_SELECT,
        SampleQueries.VALID_SELECT_FROM_TABLE,
        SampleQueries.VALID_SELECT_WITH_JOIN,
        SampleQueries.VALID_SELECT_WITH_SUBQUERY,
        SampleQueries.VALID_SELECT_STAR,
    ]

    ALL_INVALID = [
        SampleQueries.INVALID_INSERT,
        SampleQueries.INVALID_UPDATE,
        SampleQueries.INVALID_DELETE,
        SampleQueries.INVALID_CREATE_TABLE,
        SampleQueries.INVALID_DROP_TABLE,
        SampleQueries.INVALID_ALTER_TABLE,
        SampleQueries.INVALID_TRUNCATE,
    ]

    ALL_DANGEROUS = [
        SampleQueries.DANGEROUS_INTO,
        SampleQueries.DANGEROUS_FOR_UPDATE,
        SampleQueries.DANGEROUS_PRAGMA,
        SampleQueries.DANGEROUS_SLEEP,
        SampleQueries.DANGEROUS_BENCHMARK,
    ]
