from fastapi.testclient import TestClient
import json
import base64
from contextlib import contextmanager

from sqlalchemy import select
from rebuild.api.app import create_app
import rebuild.api.app as rebuild_app
from rebuild.identity.models import ProjectMemberRecord, UserRecord
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.project.repository import ProjectRepository


_TEST_USERNAME = "rebuild-test-dev"
_TEST_PASSWORD = "unit-test-password"


@contextmanager
def developer_client(database_url: str):
    app = create_app(database_url, token_secret="unit-test-token-secret")
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            UserRepository(session).create(username=_TEST_USERNAME, password=_TEST_PASSWORD, role=Role.DEVELOPER)
            session.commit()
        yield client


def test_login_returns_token_and_role_context():
    with developer_client("sqlite+pysqlite:///:memory:") as client:
        response = client.post("/api/v1/rebuild/login", json={"username": _TEST_USERNAME, "password": _TEST_PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["user"]["role"] == "developer"
    assert body["data"]["token"]


def test_wrong_password_is_rejected_with_auth_error():
    with developer_client("sqlite+pysqlite:///:memory:") as client:
        response = client.post("/api/v1/rebuild/login", json={"username": _TEST_USERNAME, "password": "wrong"})

    assert response.status_code == 401
    assert response.json()["code"] == 1001


def test_developer_can_create_project_and_list_it():
    with developer_client("sqlite+pysqlite:///:memory:") as client:
        login = client.post("/api/v1/rebuild/login", json={"username": _TEST_USERNAME, "password": _TEST_PASSWORD})
        token = login.json()["data"]["token"]

        created = client.post(
            "/api/v1/rebuild/projects",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "I1验证项目", "description": "rebuild"},
        )
        listed = client.get("/api/v1/rebuild/projects", headers={"Authorization": f"Bearer {token}"})

    assert created.status_code == 200
    assert listed.json()["data"]["total"] == 1
    assert listed.json()["data"]["list"][0]["name"] == "I1验证项目"


def test_real_app_assembly_resolves_execute_sql_permission_for_project_owner():
    with developer_client("sqlite+pysqlite:///:memory:") as client:
        login = client.post("/api/v1/rebuild/login", json={"username": _TEST_USERNAME, "password": _TEST_PASSWORD})
        token = login.json()["data"]["token"]
        project = client.post(
            "/api/v1/rebuild/projects", headers={"Authorization": f"Bearer {token}"},
            json={"name": "sql-permission", "description": ""},
        ).json()["data"]["id"]
        response = client.post(
            f"/api/v1/projects/{project}/sql-ide/executions",
            headers={"Authorization": f"Bearer {token}"},
            json={"datasourceId": 1, "sql": "select 1", "mode": "auto"},
        )

    # The currently unconfigured SQL execution port is intentionally 501;
    # reaching it proves real auth assembly resolved EXECUTE_SQL successfully.
    assert response.status_code == 501
    assert response.json()["msg"] == "SQL IDE service is not configured"


def test_admin_can_list_projects_even_when_not_project_owner_or_member():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="unit-test-token-secret")
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="rebuild-test-admin", password="admin-password", role=Role.ADMIN)
            ProjectRepository(session).create(name="unowned-project", description="", owner_id=0)
            ProjectRepository(session).create(name="other-owner-project", description="", owner_id=999)
            session.commit()

        login = client.post(
            "/api/v1/rebuild/login", json={"username": "rebuild-test-admin", "password": "admin-password"}
        )
        listed = client.get(
            "/api/v1/rebuild/projects",
            headers={"Authorization": f"Bearer {login.json()['data']['token']}"},
        )

    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 2
    assert {project["name"] for project in listed.json()["data"]["list"]} == {
        "unowned-project",
        "other-owner-project",
    }


def test_developer_project_list_does_not_include_unowned_project():
    with developer_client("sqlite+pysqlite:///:memory:") as client:
        with client.app.state.session_factory() as session:
            ProjectRepository(session).create(name="foreign-project", description="", owner_id=999)
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": _TEST_USERNAME, "password": _TEST_PASSWORD})
        listed = client.get(
            "/api/v1/rebuild/projects",
            headers={"Authorization": f"Bearer {login.json()['data']['token']}"},
        )

    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 0


def test_project_member_can_list_member_project():
    with developer_client("sqlite+pysqlite:///:memory:") as client:
        with client.app.state.session_factory() as session:
            project = ProjectRepository(session).create(name="member-project", description="", owner_id=999)
            user = session.scalar(select(UserRecord).where(UserRecord.username == _TEST_USERNAME))
            session.add(ProjectMemberRecord(project_id=project.id, user_id=user.id, role="viewer"))
            session.commit()
        login = client.post("/api/v1/rebuild/login", json={"username": _TEST_USERNAME, "password": _TEST_PASSWORD})
        listed = client.get(
            "/api/v1/rebuild/projects",
            headers={"Authorization": f"Bearer {login.json()['data']['token']}"},
        )

    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1
    assert listed.json()["data"]["list"][0]["name"] == "member-project"


def test_datasource_validation_returns_capability_matrix():
    with developer_client("sqlite+pysqlite:///:memory:") as client:
        login = client.post("/api/v1/rebuild/login", json={"username": _TEST_USERNAME, "password": _TEST_PASSWORD})
        token = login.json()["data"]["token"]
        response = client.post(
            "/api/v1/rebuild/datasources/validate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "source",
                "kind": "mysql",
                "host": "mysql-src",
                "port": 3306,
                "database": "ec_retail",
                "username": "root",
            },
        )

    assert response.status_code == 200
    assert response.json()["data"]["capabilities"] == ["cross_schema", "metadata", "query"]


def test_logout_revokes_token_and_developer_cannot_add_member():
    with developer_client("sqlite+pysqlite:///:memory:") as client:
        login = client.post("/api/v1/rebuild/login", json={"username": _TEST_USERNAME, "password": _TEST_PASSWORD})
        token = login.json()["data"]["token"]
        headers = {"Authorization": f"Bearer {token}"}
        created = client.post("/api/v1/rebuild/projects", headers=headers, json={"name": "member-test"})
        project_id = created.json()["data"]["id"]
        denied = client.post(
            f"/api/v1/rebuild/projects/{project_id}/members",
            headers=headers,
            json={"username": "dev", "role": "viewer"},
        )
        logged_out = client.post("/api/v1/rebuild/logout", headers=headers)
        after_logout = client.get("/api/v1/rebuild/projects", headers=headers)

    assert created.status_code == 200
    assert denied.status_code == 403
    assert logged_out.status_code == 200
    assert after_logout.status_code == 401


def test_add_member_rejects_nonexistent_project():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="unit-test-token-secret")
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="rebuild-test-admin", password="admin-password", role=Role.ADMIN)
            session.commit()
        login = client.post(
            "/api/v1/rebuild/login", json={"username": "rebuild-test-admin", "password": "admin-password"}
        )
        headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}
        response = client.post(
            "/api/v1/rebuild/projects/99999/members",
            headers=headers,
            json={"username": "rebuild-test-admin", "role": "viewer"},
        )

    assert response.status_code == 404
    assert response.json()["code"] == 4042


def test_add_member_rejects_duplicate_member():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="unit-test-token-secret")
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="rebuild-test-admin", password="admin-password", role=Role.ADMIN)
            UserRepository(session).create(username="rebuild-test-dev2", password="dev-password", role=Role.DEVELOPER)
            session.commit()
        login = client.post(
            "/api/v1/rebuild/login", json={"username": "rebuild-test-admin", "password": "admin-password"}
        )
        headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}
        project = client.post("/api/v1/rebuild/projects", headers=headers, json={"name": "dup-member-test"})
        project_id = project.json()["data"]["id"]
        first = client.post(
            f"/api/v1/rebuild/projects/{project_id}/members",
            headers=headers,
            json={"username": "rebuild-test-dev2", "role": "viewer"},
        )
        second = client.post(
            f"/api/v1/rebuild/projects/{project_id}/members",
            headers=headers,
            json={"username": "rebuild-test-dev2", "role": "viewer"},
        )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["code"] == 4091


def test_admin_can_list_remove_and_update_members():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="unit-test-token-secret")
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="rebuild-test-admin", password="admin-password", role=Role.ADMIN)
            UserRepository(session).create(username="rebuild-test-dev3", password="dev-password", role=Role.DEVELOPER)
            session.commit()
        login = client.post(
            "/api/v1/rebuild/login", json={"username": "rebuild-test-admin", "password": "admin-password"}
        )
        headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}
        project = client.post("/api/v1/rebuild/projects", headers=headers, json={"name": "member-crud-test"})
        project_id = project.json()["data"]["id"]
        added = client.post(
            f"/api/v1/rebuild/projects/{project_id}/members",
            headers=headers,
            json={"username": "rebuild-test-dev3", "role": "viewer"},
        )
        listed = client.get(f"/api/v1/rebuild/projects/{project_id}/members", headers=headers)
        user_id = listed.json()["data"]["list"][0]["user_id"]
        updated = client.patch(
            f"/api/v1/rebuild/projects/{project_id}/members/{user_id}",
            headers=headers,
            json={"username": "rebuild-test-dev3", "role": "developer"},
        )
        removed = client.delete(
            f"/api/v1/rebuild/projects/{project_id}/members/{user_id}",
            headers=headers,
        )
        listed_after = client.get(f"/api/v1/rebuild/projects/{project_id}/members", headers=headers)

    assert added.status_code == 200
    assert listed.status_code == 200
    assert len(listed.json()["data"]["list"]) == 1
    assert updated.status_code == 200
    assert updated.json()["data"]["role"] == "developer"
    assert removed.status_code == 200
    assert listed_after.json()["data"]["list"] == []


def test_i2_status_returns_reconcile_summary_and_samples(tmp_path, monkeypatch):
    report = {
        "generated_at": "2026-10-14 05:34:07",
        "mode": "verify",
        "seed": 20260918,
        "summary": {"status": "PASS", "rows": 1620200, "mismatch": 0},
        "databases": {"ec_retail": {}, "datara_dw": {}},
    }
    report_path = tmp_path / "reconcile.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    samples_path = tmp_path / "samples"
    samples_path.mkdir()
    (samples_path / "orders_part.csv").write_text("id\n1\n", encoding="utf-8")
    monkeypatch.setenv("I2_RECONCILE_PATH", str(report_path))
    monkeypatch.setenv("I2_SAMPLES_PATH", str(samples_path))

    with developer_client("sqlite+pysqlite:///:memory:") as client:
        login = client.post("/api/v1/rebuild/login", json={"username": _TEST_USERNAME, "password": _TEST_PASSWORD})
        token = login.json()["data"]["token"]
        response = client.get("/api/v1/rebuild/i2/status", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["data"]["summary"]["status"] == "PASS"
    assert response.json()["data"]["samples"] == ["orders_part.csv"]


def test_validation_bootstrap_is_disabled_when_no_runtime_key_is_configured():
    with TestClient(create_app("sqlite+pysqlite:///:memory:", token_secret="unit-test-secret")) as client:
        response = client.post(
            "/api/v1/rebuild/validation-token",
            headers={"X-Backend-Validation-Key": "unit-test-key"},
        )

    assert response.status_code == 404
    assert response.json()["code"] == 4043


def test_validation_key_issues_short_lived_non_admin_token_and_rejects_bad_key():
    with TestClient(
        create_app(
            "sqlite+pysqlite:///:memory:",
            token_secret="unit-test-secret",
            validation_key="unit-test-key",
        )
    ) as client:
        rejected = client.post(
            "/api/v1/rebuild/validation-token",
            headers={"X-Backend-Validation-Key": "wrong-key"},
        )
        issued = client.post(
            "/api/v1/rebuild/validation-token",
            headers={"X-Backend-Validation-Key": "unit-test-key"},
        )
        token = issued.json()["data"]["token"]
        claims = json.loads(base64.urlsafe_b64decode(token.split(".", 1)[0] + "=="))
        headers = {"Authorization": f"Bearer {token}"}
        project = client.post("/api/v1/rebuild/projects", headers=headers, json={"name": "bootstrap-test"})
        permission_denial = client.post(
            f"/api/v1/rebuild/projects/{project.json()['data']['id']}/members",
            headers=headers,
            json={"username": "missing", "role": "viewer"},
        )

    assert rejected.status_code == 401
    assert issued.status_code == 200
    assert issued.json()["data"]["user"]["username"] == "validation-runner"
    assert issued.json()["data"]["user"]["role"] == "viewer"
    assert claims["exp"] - claims["iat"] <= 900
    assert project.status_code == 200
    assert permission_denial.status_code == 403


def test_app_requires_database_and_token_secrets_without_environment_defaults(monkeypatch):
    monkeypatch.delenv("REBUILD_DB_URL", raising=False)
    monkeypatch.delenv("REBUILD_TOKEN_SECRET", raising=False)

    try:
        create_app()
    except RuntimeError as exc:
        assert "REBUILD_DB_URL" in str(exc)
    else:
        raise AssertionError("create_app must reject missing database configuration")

    try:
        create_app("sqlite+pysqlite:///:memory:")
    except RuntimeError as exc:
        assert "REBUILD_TOKEN_SECRET" in str(exc)
    else:
        raise AssertionError("create_app must reject missing token signing configuration")


def test_datasource_profile_probe_uses_backend_managed_connection(monkeypatch):
    monkeypatch.setenv(
        "REBUILD_MYSQL_SRC_URL",
        "mysql+pymysql://unit_user:unit-test-pass@mysql-src:3306/ec_retail",
    )
    captured = {}

    def probe(draft):
        captured["draft"] = draft
        return {"connected": True, "database": draft.database, "capabilities": ["metadata", "query"]}

    monkeypatch.setattr(rebuild_app, "probe_datasource", probe)
    with TestClient(
        create_app("sqlite+pysqlite:///:memory:", token_secret="unit-test-secret", validation_key="unit-test-key")
    ) as client:
        with client.app.state.session_factory() as session:
            UserRepository(session).create(username="datasource-admin", password="admin-password", role=Role.ADMIN)
            session.commit()
        runner_token = client.post(
            "/api/v1/rebuild/validation-token",
            headers={"X-Backend-Validation-Key": "unit-test-key"},
        ).json()["data"]["token"]
        runner_denied = client.post(
            "/api/v1/rebuild/datasources/profiles/mysql-src/probe",
            headers={"Authorization": f"Bearer {runner_token}"},
        )
        admin_token = client.post(
            "/api/v1/rebuild/login", json={"username": "datasource-admin", "password": "admin-password"}
        ).json()["data"]["token"]
        response = client.post(
            "/api/v1/rebuild/datasources/profiles/mysql-src/probe",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert runner_denied.status_code == 403
    assert response.status_code == 200
    assert response.json()["data"]["connected"] is True
    assert response.json()["data"]["database"] == "ec_retail"
    assert captured["draft"].password == "unit-test-pass"
