import threading
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from rebuild.common.db import Base
from rebuild.dbx.access import DbxConnectionAccess, DbxObjectAccess
from rebuild.dbx.connection_catalog import ConnectionCatalogCache
from rebuild.dbx.ide_proxy import IdeSessionRegistry, build_dbx_ide_router, is_supported_ide_route
from rebuild.dbx.models import DbxAiUserStateRecord, DbxConnectionOwnershipRecord, DbxConnectionShareRecord, DbxObjectOwnershipRecord, DbxObjectShareRecord
from rebuild.identity.models import UserRecord


def test_new_ide_session_reaps_expired_bearer_tokens(monkeypatch):
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr("rebuild.dbx.ide_proxy.time", SimpleNamespace(monotonic=lambda: clock.now))

    class FakeTimer:
        def __init__(self, delay, callback):
            self.delay = delay
            self.callback = callback
            self.daemon = False
            self.cancelled = False

        def start(self):
            pass

        def cancel(self):
            self.cancelled = True

    registry = IdeSessionRegistry(ttl_seconds=10, timer_factory=FakeTimer)
    expired = registry.issue("old-bearer", 33)

    clock.now = 110.0
    current = registry.issue("current-bearer", 33)

    assert expired not in registry._sessions
    assert registry.resolve(current) == ("current-bearer", 33)
    assert len(registry._sessions) == 1

    clock.now = 120.0
    registry._timer.callback()
    assert registry._sessions == {}
    assert registry._timer is None


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
        self.ai_configs = [{"id": "legacy-config", "name": "Legacy", "provider": "openai", "apiKey": "legacy-secret", "endpoint": "https://legacy.example/api", "model": "m1"}]
        self.prompt_templates = [{"id": "legacy-template", "name": "Legacy", "content": "legacy private"}]
        self.tunnel_profiles = [
            {"type": "ssh", "id": "legacy-tunnel", "name": "Legacy", "host": "legacy.host", "password": "legacy-secret"},
            {"type": "ssh", "id": "other-tunnel", "name": "Other", "host": "other.host", "password": "other-secret"},
        ]
        self.stream_payloads = []

    def list_connections(self):
        return self.rows

    def _request(self, method, path, *, params=None, payload=None):
        self.calls.append((method, path, payload))
        if path == "ai/configs" and method == "GET":
            return self.ai_configs
        if path == "prompt-templates" and method == "GET":
            return self.prompt_templates
        if path == "tunnel-profiles/list" and method == "GET":
            return self.tunnel_profiles
        if path == "tunnel-profiles/save" and method == "POST":
            self.tunnel_profiles = payload["profiles"]
            return None
        if path == "tunnel-profiles/test" and method == "POST":
            return "connected"
        if path == "prompt-templates" and method == "POST":
            self.prompt_templates = [item for item in self.prompt_templates if item["id"] != payload["id"]] + [payload]
            return payload
        if path.startswith("prompt-templates/") and method == "DELETE":
            self.prompt_templates = [item for item in self.prompt_templates if item["id"] != path.split("/", 1)[1]]
            return None
        if path == "ai/config-item" and method == "POST":
            config = payload["config"]
            self.ai_configs = [item for item in self.ai_configs if item["id"] != config["id"]] + [config]
            return None
        if path.startswith("ai/config/") and method == "DELETE":
            self.ai_configs = [item for item in self.ai_configs if item["id"] != path.split("/")[-1]]
            return None
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

    def open_stream(self, path, payload):
        self.stream_payloads.append((path, payload))
        return BytesIO(b'data: {"delta":"hello","done":true}\n\n')


def setup_proxy(project_gate=None, *, share_with_other=False):
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[UserRecord.__table__, DbxConnectionOwnershipRecord.__table__, DbxConnectionShareRecord.__table__, DbxObjectOwnershipRecord.__table__, DbxObjectShareRecord.__table__, DbxAiUserStateRecord.__table__])
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
        DbxObjectAccess(session).claim(kind="tunnel-profile", object_id="other-tunnel", project_id=33, owner_id=2)
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


def test_ide_session_bootstrap_accepts_datara_http_only_session_cookie():
    client, _ = setup_proxy()
    client.cookies.set("datara_session", "owner-token", path="/api/v1")

    response = client.post("/api/v1/rebuild/dbx/projects/33/ide-session")

    assert response.status_code == 200
    assert "datara_dbx_ide=" in response.headers.get("set-cookie", "")


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
    assert ide.get("ai/configs").json() == []
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


def test_ai_configs_are_owner_scoped_and_shared_stream_uses_server_secret():
    client, dbx = setup_proxy()
    proxy = "/api/v1/rebuild/dbx/ide-proxy"

    def login(token):
        response = client.post("/api/v1/rebuild/dbx/projects/33/ide-session", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        return {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}

    owner = login("owner-token")
    config = {"id": "mine-config", "name": "Mine AI", "provider": "openai", "apiKey": "owner-ai-secret",
              "endpoint": "https://owner.example/api?token=private", "model": "m1", "customHeaders": {"X-Private": "header-secret"}}
    assert client.post(f"{proxy}/ai/config-item", headers=owner, json={"config": config}).status_code == 200
    mine = client.get(f"{proxy}/ai/configs", headers=owner).json()
    assert [item["id"] for item in mine] == ["mine-config"]
    assert mine[0]["apiKey"] == "owner-ai-secret"
    assert client.post(f"{proxy}/ai/configs", headers=owner, json={"configs": [
        {"id": "second-config", "name": "Second AI", "provider": "openai", "apiKey": "second-secret", "endpoint": "https://second.example", "model": "m2"},
    ]}).status_code == 200
    assert {item["id"] for item in dbx.ai_configs} == {"legacy-config", "mine-config", "second-config"}

    other = login("other-token")
    assert client.get(f"{proxy}/ai/configs", headers=other).json() == []
    assert client.post(f"{proxy}/ai/config-item", headers=other, json={"config": config}).status_code == 403
    assert client.post(f"{proxy}/ai/stream", headers=other, json={"session_id": "x", "request": {
        "config": config, "system_prompt": "", "messages": [],
    }}).status_code == 403

    with client.app.state.session_factory() as session:
        DbxObjectAccess(session).share(kind="ai-config", object_id="mine-config", owner_id=1, user_id=2)
        session.commit()
    shared = client.get(f"{proxy}/ai/configs", headers=other).json()
    assert len(shared) == 1 and shared[0]["id"] == "mine-config"
    assert shared[0]["apiKey"] == "datara-shared-ai-config:mine-config"
    assert shared[0]["endpoint"] == "https://shared-config.invalid"
    assert "owner-ai-secret" not in str(shared) and "header-secret" not in str(shared) and "private" not in str(shared)
    streamed = client.post(f"{proxy}/ai/stream", headers=other, json={"session_id": "s-1", "request": {
        "config": shared[0], "system_prompt": "", "messages": [],
    }})
    assert streamed.status_code == 200 and "hello" in streamed.text
    _, forwarded = dbx.stream_payloads[-1]
    assert forwarded["sessionId"] == "33:2:s-1"
    assert forwarded["request"]["config"]["apiKey"] == "owner-ai-secret"
    assert forwarded["request"]["config"]["customHeaders"] == {"X-Private": "header-secret"}
    agent_frame = {"sessionId": "agent-1", "request": {"config": shared[0], "system_prompt": "", "messages": []},
                   "connectionId": "mine", "database": "sales", "dbType": "mysql"}
    assert client.post(f"{proxy}/ai/agent-stream", headers=other, json=agent_frame).status_code == 403
    with client.app.state.session_factory() as session:
        DbxConnectionAccess(session).share(connection_id="mine", owner_id=1, user_id=2)
        session.commit()
    assert client.post(f"{proxy}/ai/agent-stream", headers=other, json=agent_frame).status_code == 200
    assert dbx.stream_payloads[-1][1]["sessionId"] == "33:2:agent-1"
    assert client.post(f"{proxy}/ai/cancel-stream", headers=other, json={"sessionId": "agent-1"}).status_code == 200
    assert dbx.calls[-1] == ("POST", "ai/cancel-stream", {"sessionId": "33:2:agent-1"})
    assert client.post(f"{proxy}/ai/default-config", headers=other, json={"configId": "mine-config"}).status_code == 200
    assert client.post(f"{proxy}/ai/chat-selection", headers=other, json={"selection": {
        "active": {"configId": "mine-config", "modelId": "m1"},
    }}).status_code == 200
    assert client.get(f"{proxy}/ai/chat-selection", headers=other).json()["active"]["configId"] == "mine-config"
    assert client.get(f"{proxy}/ai/chat-selection", headers=owner).json() is None

    admin = login("admin-token")
    assert {item["id"] for item in client.get(f"{proxy}/ai/configs", headers=admin).json()} == {
        "legacy-config", "mine-config", "second-config",
    }


def test_prompt_templates_and_global_instructions_are_owner_scoped():
    client, dbx = setup_proxy()
    proxy = "/api/v1/rebuild/dbx/ide-proxy"

    def login(token):
        client.post("/api/v1/rebuild/dbx/projects/33/ide-session", headers={"Authorization": f"Bearer {token}"})
        return {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}

    owner = login("owner-token")
    assert client.get(f"{proxy}/prompt-templates", headers=owner).json() == []
    saved = client.post(f"{proxy}/prompt-templates", headers=owner, json={
        "id": "my-template", "name": "Order review", "content": "Check order refunds",
    })
    assert saved.status_code == 200
    assert [item["id"] for item in client.get(f"{proxy}/prompt-templates", headers=owner).json()] == ["my-template"]
    assert client.put(f"{proxy}/prompt-templates/global-instructions", headers=owner,
                      json={"content": "Use customer order policy"}).status_code == 200
    assert client.get(f"{proxy}/prompt-templates/global-instructions", headers=owner).json() == {
        "content": "Use customer order policy",
    }
    assert client.post(f"{proxy}/ai/chat-selection", headers=owner, json={"selection": {"defaultMode": "ask"}}).status_code == 200
    assert client.get(f"{proxy}/prompt-templates/global-instructions", headers=owner).json()["content"] == "Use customer order policy"

    other = login("other-token")
    assert client.get(f"{proxy}/prompt-templates", headers=other).json() == []
    assert client.get(f"{proxy}/prompt-templates/global-instructions", headers=other).json() == {"content": ""}
    assert client.post(f"{proxy}/prompt-templates", headers=other, json={
        "id": "my-template", "name": "Stolen", "content": "bad",
    }).status_code == 403
    assert client.delete(f"{proxy}/prompt-templates/my-template", headers=other).status_code == 403
    assert client.put(f"{proxy}/prompt-templates/global-instructions", headers=other,
                      json={"content": "Other instruction"}).status_code == 200
    with client.app.state.session_factory() as session:
        DbxObjectAccess(session).share(kind="prompt-template", object_id="my-template", owner_id=1, user_id=2)
        session.commit()
    assert [item["id"] for item in client.get(f"{proxy}/prompt-templates", headers=other).json()] == ["my-template"]
    assert client.delete(f"{proxy}/prompt-templates/my-template", headers=other).status_code == 403
    assert client.get(f"{proxy}/prompt-templates/global-instructions", headers=other).json()["content"] == "Other instruction"

    admin = login("admin-token")
    assert {item["id"] for item in client.get(f"{proxy}/prompt-templates", headers=admin).json()} == {
        "legacy-template", "my-template",
    }
    owner = login("owner-token")
    assert client.delete(f"{proxy}/prompt-templates/my-template", headers=owner).status_code == 200
    assert all(item["id"] != "my-template" for item in dbx.prompt_templates)


def test_tunnel_profile_save_preserves_foreign_rows_and_shared_profile_secrets():
    client, dbx = setup_proxy()
    proxy = "/api/v1/rebuild/dbx/ide-proxy"

    def login(token):
        client.post("/api/v1/rebuild/dbx/projects/33/ide-session", headers={"Authorization": f"Bearer {token}"})
        return {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}

    owner = login("owner-token")
    assert client.get(f"{proxy}/tunnel-profiles/list", headers=owner).json() == []
    profile = {"type": "ssh", "id": "my-tunnel", "name": "My tunnel", "host": "my.host",
               "password": "owner-tunnel-secret", "key_path": "/private/id_rsa"}
    assert client.post(f"{proxy}/tunnel-profiles/save", headers=owner,
                       json={"profiles": [profile]}).status_code == 200
    assert {row["id"] for row in dbx.tunnel_profiles} == {"legacy-tunnel", "other-tunnel", "my-tunnel"}
    assert [row["id"] for row in client.get(f"{proxy}/tunnel-profiles/list", headers=owner).json()] == ["my-tunnel"]

    other = login("other-token")
    assert [row["id"] for row in client.get(f"{proxy}/tunnel-profiles/list", headers=other).json()] == ["other-tunnel"]
    assert client.post(f"{proxy}/tunnel-profiles/test", headers=other, json=profile).status_code == 403
    with client.app.state.session_factory() as session:
        DbxObjectAccess(session).share(kind="tunnel-profile", object_id="my-tunnel", owner_id=1, user_id=2)
        session.commit()
    shared = client.get(f"{proxy}/tunnel-profiles/list", headers=other).json()
    shared_profile = next(row for row in shared if row["id"] == "my-tunnel")
    assert shared_profile["password"] == "" and shared_profile["key_path"] == ""
    assert "owner-tunnel-secret" not in str(shared) and "/private/id_rsa" not in str(shared)
    assert client.post(f"{proxy}/tunnel-profiles/test", headers=other, json=shared_profile).json() == "connected"
    assert dbx.calls[-1] == ("POST", "tunnel-profiles/test", profile)
    changed = dict(shared_profile, host="attacker.host")
    assert client.post(f"{proxy}/tunnel-profiles/save", headers=other,
                       json={"profiles": [changed]}).status_code == 403
    assert next(row for row in dbx.tunnel_profiles if row["id"] == "my-tunnel")["host"] == "my.host"

    owner = login("owner-token")
    assert client.post(f"{proxy}/tunnel-profiles/save", headers=owner, json={"profiles": []}).status_code == 200
    assert {row["id"] for row in dbx.tunnel_profiles} == {"legacy-tunnel", "other-tunnel"}


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
        "database-backups",
        "schema/databases", "schema/cache", "schema/ddl", "query/execute",
        "query/execute-batch", "query/large-value/download/item-1",
        "mq/topics/list", "history/search", "history/item-1",
        "saved-sql/item-1/default-content", "saved-sql/folders/item-1",
    ):
        assert is_supported_ide_route(path), path
    for path in ("schema/secret-dump", "query/secret-dump", "mq/secret-dump", "saved-sql/item-1/extra"):
        assert not is_supported_ide_route(path), path


@pytest.mark.parametrize("path", [
    "redis/list-databases", "redis/scan-keys-batch",
    "document-store/list-databases", "document-store/list-collections",
    "etcd/list-prefix", "zookeeper/list-prefix", "consul/list-prefix",
])
def test_object_tree_metadata_is_scoped_to_visible_connection(path):
    client, dbx = setup_proxy()
    client.post("/api/v1/rebuild/dbx/projects/33/ide-session", headers={"Authorization": "Bearer owner-token"})
    headers = {"Cookie": f"datara_dbx_ide={client.cookies.get('datara_dbx_ide')}"}
    endpoint = f"/api/v1/rebuild/dbx/ide-proxy/{path}"

    own = client.post(endpoint, headers=headers, json={"connectionId": "mine"})
    assert own.status_code == 200
    assert dbx.calls[-1] == ("POST", path, {"connectionId": "mine"})

    foreign = client.post(endpoint, headers=headers, json={"connectionId": "foreign"})
    assert foreign.status_code == 403
    assert dbx.calls[-1] == ("POST", path, {"connectionId": "mine"})


def test_object_tree_route_manifest_does_not_expose_database_mutations():
    for path in ("redis/flush-db", "redis/execute-command", "mongo/drop-database",
                 "etcd/put", "zookeeper/delete", "consul/delete"):
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


def test_connection_catalog_cache_dedupes_repeated_reads():
    calls = []

    def load():
        calls.append(1)
        return [{"id": "mine"}]

    cache = ConnectionCatalogCache(ttl_seconds=60)
    assert cache.get(load) == [{"id": "mine"}]
    assert cache.get(load) == [{"id": "mine"}]
    assert len(calls) == 1


def test_connection_catalog_cache_invalidate_forces_reload():
    state = {"rows": [{"id": "mine"}]}
    cache = ConnectionCatalogCache(ttl_seconds=60)
    assert cache.get(lambda: state["rows"]) == [{"id": "mine"}]
    state["rows"] = [{"id": "mine"}, {"id": "new"}]
    cache.invalidate()
    assert cache.get(lambda: state["rows"]) == [{"id": "mine"}, {"id": "new"}]


def test_connection_catalog_cache_does_not_cache_a_failed_load():
    cache = ConnectionCatalogCache(ttl_seconds=60)

    def down():
        raise RuntimeError("dbx unreachable")

    with pytest.raises(RuntimeError):
        cache.get(down)
    # The failure must not poison the cache; the next read retries upstream.
    assert cache.get(lambda: [{"id": "mine"}]) == [{"id": "mine"}]


def test_connection_catalog_cache_single_flight_reuses_in_flight_load():
    started = threading.Event()
    release = threading.Event()
    calls = []

    def load():
        calls.append(1)
        started.set()
        assert release.wait(2)
        return [{"id": "mine"}]

    cache = ConnectionCatalogCache(ttl_seconds=60)
    results = {}

    def first():
        results["first"] = cache.get(load)

    def second():
        results["second"] = cache.get(load)

    thread = threading.Thread(target=first)
    thread.start()
    assert started.wait(2)
    # A second caller joins the in-flight load instead of hitting dbx again.
    joiner = threading.Thread(target=second)
    joiner.start()
    release.set()
    thread.join(2)
    joiner.join(2)

    assert results["first"] == [{"id": "mine"}]
    assert results["second"] == [{"id": "mine"}]
    assert len(calls) == 1


def test_connection_catalog_cache_ignores_stale_load_after_invalidate():
    started = threading.Event()
    release = threading.Event()

    def load():
        started.set()
        assert release.wait(2)
        return [{"id": "stale"}]

    cache = ConnectionCatalogCache(ttl_seconds=60)
    thread = threading.Thread(target=lambda: cache.get(load))
    thread.start()
    assert started.wait(2)
    # A write lands while the load is still in flight.
    cache.invalidate()
    release.set()
    thread.join(2)
    # The stale rows must not be republished; the next read re-fetches.
    assert cache.get(lambda: [{"id": "fresh"}]) == [{"id": "fresh"}]


def test_rebuild_app_registers_ide_session_and_proxy_routes():
    from rebuild.api.app import create_app

    app = create_app("sqlite+pysqlite:///:memory:", token_secret="dbx-ide-route-test")
    paths = set(app.openapi()["paths"])
    assert "/api/v1/rebuild/dbx/projects/{project_id}/ide-session" in paths
    assert "/api/v1/rebuild/dbx/ide-proxy/{path}" in paths
