"""Resource edit-flow API tests — content read, version append, script checks.

Covers the three endpoints added for resource-management script editing:
``GET /{id}/versions/{v}/content``, ``POST /{id}/versions`` and
``POST /{id}/script-checks``. Asserts the append path is keyed by resource_id
(no duplicate resource when the filename drifts), the version chain stays
monotonic and immutable, and the check endpoint's contract
(``syntax.status`` / ``references`` / ``run``) plus its auth and frame gates.
"""

from fastapi.testclient import TestClient
from sqlalchemy import select

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.models import ProjectMemberRecord, UserRecord
from rebuild.identity.repository import UserRepository
from rebuild.project.models import ProjectRecord
from rebuild.sshnode.governance import SshNodeAccess
from rebuild.sshnode.models import SshNodeRecord

RESOURCES = "/api/v1/rebuild/resources"
MAX_SIZE_BYTES = 20 * 1024 * 1024


def _client(*, ssh_trial_runner=None):
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="r4-resource-edit-secret", ssh_trial_runner=ssh_trial_runner)
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        admin = UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        dev = UserRepository(session).create(username="dev", password="dev-pass", role=Role.DEVELOPER)
        viewer = UserRepository(session).create(username="viewer", password="viewer-pass", role=Role.VIEWER)
        owned = ProjectRecord(name="r4-res-edit-owned", description="", owner_id=dev.id)
        other = ProjectRecord(name="r4-res-edit-other", description="", owner_id=admin.id)
        session.add_all((owned, other))
        session.commit()
        owned_id, other_id = owned.id, other.id
        session.add(ProjectMemberRecord(project_id=owned_id, user_id=viewer.id, role="viewer"))
        session.commit()
    tokens = {}
    for username, password in (("admin", "admin-pass"), ("dev", "dev-pass"), ("viewer", "viewer-pass")):
        response = client.post("/api/v1/rebuild/login", json={"username": username, "password": password})
        tokens[username] = {"Authorization": f"Bearer {response.json()['data']['token']}"}
    return client, app, owned_id, other_id, tokens


def _upload(client, headers, project_id, filename="etl_job.sql", kind="sql", content=b"SELECT 1;"):
    return client.post(
        f"{RESOURCES}/uploads",
        headers=headers,
        data={"project_id": str(project_id), "kind": kind},
        files={"file": (filename, content, "application/octet-stream")},
    )


def _append(client, headers, project_id, resource_id, content: bytes, filename="etl_job.sql"):
    return client.post(
        f"{RESOURCES}/{resource_id}/versions",
        headers=headers,
        data={"project_id": str(project_id)},
        files={"file": (filename, content, "application/octet-stream")},
    )


def _check(client, headers, project_id, resource_id, content, **extra):
    return client.post(
        f"{RESOURCES}/{resource_id}/script-checks",
        headers=headers,
        json={"project_id": project_id, "content": content, **extra},
    )


def test_content_endpoint_reads_utf8_and_is_project_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path))
    client, app, owned_id, other_id, tokens = _client()
    try:
        content = "SELECT 1;\n-- 中文注释\n".encode("utf-8")
        upload = _upload(client, tokens["dev"], owned_id, filename="clean.sql", content=content)
        resource_id = upload.json()["data"]["resource_id"]
        url = f"{RESOURCES}/{resource_id}/versions/1/content"

        # VIEW_ALL is enough to read (viewer is a project member).
        viewer = client.get(url, headers=tokens["viewer"], params={"project_id": owned_id})
        assert viewer.status_code == 200
        data = viewer.json()["data"]
        assert data["resource_id"] == resource_id
        assert data["version"] == 1
        assert data["name"] == "clean.sql"
        assert data["content"].encode("utf-8") == content

        missing_version = client.get(
            f"{RESOURCES}/{resource_id}/versions/9/content", headers=tokens["dev"], params={"project_id": owned_id}
        )
        assert missing_version.status_code == 404 and missing_version.json()["code"] == "RES_VERSION_NOT_FOUND"

        foreign = client.get(url, headers=tokens["admin"], params={"project_id": other_id})
        assert foreign.status_code == 404 and foreign.json()["code"] == "RES_OBJECT_NOT_FOUND"

        # The login call sets a session cookie that TestClient replays, so clear
        # it to exercise the genuinely unauthenticated path.
        client.cookies.clear()
        anonymous = client.get(url, params={"project_id": owned_id})
        assert anonymous.status_code == 401 and anonymous.json()["code"] == 1001

        missing_project = client.get(url, headers=tokens["dev"])
        assert missing_project.status_code == 400 and missing_project.json()["code"] == 4001
    finally:
        client.__exit__(None, None, None)


def test_append_version_is_resource_scoped_and_immutable(tmp_path, monkeypatch):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path))
    client, app, owned_id, _other_id, tokens = _client()
    try:
        first = _upload(client, tokens["dev"], owned_id, filename="etl_job.sql", content=b"SELECT 1;")
        resource_id = first.json()["data"]["resource_id"]

        # The edited draft arrives under a different filename: append must still
        # extend the SAME resource instead of forking a duplicate.
        second = _append(client, tokens["dev"], owned_id, resource_id, b"SELECT 2;", filename="etl_job_v2.sql")
        assert second.status_code == 200
        payload = second.json()["data"]
        assert payload["resource_id"] == resource_id
        assert payload["version"] == 2

        listed = client.get(
            f"{RESOURCES}/{resource_id}/versions", headers=tokens["dev"], params={"project_id": owned_id}
        ).json()["data"]
        assert [row["version"] for row in listed] == [1, 2]

        rows = client.get(RESOURCES, headers=tokens["dev"], params={"project_id": owned_id}).json()["data"]
        assert len(rows) == 1  # no duplicate resource created by the name drift
        assert rows[0]["latest_version"] == 2
        assert rows[0]["name"] == "etl_job.sql"  # name is immutable metadata

        # v1 bytes are untouched; v2 holds the edited content.
        assert (tmp_path / str(resource_id) / "v1").read_bytes() == b"SELECT 1;"
        assert (tmp_path / str(resource_id) / "v2").read_bytes() == b"SELECT 2;"

        unknown = _append(client, tokens["dev"], owned_id, 999, b"SELECT 3;")
        assert unknown.status_code == 404 and unknown.json()["code"] == "RES_OBJECT_NOT_FOUND"

        viewer = _append(client, tokens["viewer"], owned_id, resource_id, b"SELECT 4;")
        assert viewer.status_code == 403 and viewer.json()["code"] == 1003

        oversized = _append(client, tokens["dev"], owned_id, resource_id, b"x" * (MAX_SIZE_BYTES + 1))
        assert oversized.status_code == 400 and oversized.json()["code"] == "RES_SIZE_EXCEEDED"

        missing_file = client.post(
            f"{RESOURCES}/{resource_id}/versions", headers=tokens["dev"], data={"project_id": str(owned_id)}
        )
        assert missing_file.status_code == 400 and missing_file.json()["code"] == 4001
    finally:
        client.__exit__(None, None, None)


def test_script_checks_sql_syntax_and_references(tmp_path, monkeypatch):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path))
    client, app, owned_id, _other_id, tokens = _client()
    try:
        _upload(client, tokens["dev"], owned_id, filename="etl_job.sql", kind="sql", content=b"SELECT 1;")
        resource_id = client.get(RESOURCES, headers=tokens["dev"], params={"project_id": owned_id}).json()["data"][0][
            "resource_id"
        ]

        ok = _check(client, tokens["dev"], owned_id, resource_id, "SELECT id FROM etl_job;")
        assert ok.status_code == 200
        data = ok.json()["data"]
        assert data["kind"] == "sql"
        assert data["syntax"]["status"] == "ok"
        assert data["syntax"]["diagnostics"] == []
        assert data["run"] is None  # execute defaults to static-only
        # etl_job resolves to the project resource itself, so no warning.
        assert [row["code"] for row in data["references"]] == []

        bad = _check(client, tokens["dev"], owned_id, resource_id, "SELECT FROM WHERE;")
        assert bad.status_code == 200
        bad_data = bad.json()["data"]
        assert bad_data["syntax"]["status"] == "error"
        assert bad_data["syntax"]["diagnostics"][0]["source"] == "syntax"
        assert bad_data["syntax"]["diagnostics"][0]["severity"] == "error"

        # Unknown ${resource.*} is an error; unknown table is only a warning.
        unknown_ref = _check(
            client, tokens["dev"], owned_id, resource_id, "SELECT id FROM etl_job WHERE x = ${resource.nope};"
        ).json()["data"]
        assert [row["code"] for row in unknown_ref["references"]] == ["SCRIPT_RESOURCE_REF_UNKNOWN"]
        assert unknown_ref["references"][0]["severity"] == "error"

        unknown_table = _check(client, tokens["dev"], owned_id, resource_id, "SELECT id FROM missing_table;").json()[
            "data"
        ]
        assert [row["code"] for row in unknown_table["references"]] == ["SCRIPT_TABLE_UNKNOWN"]
        assert unknown_table["references"][0]["severity"] == "warning"
        assert unknown_table["syntax"]["status"] == "ok"
    finally:
        client.__exit__(None, None, None)


def test_script_checks_python_syntax_and_imports_without_execution(tmp_path, monkeypatch):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path))
    client, app, owned_id, _other_id, tokens = _client()
    try:
        _upload(client, tokens["dev"], owned_id, filename="helper.py", kind="python", content=b"print(1)")
        resource_id = client.get(
            RESOURCES, headers=tokens["dev"], params={"project_id": owned_id, "kind": "python"}
        ).json()["data"][0]["resource_id"]

        ok = _check(
            client,
            tokens["dev"],
            owned_id,
            resource_id,
            "import os\nprint('hello-from-script')",
        )
        assert ok.status_code == 200
        data = ok.json()["data"]
        assert data["kind"] == "python"
        assert data["syntax"]["status"] == "ok"
        # os is stdlib → no import warning.
        assert data["references"] == []
        assert data["run"] is None

        syntax_error = _check(client, tokens["dev"], owned_id, resource_id, "def broken(:\n    pass").json()["data"]
        assert syntax_error["syntax"]["status"] == "error"
        assert syntax_error["syntax"]["diagnostics"][0]["code"] == "PY_SYNTAX_ERROR"
        assert syntax_error["syntax"]["diagnostics"][0]["line"] == 1

        unresolved = _check(client, tokens["dev"], owned_id, resource_id, "import not_installed_pkg").json()["data"]
        assert [row["code"] for row in unresolved["references"]] == ["PY_IMPORT_UNRESOLVED"]
        assert unresolved["references"][0]["severity"] == "warning"
    finally:
        client.__exit__(None, None, None)


def test_script_checks_shell_contract_and_execute_guard(tmp_path, monkeypatch):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path))
    client, app, owned_id, _other_id, tokens = _client()
    try:
        _upload(client, tokens["dev"], owned_id, filename="run.sh", kind="shell", content=b"echo hi")
        resource_id = client.get(
            RESOURCES, headers=tokens["dev"], params={"project_id": owned_id, "kind": "shell"}
        ).json()["data"][0]["resource_id"]

        ok = _check(client, tokens["dev"], owned_id, resource_id, "echo hello-from-shell")
        assert ok.status_code == 200
        data = ok.json()["data"]
        assert data["kind"] == "shell"
        # bash/sh may be absent on some hosts: ok or an explicit skipped warning.
        assert data["syntax"]["status"] in ("ok", "skipped")
        if data["syntax"]["status"] == "skipped":
            assert data["syntax"]["diagnostics"][0]["severity"] == "warning"
        assert data["run"] is None

        malformed = _check(client, tokens["dev"], owned_id, resource_id, "if [ -n x ]; then").json()["data"]
        assert malformed["syntax"]["status"] in ("error", "skipped")

        unknown_source = _check(client, tokens["dev"], owned_id, resource_id, "source /opt/other.sh").json()["data"]
        assert [row["code"] for row in unknown_source["references"]] == ["SH_SOURCE_UNKNOWN"]
        assert unknown_source["references"][0]["severity"] == "warning"

        # Script checks never execute, regardless of script kind.
        sql_id = _upload(client, tokens["dev"], owned_id, filename="q.sql", kind="sql").json()["data"]["resource_id"]
        refused = _check(client, tokens["dev"], owned_id, sql_id, "SELECT 1;", execute=True)
        assert refused.status_code == 400 and refused.json()["code"] == 4001
    finally:
        client.__exit__(None, None, None)


def test_ssh_trial_requires_visible_permitted_node_and_uses_selected_host(tmp_path, monkeypatch):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path))
    calls = []

    def fake_trial(node, kind, content):
        calls.append((node.id, kind, content))
        return {"executed": True, "exitCode": 0, "stdout": "remote ok", "stderr": ""}

    client, app, owned_id, _other_id, tokens = _client(ssh_trial_runner=fake_trial)
    try:
        resource_id = _upload(client, tokens["dev"], owned_id, filename="job.py", kind="python", content=b"print(1)").json()["data"]["resource_id"]
        with app.state.session_factory() as session:
            dev_id = session.scalar(select(UserRecord.id).where(UserRecord.username == "dev"))
            admin_id = session.scalar(select(UserRecord.id).where(UserRecord.username == "admin"))
            node = SshNodeRecord(name="trial-host", host="192.0.2.1", port=22, ssh_user="runner", cred="secret", enabled=True)
            session.add(node)
            session.flush()
            SshNodeAccess(session).claim(node.id, admin_id, allow_trial=False)
            node_id = node.id
            session.commit()

        url = f"{RESOURCES}/{resource_id}/ssh-trials"
        body = {"project_id": owned_id, "node_id": node_id, "content": "print('remote ok')"}
        hidden = client.post(url, headers=tokens["dev"], json=body)
        assert hidden.status_code == 403 and calls == []

        with app.state.session_factory() as session:
            SshNodeAccess(session).share(node_id, dev_id)
            session.commit()
        disabled = client.post(url, headers=tokens["dev"], json=body)
        assert disabled.status_code == 403 and calls == []

        with app.state.session_factory() as session:
            SshNodeAccess(session).get(node_id).allow_trial = True
            session.commit()
        syntax_error = client.post(url, headers=tokens["dev"], json={**body, "content": "def broken(:"})
        assert syntax_error.status_code == 200
        assert syntax_error.json()["data"]["syntax"]["status"] == "error"
        assert calls == []

        allowed = client.post(url, headers=tokens["dev"], json=body)
        assert allowed.status_code == 200
        assert allowed.json()["data"]["run"]["stdout"] == "remote ok"
        assert calls == [(node_id, "python", body["content"])]
    finally:
        client.__exit__(None, None, None)


def test_script_environment_reports_run_location_and_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path))
    client, app, owned_id, other_id, tokens = _client()
    try:
        url = f"{RESOURCES}/script-environment"

        ok = client.get(url, headers=tokens["viewer"], params={"project_id": owned_id})
        assert ok.status_code == 200
        data = ok.json()["data"]
        assert data["run_location"]["scope"] == "selected_ssh_node"
        assert data["python"]["available"] is True
        assert data["python"]["version"]
        assert data["python"]["package_count"] >= 0
        assert isinstance(data["python"]["packages"], list)
        assert set(data["shell"]) == {"available", "path", "kind", "version"}
        assert data["database"] is None
        assert data["output"]["channel"] == "run_log"

        missing_project = client.get(url, headers=tokens["dev"])
        assert missing_project.status_code == 400 and missing_project.json()["code"] == 4001

        # Project scoping still applies: admin is not a member of dev's project.
        foreign = client.get(url, headers=tokens["admin"], params={"project_id": other_id})
        assert foreign.status_code == 200

        client.cookies.clear()
        anonymous = client.get(url, params={"project_id": owned_id})
        assert anonymous.status_code == 401 and anonymous.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_script_checks_frame_and_auth_gates(tmp_path, monkeypatch):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path))
    client, app, owned_id, _other_id, tokens = _client()
    try:
        resource_id = _upload(client, tokens["dev"], owned_id).json()["data"]["resource_id"]

        empty = _check(client, tokens["dev"], owned_id, resource_id, "   ")
        assert empty.status_code == 400 and empty.json()["code"] == 4001

        bad_execute = client.post(
            f"{RESOURCES}/{resource_id}/script-checks",
            headers=tokens["dev"],
            json={"project_id": owned_id, "content": "SELECT 1;", "execute": "yes"},
        )
        assert bad_execute.status_code == 400 and bad_execute.json()["code"] == 4001

        bad_timeout = client.post(
            f"{RESOURCES}/{resource_id}/script-checks",
            headers=tokens["dev"],
            json={"project_id": owned_id, "content": "SELECT 1;", "timeout_seconds": "5"},
        )
        assert bad_timeout.status_code == 400 and bad_timeout.json()["code"] == 4001

        missing_project = client.post(
            f"{RESOURCES}/{resource_id}/script-checks", headers=tokens["dev"], json={"content": "SELECT 1;"}
        )
        assert missing_project.status_code == 400 and missing_project.json()["code"] == 4001

        viewer = _check(client, tokens["viewer"], owned_id, resource_id, "SELECT 1;")
        assert viewer.status_code == 403 and viewer.json()["code"] == 1003

        client.cookies.clear()
        anonymous = client.post(
            f"{RESOURCES}/{resource_id}/script-checks", json={"project_id": owned_id, "content": "SELECT 1;"}
        )
        assert anonymous.status_code == 401 and anonymous.json()["code"] == 1001

        oversized = _check(client, tokens["dev"], owned_id, resource_id, "x" * (MAX_SIZE_BYTES + 1))
        assert oversized.status_code == 400 and oversized.json()["code"] == "RES_SIZE_EXCEEDED"
    finally:
        client.__exit__(None, None, None)
