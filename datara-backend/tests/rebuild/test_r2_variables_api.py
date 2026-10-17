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
        bad_type = _save(client, tokens["dev"], project_id, name="x", value="not-a-number", value_type="number")
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
                        "value_type": "number",
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
                        "value_type": "number",
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
                            "value_type": "number",
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
                            "value_type": "number",
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
