from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from rebuild.common.db import Base
from rebuild.dbx.access import DbxConnectionAccess, DbxObjectAccess
from rebuild.dbx.ide_proxy import build_dbx_ide_router, is_supported_ide_route
from rebuild.dbx.models import DbxConnectionOwnershipRecord, DbxConnectionShareRecord, DbxObjectOwnershipRecord, DbxObjectShareRecord
from rebuild.identity.models import UserRecord


class FakeDbx:
    def __init__(self):
        self.rows = [
            {"id": "mine", "name": "Mine", "db_type": "mysql", "password": "owner-secret", "ssl": True,
             "driver_profile": "native", "connection_string": "mysql://private@host", "external_config": {"secret": "private"}},
            {"id": "foreign", "name": "Foreign", "db_type": "mysql", "password": "foreign-secret"},
        ]
        self.calls = []
        self.sql_library = {"folders": [], "files": [{"id": "legacy", "connectionId": "mine", "name": "Legacy"}]}
        self.history_entries = []
        self.conversations = [
            {"id": "legacy-ai", "connectionId": "mine", "messages": [{"content": "private legacy"}]},
            {"id": "foreign-ai", "connectionId": "foreign", "messages": [{"content": "private other"}]},
        ]

    def list_connections(self):
        return self.rows

    def _request(self, method, path, *, params=None, payload=None):
        self.calls.append((method, path, payload))
        if path == "ai/conversations" and method == "GET":
            return self.conversations
        if path == "ai/conversation" and method == "POST":
            self.conversations = [item for item in self.conversations if item["id"] != payload["conversation"]["id"]] + [payload["conversation"]]
            return None
        if path.startswith("ai/conversation/") and method == "DELETE":
            self.conversations = [item for item in self.conversations if item["id"] != path.split("/")[-1]]
            return None
        if path == "history/options":
            return [{"connection_id": row["id"], "connection_name": row["name"], "databases": []} for row in self.rows]
        if path == "history/search":
            allowed = {item["connection_id"] for item in payload.get("connections", [])}
            entries = [item for item in self.history_entries if item["connection_id"] in allowed]
            return {"entries": entries[:payload.get("limit", 100)], "next_cursor": None, "total": len(entries)}
        if path == "saved-sql" and method == "GET":
            return self.sql_library
        if path == "saved-sql" and method == "POST":
            self.sql_library["files"] = [item for item in self.sql_library["files"] if item["id"] != payload["id"]] + [payload]
            return payload
        if path == "saved-sql/folders" and method == "POST":
            self.sql_library["folders"] = [item for item in self.sql_library["folders"] if item["id"] != payload["id"]] + [payload]
            return payload
        if path.endswith("/default-content") and method == "POST":
            return None
        if path.startswith("saved-sql/") and method == "GET":
            return next((item for item in self.sql_library["files"] if item["id"] == path.split("/")[-1]), None)
        if path.startswith("saved-sql/") and method == "DELETE":
            object_id = path.split("/")[-1]
            if path.startswith("saved-sql/folders/"):
                self.sql_library["folders"] = [item for item in self.sql_library["folders"] if item["id"] != object_id]
                self.sql_library["files"] = [item for item in self.sql_library["files"] if item.get("folderId") != object_id]
            else:
                self.sql_library["files"] = [item for item in self.sql_library["files"] if item["id"] != object_id]
            return None
        if path == "connection/save":
            self.rows = [item for item in self.rows if item["id"] not in set(payload.get("removedIds", []))]
            for config in payload.get("configs", []):
                self.rows = [item for item in self.rows if item["id"] != config["id"]] + [config]
        return {"ok": True}


def setup_proxy(project_gate=None, *, share_with_other=False):
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[UserRecord.__table__, DbxConnectionOwnershipRecord.__table__, DbxConnectionShareRecord.__table__, DbxObjectOwnershipRecord.__table__, DbxObjectShareRecord.__table__])
    factory = sessionmaker(bind=engine)
    with Session(engine) as session:
        session.add_all([
            UserRecord(id=1, username="owner", password_hash="x", role="developer"),
            UserRecord(id=2, username="other", password_hash="x", role="developer"),
            UserRecord(id=3, username="admin", password_hash="x", role="admin"),
        ])
        session.flush()
        access = DbxConnectionAccess(session)
        access.claim(connection_id="mine", project_id=33, owner_id=1)
        access.claim(connection_id="foreign", project_id=33, owner_id=2)
        if share_with_other:
            access.share(connection_id="mine", owner_id=1, user_id=2)
        session.commit()
    users = {"owner-token": {"user_id": 1, "role": "developer"}, "other-token": {"user_id": 2, "role": "developer"}, "admin-token": {"user_id": 3, "role": "admin"}}

    def current_user(authorization):
        user = users.get(authorization.removeprefix("Bearer "))
        if user is None:
            raise ValueError("invalid token")
        return user

    dbx = FakeDbx()
    app = FastAPI()
    app.state.session_factory = factory
    app.include_router(build_dbx_ide_router(factory, current_user, project_gate or (lambda *args: None), client_factory=lambda: dbx))
    return TestClient(app), dbx


def test_ai_conversations_are_owned_and_shared_without_leaking_legacy_data():
    client, dbx = setup_proxy(share_with_other=True)
    proxy = "/api/v1/rebuild/dbx/ide-proxy"
    client.post("/api/v1/rebuild/dbx/projects/33/ide-session", headers={"Authorization": "Bearer owner-token"})
    headers = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    class Ide:
        def get(self, path):
            return client.get(f"{proxy}/{path}", headers=headers)
        def post(self, path, body):
            return client.post(f"{proxy}/{path}", headers=headers, json=body)
        def delete(self, path):
            return client.delete(f"{proxy}/{path}", headers=headers)
    ide = Ide()
    assert ide.get("ai/conversations").json() == []
    assert ide.post("ai/conversation", {"conversation": {
        "id": "mine-ai", "connectionId": "mine", "messages": [{"content": "mine"}],
    }}).status_code == 200
    assert [row["id"] for row in ide.get("ai/conversations").json()] == ["mine-ai"]
    assert ide.post("ai/conversation", {"conversation": {
        "id": "legacy-ai", "connectionId": "mine", "messages": [],
    }}).status_code == 403
    assert ide.post("ai/conversation", {"conversation": {
        "id": "foreign-ai", "connectionId": "foreign", "messages": [],
    }}).status_code == 403
    assert ide.get("ai/configs").status_code == 403
    assert ide.delete("ai/conversation/legacy-ai").status_code == 403

    with client.app.state.session_factory() as session:
        DbxObjectAccess(session).share(kind="ai-conversation", object_id="mine-ai", owner_id=1, user_id=2)
        session.commit()
    client.post("/api/v1/rebuild/dbx/projects/33/ide-session", headers={"Authorization": "Bearer other-token"})
    headers = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    assert [row["id"] for row in ide.get("ai/conversations").json()] == ["mine-ai"]
    assert ide.post("ai/conversation", {"conversation": {
        "id": "mine-ai", "connectionId": "mine", "messages": [],
    }}).status_code == 403
    assert ide.delete("ai/conversation/mine-ai").status_code == 403
    client.post("/api/v1/rebuild/dbx/projects/33/ide-session", headers={"Authorization": "Bearer owner-token"})
    headers = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    assert ide.delete("ai/conversation/mine-ai").status_code == 200
    assert all(row["id"] != "mine-ai" for row in dbx.conversations)


def test_ide_cookie_is_opaque_and_connection_list_is_filtered():
    client, dbx = setup_proxy()
    proxy = "/api/v1/rebuild/dbx/ide-proxy"
    assert client.get(f"{proxy}/connection/list").status_code == 401
    session = client.post("/api/v1/rebuild/dbx/projects/33/ide-session", headers={"Authorization": "Bearer owner-token"})
    assert session.status_code == 200
    cookie = session.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "owner-token" not in cookie
    headers = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    response = client.get(f"{proxy}/connection/list", headers=headers)
    assert response.status_code == 200
    assert response.json() == [{"id": "mine", "name": "Mine", "db_type": "mysql", "ssl": True,
                                "driver_profile": "native", "password": ""}]
    assert "secret" not in response.text


def test_ide_proxy_blocks_foreign_query_and_canonicalizes_connect():
    client, dbx = setup_proxy()
    client.post("/api/v1/rebuild/dbx/projects/33/ide-session", headers={"Authorization": "Bearer owner-token"})
    proxy = "/api/v1/rebuild/dbx/ide-proxy"
    headers = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    foreign = client.post(f"{proxy}/query/execute", headers=headers, json={"connectionId": "foreign", "database": "x", "sql": "select 1"})
    assert foreign.status_code == 403 and dbx.calls == []
    forged = client.post(f"{proxy}/connection/connect", headers=headers, json={"config": {"id": "mine", "host": "forged"}})
    assert forged.status_code == 200
    assert dbx.calls[-1][2]["config"] == dbx.rows[0]
    assert client.post(f"{proxy}/connection/connect", headers=headers, json={"config": {"id": "foreign"}}).status_code == 403


def test_shared_connection_cannot_modify_owner_settings_through_dbx_routes():
    client, dbx = setup_proxy(share_with_other=True)
    endpoint = "/api/v1/rebuild/dbx/projects/33/ide-session"
    proxy = "/api/v1/rebuild/dbx/ide-proxy"
    client.post(endpoint, headers={"Authorization": "Bearer other-token"})
    cookie = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    before = len(dbx.calls)
    for path in ("connection/database-info/save", "connection/write-unlock", "connection/write-unlock/lock",
                 "connection/forget-session-credential", "connection/replace-nacos-session-credential",
                 "connection/disconnect", "connection/close-database", "connection/salesforce-oauth-refresh"):
        assert client.post(f"{proxy}/{path}", headers=cookie, json={"connectionId": "mine"}).status_code == 403
    assert client.post(f"{proxy}/connection/mcp/remove", headers=cookie, json={"connectionId": "mine"}).status_code == 403
    assert len(dbx.calls) == before
    assert client.post(f"{proxy}/connection/write-unlock", headers=cookie, json={"connectionId": "foreign"}).status_code == 200


def test_forged_visible_connection_id_cannot_authorize_unmapped_admin_api():
    client, dbx = setup_proxy()
    client.post("/api/v1/rebuild/dbx/projects/33/ide-session", headers={"Authorization": "Bearer owner-token"})
    cookie = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    proxy = "/api/v1/rebuild/dbx/ide-proxy"
    before = len(dbx.calls)
    for path in (
        "auth/change-password", "app-settings/config/decrypt", "backup/restore",
        "connection/unmapped-admin-action", "schema/unmapped-admin-action",
        "query/unmapped-admin-action", "mq/unmapped-admin-action",
        "history/unmapped/extra", "saved-sql/unmapped/extra",
    ):
        response = client.post(f"{proxy}/{path}", headers=cookie, json={"connectionId": "mine"})
        assert response.status_code == 403, path
    assert len(dbx.calls) == before


def test_dbx_06060_route_manifest_preserves_known_ide_paths():
    for path in (
        "schema/databases", "schema/cache", "schema/ddl", "query/execute",
        "query/execute-batch", "query/large-value/download/item-1",
        "mq/topics/list", "history/search", "history/item-1",
        "saved-sql/item-1/default-content", "saved-sql/folders/item-1",
    ):
        assert is_supported_ide_route(path), path
    for path in ("schema/secret-dump", "query/secret-dump", "mq/secret-dump", "saved-sql/item-1/extra"):
        assert not is_supported_ide_route(path), path


def test_ide_auth_check_uses_datara_session_without_dbx_login():
    client, dbx = setup_proxy()
    proxy = "/api/v1/rebuild/dbx/ide-proxy/auth/check"
    assert client.get(proxy).status_code == 401
    client.post("/api/v1/rebuild/dbx/projects/33/ide-session", headers={"Authorization": "Bearer owner-token"})
    # In deployment Nginx maps /ide/api/* to this route, preserving the cookie;
    # TestClient calls the backend route directly, so it must set that cookie.
    response = client.get(proxy, headers={"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"})
    assert response.status_code == 200
    assert response.json() == {"authenticated": True, "required": False, "setup_required": False}
    assert dbx.calls == []


def test_history_is_scoped_to_visible_connections_even_with_forged_filters():
    client, dbx = setup_proxy()
    client.post("/api/v1/rebuild/dbx/projects/33/ide-session", headers={"Authorization": "Bearer owner-token"})
    headers = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    proxy = "/api/v1/rebuild/dbx/ide-proxy"
    options = client.get(f"{proxy}/history/options", headers=headers)
    assert [item["connection_id"] for item in options.json()] == ["mine"]
    search = client.post(f"{proxy}/history/search", headers=headers, json={"search_text": "order", "connections": []})
    assert search.status_code == 200
    assert dbx.calls[-1][2]["connections"] == [{"connection_id": "mine"}]
    assert dbx.calls[-1][2]["search_text"] == "order"

    mixed = client.post(f"{proxy}/history/search", headers=headers, json={
        "connections": [{"connection_id": "mine"}],
        "databases": [{"connection_id": "foreign", "database": "secret"}],
    })
    assert mixed.status_code == 200
    assert dbx.calls[-1][2]["connections"] == [{"connection_id": "mine"}]
    assert dbx.calls[-1][2]["databases"] == []

    before = len(dbx.calls)
    foreign = client.post(f"{proxy}/history/search", headers=headers, json={
        "connections": [{"connection_id": "foreign"}],
        "databases": [{"connection_id": "foreign", "database": "secret"}],
    })
    assert foreign.json() == {"entries": [], "next_cursor": None, "total": 0}
    assert len(dbx.calls) == before
    legacy_name = client.post(f"{proxy}/history/search", headers=headers, json={
        "connections": [{"connection_name": "Foreign"}],
    })
    assert legacy_name.json()["entries"] == []
    assert len(dbx.calls) == before


def test_legacy_history_list_is_scoped_before_pagination():
    client, dbx = setup_proxy()
    dbx.history_entries = [
        {"id": "foreign-1", "connection_id": "foreign"},
        {"id": "mine-1", "connection_id": "mine"},
        {"id": "mine-2", "connection_id": "mine"},
    ]
    client.post("/api/v1/rebuild/dbx/projects/33/ide-session", headers={"Authorization": "Bearer owner-token"})
    headers = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    response = client.get("/api/v1/rebuild/dbx/ide-proxy/history?limit=1&offset=1", headers=headers)
    assert response.status_code == 200
    assert response.json() == [{"id": "mine-2", "connection_id": "mine"}]
    assert dbx.calls[-1][1] == "history/search"
    assert dbx.calls[-1][2]["connections"] == [{"connection_id": "mine"}]


def test_history_write_requires_visible_connection_and_delete_is_admin_only():
    client, dbx = setup_proxy()
    endpoint = "/api/v1/rebuild/dbx/projects/33/ide-session"
    proxy = "/api/v1/rebuild/dbx/ide-proxy"
    client.post(endpoint, headers={"Authorization": "Bearer owner-token"})
    owner_cookie = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    assert client.post(f"{proxy}/history/save", headers=owner_cookie, json={"entry": {"connection_id": "foreign"}}).status_code == 403
    assert client.post(f"{proxy}/history/save", headers=owner_cookie, json={"entry": {"connection_id": "mine"}}).status_code == 200
    assert client.delete(f"{proxy}/history", headers=owner_cookie).status_code == 403
    assert client.delete(f"{proxy}/history/entry-1", headers=owner_cookie).status_code == 403
    client.post(endpoint, headers={"Authorization": "Bearer admin-token"})
    admin_cookie = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    assert client.post(f"{proxy}/history/search", headers=admin_cookie, json={"connections": [], "search_text": "legacy"}).status_code == 200
    assert dbx.calls[-1][2] == {"connections": [], "search_text": "legacy"}
    assert client.delete(f"{proxy}/history/entry-1", headers=admin_cookie).status_code == 200
    assert dbx.calls[-1][1] == "history/entry-1"


def test_saved_sql_is_owned_independently_of_shared_connection():
    client, dbx = setup_proxy(share_with_other=True)
    endpoint = "/api/v1/rebuild/dbx/projects/33/ide-session"
    proxy = "/api/v1/rebuild/dbx/ide-proxy"
    client.post(endpoint, headers={"Authorization": "Bearer owner-token"})
    owner_cookie = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    created = client.post(f"{proxy}/saved-sql", headers=owner_cookie, json={
        "id": "owner-sql", "connectionId": "mine", "folderId": None, "name": "订单对账", "database": "ec_retail",
        "sql": "select count(*) from ods_order", "createdAt": "2026-10-30", "updatedAt": "2026-10-30",
    })
    assert created.status_code == 200
    assert [item["id"] for item in client.get(f"{proxy}/saved-sql", headers=owner_cookie).json()["files"]] == ["owner-sql"]
    assert client.get(f"{proxy}/saved-sql/legacy", headers=owner_cookie).status_code == 403

    client.post(endpoint, headers={"Authorization": "Bearer other-token"})
    other_cookie = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    assert client.get(f"{proxy}/saved-sql", headers=other_cookie).json()["files"] == []
    assert client.get(f"{proxy}/saved-sql/owner-sql", headers=other_cookie).status_code == 403
    assert client.post(f"{proxy}/saved-sql", headers=other_cookie, json={
        "id": "owner-sql", "connectionId": "mine", "name": "stolen",
    }).status_code == 403
    assert [item["id"] for item in dbx.sql_library["files"]] == ["legacy", "owner-sql"]

    with client.app.state.session_factory() as session:
        DbxObjectAccess(session).share(kind="sql-file", object_id="owner-sql", owner_id=1, user_id=2)
        session.commit()
    assert [item["id"] for item in client.get(f"{proxy}/saved-sql", headers=other_cookie).json()["files"]] == ["owner-sql"]
    assert client.get(f"{proxy}/saved-sql/owner-sql", headers=other_cookie).status_code == 200
    assert client.post(f"{proxy}/saved-sql/owner-sql/default-content", headers=other_cookie, json={
        "sql": "delete from ods_order", "updatedAt": "2026-10-30",
    }).status_code == 403
    assert client.post(f"{proxy}/saved-sql", headers=other_cookie, json={
        "id": "owner-sql", "connectionId": "mine", "name": "stolen",
    }).status_code == 403
    with client.app.state.session_factory() as session:
        DbxObjectAccess(session).unshare(kind="sql-file", object_id="owner-sql", owner_id=1, user_id=2)
        session.commit()
    assert client.get(f"{proxy}/saved-sql/owner-sql", headers=other_cookie).status_code == 403


def test_saved_sql_folder_delete_cannot_remove_another_users_file():
    client, dbx = setup_proxy(share_with_other=True)
    client.post("/api/v1/rebuild/dbx/projects/33/ide-session", headers={"Authorization": "Bearer owner-token"})
    headers = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    proxy = "/api/v1/rebuild/dbx/ide-proxy"
    folder = {"id": "folder-1", "connectionId": "mine", "parentFolderId": None, "name": "交易", "createdAt": "2026-10-30", "updatedAt": "2026-10-30"}
    assert client.post(f"{proxy}/saved-sql/folders", headers=headers, json=folder).status_code == 200
    dbx.sql_library["files"].append({"id": "other-file", "connectionId": "mine", "folderId": "folder-1", "name": "private"})
    with client.app.state.session_factory() as session:
        DbxObjectAccess(session).claim(kind="sql-file", object_id="other-file", project_id=33, owner_id=2, connection_id="mine")
        session.commit()
    denied = client.delete(f"{proxy}/saved-sql/folders/folder-1", headers=headers)
    assert denied.status_code == 403
    assert any(item["id"] == "other-file" for item in dbx.sql_library["files"])


def test_admin_can_use_existing_unclaimed_saved_sql_without_claiming_it():
    client, dbx = setup_proxy()
    client.post("/api/v1/rebuild/dbx/projects/33/ide-session", headers={"Authorization": "Bearer admin-token"})
    headers = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    proxy = "/api/v1/rebuild/dbx/ide-proxy"
    listed = client.get(f"{proxy}/saved-sql", headers=headers)
    assert [item["id"] for item in listed.json()["files"]] == ["legacy"]
    updated = client.post(f"{proxy}/saved-sql", headers=headers, json={
        "id": "legacy", "connectionId": "mine", "name": "Legacy edited", "database": "ec_retail", "sql": "select 1",
    })
    assert updated.status_code == 200
    assert dbx.sql_library["files"][0]["name"] == "Legacy edited"


def test_deleted_sql_id_does_not_inherit_old_owner_or_shares():
    client, _ = setup_proxy(share_with_other=True)
    endpoint = "/api/v1/rebuild/dbx/projects/33/ide-session"
    proxy = "/api/v1/rebuild/dbx/ide-proxy"
    client.post(endpoint, headers={"Authorization": "Bearer owner-token"})
    owner_cookie = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    frame = {"id": "reused", "connectionId": "mine", "folderId": None, "name": "first", "database": "ec_retail", "sql": "select 1"}
    assert client.post(f"{proxy}/saved-sql", headers=owner_cookie, json=frame).status_code == 200
    with client.app.state.session_factory() as session:
        DbxObjectAccess(session).share(kind="sql-file", object_id="reused", owner_id=1, user_id=2)
        session.commit()
    assert client.delete(f"{proxy}/saved-sql/reused", headers=owner_cookie).status_code == 200
    client.post(endpoint, headers={"Authorization": "Bearer other-token"})
    other_cookie = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    assert client.post(f"{proxy}/saved-sql", headers=other_cookie, json={**frame, "name": "second"}).status_code == 200
    assert client.get(f"{proxy}/saved-sql/reused", headers=owner_cookie).status_code == 403
    with client.app.state.session_factory() as session:
        owner = DbxObjectAccess(session).get("sql-file", "reused")
        assert owner is not None and owner.owner_id == 2


def test_resource_share_does_not_grant_project_permission():
    granted = False

    def project_gate(_session, _project_id, user, _permission):
        if user["user_id"] == 2 and not granted:
            return JSONResponse(status_code=403, content={"code": 1003, "msg": "permission denied", "data": None})
        return None

    client, _ = setup_proxy(project_gate, share_with_other=True)
    endpoint = "/api/v1/rebuild/dbx/projects/33/ide-session"
    headers = {"Authorization": "Bearer other-token"}
    assert client.post(endpoint, headers=headers).status_code == 403

    granted = True
    assert client.post(endpoint, headers=headers).status_code == 200
    cookie = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    rows = client.get("/api/v1/rebuild/dbx/ide-proxy/connection/list", headers=cookie).json()
    assert {row["id"] for row in rows} == {"mine", "foreign"}


def test_ide_proxy_save_claims_new_connection_and_preserves_password():
    client, dbx = setup_proxy()
    client.post("/api/v1/rebuild/dbx/projects/33/ide-session", headers={"Authorization": "Bearer owner-token"})
    proxy = "/api/v1/rebuild/dbx/ide-proxy"
    headers = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    assert client.post(f"{proxy}/connection/save", headers=headers, json={"configs": [{"id": "foreign", "name": "stolen"}]}).status_code == 403
    saved = client.post(f"{proxy}/connection/save", headers=headers, json={"configs": [{"id": "mine", "name": "Renamed", "password": ""}, {"id": "new", "name": "New", "password": "new-secret"}]})
    assert saved.status_code == 200
    assert dbx.calls[-1][2]["configs"][0]["password"] == "owner-secret"
    assert dbx.calls[-1][2]["configs"][0]["connection_string"] == "mysql://private@host"
    assert dbx.calls[-1][2]["configs"][0]["external_config"] == {"secret": "private"}
    rows = client.get(f"{proxy}/connection/list", headers=headers).json()
    assert {item["id"] for item in rows} == {"mine", "new"}
    assert "new-secret" not in str(rows)


def test_rebuild_app_registers_ide_session_and_proxy_routes():
    from rebuild.api.app import create_app

    app = create_app("sqlite+pysqlite:///:memory:", token_secret="dbx-ide-route-test")
    paths = set(app.openapi()["paths"])
    assert "/api/v1/rebuild/dbx/projects/{project_id}/ide-session" in paths
    assert "/api/v1/rebuild/dbx/ide-proxy/{path}" in paths
