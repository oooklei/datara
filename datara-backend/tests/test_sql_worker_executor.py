import threading
from types import SimpleNamespace

import pytest

from worker.executors import sql as sql_executor
from worker.state import FAILURE, KILL, SUCCESS


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.description = None
        self.rowcount = 0
        self._rows = []

    def execute(self, statement):
        self.connection.statements.append(statement)
        if statement == "FAIL" or statement in self.connection.fail_statements:
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
        self.close_calls = 0
        self.rollback_error = None
        self.autocommit_error = None
        self.autocommit_enabled = True
        self.fail_statements = set()

    def cursor(self):
        return FakeCursor(self)

    def begin(self):
        self.transaction_calls.append("begin")

    def commit(self):
        self.transaction_calls.append("commit")

    def rollback(self):
        self.transaction_calls.append("rollback")
        if self.rollback_error:
            raise self.rollback_error

    def get_autocommit(self):
        return self.autocommit_enabled

    def autocommit(self, enabled):
        if self.autocommit_error:
            raise self.autocommit_error
        self.autocommit_enabled = enabled

    def thread_id(self):
        return 73

    def close(self):
        self.close_calls += 1

    def ping(self, reconnect=False):
        del reconnect


@pytest.fixture()
def executor_env(monkeypatch):
    sql_executor._conn_pool.clear()
    connection = FakeConnection()
    datasource = SimpleNamespace(
        id=1,
        name="warehouse",
        type="mysql",
        host="db",
        port=3306,
        db_name="analytics",
        user="runner",
        pwd="secret",
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
    yield connection
    sql_executor._conn_pool.clear()


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
            "pre": "SELECT 0",
            "sql": "SELECT 1; UPDATE summary SET n=1",
            "post": "DELETE FROM summary WHERE n=0",
            "transaction": "all",
        }
    )

    result = sql_executor.execute(ctx)

    assert result.state == SUCCESS
    assert executor_env.transaction_calls == ["begin", "commit"]
    assert executor_env.statements == [
        "SELECT 0",
        "SELECT 1",
        "UPDATE summary SET n=1",
        "DELETE FROM summary WHERE n=0",
    ]


def test_transaction_all_rolls_back_every_phase_when_a_statement_fails(executor_env):
    executor_env.fail_statements.add("UPDATE broken SET n=1")
    ctx, _logs = make_context(
        {
            "datasource": "warehouse",
            "pre": "INSERT INTO audit VALUES (1)",
            "sql": "UPDATE summary SET n=1; UPDATE broken SET n=1; UPDATE summary SET n=2",
            "post": "DELETE FROM audit",
            "transaction": "all",
        }
    )

    result = sql_executor.execute(ctx)

    assert result.state == FAILURE
    assert executor_env.transaction_calls == ["begin", "rollback"]
    assert executor_env.statements == [
        "INSERT INTO audit VALUES (1)",
        "UPDATE summary SET n=1",
        "UPDATE broken SET n=1",
    ]


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

    assert result.state == KILL
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

    assert result.state == KILL
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

    assert result.state == KILL
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


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE new_table (id INT)",
        "ALTER TABLE users ADD COLUMN active INT",
        "DROP TABLE users",
        "TRUNCATE TABLE users",
        "RENAME TABLE users TO old_users",
        "LOCK TABLES users READ",
        "LOCK INSTANCE FOR BACKUP",
        "UNLOCK TABLES",
        "GRANT SELECT ON db.* TO reader",
        "REVOKE SELECT ON db.* FROM reader",
        "ANALYZE TABLE users",
        "SET PASSWORD FOR reader = 'secret'",
    ],
)
def test_transaction_all_rejects_implicit_commit_statements_before_execution(executor_env, statement):
    ctx, logs = make_context(
        {"datasource": "warehouse", "sql": statement, "transaction": "all"}
    )

    result = sql_executor.execute(ctx)

    assert result.state == FAILURE
    assert executor_env.statements == []
    assert executor_env.transaction_calls == []
    assert any("transaction=all" in line for line in logs)


@pytest.mark.parametrize(
    "statement",
    [
        "SELECT GET_LOCK('resource', 1)",
        "SELECT unknown_side_effect(1)",
        "SELECT @session_value := 1",
    ],
)
def test_read_only_rejects_unsafe_functions_and_session_assignment_before_execution(
    executor_env, statement
):
    ctx, logs = make_context(
        {"datasource": "warehouse", "sql": statement, "readOnly": True}
    )

    result = sql_executor.execute(ctx)

    assert result.state == FAILURE
    assert executor_env.statements == []
    assert any("readOnly" in line for line in logs)


def test_read_only_allows_whitelisted_safe_select(executor_env):
    ctx, _logs = make_context(
        {"datasource": "warehouse", "sql": "SELECT ABS(1)", "readOnly": True}
    )

    result = sql_executor.execute(ctx)

    assert result.state == SUCCESS
    assert executor_env.statements == ["SELECT ABS(1)"]


def test_explicit_transaction_fails_and_cleans_up_when_script_leaves_transaction_open(executor_env):
    ctx, logs = make_context(
        {
            "datasource": "warehouse",
            "sql": "START TRANSACTION; SELECT 1",
            "transaction": "explicit",
        }
    )

    result = sql_executor.execute(ctx)

    assert result.state == FAILURE
    assert executor_env.statements == ["START TRANSACTION", "SELECT 1"]
    assert executor_env.transaction_calls == ["rollback"]
    assert any("未闭合" in line for line in logs)


def test_explicit_rollback_to_savepoint_does_not_count_as_transaction_close(executor_env):
    ctx, logs = make_context(
        {
            "datasource": "warehouse",
            "sql": "START TRANSACTION; SAVEPOINT before_write; ROLLBACK TO SAVEPOINT before_write",
            "transaction": "explicit",
        }
    )

    result = sql_executor.execute(ctx)

    assert result.state == FAILURE
    assert executor_env.transaction_calls == ["rollback"]
    assert any("未闭合" in line for line in logs)


def test_split_sql_respects_semicolons_inside_strings_and_comments():
    assert sql_executor._split_sql("SELECT 'a;b'; SELECT 1 /* ; retained */;") == [
        "SELECT 'a;b'",
        "SELECT 1 /* ; retained */",
    ]


def test_executor_uses_lexical_statement_boundaries(executor_env):
    ctx, _logs = make_context(
        {"datasource": "warehouse", "sql": "SELECT 'a;b'; SELECT 1 /* ; retained */;"}
    )

    result = sql_executor.execute(ctx)

    assert result.state == SUCCESS
    assert executor_env.statements == ["SELECT 'a;b'", "SELECT 1 /* ; retained */"]


def test_transaction_none_reports_kill_arriving_after_last_statement(executor_env):
    kill_checks = iter((False, True))
    ctx, _logs = make_context(
        {"datasource": "warehouse", "sql": "UPDATE summary SET n=1", "transaction": "none"},
        killed=lambda: next(kill_checks),
    )

    result = sql_executor.execute(ctx)

    assert result.state == KILL
    assert executor_env.statements == ["UPDATE summary SET n=1"]
    assert executor_env.transaction_calls == []


@pytest.mark.parametrize(
    "statement",
    ["START TRANSACTION", "BEGIN", "COMMIT", "ROLLBACK", "SET autocommit=0", "SET @@LOCAL.autocommit=0"],
)
def test_transaction_none_rejects_transaction_boundaries_before_connection(monkeypatch, statement):
    datasource = SimpleNamespace(id=1, name="warehouse", type="mysql", host="db", port=3306, db_name="analytics")
    monkeypatch.setattr(sql_executor, "_lookup_datasource", lambda _ref: datasource)
    called = []
    monkeypatch.setattr(sql_executor, "_get_conn", lambda _ds: called.append(True))
    ctx, _logs = make_context({"datasource": "warehouse", "sql": statement, "transaction": "none"})

    result = sql_executor.execute(ctx)

    assert result.state == FAILURE
    assert called == []


def test_connection_is_checked_out_exclusively_and_released_after_execution(monkeypatch):
    datasource = SimpleNamespace(
        id=91, name="warehouse", type="mysql", host="db", port=3306,
        db_name="analytics", user="runner", pwd="secret",
    )
    connection = FakeConnection()
    monkeypatch.setattr(sql_executor, "_lookup_datasource", lambda _ref: datasource)
    monkeypatch.setitem(sql_executor._conn_pool, 91, connection)
    checked_out = sql_executor._get_conn(datasource)
    assert checked_out is connection
    assert 91 not in sql_executor._conn_pool
    monkeypatch.setattr(sql_executor, "_get_conn", lambda _ds: checked_out)
    monkeypatch.setattr(sql_executor, "collect_sql_lineage", lambda *_args: (0, 0))
    ctx, _logs = make_context({"datasource": "warehouse", "sql": "SELECT 1"})

    result = sql_executor.execute(ctx)

    assert result.state == SUCCESS
    assert sql_executor._conn_pool[91] is connection


@pytest.mark.parametrize(
    "statement",
    [
        "LOCK TABLES users READ",
        "LOCK INSTANCE FOR BACKUP",
        "SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED",
        "SET sql_mode='STRICT_ALL_TABLES'",
        "USE analytics",
    ],
)
def test_none_mode_discards_connections_after_session_affecting_statements(executor_env, statement):
    ctx, _logs = make_context({"datasource": "warehouse", "sql": statement, "transaction": "none"})

    result = sql_executor.execute(ctx)

    assert result.state == SUCCESS
    assert executor_env.close_calls == 1
    assert 1 not in sql_executor._conn_pool


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE TABLE t(id INT)",
        "START REPLICA",
        "STOP REPLICA",
        "CHANGE REPLICATION SOURCE TO SOURCE_HOST='db'",
        "SET sql_mode='STRICT_ALL_TABLES'",
        "XA START 'job-1'",
    ],
)
def test_transaction_all_fail_closed_allowlist_rejects_non_dml_before_connection(
    monkeypatch, statement
):
    datasource = SimpleNamespace(id=1, name="warehouse", type="mysql", host="db", port=3306, db_name="analytics")
    monkeypatch.setattr(sql_executor, "_lookup_datasource", lambda _ref: datasource)
    called = []
    monkeypatch.setattr(sql_executor, "_get_conn", lambda _ds: called.append(True))
    ctx, _logs = make_context({"datasource": "warehouse", "sql": statement, "transaction": "all"})

    result = sql_executor.execute(ctx)

    assert result.state == FAILURE
    assert called == []


@pytest.mark.parametrize(
    ("statement", "effect"),
    [
        ("SET LOCAL autocommit=0", "autocommit_off"),
        ("SET @@LOCAL.autocommit=0", "autocommit_off"),
        ("SET @@SESSION.autocommit=1", "autocommit_on"),
    ],
)
def test_explicit_transaction_tracks_autocommit_scope_aliases(statement, effect):
    assert sql_executor._explicit_transaction_effect(statement) == effect


def test_explicit_rejects_xa_before_connection(monkeypatch):
    datasource = SimpleNamespace(id=1, name="warehouse", type="mysql", host="db", port=3306, db_name="analytics")
    monkeypatch.setattr(sql_executor, "_lookup_datasource", lambda _ref: datasource)
    called = []
    monkeypatch.setattr(sql_executor, "_get_conn", lambda _ds: called.append(True))
    ctx, _logs = make_context({"datasource": "warehouse", "sql": "XA START 'job-1'", "transaction": "explicit"})

    result = sql_executor.execute(ctx)

    assert result.state == FAILURE
    assert called == []


def test_explicit_cleanup_discards_connection_when_rollback_fails(executor_env, monkeypatch):
    executor_env.rollback_error = RuntimeError("rollback lost")
    monkeypatch.setitem(sql_executor._conn_pool, 1, executor_env)
    ctx, _logs = make_context({
        "datasource": "warehouse", "sql": "START TRANSACTION; FAIL", "transaction": "explicit",
    })

    result = sql_executor.execute(ctx)

    assert result.state == FAILURE
    assert executor_env.close_calls == 1
    assert 1 not in sql_executor._conn_pool


def test_explicit_cleanup_discards_connection_when_autocommit_restore_fails(executor_env, monkeypatch):
    executor_env.autocommit_enabled = False
    executor_env.autocommit_error = RuntimeError("restore lost")
    monkeypatch.setitem(sql_executor._conn_pool, 1, executor_env)
    ctx, _logs = make_context({
        "datasource": "warehouse", "sql": "START TRANSACTION; SELECT 1", "transaction": "explicit",
    })

    result = sql_executor.execute(ctx)

    assert result.state == FAILURE
    assert executor_env.close_calls == 1
    assert 1 not in sql_executor._conn_pool


def test_blocking_statement_is_cancelled_through_control_connection(executor_env, monkeypatch):
    started = threading.Event()
    released = threading.Event()
    original_run_one = sql_executor._run_one

    def blocking_run_one(conn, stmt, log):
        started.set()
        assert released.wait(2)
        return original_run_one(conn, stmt, log)

    class ControlCursor:
        def execute(self, statement):
            assert statement == "KILL QUERY 73"
            released.set()
        def close(self):
            pass

    class ControlConnection:
        def cursor(self):
            return ControlCursor()
        def close(self):
            pass

    monkeypatch.setattr(sql_executor, "_run_one", blocking_run_one)
    monkeypatch.setattr(sql_executor.pymysql, "connect", lambda **_kwargs: ControlConnection())
    ctx, _logs = make_context(
        {"datasource": "warehouse", "sql": "SELECT SLEEP(60)"},
        killed=lambda: started.is_set(),
    )

    result = sql_executor.execute(ctx)

    assert result.state == KILL
    assert released.is_set()
