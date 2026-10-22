from __future__ import annotations

import stat

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.runtime_node.models import RuntimeNodeRecord
from rebuild.runtime_node.service import (
    LS_MAX_ENTRIES,
    RuntimeNodeDomainError,
    RuntimeNodeService,
)


def _client(role: Role = Role.DEVELOPER):
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="runtime-node-test-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        UserRepository(session).create(
            username="runtime-user", password="runtime-password", role=role
        )
        session.commit()
    token = client.post(
        "/api/v1/rebuild/login", json={"username": "runtime-user", "password": "runtime-password"}
    ).json()["data"]["token"]
    return client, app, {"Authorization": f"Bearer {token}"}


def test_both_endpoints_require_token():
    client, _, _ = _client()
    try:
        anon_list = client.get("/api/v1/rebuild/runtime-nodes")
        anon_ls = client.get("/api/v1/rebuild/runtime-nodes/1/ls")
        assert anon_list.status_code == 401
        assert anon_list.json()["code"] == 1001
        assert anon_ls.status_code == 401
        assert anon_ls.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_list_returns_seeded_node_with_frozen_nine_field_payload():
    client, _, headers = _client()
    try:
        listed = client.get("/api/v1/rebuild/runtime-nodes", headers=headers)
        assert listed.status_code == 200
        rows = listed.json()["data"]
        assert len(rows) == 1
        row = rows[0]
        # B6-1 frozen nine fields; auth is never echoed.
        assert set(row) == {
            "id", "name", "kind", "host", "port", "user",
            "runtimeDir", "status", "lastHeartbeat",
        }
        assert "auth" not in row
        assert row["name"] == "1.9宿主机"
        assert row["kind"] == "远程"
        assert row["host"] == "192.168.1.9"
        assert row["port"] == 22
        assert row["user"] == "root"
        assert row["runtimeDir"] == "/tmp/datara_runtime"
        assert row["status"] == "offline"
        assert row["lastHeartbeat"] is None
    finally:
        client.__exit__(None, None, None)


def test_ls_unknown_node_maps_to_404_4101():
    client, _, headers = _client()
    try:
        missing = client.get("/api/v1/rebuild/runtime-nodes/9999/ls", headers=headers)
        assert missing.status_code == 404
        assert missing.json()["code"] == 4101
        assert missing.json()["msg"] == "运行时节点不存在"
    finally:
        client.__exit__(None, None, None)


def test_ls_relative_path_maps_to_400_4002():
    client, _, headers = _client()
    try:
        node_id = client.get(
            "/api/v1/rebuild/runtime-nodes", headers=headers
        ).json()["data"][0]["id"]
        bad = client.get(
            f"/api/v1/rebuild/runtime-nodes/{node_id}/ls",
            headers=headers,
            params={"path": "relative"},
        )
        assert bad.status_code == 400
        assert bad.json()["code"] == 4002
        assert bad.json()["msg"] == "路径必须为绝对路径"
    finally:
        client.__exit__(None, None, None)


def test_ls_node_without_host_maps_to_400_4002():
    client, app, headers = _client()
    try:
        with app.state.session_factory() as session:
            session.add(
                RuntimeNodeRecord(name="no-host", kind="本地", host="", runtime_dir="/tmp/x")
            )
            session.commit()
            node_id = session.query(RuntimeNodeRecord).filter_by(name="no-host").one().id
        response = client.get(
            f"/api/v1/rebuild/runtime-nodes/{node_id}/ls", headers=headers
        )
        assert response.status_code == 400
        assert response.json()["code"] == 4002
        assert response.json()["msg"] == "节点未配置主机地址"
    finally:
        client.__exit__(None, None, None)


class _Attr:
    """Minimal listdir_attr entry stub (filename/st_mode/st_size/st_mtime only)."""

    def __init__(self, filename: str, is_dir: bool):
        self.filename = filename
        self.st_mode = (stat.S_IFDIR | 0o755) if is_dir else (stat.S_IFREG | 0o644)
        self.st_size = 42
        self.st_mtime = 1700000000.5


def _add_node(app, name: str, runtime_dir: str = "/tmp") -> int:
    with app.state.session_factory() as session:
        session.add(
            RuntimeNodeRecord(name=name, kind="远程", host="10.0.0.9", port=22, user="root",
                              runtime_dir=runtime_dir)
        )
        session.commit()
        return session.query(RuntimeNodeRecord).filter_by(name=name).one().id


def test_service_ls_missing_path_maps_to_400_4002():
    client, app, _ = _client()
    try:
        node_id = _add_node(app, "svc-missing")
        with app.state.session_factory() as session:
            service = RuntimeNodeService(
                session, lambda node, base: (_ for _ in ()).throw(FileNotFoundError(base))
            )
            try:
                service.ls(node_id, "/missing")
            except RuntimeNodeDomainError as exc:
                assert (exc.status, exc.code) == (400, 4002)
                assert str(exc).startswith("路径不存在: /missing（")
            else:
                raise AssertionError("missing path must map to the frozen 4002 domain error")
    finally:
        client.__exit__(None, None, None)


def test_service_ls_connection_failure_maps_to_502_5002():
    client, app, _ = _client()
    try:
        node_id = _add_node(app, "svc-boom")
        with app.state.session_factory() as session:
            service = RuntimeNodeService(
                session, lambda node, base: (_ for _ in ()).throw(Exception("boom"))
            )
            try:
                service.ls(node_id, "/data")
            except RuntimeNodeDomainError as exc:
                assert (exc.status, exc.code) == (502, 5002)
                assert str(exc) == "SSH 目录浏览失败: boom"
            else:
                raise AssertionError("connection failure must map to the frozen 5002 domain error")
    finally:
        client.__exit__(None, None, None)


def test_service_ls_sorts_dirs_first_and_truncates_to_500():
    client, app, _ = _client()
    try:
        node_id = _add_node(app, "svc-big")
        attrs = [_Attr("dir-%03d" % i, True) for i in range(205)]
        attrs += [_Attr("file-%03d" % i, False) for i in range(300)]
        with app.state.session_factory() as session:
            data = RuntimeNodeService(session, lambda node, base: attrs).ls(node_id)
        assert data["path"] == "/tmp"
        entries = data["entries"]
        assert len(entries) == LS_MAX_ENTRIES
        assert set(entries[0]) == {"name", "dir", "size", "mtime"}
        assert entries[0] == {"name": "dir-000", "dir": True, "size": 42, "mtime": 1700000000}
        assert entries[204] == {"name": "dir-204", "dir": True, "size": 42, "mtime": 1700000000}
        assert entries[205] == {"name": "file-000", "dir": False, "size": 42, "mtime": 1700000000}
        assert entries[499] == {"name": "file-294", "dir": False, "size": 42, "mtime": 1700000000}
    finally:
        client.__exit__(None, None, None)


def test_service_ls_resolves_default_and_explicit_paths():
    client, app, _ = _client()
    try:
        node_id = _add_node(app, "svc-path", runtime_dir="/tmp/datara_runtime")
        calls: list[str] = []

        def fake(node, base):
            calls.append(base)
            return []

        with app.state.session_factory() as session:
            service = RuntimeNodeService(session, fake)
            assert service.ls(node_id)["path"] == "/tmp/datara_runtime"
            assert service.ls(node_id, "/x/")["path"] == "/x"
            assert service.ls(node_id, "/")["path"] == "/"
        assert calls == ["/tmp/datara_runtime", "/x", "/"]
    finally:
        client.__exit__(None, None, None)
