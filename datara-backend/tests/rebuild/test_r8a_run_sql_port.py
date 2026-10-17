"""R8-A run_sql read-only execution port tests (P1-3 step 4, TDD).

Contract (frozen v1): docs/increments/2026-10-17-R8-A八工具契约.md §7.3/§6/§11.
Acceptance: docs/increments/evidence/R8/2026-10-17-Codex-P1-3-acceptance-assertions.md.
Readiness red lines: run_sql executes ONLY through the injected R5-A execution
port — no DatasourceEngineRegistry.connect, no new engine, no SQLAlchemy direct
connection; authorization precedes execution with ZERO port calls on denial;
the read-only PoC rejects mutating SQL before dispatch.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from rebuild.ai_bridge import AiBridgePorts
from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.project.models import ProjectRecord
from rebuild.run_sql import (
    SqlDependencyUnavailable,
    SqlExecutionCancelled,
    SqlExecutionFailed,
    SqlExecutionTimeout,
    build_run_sql_handler,
    evaluate_readonly_sql,
)

AI_TOOLS_URL = "/api/v1/rebuild/ai/tools"
AI_TOOL_CALLS_URL = "/api/v1/rebuild/ai/tool-calls"

RUN_SQL_RESULT_KEYS = {
    "execution_id",
    "columns",
    "rows",
    "row_count",
    "truncated",
    "duration_ms",
    "sql_statement_digest",
}


class _FakeAuditWriter:
    def __init__(self):
        self.records = []

    def write(self, record):
        self.records.append(dict(record))
        return record["audit_id"]


class _FakeSearchHandler:
    def __init__(self):
        self.calls = 0

    def __call__(self, params, page_context, ctx):
        self.calls += 1
        return {"entries": []}


class _FakePort:
    """Injected R5-A execution-port stub: records every call, scripts the outcome."""

    def __init__(self, *, result=None, exc=None):
        self.calls = []
        self.result = result or {
            "execution_id": "exec-1",
            "columns": [{"name": "1", "type": "INTEGER"}],
            "rows": [[1]],
            "row_count": 1,
            "truncated": False,
            "duration_ms": 12,
            "sql_statement_digest": "digest-1",
        }
        self.exc = exc

    def execute(self, **kwargs):
        self.calls.append(kwargs)
        if self.exc is not None:
            raise self.exc
        return dict(self.result)


def _bridge_app(port):
    search = _FakeSearchHandler()
    writer = _FakeAuditWriter()
    ports = AiBridgePorts(
        handlers={"search_schema": search, "run_sql": build_run_sql_handler(port)},
        audit_writer=writer,
    )
    app = create_app(
        "sqlite+pysqlite:///:memory:",
        token_secret="r8a-run-sql-test-secret",
        ai_bridge_ports=ports,
    )
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        dev = UserRepository(session).create(username="dev", password="dev-pass", role=Role.DEV)
        UserRepository(session).create(username="viewer", password="viewer-pass", role=Role.VIEWER)
        owned = ProjectRecord(name="r8a-run-sql", description="", owner_id=dev.id)
        session.add_all((owned,))
        session.commit()
        project_id = owned.id
    tokens = {}
    for username, password in (("dev", "dev-pass"), ("viewer", "viewer-pass")):
        response = client.post("/api/v1/rebuild/login", json={"username": username, "password": password})
        tokens[username] = {"token": response.json()["data"]["token"]}
    return client, project_id, tokens, writer, search


def _run_sql_call(client, headers, project_id, sql, **extra_params):
    return client.post(
        AI_TOOL_CALLS_URL,
        headers=headers,
        json={
            "tool_call_id": f"tc-{uuid.uuid4()}",
            "tool": "run_sql",
            "tool_version": 1,
            "params": {"project_id": project_id, "datasource_id": 7, "sql": sql, **extra_params},
        },
    )


def test_registry_reports_run_sql_enabled_once_port_composed():
    client, _pid, tokens, _writer, _search = _bridge_app(_FakePort())
    try:
        entries = {e["name"]: e for e in client.get(AI_TOOLS_URL, headers=tokens["dev"]).json()}
        assert entries["run_sql"]["enabled"] is True  # enabled ⇔ handler wired (R8A-02)
    finally:
        client.__exit__(None, None, None)


def test_run_sql_success_delegates_port_once_and_threads_audit():
    port = _FakePort()
    client, project_id, tokens, writer, search = _bridge_app(port)
    try:
        response = client.post(
            AI_TOOL_CALLS_URL,
            headers=tokens["dev"],
            json={
                "tool_call_id": "tc-run-sql-success",
                "tool": "run_sql",
                "tool_version": 1,
                "params": {"project_id": project_id, "datasource_id": 7, "sql": "SELECT id FROM users"},
                "page_context": {"context_type": "SQL", "context_ref": {"tab": "editor-1"}},
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "SUCCESS" and body["error"] is None
        assert set(body["result"].keys()) == RUN_SQL_RESULT_KEYS  # §7.3 wire shape, no refs key
        assert body["result"]["execution_id"] == "exec-1"
        # port delegated exactly once, with §7.3 defaults materialized
        assert port.calls == [
            {
                "project_id": project_id,
                "datasource_id": 7,
                "sql": "SELECT id FROM users",
                "row_limit": 200,
                "timeout_ms": 30000,
                "dialect": None,
            }
        ]
        assert search.calls == 0  # only the run_sql path ran
        record = writer.records[-1]
        assert record["outcome"] == "SUCCESS"
        assert record["refs"] == {"tab": "editor-1", "execution_id": "exec-1", "datasource_id": 7}
        assert record["budget"] == {"rows_returned": 1, "truncated": False, "duration_ms": 12}
    finally:
        client.__exit__(None, None, None)


def test_run_sql_passes_requested_converged_budget_to_port():
    port = _FakePort()
    client, project_id, tokens, _writer, _search = _bridge_app(port)
    try:
        response = _run_sql_call(
            client, tokens["dev"], project_id, "SELECT 1", row_limit=50, timeout_ms=15000, dialect="sqlite"
        )
        body = response.json()
        assert body["status"] == "SUCCESS"
        call = port.calls[0]
        assert call["row_limit"] == 50
        assert call["timeout_ms"] == 15000  # §6: converge only — requested value passes as-is
        assert call["dialect"] == "sqlite"
    finally:
        client.__exit__(None, None, None)


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO t VALUES (1)",
        "UPDATE t SET a = 1",
        "DELETE FROM t",
        "CREATE TABLE t (id INTEGER)",
        "DROP TABLE t",
        "TRUNCATE TABLE t",
        "ALTER TABLE t ADD COLUMN c INTEGER",
        "-- looks safe\nDELETE FROM t",
    ],
)
def test_run_sql_mutating_sql_rejected_with_zero_port_calls(sql):
    port = _FakePort()
    client, project_id, tokens, writer, _search = _bridge_app(port)
    try:
        response = _run_sql_call(client, tokens["dev"], project_id, sql)
        body = response.json()
        assert body["status"] == "ERROR"
        assert body["error"]["code"] == "INVALID_PARAMS"
        assert body["error"]["retryable"] is False
        assert body["error"]["details"]["readonly_policy"]  # structured violations (§5)
        assert port.calls == []  # acceptance: denial -> the execution port is never called
        assert writer.records[-1]["error_code"] == "INVALID_PARAMS"
    finally:
        client.__exit__(None, None, None)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; SELECT 2",
        "SELECT 1; DELETE FROM t",
        "SELECT 'unterminated",
        "SELECT 1 /* unterminated",
        "WITH cte AS (SELECT 1) SELECT * FROM cte",  # honest PoC scope: SELECT-only
    ],
)
def test_run_sql_non_single_select_rejected_with_zero_port_calls(sql):
    port = _FakePort()
    client, project_id, tokens, _writer, _search = _bridge_app(port)
    try:
        response = _run_sql_call(client, tokens["dev"], project_id, sql)
        body = response.json()
        assert body["status"] == "ERROR"
        assert body["error"]["code"] == "INVALID_PARAMS"
        assert port.calls == []
    finally:
        client.__exit__(None, None, None)


def test_readonly_guard_unit_verdicts():
    allowed, violations = evaluate_readonly_sql("SELECT 1")
    assert allowed and violations == []
    allowed, _violations = evaluate_readonly_sql("  /* leading */ SELECT 1 -- trailing\n")
    assert allowed
    allowed, violations = evaluate_readonly_sql("")
    assert not allowed and violations


@pytest.mark.parametrize(
    "exc, code",
    [
        (SqlExecutionFailed("syntax error near FROM", details={"position": 12}), "EXECUTION_FAILED"),
        (SqlExecutionTimeout("query exceeded 30000ms"), "EXECUTION_TIMEOUT"),
        (SqlExecutionCancelled("cancelled by operator"), "EXECUTION_CANCELLED"),
        (SqlDependencyUnavailable("datasource connection refused"), "DEPENDENCY_UNAVAILABLE"),
    ],
)
def test_run_sql_port_failures_map_frozen_codes_no_auto_retry(exc, code):
    port = _FakePort(exc=exc)
    client, project_id, tokens, writer, _search = _bridge_app(port)
    try:
        response = _run_sql_call(client, tokens["dev"], project_id, "SELECT 1")
        body = response.json()
        assert body["status"] == "ERROR"
        assert body["error"]["code"] == code
        assert body["error"]["retryable"] is False  # run_sql 非幂等：§6 不自动重试覆盖 §5 默认
        assert len(port.calls) == 1  # no auto retry: the port ran exactly once
        if exc.details is not None:
            assert body["error"]["details"] == exc.details  # engine-side info (§5)
        assert writer.records[-1]["error_code"] == code
    finally:
        client.__exit__(None, None, None)


def test_run_sql_viewer_denied_before_port():
    port = _FakePort()
    client, project_id, tokens, writer, _search = _bridge_app(port)
    try:
        response = _run_sql_call(client, tokens["viewer"], project_id, "SELECT 1")
        body = response.json()
        assert body["error"]["code"] == "PERMISSION_DENIED"
        assert body["error"]["retryable"] is False
        assert port.calls == []  # R8A-05: authorization precedes dispatch
        assert writer.records[-1]["outcome"] == "ERROR"
    finally:
        client.__exit__(None, None, None)


@pytest.mark.parametrize("field, value", [("row_limit", 0), ("row_limit", -5), ("timeout_ms", 0)])
def test_run_sql_nonpositive_budget_params_rejected_before_port(field, value):
    port = _FakePort()
    client, project_id, tokens, _writer, _search = _bridge_app(port)
    try:
        response = _run_sql_call(client, tokens["dev"], project_id, "SELECT 1", **{field: value})
        body = response.json()
        assert body["error"]["code"] == "INVALID_PARAMS"
        assert port.calls == []
    finally:
        client.__exit__(None, None, None)


def test_run_sql_truncation_relayed_to_audit_budget():
    port = _FakePort(
        result={
            "execution_id": "exec-9",
            "columns": [],
            "rows": [[1], [2]],
            "row_count": 2,
            "truncated": True,
            "duration_ms": 5,
            "sql_statement_digest": "digest-9",
        }
    )
    client, project_id, tokens, writer, _search = _bridge_app(port)
    try:
        response = _run_sql_call(client, tokens["dev"], project_id, "SELECT id FROM big", row_limit=2)
        body = response.json()
        assert body["status"] == "SUCCESS"
        assert body["result"]["truncated"] is True
        record = writer.records[-1]
        assert record["budget"] == {"rows_returned": 2, "truncated": True, "duration_ms": 5}
        assert record["refs"]["execution_id"] == "exec-9"
    finally:
        client.__exit__(None, None, None)


# supervisor #178 read-only ruling layer-1: lexical gate alone is NOT sufficient —
# SELECT-leading single-statement SQL with side-effect patterns must also be
# rejected BEFORE the port (SELECT INTO / side-effect functions / locking reads).
@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * INTO new_t FROM users",
        "SELECT SLEEP(10)",
        "SELECT BENCHMARK(1000000, MD5('x'))",
        "SELECT GET_LOCK('x', 10)",
        "SELECT LOAD_FILE('/etc/passwd')",
        "PRAGMA table_info(t)",
        "SELECT * FROM users FOR UPDATE",
    ],
)
def test_run_sql_dangerous_patterns_rejected_with_zero_port_calls(sql):
    port = _FakePort()
    client, project_id, tokens, _writer, _search = _bridge_app(port)
    try:
        response = _run_sql_call(client, tokens["dev"], project_id, sql)
        body = response.json()
        assert body["status"] == "ERROR"
        assert body["error"]["code"] == "INVALID_PARAMS"
        violations = body["error"]["details"]["readonly_policy"]
        assert any(v["code"] == "dangerous_pattern" for v in violations)
        assert port.calls == []  # denial precedes dispatch, zero port calls
    finally:
        client.__exit__(None, None, None)


# supervisor #178 ruling-3: budget is counted only AFTER params pass, for wired
# tools — static budget denial on the wired run_sql path with zero port calls.
@pytest.mark.parametrize("field, value", [("row_limit", 2000), ("timeout_ms", 60000)])
def test_run_sql_budget_static_exceeded_with_wired_tool(field, value):
    port = _FakePort()
    client, project_id, tokens, _writer, _search = _bridge_app(port)
    try:
        response = _run_sql_call(client, tokens["dev"], project_id, "SELECT 1", **{field: value})
        body = response.json()
        assert body["status"] == "ERROR"
        assert body["error"]["code"] == "BUDGET_EXCEEDED"
        assert body["error"]["retryable"] is False
        assert port.calls == []
    finally:
        client.__exit__(None, None, None)
