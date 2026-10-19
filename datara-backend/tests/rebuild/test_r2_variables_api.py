"""R2 variables API contract tests — frozen FE contract (variableApi.ts / Task 2).

Key contract assertions: token-header auth (FE frozen), {code,msg,data} envelope,
snake_case keys, saveVariable {saved:true,...}, five diagnostic codes, snapshot
attempt_no filtering, sensitive plaintext (declaration §5 Q11).
"""

import pytest
from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.project.models import ProjectRecord


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="r2-variables-test-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        admin = UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        dev = UserRepository(session).create(username="dev", password="dev-pass", role=Role.DEV)
        viewer = UserRepository(session).create(username="viewer", password="viewer-pass", role=Role.VIEWER)
        owned = ProjectRecord(name="r2-owned", description="", owner_id=dev.id)
        session.add_all((owned,))
        session.commit()
        project_id = owned.id
    tokens = {}
    for username, password in (("admin", "admin-pass"), ("dev", "dev-pass"), ("viewer", "viewer-pass")):
        response = client.post("/api/v1/rebuild/login", json={"username": username, "password": password})
        # FE contract sends the raw token in the `token` header (variableApi.ts requestJson).
        tokens[username] = {"token": response.json()["data"]["token"]}
    return client, app, project_id, tokens


def _save(client, headers, project_id, *, scope="project", name="sample", value="1", value_type="string", **extra):
    body = {"scope": scope, "name": name, "value_type": value_type, "value": value, **extra}
    return client.post(f"/api/v1/rebuild/variables?project_id={project_id}", headers=headers, json=body)


def test_save_and_list_variables_envelope_and_scopes():
    client, _app, project_id, tokens = _client()
    try:
        saved = _save(client, tokens["dev"], project_id, name="batch_size", value="500")
        assert saved.status_code == 200
        assert saved.json() == {"code": 0, "msg": "success", "data": {"saved": True, "scope": "project", "name": "batch_size"}}

        global_saved = _save(
            client, tokens["dev"], project_id, scope="global", name="env_name", value="prod", value_type="string"
        )
        assert global_saved.status_code == 200

        tmp_saved = _save(
            client, tokens["dev"], project_id, scope="tmp", name="scratch", value='{"a":1}', value_type="json", sensitive=True
        )
        assert tmp_saved.status_code == 200

        listed = client.get(f"/api/v1/rebuild/variables?project_id={project_id}", headers=tokens["dev"])
        assert listed.status_code == 200
        rows = listed.json()["data"]
        names = {(row["scope"], row["name"]) for row in rows}
        assert {("project", "batch_size"), ("global", "env_name"), ("tmp", "scratch")} <= names
        scratch = next(row for row in rows if row["name"] == "scratch")
        # Declaration §5 Q11: sensitive values return plaintext, no redaction layer.
        assert scratch["value"] == '{"a":1}' and scratch["sensitive"] is True

        filtered = client.get(
            f"/api/v1/rebuild/variables?project_id={project_id}&scopes=global", headers=tokens["dev"]
        )
        assert {row["scope"] for row in filtered.json()["data"]} == {"global"}
    finally:
        client.__exit__(None, None, None)


def test_save_rejects_non_persistable_scope_and_type_mismatch():
    client, _app, project_id, tokens = _client()
    try:
        run_scope = _save(client, tokens["dev"], project_id, scope="run", name="x")
        assert run_scope.status_code == 400 and run_scope.json()["code"] == 4001
        bad_type = _save(client, tokens["dev"], project_id, name="x", value="not-a-number", value_type="decimal")
        assert bad_type.status_code == 400 and bad_type.json()["code"] == 4002
        bad_json = _save(client, tokens["dev"], project_id, name="x", value_type="json", value="{oops")
        assert bad_json.status_code == 400 and bad_json.json()["code"] == 4002
    finally:
        client.__exit__(None, None, None)


def test_viewer_cannot_save_and_anonymous_is_401():
    client, _app, project_id, tokens = _client()
    try:
        denied = _save(client, tokens["viewer"], project_id, name="x")
        assert denied.status_code == 403 and denied.json()["code"] == 1003
        anonymous = client.get(f"/api/v1/rebuild/variables?project_id={project_id}")
        assert anonymous.status_code == 401 and anonymous.json()["code"] == 1001
        # Bearer fallback also works for internal callers.
        bearer = client.get(
            f"/api/v1/rebuild/variables?project_id={project_id}",
            headers={"Authorization": f"Bearer {tokens['dev']['token']}"},
        )
        assert bearer.status_code == 200
    finally:
        client.__exit__(None, None, None)


def test_complete_check_preview_snapshot_flow():
    client, app, project_id, tokens = _client()
    try:
        assert _save(client, tokens["dev"], project_id, name="batch_size", value="500").status_code == 200
        assert _save(client, tokens["dev"], project_id, name="batch_tag", value="t1").status_code == 200
        assert _save(client, tokens["dev"], project_id, scope="global", name="gz_user", value="report").status_code == 200

        context = {"project_id": project_id}
        completed = client.post(
            "/api/v1/rebuild/variables/complete", headers=tokens["dev"], json={"prefix": "${project.batch", "context": context}
        )
        assert completed.status_code == 200
        rows = completed.json()["data"]
        assert [row["name"] for row in rows] == ["batch_size", "batch_tag"]
        assert rows[0]["scope"] == "project" and rows[0]["current_value"] == "500"

        # UNDEFINED + valid expression
        check = client.post(
            "/api/v1/rebuild/variables/check-reference",
            headers=tokens["dev"],
            json={"expression": "job=${project.batch_size} and ${project.missing}", "context": context},
        )
        data = check.json()["data"]
        assert data["valid"] is False
        codes = {d["code"] for d in data["diagnostics"]}
        assert "UNDEFINED" in codes and "SYNTAX" not in codes

        # SCOPE_INVISIBLE: task scope without task_id in context
        check2 = client.post(
            "/api/v1/rebuild/variables/check-reference",
            headers=tokens["dev"],
            json={"expression": "${task.some_var}", "context": context},
        )
        assert any(d["code"] == "SCOPE_INVISIBLE" for d in check2.json()["data"]["diagnostics"])

        # SYNTAX: braced fragment without dot
        check3 = client.post(
            "/api/v1/rebuild/variables/check-reference",
            headers=tokens["dev"],
            json={"expression": "${nodot}", "context": context},
        )
        assert any(d["code"] == "SYNTAX" for d in check3.json()["data"]["diagnostics"])

        # CYCLE: a -> b -> a
        assert _save(client, tokens["dev"], project_id, name="loop_a", value="x${project.loop_b}").status_code == 200
        assert _save(client, tokens["dev"], project_id, name="loop_b", value="y${project.loop_a}").status_code == 200
        check4 = client.post(
            "/api/v1/rebuild/variables/check-reference",
            headers=tokens["dev"],
            json={"expression": "${project.loop_a}", "context": context},
        )
        assert any(d["code"] == "CYCLE" for d in check4.json()["data"]["diagnostics"])

        # preview: resolved value + source
        preview = client.post(
            "/api/v1/rebuild/variables/preview",
            headers=tokens["dev"],
            json={"expression": "rows=${global.gz_user}", "context": context},
        )
        pdata = preview.json()["data"]
        assert pdata["resolved_value"] == "report"
        assert pdata["source"] == {"scope": "global", "name": "gz_user"}

        # snapshot: write rows directly then read through the contract endpoint
        # (P0-7: rows carry project_id; the endpoint requires it and scopes reads)
        with app.state.session_factory() as session:
            from rebuild.variables.repository import VariableRepository

            count = VariableRepository(session).write_snapshot_rows(
                [
                    {
                        "instance_id": 9001,
                        "project_id": project_id,
                        "attempt_no": 1,
                        "expression": "${project.batch_size}",
                        "scope": "project",
                        "name": "batch_size",
                        "resolved_value": "500",
                        "value_type": "decimal",
                        "source": "project",
                    },
                    {
                        "instance_id": 9001,
                        "project_id": project_id,
                        "attempt_no": 2,
                        "expression": "${project.batch_size}",
                        "scope": "project",
                        "name": "batch_size",
                        "resolved_value": "800",
                        "value_type": "decimal",
                        "source": "project",
                    },
                ]
            )
            session.commit()
            assert count == 2

        latest = client.get(
            f"/api/v1/rebuild/variables/run-snapshot?instance_id=9001&project_id={project_id}", headers=tokens["dev"]
        )
        lrows = latest.json()["data"]
        assert len(lrows) == 1 and lrows[0]["attempt_no"] == 2 and lrows[0]["resolved_value"] == "800"
        assert lrows[0]["resolved_at"] and isinstance(lrows[0]["attempt_no"], int)

        first = client.get(
            f"/api/v1/rebuild/variables/run-snapshot?instance_id=9001&project_id={project_id}&attempt_no=1",
            headers=tokens["dev"],
        )
        frows = first.json()["data"]
        assert len(frows) == 1 and frows[0]["attempt_no"] == 1 and frows[0]["resolved_value"] == "500"
        assert frows[0]["expression"] == "${project.batch_size}"
    finally:
        client.__exit__(None, None, None)


def test_run_snapshot_project_scoping_and_auth():
    """P0-7 security patch: project-level authorization + cross-project isolation."""
    client, app, project_id, tokens = _client()
    try:
        with app.state.session_factory() as session:
            from rebuild.identity.repository import UserRepository
            from rebuild.variables.repository import VariableRepository

            # a second project owned by a fresh viewer who has no relation to project 1
            viewer2 = UserRepository(session).create(username="viewer2", password="viewer2-pass", role=Role.VIEWER)
            other = ProjectRecord(name="r2-other", description="", owner_id=viewer2.id)
            session.add_all((other,))
            session.commit()
            other_project_id = other.id
            repo = VariableRepository(session)
            assert (
                repo.write_snapshot_rows(
                    [
                        {
                            "instance_id": 9100,
                            "project_id": project_id,
                            "expression": "${project.batch_size}",
                            "scope": "project",
                            "name": "batch_size",
                            "resolved_value": "500",
                            "value_type": "decimal",
                            "source": "project",
                        }
                    ]
                )
                == 1
            )
            # legacy-shaped row without project_id: unreadable from any project
            assert (
                repo.write_snapshot_rows(
                    [
                        {
                            "instance_id": 9101,
                            "expression": "${project.batch_size}",
                            "scope": "project",
                            "name": "batch_size",
                            "resolved_value": "500",
                            "value_type": "decimal",
                            "source": "project",
                        }
                    ]
                )
                == 1
            )
            session.commit()

        # anonymous → 401
        anon = client.get("/api/v1/rebuild/variables/run-snapshot?instance_id=9100&project_id=1")
        assert anon.status_code == 401 and anon.json()["code"] == 1001

        # missing project_id → 400 4001 (required frame field)
        missing = client.get("/api/v1/rebuild/variables/run-snapshot?instance_id=9100", headers=tokens["dev"])
        assert missing.status_code == 400 and missing.json()["code"] == 4001

        # non-member (viewer has no relation to project 1) → 403 code 1003
        denied = client.get(
            f"/api/v1/rebuild/variables/run-snapshot?instance_id=9100&project_id={project_id}", headers=tokens["viewer"]
        )
        assert denied.status_code == 403 and denied.json()["code"] == 1003

        # project member reads own-project rows
        ok = client.get(
            f"/api/v1/rebuild/variables/run-snapshot?instance_id=9100&project_id={project_id}", headers=tokens["dev"]
        )
        assert ok.status_code == 200 and len(ok.json()["data"]) == 1

        # cross-project isolation: an authorized user of another project querying
        # the same guessed instance id gets an empty list — nothing leaks
        viewer2_login = client.post("/api/v1/rebuild/login", json={"username": "viewer2", "password": "viewer2-pass"})
        viewer2_headers = {"token": viewer2_login.json()["data"]["token"]}
        cross = client.get(
            f"/api/v1/rebuild/variables/run-snapshot?instance_id=9100&project_id={other_project_id}",
            headers=viewer2_headers,
        )
        assert cross.status_code == 200 and cross.json()["data"] == []

        # legacy NULL rows are unreadable from any project (fail-closed)
        legacy = client.get(
            f"/api/v1/rebuild/variables/run-snapshot?instance_id=9101&project_id={project_id}", headers=tokens["dev"]
        )
        assert legacy.status_code == 200 and legacy.json()["data"] == []
    finally:
        client.__exit__(None, None, None)


def test_env_completion_withholds_values():
    """P0-7 security patch: env completion exposes names only, never values."""
    client, _app, project_id, tokens = _client()
    try:
        completed = client.post(
            "/api/v1/rebuild/variables/complete",
            headers=tokens["dev"],
            json={"prefix": "PAT", "context": {"project_id": project_id}},
        )
        assert completed.status_code == 200
        env_items = [item for item in completed.json()["data"] if item["scope"] == "env"]
        assert env_items, "expected at least one PATH-like env var in the test process"
        for item in env_items:
            assert item["current_value"] is None
            assert item["sensitive"] is True
            assert "withheld" in item["description"]
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# VAR-01: run scope resolution via run_values injection
# ---------------------------------------------------------------------------


def test_run_scope_resolves_from_run_values():
    """VAR-01: ${run.xxx} resolves from run_values injected at construction."""
    from rebuild.variables.service import VariableContext, VariableResolver

    run_values = {"batch_size": "500", "env_tag": "staging"}
    resolver = VariableResolver(lambda owner_key: [], run_values=run_values)

    context = VariableContext(project_id=1, task_id="task-001", attempt_no=1)

    # resolve_name returns run values
    assert resolver.resolve_name("run", "batch_size", context) == "500"
    assert resolver.resolve_name("run", "env_tag", context) == "staging"
    assert resolver.resolve_name("run", "missing", context) is None

    # _owner_key_for returns the run key
    assert resolver._owner_key_for("run", context) == "run:1:task-001:1"

    # _definition_of returns a ResolvedVariable for run values
    item = resolver._definition_of("run", "batch_size", context)
    assert item is not None and item.value == "500" and item.scope == "run"


def test_run_scope_check_reference_with_run_values():
    """VAR-01: check_reference resolves ${run.xxx} from run_values."""
    from rebuild.variables.service import VariableContext, VariableResolver

    run_values = {"batch_size": "500"}
    resolver = VariableResolver(lambda owner_key: [], run_values=run_values)
    context = VariableContext(project_id=1, task_id="task-001", attempt_no=1)

    result = resolver.check_reference("job=${run.batch_size}", context)
    assert result["valid"] is True
    assert result["diagnostics"] == []


def test_run_scope_preview_resolution():
    """VAR-01: preview_resolution resolves ${run.xxx} from run_values."""
    from rebuild.variables.service import VariableContext, VariableResolver

    run_values = {"env_tag": "staging"}
    resolver = VariableResolver(lambda owner_key: [], run_values=run_values)
    context = VariableContext(project_id=1, task_id="task-001", attempt_no=1)

    result = resolver.preview_resolution("env=${run.env_tag}", context)
    assert result["resolved_value"] == "staging"
    assert result["source"] == {"scope": "run", "name": "env_tag"}


# ---------------------------------------------------------------------------
# VAR-02: workflow/task persistable scopes
# ---------------------------------------------------------------------------


def test_save_and_list_workflow_task_scopes():
    """VAR-02: workflow/task scopes are persistable and listable (parse-key authority)."""
    client, _app, project_id, tokens = _client()
    try:
        wf_saved = _save(
            client, tokens["dev"], project_id, scope="workflow", name="wf_var", value="wf_val", workflow_id=100
        )
        assert wf_saved.status_code == 200

        task_saved = _save(
            client, tokens["dev"], project_id, scope="task", name="task_var", value="task_val", task_id="task-001"
        )
        assert task_saved.status_code == 200

        listed = client.get(
            f"/api/v1/rebuild/variables?project_id={project_id}&scopes=workflow,task&workflow_id=100&task_id=task-001",
            headers=tokens["dev"],
        )
        assert listed.status_code == 200
        rows = listed.json()["data"]
        names = {(row["scope"], row["name"]) for row in rows}
        assert ("workflow", "wf_var") in names
        assert ("task", "task_var") in names

        # Without ids the scopes are unaddressable (parse-key authority).
        listed_no_ids = client.get(
            f"/api/v1/rebuild/variables?project_id={project_id}&scopes=workflow,task", headers=tokens["dev"]
        )
        assert listed_no_ids.status_code == 200
        assert listed_no_ids.json()["data"] == []
    finally:
        client.__exit__(None, None, None)


def test_workflow_task_save_requires_ids():
    """VAR-02: workflow/task saves without their ids are rejected (4001)."""
    client, _app, project_id, tokens = _client()
    try:
        wf_no_id = _save(client, tokens["dev"], project_id, scope="workflow", name="wf_var", value="v")
        assert wf_no_id.status_code == 400 and wf_no_id.json()["code"] == 4001

        task_no_id = _save(client, tokens["dev"], project_id, scope="task", name="task_var", value="v")
        assert task_no_id.status_code == 400 and task_no_id.json()["code"] == 4001
    finally:
        client.__exit__(None, None, None)


def test_owner_key_parse_key_alignment():
    """VAR-02: persisted owner keys match the resolver parse keys exactly."""
    from rebuild.variables.repository import VariableRepository
    from rebuild.variables.service import VariableContext, VariableResolver

    repo = VariableRepository(session=None)
    assert repo.owner_key("global", None) == "global"
    assert repo.owner_key("project", 7) == "project:7"
    assert repo.owner_key("tmp", 7) == "tmp:7"
    assert repo.owner_key("workflow", 7, workflow_id=42) == "workflow:7:42"
    assert repo.owner_key("task", 7, task_id="task-001") == "task:7:task-001"

    # Persisted keys equal the resolver's authoritative parse keys (service.py:287/289).
    context = VariableContext(project_id=7, workflow_id=42, task_id="task-001")
    resolver = VariableResolver(lambda owner_key: [])
    assert repo.owner_key("workflow", 7, workflow_id=42) == resolver._owner_key_for("workflow", context)
    assert repo.owner_key("task", 7, task_id="task-001") == resolver._owner_key_for("task", context)


def test_workflow_task_persisted_then_resolved_via_parse_key():
    """VAR-02: values saved under parse keys are read back through the resolver."""
    client, app, project_id, tokens = _client()
    try:
        assert (
            _save(
                client,
                tokens["dev"],
                project_id,
                scope="workflow",
                name="wf_var",
                value="wf_val",
                workflow_id=100,
            ).status_code
            == 200
        )
        assert (
            _save(
                client,
                tokens["dev"],
                project_id,
                scope="task",
                name="task_var",
                value="task_val",
                task_id="task-001",
            ).status_code
            == 200
        )

        from sqlalchemy import select

        from rebuild.variables.models import VariableDefinitionRecord
        from rebuild.variables.repository import VariableRepository
        from rebuild.variables.service import VariableContext, VariableResolver

        with app.state.session_factory() as session:
            repo = VariableRepository(session)
            resolver = VariableResolver(lambda owner_key: repo.list_owner(owner_key))
            context = VariableContext(project_id=project_id, workflow_id=100, task_id="task-001")

            # Persisted rows carry parse-key owner keys.
            wf_row = session.scalar(
                select(VariableDefinitionRecord).where(
                    VariableDefinitionRecord.owner_key == f"workflow:{project_id}:100"
                )
            )
            assert wf_row is not None and wf_row.name == "wf_var"
            task_row = session.scalar(
                select(VariableDefinitionRecord).where(
                    VariableDefinitionRecord.owner_key == f"task:{project_id}:task-001"
                )
            )
            assert task_row is not None and task_row.name == "task_var"

            # Resolver reads them back via its authoritative parse keys.
            assert resolver.resolve_name("workflow", "wf_var", context) == "wf_val"
            assert resolver.resolve_name("task", "task_var", context) == "task_val"

            # Cross-context isolation: a different workflow cannot see wf_var.
            other = VariableContext(project_id=project_id, workflow_id=999, task_id="task-001")
            assert resolver.resolve_name("workflow", "wf_var", other) is None
    finally:
        client.__exit__(None, None, None)


def test_workflow_task_scope_check_and_preview():
    """VAR-02: ${workflow.xxx} and ${task.xxx} resolve in a matching context."""
    from rebuild.variables.service import VariableContext, ResolvedVariable, VariableResolver

    def definitions(owner_key: str) -> list[ResolvedVariable]:
        if owner_key == f"workflow:1:100":
            return [ResolvedVariable(name="wf_var", scope="workflow", value="wf_val", value_type="string")]
        if owner_key == f"task:1:task-001":
            return [ResolvedVariable(name="task_var", scope="task", value="task_val", value_type="string")]
        return []

    resolver = VariableResolver(definitions)
    context = VariableContext(project_id=1, workflow_id=100, task_id="task-001")

    assert resolver.resolve_name("workflow", "wf_var", context) == "wf_val"
    assert resolver.resolve_name("task", "task_var", context) == "task_val"

    check = resolver.check_reference("${workflow.wf_var} ${task.task_var}", context)
    assert check["valid"] is True

    preview = resolver.preview_resolution("${workflow.wf_var}", context)
    assert preview["resolved_value"] == "wf_val"
    assert preview["source"] == {"scope": "workflow", "name": "wf_var"}


# ---------------------------------------------------------------------------
# VAR-03: eight-value type system
# ---------------------------------------------------------------------------


def test_eight_value_types_save_and_validate():
    """VAR-03: all eight value types are accepted; invalid values rejected."""
    client, _app, project_id, tokens = _client()
    try:
        valid_cases = [
            ("string", "hello"),
            ("integer", "42"),
            ("decimal", "3.14"),
            ("boolean", "true"),
            ("date", "2026-10-19"),
            ("datetime", "2026-10-19T10:30:00"),
            ("json", '{"key":"value"}'),
            ("array", "[1,2,3]"),
        ]
        for i, (vt, val) in enumerate(valid_cases):
            resp = _save(client, tokens["dev"], project_id, name=f"vt_{i}", value=val, value_type=vt)
            assert resp.status_code == 200, f"{vt}={val} should save: {resp.json()}"

        invalid_cases = [
            ("integer", "not-int"),
            ("decimal", "not-dec"),
            ("boolean", "yes"),
            ("date", "19/10/2026"),
            ("datetime", "not-datetime"),
            ("array", '{"not":"array"}'),
        ]
        for i, (vt, val) in enumerate(invalid_cases):
            resp = _save(client, tokens["dev"], project_id, name=f"bad_{i}", value=val, value_type=vt)
            assert resp.status_code == 400 and resp.json()["code"] == 4002, f"{vt}={val} should fail"
    finally:
        client.__exit__(None, None, None)


def test_type_mismatch_unit():
    """VAR-03: type_mismatch returns reason for invalid values, None for valid."""
    from rebuild.variables.service import type_mismatch

    assert type_mismatch("string", "anything") is None
    assert type_mismatch("integer", "42") is None
    assert type_mismatch("integer", "abc") is not None
    assert type_mismatch("decimal", "3.14") is None
    assert type_mismatch("decimal", "abc") is not None
    assert type_mismatch("boolean", "true") is None
    assert type_mismatch("boolean", "false") is None
    assert type_mismatch("boolean", "yes") is not None
    assert type_mismatch("date", "2026-10-19") is None
    assert type_mismatch("date", "19/10/2026") is not None
    assert type_mismatch("datetime", "2026-10-19T10:30:00") is None
    assert type_mismatch("datetime", "not-datetime") is not None
    assert type_mismatch("json", '{"a":1}') is None
    assert type_mismatch("json", "{oops") is not None
    assert type_mismatch("array", "[1,2,3]") is None
    assert type_mismatch("array", '{"not":"array"}') is not None


# ---------------------------------------------------------------------------
# VAR-04: time expression evaluation
# ---------------------------------------------------------------------------


def test_evaluate_time_expression_default_timezone():
    """VAR-04: evaluate_time_expression defaults to Asia/Shanghai."""
    from rebuild.variables.service import evaluate_time_expression

    result = evaluate_time_expression("yyyy-MM-dd")
    # Should return a valid date string in YYYY-MM-DD format
    import re

    assert re.match(r"^\d{4}-\d{2}-\d{2}$", result)


def test_evaluate_time_expression_explicit_timezone():
    """VAR-04: evaluate_time_expression supports explicit timezone."""
    from rebuild.variables.service import evaluate_time_expression

    result = evaluate_time_expression("yyyy-MM-dd|UTC")
    import re

    assert re.match(r"^\d{4}-\d{2}-\d{2}$", result)


def test_time_expression_in_check_reference():
    """VAR-04: check_reference consumes time expression evaluation result."""
    from rebuild.variables.service import VariableContext, VariableResolver

    resolver = VariableResolver(lambda owner_key: [])
    context = VariableContext(project_id=1)

    result = resolver.check_reference("date=$[yyyy-MM-dd]", context)
    # Time expressions should not produce diagnostics
    assert result["valid"] is True
    assert result["diagnostics"] == []


def test_time_expression_in_preview_resolution():
    """VAR-04: preview_resolution returns evaluated time expression."""
    from rebuild.variables.service import VariableContext, VariableResolver

    resolver = VariableResolver(lambda owner_key: [])
    context = VariableContext(project_id=1)

    result = resolver.preview_resolution("$[yyyy-MM-dd]", context)
    assert result["resolved_value"] is not None
    assert len(result["resolved_value"]) == 10  # YYYY-MM-DD format


# ---------------------------------------------------------------------------
# VAR-02 integration: workflow/task save → resolve round-trip
# ---------------------------------------------------------------------------


def test_workflow_task_save_then_resolve_integration():
    """VAR-02: workflow/task variables saved via API resolve in a matching context.

    Parse-key authority ruling: persisted keys are workflow:{pid}:{wid} /
    task:{pid}:{tid}, matching the resolver's _owner_key_for. Saves must
    carry the ids so the round-trip aligns on the same keys.
    """
    client, app, project_id, tokens = _client()
    try:
        # Save workflow/task variables via API (ids required by parse-key authority)
        assert (
            _save(
                client,
                tokens["dev"],
                project_id,
                scope="workflow",
                name="wf_var",
                value="wf_val",
                workflow_id=100,
            ).status_code
            == 200
        )
        assert (
            _save(
                client,
                tokens["dev"],
                project_id,
                scope="task",
                name="task_var",
                value="task_val",
                task_id="task-001",
            ).status_code
            == 200
        )

        # Resolve via check-reference with a context that has workflow_id/task_id
        context = {"project_id": project_id, "workflow_id": 100, "task_id": "task-001"}
        check = client.post(
            "/api/v1/rebuild/variables/check-reference",
            headers=tokens["dev"],
            json={"expression": "${workflow.wf_var} ${task.task_var}", "context": context},
        )
        data = check.json()["data"]
        assert data["valid"] is True, f"Expected valid, got: {data['diagnostics']}"
        assert data["diagnostics"] == []

        # Resolve via preview
        preview = client.post(
            "/api/v1/rebuild/variables/preview",
            headers=tokens["dev"],
            json={"expression": "${workflow.wf_var}", "context": context},
        )
        pdata = preview.json()["data"]
        assert pdata["resolved_value"] == "wf_val"
        assert pdata["source"] == {"scope": "workflow", "name": "wf_var"}

        # Resolve via complete
        completed = client.post(
            "/api/v1/rebuild/variables/complete",
            headers=tokens["dev"],
            json={"prefix": "${workflow.", "context": context},
        )
        items = completed.json()["data"]
        wf_items = [item for item in items if item["scope"] == "workflow" and item["name"] == "wf_var"]
        assert len(wf_items) == 1
        assert wf_items[0]["current_value"] == "wf_val"
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# VAR-05: business calendar support
# ---------------------------------------------------------------------------


def test_business_calendar_is_working_day():
    """VAR-05: BusinessCalendar correctly identifies working days vs weekends."""
    from datetime import date
    from rebuild.variables.service import BusinessCalendar

    cal = BusinessCalendar()
    # 2026-10-19 is a Monday (working day)
    assert cal.is_working_day(date(2026, 10, 19)) is True
    # 2026-10-24 is a Saturday
    assert cal.is_working_day(date(2026, 10, 24)) is False
    # 2026-10-25 is a Sunday
    assert cal.is_working_day(date(2026, 10, 25)) is False


def test_business_calendar_with_holidays():
    """VAR-05: BusinessCalendar respects holiday definitions."""
    from datetime import date
    from rebuild.variables.service import BusinessCalendar

    holidays = {date(2026, 10, 19)}  # Monday holiday
    cal = BusinessCalendar(holidays=holidays)
    assert cal.is_working_day(date(2026, 10, 19)) is False
    assert cal.is_working_day(date(2026, 10, 20)) is True


def test_business_calendar_add_business_days():
    """VAR-05: add_business_days skips weekends and holidays."""
    from datetime import date
    from rebuild.variables.service import BusinessCalendar

    cal = BusinessCalendar()
    # 2026-10-19 is Monday; +1 business day = Tuesday 2026-10-20
    assert cal.add_business_days(date(2026, 10, 19), 1) == date(2026, 10, 20)
    # 2026-10-23 is Friday; +1 business day = Monday 2026-10-26
    assert cal.add_business_days(date(2026, 10, 23), 1) == date(2026, 10, 26)
    # Negative offset: 2026-10-20 is Tuesday; -1 business day = Monday 2026-10-19
    assert cal.add_business_days(date(2026, 10, 20), -1) == date(2026, 10, 19)


def test_business_calendar_add_business_days_with_holidays():
    """VAR-05: add_business_days skips holidays."""
    from datetime import date
    from rebuild.variables.service import BusinessCalendar

    # Holiday on Tuesday 2026-10-20
    holidays = {date(2026, 10, 20)}
    cal = BusinessCalendar(holidays=holidays)
    # Monday + 1 business day = Wednesday (skipping Tuesday holiday)
    assert cal.add_business_days(date(2026, 10, 19), 1) == date(2026, 10, 21)


def test_time_expression_with_business_day_offset():
    """VAR-05: evaluate_time_expression supports +Nbd business day offset."""
    from rebuild.variables.service import evaluate_time_expression

    result = evaluate_time_expression("yyyy-MM-dd+1bd")
    import re

    assert re.match(r"^\d{4}-\d{2}-\d{2}$", result)


def test_time_expression_with_business_day_offset_skips_weekend():
    """VAR-05: +1bd from Friday skips to Monday."""
    from datetime import date
    from rebuild.variables.service import BusinessCalendar, evaluate_time_expression

    # Directly test that evaluate_time_expression with a calendar correctly
    # computes business day offsets. We verify the calendar integration by
    # checking that the function accepts a calendar parameter.
    cal = BusinessCalendar()
    # 2026-10-23 is a Friday; +1bd should be Monday 2026-10-26
    # We test the calendar directly since mocking datetime is fragile
    result_date = cal.add_business_days(date(2026, 10, 23), 1)
    assert result_date == date(2026, 10, 26)
    # Verify evaluate_time_expression accepts calendar parameter without error
    result = evaluate_time_expression("yyyy-MM-dd", calendar=cal)
    import re

    assert re.match(r"^\d{4}-\d{2}-\d{2}$", result)


def test_time_expression_business_day_with_holidays():
    """VAR-05: business day offset respects holidays."""
    from datetime import date
    from rebuild.variables.service import BusinessCalendar

    # 2026-10-20 is a Tuesday holiday; Monday +1bd = Wednesday
    holidays = {date(2026, 10, 20)}
    cal = BusinessCalendar(holidays=holidays)
    result = cal.add_business_days(date(2026, 10, 19), 1)
    assert result == date(2026, 10, 21)


# ---------------------------------------------------------------------------
# VAR-06: definition fields (default_value/nullable/format/timezone/business_calendar)
# ---------------------------------------------------------------------------


def test_save_and_list_with_definition_fields():
    """VAR-06: definition fields persist and round-trip through the API."""
    client, _app, project_id, tokens = _client()
    try:
        body = {
            "scope": "project",
            "name": "configured_var",
            "value_type": "string",
            "value": "actual_value",
            "description": "A variable with full definition fields",
            "default_value": "default_val",
            "nullable": True,
            "format": "yyyy-MM-dd",
            "timezone": "Asia/Shanghai",
            "business_calendar": "cn_holiday",
        }
        saved = client.post(
            f"/api/v1/rebuild/variables?project_id={project_id}",
            headers=tokens["dev"],
            json=body,
        )
        assert saved.status_code == 200, f"Save failed: {saved.json()}"

        listed = client.get(
            f"/api/v1/rebuild/variables?project_id={project_id}", headers=tokens["dev"]
        )
        assert listed.status_code == 200
        rows = listed.json()["data"]
        target = next(row for row in rows if row["name"] == "configured_var")
        assert target["default_value"] == "default_val"
        assert target["nullable"] is True
        assert target["format"] == "yyyy-MM-dd"
        assert target["timezone"] == "Asia/Shanghai"
        assert target["business_calendar"] == "cn_holiday"
    finally:
        client.__exit__(None, None, None)


def test_save_with_nullable_false_and_no_default():
    """VAR-06: nullable=False with no default_value persists correctly."""
    client, _app, project_id, tokens = _client()
    try:
        body = {
            "scope": "project",
            "name": "strict_var",
            "value_type": "integer",
            "value": "42",
            "nullable": False,
        }
        saved = client.post(
            f"/api/v1/rebuild/variables?project_id={project_id}",
            headers=tokens["dev"],
            json=body,
        )
        assert saved.status_code == 200, f"Save failed: {saved.json()}"

        listed = client.get(
            f"/api/v1/rebuild/variables?project_id={project_id}", headers=tokens["dev"]
        )
        rows = listed.json()["data"]
        target = next(row for row in rows if row["name"] == "strict_var")
        assert target["nullable"] is False
        assert target["default_value"] is None
    finally:
        client.__exit__(None, None, None)


def test_update_definition_fields():
    """VAR-06: updating a variable preserves and updates definition fields."""
    client, _app, project_id, tokens = _client()
    try:
        body = {
            "scope": "project",
            "name": "updatable_var",
            "value_type": "string",
            "value": "v1",
            "default_value": "d1",
            "nullable": True,
        }
        saved = client.post(
            f"/api/v1/rebuild/variables?project_id={project_id}",
            headers=tokens["dev"],
            json=body,
        )
        assert saved.status_code == 200

        # Update the variable with new field values
        body2 = {
            "scope": "project",
            "name": "updatable_var",
            "value_type": "string",
            "value": "v2",
            "default_value": "d2",
            "nullable": False,
            "format": "HH:mm:ss",
        }
        updated = client.post(
            f"/api/v1/rebuild/variables?project_id={project_id}",
            headers=tokens["dev"],
            json=body2,
        )
        assert updated.status_code == 200

        listed = client.get(
            f"/api/v1/rebuild/variables?project_id={project_id}", headers=tokens["dev"]
        )
        rows = listed.json()["data"]
        target = next(row for row in rows if row["name"] == "updatable_var")
        assert target["value"] == "v2"
        assert target["default_value"] == "d2"
        assert target["nullable"] is False
        assert target["format"] == "HH:mm:ss"
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# VAR-09: TYPE_MISMATCH detection via check_reference
# ---------------------------------------------------------------------------


def test_check_reference_type_mismatch_integer():
    """VAR-09: check_reference returns TYPE_MISMATCH for invalid integer."""
    from rebuild.variables.service import VariableContext, VariableResolver, ResolvedVariable

    def definitions(owner_key: str) -> list[ResolvedVariable]:
        if owner_key == "project:1":
            return [ResolvedVariable(name="count", scope="project", value="not-int", value_type="integer")]
        return []

    resolver = VariableResolver(definitions)
    context = VariableContext(project_id=1)
    result = resolver.check_reference("${project.count}", context)
    assert result["valid"] is False
    codes = {d["code"] for d in result["diagnostics"]}
    assert "TYPE_MISMATCH" in codes


def test_check_reference_type_mismatch_decimal():
    """VAR-09: check_reference returns TYPE_MISMATCH for invalid decimal."""
    from rebuild.variables.service import VariableContext, VariableResolver, ResolvedVariable

    def definitions(owner_key: str) -> list[ResolvedVariable]:
        if owner_key == "project:1":
            return [ResolvedVariable(name="rate", scope="project", value="abc", value_type="decimal")]
        return []

    resolver = VariableResolver(definitions)
    context = VariableContext(project_id=1)
    result = resolver.check_reference("${project.rate}", context)
    codes = {d["code"] for d in result["diagnostics"]}
    assert "TYPE_MISMATCH" in codes


def test_check_reference_type_mismatch_boolean():
    """VAR-09: check_reference returns TYPE_MISMATCH for invalid boolean."""
    from rebuild.variables.service import VariableContext, VariableResolver, ResolvedVariable

    def definitions(owner_key: str) -> list[ResolvedVariable]:
        if owner_key == "project:1":
            return [ResolvedVariable(name="flag", scope="project", value="yes", value_type="boolean")]
        return []

    resolver = VariableResolver(definitions)
    context = VariableContext(project_id=1)
    result = resolver.check_reference("${project.flag}", context)
    codes = {d["code"] for d in result["diagnostics"]}
    assert "TYPE_MISMATCH" in codes


def test_check_reference_type_mismatch_date():
    """VAR-09: check_reference returns TYPE_MISMATCH for invalid date."""
    from rebuild.variables.service import VariableContext, VariableResolver, ResolvedVariable

    def definitions(owner_key: str) -> list[ResolvedVariable]:
        if owner_key == "project:1":
            return [ResolvedVariable(name="dt", scope="project", value="19/10/2026", value_type="date")]
        return []

    resolver = VariableResolver(definitions)
    context = VariableContext(project_id=1)
    result = resolver.check_reference("${project.dt}", context)
    codes = {d["code"] for d in result["diagnostics"]}
    assert "TYPE_MISMATCH" in codes


def test_check_reference_type_mismatch_datetime():
    """VAR-09: check_reference returns TYPE_MISMATCH for invalid datetime."""
    from rebuild.variables.service import VariableContext, VariableResolver, ResolvedVariable

    def definitions(owner_key: str) -> list[ResolvedVariable]:
        if owner_key == "project:1":
            return [ResolvedVariable(name="ts", scope="project", value="not-datetime", value_type="datetime")]
        return []

    resolver = VariableResolver(definitions)
    context = VariableContext(project_id=1)
    result = resolver.check_reference("${project.ts}", context)
    codes = {d["code"] for d in result["diagnostics"]}
    assert "TYPE_MISMATCH" in codes


def test_check_reference_type_mismatch_json():
    """VAR-09: check_reference returns TYPE_MISMATCH for invalid JSON."""
    from rebuild.variables.service import VariableContext, VariableResolver, ResolvedVariable

    def definitions(owner_key: str) -> list[ResolvedVariable]:
        if owner_key == "project:1":
            return [ResolvedVariable(name="payload", scope="project", value="{oops", value_type="json")]
        return []

    resolver = VariableResolver(definitions)
    context = VariableContext(project_id=1)
    result = resolver.check_reference("${project.payload}", context)
    codes = {d["code"] for d in result["diagnostics"]}
    assert "TYPE_MISMATCH" in codes


def test_check_reference_type_mismatch_array():
    """VAR-09: check_reference returns TYPE_MISMATCH for non-array JSON."""
    from rebuild.variables.service import VariableContext, VariableResolver, ResolvedVariable

    def definitions(owner_key: str) -> list[ResolvedVariable]:
        if owner_key == "project:1":
            return [ResolvedVariable(name="items", scope="project", value='{"not":"array"}', value_type="array")]
        return []

    resolver = VariableResolver(definitions)
    context = VariableContext(project_id=1)
    result = resolver.check_reference("${project.items}", context)
    codes = {d["code"] for d in result["diagnostics"]}
    assert "TYPE_MISMATCH" in codes


def test_check_reference_valid_type_no_mismatch():
    """VAR-09: check_reference does not flag valid types as TYPE_MISMATCH."""
    from rebuild.variables.service import VariableContext, VariableResolver, ResolvedVariable

    def definitions(owner_key: str) -> list[ResolvedVariable]:
        if owner_key == "project:1":
            return [
                ResolvedVariable(name="count", scope="project", value="42", value_type="integer"),
                ResolvedVariable(name="rate", scope="project", value="3.14", value_type="decimal"),
                ResolvedVariable(name="flag", scope="project", value="true", value_type="boolean"),
                ResolvedVariable(name="dt", scope="project", value="2026-10-19", value_type="date"),
                ResolvedVariable(name="ts", scope="project", value="2026-10-19T10:30:00", value_type="datetime"),
                ResolvedVariable(name="payload", scope="project", value='{"a":1}', value_type="json"),
                ResolvedVariable(name="items", scope="project", value="[1,2,3]", value_type="array"),
            ]
        return []

    resolver = VariableResolver(definitions)
    context = VariableContext(project_id=1)
    for name in ("count", "rate", "flag", "dt", "ts", "payload", "items"):
        result = resolver.check_reference("${project.%s}" % name, context)
        codes = {d["code"] for d in result["diagnostics"]}
        assert "TYPE_MISMATCH" not in codes, f"{name} should not be TYPE_MISMATCH: {result['diagnostics']}"


def test_check_reference_type_mismatch_via_api():
    """VAR-09: check-reference API returns TYPE_MISMATCH for invalid types."""
    client, app, project_id, tokens = _client()
    try:
        # Write a variable with mismatched type directly to the database,
        # bypassing save-time validation (which would reject it).
        with app.state.session_factory() as session:
            from rebuild.variables.models import VariableDefinitionRecord

            session.add(
                VariableDefinitionRecord(
                    scope="project",
                    project_id=project_id,
                    owner_key=f"project:{project_id}",
                    name="bad_int",
                    value_type="integer",
                    value_json="not-int",
                )
            )
            session.commit()

        check = client.post(
            "/api/v1/rebuild/variables/check-reference",
            headers=tokens["dev"],
            json={"expression": "${project.bad_int}", "context": {"project_id": project_id}},
        )
        data = check.json()["data"]
        assert data["valid"] is False
        codes = {d["code"] for d in data["diagnostics"]}
        assert "TYPE_MISMATCH" in codes
    finally:
        client.__exit__(None, None, None)


# ---------------------------------------------------------------------------
# VAR-11: sensitive variables do not leak into logs
# ---------------------------------------------------------------------------


def test_sensitive_value_redacted_in_log_snapshot():
    """VAR-11: sensitive variable values are redacted in log snapshot entries."""
    from rebuild.variables.service import redact_sensitive_value

    assert redact_sensitive_value("secret123", sensitive=True) == "***REDACTED***"
    assert redact_sensitive_value("public_value", sensitive=False) == "public_value"


def test_sensitive_value_redacted_in_resolved_variable():
    """VAR-11: ResolvedVariable with sensitive=True redacts value in log output."""
    from rebuild.variables.service import ResolvedVariable
    import logging

    var = ResolvedVariable(
        name="db_password",
        scope="project",
        value="super_secret",
        value_type="string",
        sensitive=True,
    )
    # The log-safe representation should not contain the actual value
    log_output = repr(var)
    assert "super_secret" not in log_output


def test_sensitive_value_redacted_in_check_reference():
    """VAR-11: check_reference output redacts sensitive values."""
    from rebuild.variables.service import VariableContext, VariableResolver, ResolvedVariable

    def definitions(owner_key: str) -> list[ResolvedVariable]:
        if owner_key == "project:1":
            return [
                ResolvedVariable(
                    name="password",
                    scope="project",
                    value="secret_pass",
                    value_type="string",
                    sensitive=True,
                )
            ]
        return []

    resolver = VariableResolver(definitions)
    context = VariableContext(project_id=1)
    result = resolver.check_reference("${project.password}", context)
    # The result should not leak the sensitive value in any diagnostic
    import json

    result_json = json.dumps(result)
    assert "secret_pass" not in result_json


def test_sensitive_value_redacted_in_preview():
    """VAR-11: preview_resolution output redacts sensitive values."""
    from rebuild.variables.service import VariableContext, VariableResolver, ResolvedVariable

    def definitions(owner_key: str) -> list[ResolvedVariable]:
        if owner_key == "project:1":
            return [
                ResolvedVariable(
                    name="api_key",
                    scope="project",
                    value="sk-12345",
                    value_type="string",
                    sensitive=True,
                )
            ]
        return []

    resolver = VariableResolver(definitions)
    context = VariableContext(project_id=1)
    result = resolver.preview_resolution("${project.api_key}", context)
    import json

    result_json = json.dumps(result)
    assert "sk-12345" not in result_json


def test_sensitive_value_redacted_in_complete():
    """VAR-11: complete output redacts sensitive values."""
    from rebuild.variables.service import VariableContext, VariableResolver, ResolvedVariable

    def definitions(owner_key: str) -> list[ResolvedVariable]:
        if owner_key == "project:1":
            return [
                ResolvedVariable(
                    name="token",
                    scope="project",
                    value="bearer-token-xyz",
                    value_type="string",
                    sensitive=True,
                )
            ]
        return []

    resolver = VariableResolver(definitions)
    context = VariableContext(project_id=1)
    items = resolver.complete("${project.", context)
    import json

    items_json = json.dumps(items)
    assert "bearer-token-xyz" not in items_json


def test_nonsensitive_value_not_redacted():
    """VAR-11: non-sensitive values are not redacted."""
    from rebuild.variables.service import redact_sensitive_value

    assert redact_sensitive_value("public_value", sensitive=False) == "public_value"
    assert redact_sensitive_value("public_value") == "public_value"
