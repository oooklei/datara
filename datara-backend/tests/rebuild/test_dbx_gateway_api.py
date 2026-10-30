from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from rebuild.common.db import Base
from rebuild.dbx.access import DbxConnectionAccess, DbxObjectAccess
from rebuild.dbx.api import build_dbx_router
from rebuild.dbx.models import DbxConnectionOwnershipRecord, DbxConnectionShareRecord, DbxObjectOwnershipRecord, DbxObjectShareRecord
from rebuild.identity.models import UserRecord


class FakeDbx:
    def __init__(self):
        self.queries = []
        self.connections = [
            {"id": "owned", "name": "Sales", "database": "sales", "password": "secret"},
            {"id": "other", "name": "HR", "database": "hr", "password": "other-secret"},
        ]
        self.saved = []
        self.sql_library = {"folders": [], "files": [{"id": "legacy-sql", "connectionId": "owned", "name": "orders"}]}
        self.ai_conversations = [{"id": "legacy-ai", "connectionId": "owned", "messages": []}]
        self.ai_configs = [{"id": "legacy-config", "name": "Legacy AI", "apiKey": "private"}]

    def _request(self, method, path, *, params=None, payload=None):
        assert method == "GET"
        if path == "ai/conversations":
            return self.ai_conversations
        if path == "ai/configs":
            return self.ai_configs
        assert path == "saved-sql"
        return self.sql_library

    def list_connections(self):
        return self.connections

    def save_connection(self, config):
        self.saved.append(config)
        self.connections = [item for item in self.connections if item["id"] != config["id"]] + [config]
        return {}

    def remove_connection(self, connection_id):
        self.connections = [item for item in self.connections if item["id"] != connection_id]
        return {}

    def test_connection(self, config):
        assert config["id"] in {item["id"] for item in self.connections}
        return {"connected": True}

    def list_databases(self, connection_id):
        return [{"name": "sales"}]

    def list_schemas(self, connection_id, database):
        return ["public"]

    def list_objects(self, connection_id, database, schema):
        return [{"name": "orders", "object_type": "TABLE"}]

    def list_columns(self, connection_id, database, schema, table):
        return [{"name": "id"}]

    def execute_sql(self, **request):
        self.queries.append(request)
        return {"rows": [[1]]}


def setup_gateway():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[UserRecord.__table__, DbxConnectionOwnershipRecord.__table__, DbxConnectionShareRecord.__table__, DbxObjectOwnershipRecord.__table__, DbxObjectShareRecord.__table__])
    factory = sessionmaker(bind=engine)
    with Session(engine) as session:
        session.add_all([
            UserRecord(id=1, username="admin", password_hash="x", role="admin"),
            UserRecord(id=2, username="owner", password_hash="x", role="developer"),
            UserRecord(id=3, username="other", password_hash="x", role="developer"),
        ])
        session.flush()
        DbxConnectionAccess(session).claim(connection_id="owned", project_id=7, owner_id=2)
        session.commit()

    users = {
        "admin": {"user_id": 1, "role": "admin"},
        "owner": {"user_id": 2, "role": "developer"},
        "other": {"user_id": 3, "role": "developer"},
    }

    def current_user(authorization):
        user = users.get(authorization.removeprefix("Bearer "))
        if user is None:
            raise ValueError("invalid token")
        return user

    dbx = FakeDbx()
    app = FastAPI()
    app.state.session_factory = factory
    app.include_router(build_dbx_router(factory, current_user, lambda *args: None, client_factory=lambda: dbx))
    return TestClient(app), dbx


def test_owner_filter_and_secret_redaction():
    client, _ = setup_gateway()
    base = "/api/v1/rebuild/dbx/projects/7"
    owner = client.get(f"{base}/connections", headers={"Authorization": "Bearer owner"})
    assert owner.status_code == 200
    assert owner.json()["data"]["items"] == [{"id": "owned", "name": "Sales", "database": "sales", "can_manage": True, "can_claim": False}]
    assert "secret" not in owner.text
    assert client.get(f"{base}/connections", headers={"Authorization": "Bearer other"}).json()["data"]["items"] == []
    assert len(client.get(f"{base}/connections", headers={"Authorization": "Bearer admin"}).json()["data"]["items"]) == 2


def test_admin_can_assign_unclaimed_connection_by_username():
    client, _ = setup_gateway()
    base = "/api/v1/rebuild/dbx/projects/7"
    admin = {"Authorization": "Bearer admin"}
    rows = client.get(f"{base}/connections", headers=admin).json()["data"]["items"]
    assert next(row for row in rows if row["id"] == "other")["can_claim"] is True
    assigned = client.post(f"{base}/connections/other/claim", headers=admin, json={"username": "other"})
    assert assigned.status_code == 200
    assert assigned.json()["data"]["owner_id"] == 3
    assert client.get(f"{base}/connections", headers={"Authorization": "Bearer other"}).json()["data"]["items"][0]["can_manage"] is True


def test_unshared_connection_cannot_be_browsed_or_executed():
    client, dbx = setup_gateway()
    base = "/api/v1/rebuild/dbx/projects/7"
    headers = {"Authorization": "Bearer other"}
    assert client.get(f"{base}/connections/owned/schemas?database=sales", headers=headers).status_code == 403
    response = client.post(f"{base}/query/execute", headers=headers, json={"connection_id": "owned", "database": "sales", "sql": "select 1"})
    assert response.status_code == 403
    assert dbx.queries == []
    shared = client.post(f"{base}/connections/owned/share", headers={"Authorization": "Bearer owner"}, json={"username": "other"})
    assert shared.status_code == 200
    assert shared.json()["data"]["user_id"] == 3
    assert client.get(f"{base}/connections", headers=headers).json()["data"]["items"][0]["can_manage"] is False
    assert client.get(f"{base}/connections/owned/schemas?database=sales", headers=headers).json()["data"] == ["public"]
    response = client.post(f"{base}/query/execute", headers=headers, json={"connection_id": "owned", "database": "sales", "sql": "select 1"})
    assert response.status_code == 200
    assert dbx.queries == [{"connection_id": "owned", "database": "sales", "sql": "select 1", "schema": None, "max_rows": None}]

    shares = client.get(f"{base}/connections/owned/shares", headers={"Authorization": "Bearer owner"})
    assert shares.json()["data"]["items"] == [{"user_id": 3, "username": "other"}]
    assert client.get(f"{base}/connections/owned/shares", headers=headers).status_code == 403
    assert client.delete(f"{base}/connections/owned/shares/3", headers=headers).status_code == 403
    revoked = client.delete(f"{base}/connections/owned/shares/3", headers={"Authorization": "Bearer owner"})
    assert revoked.status_code == 200
    assert client.get(f"{base}/connections/owned/shares", headers={"Authorization": "Bearer owner"}).json()["data"]["items"] == []
    assert client.get(f"{base}/connections/owned/schemas?database=sales", headers=headers).status_code == 403


def test_connection_crud_is_owner_scoped_and_password_stays_in_dbx():
    client, dbx = setup_gateway()
    base = "/api/v1/rebuild/dbx/projects/7"
    draft = {"name": "New", "db_type": "postgres", "host": "db", "port": 5432,
             "database": "warehouse", "username": "etl", "password": "new-secret"}
    created = client.post(f"{base}/connections", headers={"Authorization": "Bearer owner"}, json=draft)
    assert created.status_code == 200
    connection_id = created.json()["data"]["connection_id"]
    assert dbx.saved[-1]["password"] == "new-secret"
    assert "new-secret" not in created.text
    owner_list = client.get(f"{base}/connections", headers={"Authorization": "Bearer owner"}).json()["data"]["items"]
    assert connection_id in {item["id"] for item in owner_list}
    assert "new-secret" not in str(owner_list)
    assert client.post(f"{base}/connections/{connection_id}/test", headers={"Authorization": "Bearer other"}).status_code == 403
    assert client.put(f"{base}/connections/{connection_id}", headers={"Authorization": "Bearer other"}, json=draft).status_code == 403
    assert client.delete(f"{base}/connections/{connection_id}", headers={"Authorization": "Bearer other"}).status_code == 403
    assert client.post(f"{base}/connections/{connection_id}/test", headers={"Authorization": "Bearer owner"}).json()["data"]["connected"] is True
    updated = client.put(f"{base}/connections/{connection_id}", headers={"Authorization": "Bearer owner"}, json={**draft, "name": "Renamed", "password": ""})
    assert updated.status_code == 200
    assert dbx.saved[-1]["password"] == "new-secret"
    assert "new-secret" not in updated.text
    assert client.delete(f"{base}/connections/{connection_id}", headers={"Authorization": "Bearer owner"}).status_code == 200
    assert connection_id not in {item["id"] for item in dbx.connections}


def test_saved_sql_share_is_explicit_and_revocable():
    client, _ = setup_gateway()
    base = "/api/v1/rebuild/dbx/projects/7"
    owner = {"Authorization": "Bearer owner"}
    other = {"Authorization": "Bearer other"}
    with client.app.state.session_factory() as session:
        DbxObjectAccess(session).claim(kind="sql-file", object_id="reconcile", project_id=7, owner_id=2, connection_id="owned")
        session.commit()
    url = f"{base}/objects/sql-file/reconcile"
    assert client.post(f"{url}/share", headers=other, json={"username": "admin"}).status_code == 403
    shared = client.post(f"{url}/share", headers=owner, json={"username": "other"})
    assert shared.status_code == 200
    assert shared.json()["data"]["user_id"] == 3
    assert client.get(f"{url}/shares", headers=owner).json()["data"]["items"] == [{"user_id": 3, "username": "other"}]
    assert client.get(f"{url}/shares", headers=other).status_code == 403
    assert client.delete(f"{url}/shares/3", headers=other).status_code == 403
    assert client.delete(f"{url}/shares/3", headers=owner).status_code == 200
    assert client.get(f"{url}/shares", headers=owner).json()["data"]["items"] == []


def test_admin_claims_existing_sql_after_connection_is_claimed():
    client, _ = setup_gateway()
    base = "/api/v1/rebuild/dbx/projects/7"
    url = f"{base}/objects/sql-file/legacy-sql/claim"
    assert client.post(url, headers={"Authorization": "Bearer owner"}, json={"username": "owner"}).status_code == 403
    claimed = client.post(url, headers={"Authorization": "Bearer admin"}, json={"username": "owner"})
    assert claimed.status_code == 200
    assert claimed.json()["data"] == {"kind": "sql-file", "object_id": "legacy-sql", "owner_id": 2}
    assert client.post(url, headers={"Authorization": "Bearer admin"}, json={"username": "other"}).status_code == 409


def test_admin_claims_legacy_ai_conversation_then_owner_shares_it():
    client, dbx = setup_gateway()
    base = "/api/v1/rebuild/dbx/projects/7/objects/ai-conversation"
    admin = {"Authorization": "Bearer admin"}
    owner = {"Authorization": "Bearer owner"}
    assert client.post(f"{base}/legacy-ai/claim", headers=owner, json={"username": "owner"}).status_code == 403
    assert client.post(f"{base}/missing/claim", headers=admin, json={"username": "owner"}).status_code == 404
    dbx.ai_conversations.append({"id": "foreign-ai", "connectionId": "other", "messages": []})
    assert client.post(f"{base}/foreign-ai/claim", headers=admin, json={"username": "owner"}).status_code == 409
    assert client.post(f"{base}/legacy-ai/claim", headers=admin, json={"username": "owner"}).status_code == 200
    assert client.post(f"{base}/legacy-ai/share", headers=owner, json={"username": "other"}).status_code == 200
    assert client.get(f"{base}/legacy-ai/shares", headers=owner).json()["data"]["items"] == [{"user_id": 3, "username": "other"}]


def test_admin_claims_legacy_ai_config_and_owner_shares_without_connection():
    client, _ = setup_gateway()
    base = "/api/v1/rebuild/dbx/projects/7/objects/ai-config"
    admin = {"Authorization": "Bearer admin"}
    owner = {"Authorization": "Bearer owner"}
    other = {"Authorization": "Bearer other"}
    assert client.post(f"{base}/legacy-config/claim", headers=owner, json={"username": "owner"}).status_code == 403
    assert client.post(f"{base}/missing/claim", headers=admin, json={"username": "owner"}).status_code == 404
    claimed = client.post(f"{base}/legacy-config/claim", headers=admin, json={"username": "owner"})
    assert claimed.status_code == 200
    assert claimed.json()["data"]["owner_id"] == 2
    assert client.post(f"{base}/legacy-config/share", headers=other, json={"username": "other"}).status_code == 403
    assert client.post(f"{base}/legacy-config/share", headers=owner, json={"username": "other"}).status_code == 200
    assert client.get(f"{base}/legacy-config/shares", headers=owner).json()["data"]["items"] == [{"user_id": 3, "username": "other"}]
