from types import SimpleNamespace

import pytest

from worker.executors import sql as sql_executor
from worker.state import FAILURE, SUCCESS


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.description = None
        self.rowcount = 0
        self._rows = []

    def execute(self, statement):
        self.connection.statements.append(statement)
        if statement == "FAIL":
            raise RuntimeError("statement failed")
        if statement.upper().startswith(("SELECT", "EXPLAIN")):
            self.description = (("plan",),)
            self._rows = [("table scan",)] if statement.upper().startswith("EXPLAIN") else [(1,)]
        else:
            self.description = None
            self.rowcount = 1

    def fetchmany(self, _size):
        rows, self._rows = self._rows, []
        return rows

    def close(self):
        pass


class FakeConnection:
    def __init__(self):
        self.statements = []
        self.transaction_calls = []
        self.lineage_calls = []

    def cursor(self):
        return FakeCursor(self)

    def begin(self):
        self.transaction_calls.append("begin")

    def commit(self):
        self.transaction_calls.append("commit")

    def rollback(self):
        self.transaction_calls.append("rollback")


@pytest.fixture()
def executor_env(monkeypatch):
    connection = FakeConnection()
    datasource = SimpleNamespace(
        id=1,
        name="warehouse",
        type="mysql",
        host="db",
        port=3306,
        db_name="analytics",
    )
    monkeypatch.setattr(sql_executor, "_lookup_datasource", lambda _ref: datasource)
    monkeypatch.setattr(sql_executor, "_get_conn", lambda _ds: connection)

    def collect_lineage(_ctx, statements, datasource_name, database_name):
        connection.lineage_calls.append(
            {
                "statements": list(statements),
                "datasource": datasource_name,
                "database": database_name,
            }
        )
        return 2, 3

    monkeypatch.setattr(sql_executor, "collect_sql_lineage", collect_lineage)
    return connection


def make_context(param, *, killed=lambda: False):
    logs = []
    return SimpleNamespace(param=param, log=logs.append, killed=killed), logs


def test_transaction_none_preserves_per_statement_execution(executor_env):
    ctx, _logs = make_context(
        {"datasource": "warehouse", "pre": "SET @x=1", "sql": "SELECT 1", "post": "SET @x=NULL"}
    )

    result = sql_executor.execute(ctx)

    assert result.state == SUCCESS
    assert executor_env.statements == ["SET @x=1", "SELECT 1", "SET @x=NULL"]
    assert executor_env.transaction_calls == []


def test_transaction_all_commits_after_every_phase_succeeds(executor_env):
    ctx, _logs = make_context(
        {
            "datasource": "warehouse",
            "pre": "SET @x=1",
            "sql": "SELECT 1; UPDATE summary SET n=1",
            "post": "SET @x=NULL",
            "transaction": "all",
        }
    )

    result = sql_executor.execute(ctx)

    assert result.state == SUCCESS
    assert executor_env.transaction_calls == ["begin", "commit"]
    assert executor_env.statements == ["SET @x=1", "SELECT 1", "UPDATE summary SET n=1", "SET @x=NULL"]


def test_transaction_all_rolls_back_every_phase_when_a_statement_fails(executor_env):
    ctx, _logs = make_context(
        {
            "datasource": "warehouse",
            "pre": "INSERT INTO audit VALUES (1)",
            "sql": "UPDATE summary SET n=1; FAIL; UPDATE summary SET n=2",
            "post": "DELETE FROM audit",
            "transaction": "all",
        }
    )

    result = sql_executor.execute(ctx)

    assert result.state == FAILURE
    assert executor_env.transaction_calls == ["begin", "rollback"]
    assert executor_env.statements == ["INSERT INTO audit VALUES (1)", "UPDATE summary SET n=1", "FAIL"]


def test_read_only_rejects_entire_batch_before_any_statement_executes(executor_env):
    ctx, logs = make_context(
        {
            "datasource": "warehouse",
            "pre": "SELECT 1",
            "sql": "SELECT * FROM users",
            "post": "DELETE FROM users",
            "readOnly": True,
            "transaction": "all",
        }
    )

    result = sql_executor.execute(ctx)

    assert result.state == FAILURE
    assert executor_env.statements == []
    assert executor_env.transaction_calls == []
    assert any("readOnly" in line for line in logs)


def test_explain_returns_plan_without_replacing_normal_results(executor_env):
    ctx, _logs = make_context(
        {"datasource": "warehouse", "sql": "SELECT * FROM users", "explain": True}
    )

    result = sql_executor.execute(ctx)

    assert result.state == SUCCESS
    assert executor_env.statements == ["EXPLAIN SELECT * FROM users", "SELECT * FROM users"]
    assert result.outputs["execution_plan"] == [
        {
            "statement": "SELECT * FROM users",
            "columns": ["plan"],
            "rows": [["table scan"]],
        }
    ]
    assert result.outputs["row_count"] == 1


def test_explicit_transaction_mode_leaves_boundaries_to_sql(executor_env):
    ctx, _logs = make_context(
        {
            "datasource": "warehouse",
            "sql": "START TRANSACTION; UPDATE summary SET n=1; COMMIT",
            "transaction": "explicit",
        }
    )

    result = sql_executor.execute(ctx)

    assert result.state == SUCCESS
    assert executor_env.transaction_calls == []
    assert executor_env.statements == ["START TRANSACTION", "UPDATE summary SET n=1", "COMMIT"]


def test_invalid_transaction_mode_is_rejected_before_execution(executor_env):
    ctx, logs = make_context(
        {"datasource": "warehouse", "sql": "SELECT 1", "transaction": "sometimes"}
    )

    result = sql_executor.execute(ctx)

    assert result.state == FAILURE
    assert executor_env.statements == []
    assert any("transaction" in line for line in logs)


def test_transaction_all_rolls_back_when_killed_between_statements(executor_env):
    kill_checks = iter((False, True))
    ctx, _logs = make_context(
        {"datasource": "warehouse", "sql": "SELECT 1; SELECT 2", "transaction": "all"},
        killed=lambda: next(kill_checks),
    )

    result = sql_executor.execute(ctx)

    assert result.state != SUCCESS
    assert executor_env.statements == ["SELECT 1"]
    assert executor_env.transaction_calls == ["begin", "rollback"]


@pytest.mark.parametrize(
    "transaction_statement",
    [
        "BEGIN",
        "START TRANSACTION",
        "COMMIT",
        "ROLLBACK",
        "SAVEPOINT batch_step",
        "RELEASE SAVEPOINT batch_step",
        "SET AUTOCOMMIT=0",
    ],
)
def test_transaction_all_rejects_embedded_transaction_boundaries_before_execution(
    executor_env, transaction_statement
):
    ctx, logs = make_context(
        {
            "datasource": "warehouse",
            "sql": f"SELECT 1; {transaction_statement}",
            "transaction": "all",
        }
    )

    result = sql_executor.execute(ctx)

    assert result.state == FAILURE
    assert executor_env.statements == []
    assert executor_env.transaction_calls == []
    assert any("transaction" in line for line in logs)


def test_transaction_all_checks_kill_after_last_statement_before_commit(executor_env):
    kill_checks = iter((False, True))
    ctx, _logs = make_context(
        {"datasource": "warehouse", "sql": "SELECT 1", "transaction": "all"},
        killed=lambda: next(kill_checks),
    )

    result = sql_executor.execute(ctx)

    assert result.state != SUCCESS
    assert executor_env.statements == ["SELECT 1"]
    assert executor_env.transaction_calls == ["begin", "rollback"]


def test_explicit_transaction_rolls_back_connection_after_statement_failure(executor_env):
    ctx, _logs = make_context(
        {
            "datasource": "warehouse",
            "sql": "START TRANSACTION; UPDATE summary SET n=1; FAIL",
            "transaction": "explicit",
        }
    )

    result = sql_executor.execute(ctx)

    assert result.state == FAILURE
    assert executor_env.transaction_calls == ["rollback"]


def test_explicit_transaction_rolls_back_connection_when_killed(executor_env):
    kill_checks = iter((False, True))
    ctx, _logs = make_context(
        {
            "datasource": "warehouse",
            "sql": "START TRANSACTION; UPDATE summary SET n=1",
            "transaction": "explicit",
        },
        killed=lambda: next(kill_checks),
    )

    result = sql_executor.execute(ctx)

    assert result.state != SUCCESS
    assert executor_env.transaction_calls == ["rollback"]


def test_explain_skips_legal_non_explainable_statements_and_keeps_results(executor_env):
    ctx, _logs = make_context(
        {
            "datasource": "warehouse",
            "sql": "SET @x=1; SELECT 1; UPDATE summary SET n=1",
            "explain": True,
        }
    )

    result = sql_executor.execute(ctx)

    assert result.state == SUCCESS
    assert executor_env.statements == [
        "SET @x=1",
        "EXPLAIN SELECT 1",
        "SELECT 1",
        "EXPLAIN UPDATE summary SET n=1",
        "UPDATE summary SET n=1",
    ]
    assert len(result.outputs["results"]) == 3
    assert [item["statement"] for item in result.outputs["execution_plan"]] == [
        "SELECT 1",
        "UPDATE summary SET n=1",
    ]
    assert result.outputs["row_count"] == 1
    assert result.outputs["result_preview"] == {"columns": ["plan"], "rows": [[1]]}
    assert result.outputs["lineage_edges"] == 2
    assert result.outputs["lineage_fields"] == 3
    assert executor_env.lineage_calls == [
        {
            "statements": ["SET @x=1", "SELECT 1", "UPDATE summary SET n=1"],
            "datasource": "warehouse",
            "database": "analytics",
        }
    ]


@pytest.mark.parametrize(
    ("statement", "expected"),
    [
        ("/*!40101 COMMIT */", True),
        ("/*!40101 SET AUTOCOMMIT=0 */", True),
        ("/* COMMIT */ SELECT 1", False),
        ("/*+ COMMIT */ SELECT 1", False),
    ],
)
def test_transaction_control_detection_understands_mysql_comment_semantics(statement, expected):
    assert sql_executor._is_transaction_control_statement(statement) is expected


@pytest.mark.parametrize(
    "statement",
    ["/*!40101 COMMIT */", "/*!40101 SET AUTOCOMMIT=0 */"],
)
def test_transaction_all_rejects_mysql_executable_comment_boundaries_before_execution(
    executor_env, statement
):
    ctx, logs = make_context(
        {"datasource": "warehouse", "sql": statement, "transaction": "all"}
    )

    result = sql_executor.execute(ctx)

    assert result.state == FAILURE
    assert executor_env.statements == []
    assert executor_env.transaction_calls == []
    assert any("transaction=all" in line for line in logs)
