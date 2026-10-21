from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.sshnode.models import SshNodeRecord
from rebuild.sshnode.service import SshNodeDomainError, SshNodeInput, SshNodeService


def _client(role: Role = Role.DEVELOPER):
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="ssh-node-test-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(username="ssh-user", password="ssh-password", role=role)
        session.commit()
    token = client.post(
        "/api/v1/rebuild/login", json={"username": "ssh-user", "password": "ssh-password"}
    ).json()["data"]["token"]
    return client, app, {"Authorization": f"Bearer {token}"}


def _body(name="node-a"):
    return {
        "name": name,
        "host": "10.0.0.1",
        "port": 22,
        "sshUser": "root",
        "cred": "plain-secret",
        "tags": ["batch", " batch ", ""],
        "enabled": True,
    }


def test_five_routes_require_token_and_apply_read_write_permission_map():
    client, _, headers = _client(Role.VIEWER)
    try:
        assert client.get("/api/v1/rebuild/ssh-nodes").status_code == 401
        assert client.get("/api/v1/rebuild/ssh-nodes", headers=headers).status_code == 200
        denied = client.post("/api/v1/rebuild/ssh-nodes", headers=headers, json=_body())
        assert denied.status_code == 403
        assert denied.json()["code"] == 1003
    finally:
        client.__exit__(None, None, None)


def test_create_list_and_full_update_preserve_frozen_envelope_and_credential_echo():
    client, _, headers = _client()
    try:
        created = client.post("/api/v1/rebuild/ssh-nodes", headers=headers, json=_body())
        assert created.status_code == 200
        assert created.json()["data"]["cred"] == "plain-secret"
        assert created.json()["data"]["tags"] == ["batch"]
        node_id = created.json()["data"]["id"]
        listed = client.get("/api/v1/rebuild/ssh-nodes", headers=headers)
        assert listed.json()["data"][0]["id"] == node_id

        replacement = _body("node-b")
        replacement.update({"host": "10.0.0.2", "sshUser": "deploy", "cred": "new-secret", "enabled": False})
        updated = client.put(f"/api/v1/rebuild/ssh-nodes/{node_id}", headers=headers, json=replacement)
        assert set(updated.json()["data"]) == {
            "id", "name", "host", "port", "sshUser", "cred", "tags",
            "enabled", "heartbeatState", "lastSeen", "createTime",
        }
        assert updated.json()["data"]["name"] == "node-b"
        assert updated.json()["data"]["host"] == "10.0.0.2"
        assert updated.json()["data"]["cred"] == "new-secret"
        assert updated.json()["data"]["enabled"] is False
    finally:
        client.__exit__(None, None, None)


def test_validation_and_duplicate_precheck_map_to_legacy_codes():
    client, app, headers = _client()
    try:
        empty = client.post("/api/v1/rebuild/ssh-nodes", headers=headers, json={**_body(), "name": " "})
        assert empty.status_code == 400
        assert empty.json()["code"] == 4103
        first = client.post("/api/v1/rebuild/ssh-nodes", headers=headers, json=_body())
        duplicate = client.post("/api/v1/rebuild/ssh-nodes", headers=headers, json=_body())
        assert first.status_code == 200
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == 4102

        other = client.post("/api/v1/rebuild/ssh-nodes", headers=headers, json=_body("node-c"))
        renamed = client.put(
            f"/api/v1/rebuild/ssh-nodes/{other.json()['data']['id']}", headers=headers, json=_body("node-a")
        )
        assert renamed.status_code == 409
        assert renamed.json()["code"] == 4102
    finally:
        client.__exit__(None, None, None)


def test_database_unique_race_is_stably_mapped_to_409_4102(monkeypatch):
    client, app, _ = _client()
    try:
        with app.state.session_factory() as session:
            service = SshNodeService(session, lambda *_: (True, "ok"))
            monkeypatch.setattr(service.repository, "find_by_name", lambda name: None)
            monkeypatch.setattr(
                service.repository,
                "add",
                lambda record: (_ for _ in ()).throw(IntegrityError("insert", {}, Exception("unique"))),
            )
            try:
                service.create(SshNodeInput("race", "host", 22, "root", "", [], True))
            except SshNodeDomainError as exc:
                assert (exc.status, exc.code) == (409, 4102)
            else:
                raise AssertionError("unique constraint race must map to the frozen domain error")
    finally:
        client.__exit__(None, None, None)


def test_delete_does_not_require_exec_node_tag_lookup():
    client, _, headers = _client()
    try:
        node_id = client.post("/api/v1/rebuild/ssh-nodes", headers=headers, json=_body()).json()["data"]["id"]
        deleted = client.delete(f"/api/v1/rebuild/ssh-nodes/{node_id}", headers=headers)
        missing = client.delete(f"/api/v1/rebuild/ssh-nodes/{node_id}", headers=headers)
        assert deleted.json() == {"code": 0, "msg": "success", "data": True}
        assert missing.status_code == 404
        assert missing.json()["code"] == 4101
    finally:
        client.__exit__(None, None, None)


def test_probe_is_immediate_and_does_not_mutate_heartbeat(monkeypatch):
    client, app, headers = _client()
    try:
        node_id = client.post("/api/v1/rebuild/ssh-nodes", headers=headers, json=_body()).json()["data"]["id"]
        # Router captured its default callable at assembly, so replace the service
        # method dependency by inspecting the route closure is intentionally avoided;
        # use a deterministic Paramiko client stub instead.
        class Stdout:
            def read(self):
                return b"ok\n"

        class Client:
            def set_missing_host_key_policy(self, policy): pass
            def connect(self, **kwargs): pass
            def exec_command(self, command, timeout): return None, Stdout(), None
            def close(self): pass

        monkeypatch.setattr("rebuild.sshnode.probe.paramiko.SSHClient", Client)
        result = client.post(f"/api/v1/rebuild/ssh-nodes/{node_id}/probe", headers=headers, json={})
        assert result.json()["data"] == {"ok": True, "message": "echo check passed"}
        with app.state.session_factory() as session:
            record = session.scalar(select(SshNodeRecord).where(SshNodeRecord.id == node_id))
            assert record.heartbeat_state == "unknown"
            assert record.last_seen is None
    finally:
        client.__exit__(None, None, None)
