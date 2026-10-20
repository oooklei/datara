from datetime import datetime
import logging

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.project.models import ProjectRecord


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="datasource-test-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        admin = UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        dev = UserRepository(session).create(username="dev", password="dev-pass", role=Role.DEVELOPER)
        viewer = UserRepository(session).create(username="viewer", password="viewer-pass", role=Role.VIEWER)
        owned = ProjectRecord(name="owned", description="", owner_id=dev.id)
        other = ProjectRecord(name="other", description="", owner_id=admin.id)
        session.add_all((owned, other))
        session.commit()
        owned_id, other_id = owned.id, other.id
        identities = {"admin": admin.id, "dev": dev.id, "viewer": viewer.id}
        from rebuild.identity.models import ProjectMemberRecord

        session.add(ProjectMemberRecord(project_id=owned_id, user_id=viewer.id, role="viewer"))
        session.commit()

    tokens = {}
    for username, password in (("admin", "admin-pass"), ("dev", "dev-pass"), ("viewer", "viewer-pass")):
        response = client.post("/api/v1/rebuild/login", json={"username": username, "password": password})
        tokens[username] = {"Authorization": f"Bearer {response.json()['data']['token']}"}
    return client, app, owned_id, other_id, identities, tokens


def _profile(name="warehouse", password="do-not-return"):
    return {
        "name": name,
        "kind": "mysql",
        "host": "mysql-test",
        "port": 3306,
        "database": "analytics",
        "username": "operator",
        "password": password,
    }


def test_project_datasource_crud_is_project_scoped_and_password_is_not_returned():
    client, app, owned_id, other_id, _identities, tokens = _client()
    try:
        created = client.post(
            f"/api/v1/rebuild/projects/{owned_id}/datasources", headers=tokens["dev"], json=_profile()
        )
        assert created.status_code == 201
        created_data = created.json()["data"]
        datasource_id = created_data["id"]
        assert created_data["name"] == "warehouse"
        assert "password" not in created_data
        assert created_data["created_at"] and created_data["updated_at"]
        assert isinstance(datetime.fromisoformat(created_data["created_at"]), datetime)

        duplicate = client.post(
            f"/api/v1/rebuild/projects/{owned_id}/datasources", headers=tokens["dev"], json=_profile()
        )

        listed = client.get(f"/api/v1/rebuild/projects/{owned_id}/datasources", headers=tokens["dev"])
        hidden_from_other_project = client.get(
            f"/api/v1/rebuild/projects/{other_id}/datasources/{datasource_id}", headers=tokens["admin"]
        )
        updated = client.put(
            f"/api/v1/rebuild/projects/{owned_id}/datasources/{datasource_id}",
            headers=tokens["dev"],
            json=_profile(name="warehouse-v2", password=""),
        )
        assert listed.status_code == 200 and len(listed.json()["data"]["items"]) == 1
        assert duplicate.status_code == 409
        assert "password" not in listed.json()["data"]["items"][0]
        assert hidden_from_other_project.status_code == 404
        assert updated.status_code == 200 and updated.json()["data"]["name"] == "warehouse-v2"
        assert "password" not in updated.json()["data"]
        with app.state.session_factory() as session:
            from rebuild.datasource.models import ProjectDatasourceRecord

            assert session.get(ProjectDatasourceRecord, datasource_id).password == "do-not-return"
        deleted = client.delete(
            f"/api/v1/rebuild/projects/{owned_id}/datasources/{datasource_id}", headers=tokens["dev"]
        )
        missing = client.get(f"/api/v1/rebuild/projects/{owned_id}/datasources/{datasource_id}", headers=tokens["dev"])
        assert deleted.status_code == 200
        assert missing.status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_viewer_cannot_create_or_probe_project_datasource():
    client, app, owned_id, _other_id, _identities, tokens = _client()
    try:
        denied_create = client.post(
            f"/api/v1/rebuild/projects/{owned_id}/datasources", headers=tokens["viewer"], json=_profile()
        )
        assert denied_create.status_code == 403

        created = client.post(
            f"/api/v1/rebuild/projects/{owned_id}/datasources", headers=tokens["dev"], json=_profile()
        )
        datasource_id = created.json()["data"]["id"]
        denied_probe = client.post(
            f"/api/v1/rebuild/projects/{owned_id}/datasources/{datasource_id}/test", headers=tokens["viewer"]
        )
        assert denied_probe.status_code == 403
    finally:
        client.__exit__(None, None, None)


def test_admin_can_manage_project_datasource_and_test_uses_saved_connection(monkeypatch):
    client, app, _owned_id, other_id, _identities, tokens = _client()
    from rebuild.api import app as rebuild_app

    observed = []
    pool_requests = []

    class FakeConnection:
        def close(self):
            pass

    monkeypatch.setattr(
        app.state.datasource_engines,
        "connect",
        lambda project_id, datasource_id, draft: pool_requests.append((project_id, datasource_id))
        or FakeConnection(),
    )

    def fake_probe(draft, *, connector=None):
        observed.append(draft)
        assert connector is not None
        connector(draft).close()
        return {"connected": True, "database": draft.database, "server_version": "8.test", "capabilities": ["metadata"]}

    monkeypatch.setattr(rebuild_app, "probe_datasource", fake_probe)
    try:
        created = client.post(
            f"/api/v1/rebuild/projects/{other_id}/datasources", headers=tokens["admin"], json=_profile()
        )
        assert created.status_code == 201
        datasource_id = created.json()["data"]["id"]
        tested = client.post(
            f"/api/v1/rebuild/projects/{other_id}/datasources/{datasource_id}/test", headers=tokens["admin"]
        )
        assert tested.status_code == 200
        assert tested.json()["data"]["connected"] is True
        assert "password" not in tested.text
        assert len(observed) == 1
        assert observed[0].username == "operator"
        assert observed[0].password == "do-not-return"
        assert pool_requests == [(other_id, datasource_id)]
    finally:
        client.__exit__(None, None, None)


def test_datasource_routes_reject_missing_or_invalid_token():
    client, app, owned_id, _other_id, _identities, _tokens = _client()
    try:
        missing = client.get(f"/api/v1/rebuild/projects/{owned_id}/datasources")
        invalid = client.post(
            f"/api/v1/rebuild/projects/{owned_id}/datasources",
            headers={"Authorization": "Bearer not-a-token"},
            json=_profile(),
        )
        assert missing.status_code == 401
        assert invalid.status_code == 401
    finally:
        client.__exit__(None, None, None)


def test_ephemeral_validation_cannot_probe_an_arbitrary_host():
    client, app, _owned_id, _other_id, _identities, tokens = _client()
    try:
        response = client.post(
            "/api/v1/rebuild/datasources/validate",
            headers=tokens["dev"],
            json={**_profile(), "probe": True},
        )
        assert response.status_code == 400
        assert response.json()["code"] == 4002
    finally:
        client.__exit__(None, None, None)


def test_metadata_browser_uses_saved_profile_and_returns_schema_qualified_identity(monkeypatch):
    client, app, owned_id, other_id, _identities, tokens = _client()
    from rebuild.api import app as rebuild_app

    created = client.post(
        f"/api/v1/rebuild/projects/{owned_id}/datasources", headers=tokens["dev"], json=_profile()
    )
    datasource_id = created.json()["data"]["id"]
    constructed = []
    pool_requests = []

    class FakeConnection:
        def close(self):
            pass

    monkeypatch.setattr(
        app.state.datasource_engines,
        "connect",
        lambda project_id, record_id, draft: pool_requests.append((project_id, record_id)) or FakeConnection(),
    )

    class Catalog:
        def __init__(self, draft, *, connector):
            constructed.append((draft, connector))
            connector(draft).close()

        def schemas(self, *, after=None, limit=100):
            return ["analytics", "shared"]

        def objects(self, schema, *, after=None, limit=100):
            return [
                {"schema": schema, "name": "orders", "type": "table"},
                {"schema": schema, "name": "orders_view", "type": "view"},
            ]

        def columns(self, schema, object_name, *, limit=500):
            return [
                {
                    "schema": schema,
                    "object": object_name,
                    "name": "order_id",
                    "data_type": "bigint",
                    "database_type": "bigint unsigned",
                    "nullable": False,
                    "primary_key": True,
                    "comment": "identifier",
                }
            ]

    monkeypatch.setattr(
        rebuild_app,
        "metadata_catalog_for",
        lambda draft, *, connector: Catalog(draft, connector=connector),
    )
    try:
        schemas = client.get(
            f"/api/v1/rebuild/projects/{owned_id}/datasources/{datasource_id}/schemas", headers=tokens["dev"]
        )
        objects = client.get(
            f"/api/v1/rebuild/projects/{owned_id}/datasources/{datasource_id}/objects",
            headers=tokens["dev"],
            params={"schema": "shared"},
        )
        columns = client.get(
            f"/api/v1/rebuild/projects/{owned_id}/datasources/{datasource_id}/columns",
            headers=tokens["dev"],
            params={"schema": "shared", "object_name": "orders"},
        )
        cross_project = client.get(
            f"/api/v1/rebuild/projects/{other_id}/datasources/{datasource_id}/schemas", headers=tokens["admin"]
        )

        assert schemas.status_code == 200
        assert schemas.json()["data"]["items"] == ["analytics", "shared"]
        assert objects.status_code == 200
        assert objects.json()["data"]["items"][0]["schema"] == "shared"
        assert columns.status_code == 200
        assert columns.json()["data"]["items"][0]["primary_key"] is True
        assert cross_project.status_code == 404
        assert all(draft.password == "do-not-return" for draft, _connector in constructed)
        assert all(callable(connector) for _draft, connector in constructed)
        assert len(constructed) == 3
        assert pool_requests == [(owned_id, datasource_id)] * 3
    finally:
        client.__exit__(None, None, None)


def test_postgresql_profile_routes_to_postgresql_metadata_catalog(monkeypatch):
    client, app, owned_id, _other_id, _identities, tokens = _client()
    from rebuild.api import app as rebuild_app

    created = client.post(
        f"/api/v1/rebuild/projects/{owned_id}/datasources",
        headers=tokens["dev"],
        json={**_profile(), "kind": "postgresql", "port": 5432},
    )
    assert created.status_code == 201
    datasource_id = created.json()["data"]["id"]
    selected = []

    class FakeConnection:
        def close(self):
            pass

    class PostgreSQLCatalog:
        def __init__(self, draft, *, connector):
            selected.append(draft.kind)
            connector(draft).close()

        def schemas(self, *, after=None, limit=100):
            return ["analytics"]

    monkeypatch.setattr(
        app.state.datasource_engines,
        "connect",
        lambda _project_id, _datasource_id, _draft: FakeConnection(),
    )
    monkeypatch.setattr(
        rebuild_app,
        "metadata_catalog_for",
        lambda draft, *, connector: PostgreSQLCatalog(draft, connector=connector),
    )
    try:
        response = client.get(
            f"/api/v1/rebuild/projects/{owned_id}/datasources/{datasource_id}/schemas",
            headers=tokens["dev"],
        )
        assert response.status_code == 200
        assert response.json()["data"]["items"] == ["analytics"]
        assert selected == ["postgresql"]
    finally:
        client.__exit__(None, None, None)


def test_postgresql_metadata_failure_logs_safe_diagnostic_without_exception_message(monkeypatch, caplog):
    client, _app, owned_id, _other_id, _identities, tokens = _client()
    created = client.post(
        f"/api/v1/rebuild/projects/{owned_id}/datasources",
        headers=tokens["dev"],
        json={**_profile(), "kind": "postgresql", "port": 5432},
    )
    datasource_id = created.json()["data"]["id"]

    class BrokenCatalog:
        def __init__(self, _draft, *, connector):
            self._connector = connector

        def schemas(self, *, after=None, limit=100):
            raise RuntimeError("do-not-log-this-secret-detail")

    from rebuild.api import app as rebuild_app

    monkeypatch.setattr(
        rebuild_app,
        "metadata_catalog_for",
        lambda draft, *, connector: BrokenCatalog(draft, connector=connector),
    )
    caplog.set_level(logging.WARNING, logger="rebuild.api.app")
    try:
        response = client.get(
            f"/api/v1/rebuild/projects/{owned_id}/datasources/{datasource_id}/schemas", headers=tokens["dev"]
        )
        assert response.status_code == 502
        assert "metadata_browse_failed operation=schemas exception_type=RuntimeError" in caplog.text
        assert "do-not-log-this-secret-detail" not in caplog.text
    finally:
        client.__exit__(None, None, None)


def test_profile_update_and_delete_invalidate_project_scoped_engines(monkeypatch):
    client, app, owned_id, _other_id, _identities, tokens = _client()
    created = client.post(
        f"/api/v1/rebuild/projects/{owned_id}/datasources", headers=tokens["dev"], json=_profile()
    )
    datasource_id = created.json()["data"]["id"]
    invalidations = []
    monkeypatch.setattr(
        app.state.datasource_engines,
        "invalidate",
        lambda project_id, record_id: invalidations.append((project_id, record_id)) or True,
    )
    try:
        updated = client.put(
            f"/api/v1/rebuild/projects/{owned_id}/datasources/{datasource_id}",
            headers=tokens["dev"],
            json=_profile(name="warehouse-v2", password="rotated"),
        )
        deleted = client.delete(
            f"/api/v1/rebuild/projects/{owned_id}/datasources/{datasource_id}", headers=tokens["dev"]
        )

        assert updated.status_code == 200
        assert deleted.status_code == 200
        assert invalidations == [(owned_id, datasource_id), (owned_id, datasource_id)]
    finally:
        client.__exit__(None, None, None)
