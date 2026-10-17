"""R8-A AI eight-tool unified bridge contract tests (P1-3 step-1 TDD red).

Contract source: docs/increments/2026-10-17-R8-A八工具契约.md (v1 frozen).
Gap list: docs/increments/evidence/R8/2026-10-17-Codex-P1-3-bridge-readiness.md.
Orders: supervisor #160 P1-3 unlock, Trae #164 five-step schedule (this file = step 1 red).

Frozen assertions:
- §2.1 GET /api/v1/rebuild/ai/tools + POST /api/v1/rebuild/ai/tool-calls;
- §2.2/§2.3 request/response envelope (snake_case wire; audit_id on success AND failure);
- §2.4 registry entries + §6 frozen timeout/retry/budget values;
- §5 error normalization (12-code space, retryable semantics);
- §3 permission (token auth first -> 401; pre-N-C roles fallback: run_sql only ADMIN/DEV);
- §4 audit (injected writer threads tool_call_id/user_id/roles/project_id/refs.run_id;
  missing writer fails closed at construction; writer failure never fakes SUCCESS);
- readiness red line: default create_app mounts no bridge (404) — no unaudited path.
"""

import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from rebuild.ai_bridge import AiBridgePorts
from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.project.models import ProjectRecord

AI_TOOLS_URL = "/api/v1/rebuild/ai/tools"
AI_TOOL_CALLS_URL = "/api/v1/rebuild/ai/tool-calls"

FROZEN_TOOL_ORDER = [
    "search_schema",
    "validate_sql",
    "run_sql",
    "get_workflow",
    "validate_workflow",
    "inspect_workflow_run",
    "get_task_metrics",
    "get_lineage",
]

FROZEN_TIMEOUT_MS = {
    "search_schema": 10000,
    "validate_sql": 10000,
    "run_sql": 30000,
    "get_workflow": 5000,
    "validate_workflow": 15000,
    "inspect_workflow_run": 5000,
    "get_task_metrics": 10000,
    "get_lineage": 10000,
}

REGISTRY_ENTRY_KEYS = {
    "name",
    "version",
    "description",
    "enabled",
    "required_permissions",
    "timeout_ms",
    "retry_policy",
    "budget",
}


class _FakeAuditWriter:
    """Injected audit-writer stub: captures §4 thread fields for assertions."""

    def __init__(self, *, fail=False):
        self.records = []
        self.fail = fail

    def write(self, record):
        if self.fail:
            raise RuntimeError("audit sink down")
        self.records.append(dict(record))
        return record["audit_id"]


def _fake_search_schema_handler(params, page_context, ctx):
    _fake_search_schema_handler.calls += 1  # R8A-05: zero-call assertion on denials
    return {
        "entries": [
            {"kind": "TABLE", "schema_name": "public", "table_name": "users", "digest": "dg-1"},
        ],
    }


_fake_search_schema_handler.calls = 0


def _bridge_app(**port_overrides):
    _fake_search_schema_handler.calls = 0
    ports_kwargs = {
        "handlers": {"search_schema": _fake_search_schema_handler},
        "audit_writer": _FakeAuditWriter(),
    }
    ports_kwargs.update(port_overrides)
    ports = AiBridgePorts(**ports_kwargs)
    app = create_app(
        "sqlite+pysqlite:///:memory:",
        token_secret="r8a-bridge-test-secret",
        ai_bridge_ports=ports,
    )
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        dev = UserRepository(session).create(username="dev", password="dev-pass", role=Role.DEV)
        UserRepository(session).create(username="viewer", password="viewer-pass", role=Role.VIEWER)
        owned = ProjectRecord(name="r8a-owned", description="", owner_id=dev.id)
        session.add_all((owned,))
        session.commit()
        project_id = owned.id
    tokens = {}
    for username, password in (("admin", "admin-pass"), ("dev", "dev-pass"), ("viewer", "viewer-pass")):
        response = client.post("/api/v1/rebuild/login", json={"username": username, "password": password})
        tokens[username] = {"token": response.json()["data"]["token"]}
    return client, app, project_id, tokens, ports_kwargs["audit_writer"]


def _call(client, headers, tool, *, tool_version=1, params=None, page_context=None, tool_call_id=None):
    body = {
        "tool_call_id": tool_call_id or f"tc-{uuid.uuid4()}",
        "tool": tool,
        "tool_version": tool_version,
        "params": params if params is not None else {},
        "page_context": page_context,
    }
    return client.post(AI_TOOL_CALLS_URL, headers=headers, json=body)


def test_default_app_fail_closed_no_ai_bridge():
    """Readiness red line: default create_app mounts no bridge — no unaudited path."""
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="r8a-default-secret")
    client = TestClient(app)
    client.__enter__()
    try:
        assert client.get(AI_TOOLS_URL).status_code == 404
        assert client.post(AI_TOOL_CALLS_URL, json={}).status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_bridge_without_audit_writer_fails_closed():
    """Readiness red line: absent audit writer -> construction-time rejection."""
    with pytest.raises(ValueError):
        _bridge_app(audit_writer=None)


def test_endpoints_require_auth_before_handler():
    client, _app, _pid, _tokens, _writer = _bridge_app()
    try:
        assert client.get(AI_TOOLS_URL).status_code == 401
        assert client.post(AI_TOOL_CALLS_URL, json={}).status_code == 401
    finally:
        client.__exit__(None, None, None)


def test_get_tools_returns_frozen_registry():
    client, _app, _pid, tokens, _writer = _bridge_app()
    try:
        response = client.get(AI_TOOLS_URL, headers=tokens["dev"])
        assert response.status_code == 200
        entries = response.json()
        assert isinstance(entries, list) and len(entries) == 8
        assert [entry["name"] for entry in entries] == FROZEN_TOOL_ORDER
        for entry in entries:
            assert set(entry.keys()) == REGISTRY_ENTRY_KEYS
            assert entry["version"] == 1
            assert entry["timeout_ms"] == FROZEN_TIMEOUT_MS[entry["name"]]
            assert isinstance(entry["required_permissions"], list)  # §8: pre-N-C may be empty
            assert set(entry["retry_policy"].keys()) == {"max_attempts", "backoff_ms"}
        by_name = {entry["name"]: entry for entry in entries}
        assert "generate_sql" not in by_name  # R8A-02: adapter-internal, never a registry tool
        # R8A-02 PoC: enabled ⇔ handler wired — unwired tools listed but disabled
        assert by_name["search_schema"]["enabled"] is True
        assert by_name["validate_sql"]["enabled"] is False
        assert by_name["run_sql"]["enabled"] is False
        assert by_name["get_workflow"]["enabled"] is False
        # run_sql is non-idempotent: no auto retry (§6/§7.3)
        assert by_name["run_sql"]["retry_policy"]["max_attempts"] == 1
        for name in FROZEN_TOOL_ORDER:
            if name != "run_sql":
                assert by_name[name]["retry_policy"] == {"max_attempts": 2, "backoff_ms": 500}
        # §6 frozen budget values (BE key materialization, contract numbers)
        assert by_name["search_schema"]["budget"]["max_limit"] == 100
        assert by_name["validate_sql"]["budget"]["max_sql_bytes"] == 102400
        assert by_name["run_sql"]["budget"] == {"max_row_limit": 1000, "max_timeout_ms": 30000}
        assert by_name["inspect_workflow_run"]["budget"]["max_tasks"] == 1000
        assert by_name["get_task_metrics"]["budget"]["max_time_window_days"] == 90
        assert by_name["get_lineage"]["budget"] == {"max_depth": 5, "max_nodes": 500}
    finally:
        client.__exit__(None, None, None)


def test_post_success_envelope_and_audit_thread():
    client, _app, project_id, tokens, writer = _bridge_app()
    try:
        response = _call(
            client,
            tokens["dev"],
            "search_schema",
            params={"project_id": project_id, "keyword": "users", "limit": 20},
            page_context={"context_type": "RUN", "context_ref": {"run_id": "run-e2e-1"}},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "SUCCESS"
        assert body["tool"] == "search_schema" and body["tool_version"] == 1
        assert body["tool_call_id"]
        assert body["error"] is None
        assert body["result"]["entries"][0]["table_name"] == "users"
        assert body["audit_id"]
        datetime.fromisoformat(body["server_time"].replace("Z", "+00:00"))  # §2.3 ISO-8601
        # §4 audit threads on success too; P1-6' evidence-chain fields all present
        assert len(writer.records) == 1
        record = writer.records[0]
        assert record["audit_id"] == body["audit_id"]
        assert record["tool_call_id"] == body["tool_call_id"]
        assert record["tool"] == "search_schema" and record["tool_version"] == 1
        assert record["project_id"] == project_id
        assert record["outcome"] == "SUCCESS"
        assert record["started_at"] and record["finished_at"]  # DB-generated (§4)
        assert record["request_payload"]["keyword"] == "users"  # Q11 verbatim snapshot
        assert "run_id" in record["refs"]  # page_context threaded into refs
        assert record["user_id"]
        assert record["roles"]
    finally:
        client.__exit__(None, None, None)


def test_post_unknown_tool_maps_tool_not_found():
    client, _app, _pid, tokens, writer = _bridge_app()
    try:
        response = _call(client, tokens["dev"], "no_such_tool")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ERROR"
        assert body["tool"] == "no_such_tool"
        assert body["error"]["code"] == "TOOL_NOT_FOUND"
        assert body["error"]["retryable"] is False
        assert body["result"] is None
        assert body["audit_id"]
        record = writer.records[-1]
        assert record["outcome"] == "ERROR" and record["error_code"] == "TOOL_NOT_FOUND"
    finally:
        client.__exit__(None, None, None)


def test_post_version_mismatch_maps_tool_version_mismatch():
    client, _app, _pid, tokens, _writer = _bridge_app()
    try:
        response = _call(client, tokens["dev"], "search_schema", tool_version=2)
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ERROR"
        assert body["error"]["code"] == "TOOL_VERSION_MISMATCH"
        assert body["error"]["retryable"] is False
    finally:
        client.__exit__(None, None, None)


def test_post_invalid_params_and_bad_page_context():
    client, _app, project_id, tokens, _writer = _bridge_app()
    try:
        missing_sql = _call(client, tokens["dev"], "run_sql", params={"project_id": project_id, "datasource_id": 1})
        assert missing_sql.status_code == 200
        body = missing_sql.json()
        assert body["status"] == "ERROR"
        assert body["error"]["code"] == "INVALID_PARAMS"
        assert body["error"]["retryable"] is False
        assert body["error"]["details"]  # per-field errors carried in details (§5)

        bad_context = _call(
            client,
            tokens["dev"],
            "get_workflow",
            page_context={"context_type": "BOGUS", "context_ref": None},
        )
        assert bad_context.json()["error"]["code"] == "INVALID_PARAMS"

        missing_envelope = client.post(AI_TOOL_CALLS_URL, headers=tokens["dev"], json={"tool": "search_schema"})
        assert missing_envelope.status_code == 200
        assert missing_envelope.json()["error"]["code"] == "INVALID_PARAMS"
    finally:
        client.__exit__(None, None, None)


def test_post_budget_static_enforcement():
    client, _app, project_id, tokens, writer = _bridge_app()
    try:
        cases = [
            ("run_sql", {"project_id": project_id, "datasource_id": 1, "sql": "SELECT 1", "row_limit": 2000}),
            ("run_sql", {"project_id": project_id, "datasource_id": 1, "sql": "SELECT 1", "timeout_ms": 60000}),
            ("validate_sql", {"project_id": project_id, "datasource_id": 1, "sql": "SELECT " + "1" * 102401}),
            ("get_lineage", {"project_id": project_id, "entity_type": "TABLE", "entity": "a.b", "depth": 6}),
            (
                "get_task_metrics",
                {
                    "project_id": project_id,
                    "time_window": {"from": "2026-01-01T00:00:00Z", "to": "2026-06-30T00:00:00Z"},
                },
            ),
            ("search_schema", {"project_id": project_id, "limit": 200}),
        ]
        for tool, params in cases:
            response = _call(client, tokens["dev"], tool, params=params)
            assert response.status_code == 200, tool
            body = response.json()
            assert body["status"] == "ERROR", tool
            assert body["error"]["code"] == "BUDGET_EXCEEDED", tool
            assert body["error"]["retryable"] is False, tool
            assert body["audit_id"], tool
            record = writer.records[-1]
            assert record["error_code"] == "BUDGET_EXCEEDED" and record["outcome"] == "ERROR", tool
    finally:
        client.__exit__(None, None, None)


def test_post_permission_denied_no_existence_leak_and_zero_side_effect():
    """R8A-05: denial shares one code/message for ghost vs real targets; handler never runs."""
    client, app, project_id, tokens, writer = _bridge_app()
    try:
        with app.state.session_factory() as session:
            admin = UserRepository(session).create(username="admin2", password="admin2-pass", role=Role.ADMIN)
            foreign = ProjectRecord(name="r8a-foreign", description="", owner_id=admin.id)
            session.add_all((foreign,))
            session.commit()
            foreign_id = foreign.id
        denials = [
            # role gate: viewer lacks RUN_INSTANCE
            _call(
                client,
                tokens["viewer"],
                "run_sql",
                params={"project_id": project_id, "datasource_id": 1, "sql": "SELECT 1"},
            ),
            # membership gate: viewer lacks even VIEW_ALL on the owned project
            _call(client, tokens["viewer"], "search_schema", params={"project_id": project_id}),
            # cross-project: dev is not a member of the admin-owned project
            _call(client, tokens["dev"], "search_schema", params={"project_id": foreign_id}),
            # ghost project vs real project — same code, same message (§3 no-leak)
            _call(
                client,
                tokens["viewer"],
                "run_sql",
                params={"project_id": 999999, "datasource_id": 1, "sql": "SELECT 1"},
            ),
        ]
        bodies = [response.json() for response in denials]
        for body in bodies:
            assert body["status"] == "ERROR"
            assert body["error"]["code"] == "PERMISSION_DENIED"
            assert body["error"]["retryable"] is False
            assert body["result"] is None
            assert body["audit_id"]
        assert bodies[0]["error"]["message"] == bodies[3]["error"]["message"]
        assert _fake_search_schema_handler.calls == 0  # zero side-effect on every denial
        record = writer.records[-1]
        assert record["outcome"] == "ERROR" and record["error_code"] == "PERMISSION_DENIED"
    finally:
        client.__exit__(None, None, None)


def test_post_disabled_tool_returns_tool_disabled_not_fake():
    """R8A-02: unwired PoC tools stay listed but disabled; calls refuse honestly."""
    client, _app, project_id, tokens, writer = _bridge_app()
    try:
        for tool, params in (
            ("run_sql", {"project_id": project_id, "datasource_id": 1, "sql": "SELECT 1"}),
            ("get_workflow", {"project_id": project_id}),
        ):
            response = _call(client, tokens["dev"], tool, params=params)
            body = response.json()
            assert body["status"] == "ERROR"
            assert body["error"]["code"] == "TOOL_DISABLED"
            assert body["error"]["retryable"] is False
            assert body["result"] is None
            record = writer.records[-1]
            assert record["error_code"] == "TOOL_DISABLED" and record["outcome"] == "ERROR"
        assert _fake_search_schema_handler.calls == 0
    finally:
        client.__exit__(None, None, None)


def test_post_disabled_tool_still_lists_in_registry_with_enabled_false():
    client, _app, _pid, tokens, _writer = _bridge_app()
    try:
        entries = {entry["name"]: entry for entry in client.get(AI_TOOLS_URL, headers=tokens["dev"]).json()}
        assert entries["run_sql"]["enabled"] is False
        assert entries["get_workflow"]["enabled"] is False
    finally:
        client.__exit__(None, None, None)


def test_post_audit_writer_failure_never_fakes_success():
    client, _app, project_id, tokens, writer = _bridge_app(audit_writer=_FakeAuditWriter(fail=True))
    try:
        response = _call(
            client,
            tokens["dev"],
            "search_schema",
            params={"project_id": project_id, "keyword": "users"},
        )
        body = response.json()
        assert body["status"] == "ERROR"
        assert body["error"]["code"] == "INTERNAL_ERROR"
        assert body["error"]["retryable"] is False
        assert body["error"]["details"]["audit_write_failed"] is True  # traceable sink outage (§4)
        assert body["result"] is None  # handler ran, but unaudited success is forbidden
        assert writer.records == []  # nothing landed in the dead sink
    finally:
        client.__exit__(None, None, None)
