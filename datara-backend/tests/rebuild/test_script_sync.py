"""脚本开发资源 → 海豚资源中心同步测试。

覆盖：根目录创建、命中覆盖（``fullName`` 取列表实值）、创建竞态回退覆盖、
项目前缀命名、回填单条失败不中断整体、保存钩子尽力而为（海豚故障不阻断
脚本保存）、回填端点 admin 门禁与结果透出。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from rebuild.common.db import Base
from rebuild.identity.contracts import Role, TokenService
from rebuild.identity.models import ProjectMemberRecord, UserRecord
from rebuild.identity.repository import UserRepository
from rebuild.orchestration.api import build_orchestration_router
from rebuild.orchestration.ds_client import DsClientError
from rebuild.orchestration.script_sync import (
    script_resource_name,
    sync_project_scripts,
    sync_script_resource,
)
from rebuild.project.models import ProjectRecord
from rebuild.resources.api import build_resources_router
from rebuild.resources.models import ResourceRecord, ResourceVersionRecord
from rebuild.resources.repository import ResourceRepository


BASE = "/api/v1/rebuild/orchestration"

PROBE_NODE = {
    "name": "datara-p7-job.sql",
    "fullName": "/tmp/dolphinscheduler/default/resources/datara-p7-job.sql",
    "description": "FILE",
}


class FakeDs:
    """最小假海豚：仅实现资源列表 / 创建 / 覆盖三个端点。"""

    def __init__(self):
        self.routes = {}
        self.calls = []

    def call(self, method, path, *, query=None, form=None, files=None):
        self.calls.append(
            {"method": method, "path": path, "query": query or {}, "form": form or {}, "files": files or {}}
        )
        handler = self.routes.get((method, path))
        if handler is None:
            raise DsClientError("DS_API_ERROR", f"no fake route for {method} {path}", 502)
        return handler(query or {}, form or {})


def test_script_resource_name_prefixes_project():
    assert script_resource_name(7, "job.sql") == "datara-p7-job.sql"


def test_sync_creates_at_root_when_absent():
    ds = FakeDs()
    ds.routes[("GET", "/resources/list")] = lambda q, f: {"totalList": []}
    ds.routes[("POST", "/resources")] = lambda q, f: None
    result = sync_script_resource(ds, project_id=7, name="job.sql", content=b"select 1;")
    assert result["action"] == "created"
    assert result["name"] == "datara-p7-job.sql"
    call = ds.calls[-1]
    assert call["form"]["currentDir"] == "/"
    assert call["form"]["type"] == "FILE"
    assert call["files"]["file"] == ("datara-p7-job.sql", b"select 1;", "application/octet-stream")


def test_sync_overwrites_existing_with_listed_full_name():
    ds = FakeDs()
    ds.routes[("GET", "/resources/list")] = lambda q, f: {"totalList": [dict(PROBE_NODE)]}
    captured = {}
    ds.routes[("PUT", "/resources")] = lambda q, f: captured.update(f)
    result = sync_script_resource(ds, project_id=7, name="job.sql", content=b"select 2;")
    assert result == {"action": "updated", "name": "datara-p7-job.sql", "fullName": PROBE_NODE["fullName"]}
    assert captured["fullName"] == PROBE_NODE["fullName"]
    assert captured["name"] == "datara-p7-job.sql"
    assert ds.calls[-1]["files"]["file"][1] == b"select 2;"


def test_sync_create_race_falls_back_to_overwrite():
    ds = FakeDs()
    state = {"created_by_racer": False}

    def _list(query, form):
        return {"totalList": [dict(PROBE_NODE)] if state["created_by_racer"] else []}

    def _post(query, form):
        state["created_by_racer"] = True  # 并发方恰好先落库
        raise DsClientError("DS_API_ERROR", "resource datara-p7-job.sql already exists", 502)

    ds.routes[("GET", "/resources/list")] = _list
    ds.routes[("POST", "/resources")] = _post
    captured = {}
    ds.routes[("PUT", "/resources")] = lambda q, f: captured.update(f)
    result = sync_script_resource(ds, project_id=7, name="job.sql", content=b"select 3;")
    assert result["action"] == "updated"
    assert captured["fullName"] == PROBE_NODE["fullName"]


def test_sync_create_failure_without_node_raises():
    ds = FakeDs()
    ds.routes[("GET", "/resources/list")] = lambda q, f: {"totalList": []}
    # 无 PUT 路由：回查仍无节点时 POST 的 DsClientError 必须如实抛出。
    ds.routes[("POST", "/resources")] = lambda q, f: (_ for _ in ()).throw(
        DsClientError("DS_API_ERROR", "boom", 502)
    )
    with pytest.raises(DsClientError):
        sync_script_resource(ds, project_id=7, name="job.sql", content=b"x")


def _make_engine(tables, tmp_path, monkeypatch):
    monkeypatch.setenv("REBUILD_RESOURCE_STORAGE_DIR", str(tmp_path / "storage"))
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=tables)
    return engine


def _resource_engine(tmp_path, monkeypatch):
    return _make_engine([ResourceRecord.__table__, ResourceVersionRecord.__table__], tmp_path, monkeypatch)


def test_sync_project_scripts_backfills_and_reports_single_failure(tmp_path, monkeypatch):
    factory = sessionmaker(bind=_resource_engine(tmp_path, monkeypatch), expire_on_commit=False)
    with factory() as session:
        repo = ResourceRepository(session)
        repo.save_upload(7, "sql", "a.sql", b"select 1;")
        repo.save_upload(7, "python", "b.py", b"print(1)")
        repo.save_upload(7, "shell", "c.sh", b"echo hi")
        session.commit()

    ds = FakeDs()
    ds.routes[("GET", "/resources/list")] = lambda q, f: {"totalList": []}

    def _post(query, form):
        if form.get("name") == "datara-p7-c.sh":
            raise DsClientError("DS_UNREACHABLE", "dolphinscheduler down", 502)
        return None

    ds.routes[("POST", "/resources")] = _post
    results = sync_project_scripts(ds, factory, project_id=7)
    by_name = {item["name"]: item for item in results}
    assert by_name["a.sql"]["action"] in {"created", "updated"}
    assert by_name["a.sql"]["dsName"] == "datara-p7-a.sql"
    assert by_name["b.py"]["action"] in {"created", "updated"}
    assert "error" in by_name["c.sh"]
    assert "DS_UNREACHABLE" in by_name["c.sh"]["error"]


def _identity_factory(tmp_path, monkeypatch, users=(("root", Role.ADMIN), ("dev", Role.DEVELOPER))):
    engine = _make_engine(
        [
            ResourceRecord.__table__,
            ResourceVersionRecord.__table__,
            UserRecord.__table__,
            ProjectMemberRecord.__table__,
            ProjectRecord.__table__,
        ],
        tmp_path,
        monkeypatch,
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    tokens: set[str] = set()
    token_service = TokenService(secret="script-sync-test-secret")
    with factory() as session:
        for username, role in users:
            UserRepository(session).create(username=username, password="pw", role=role)
        session.add(ProjectRecord(name="demo", description="demo", owner_id=1))
        session.commit()
    return factory, tokens, token_service


def test_upload_hook_syncs_and_survives_dolphin_failure(tmp_path, monkeypatch):
    factory, tokens, token_service = _identity_factory(tmp_path, monkeypatch)
    syncs: list[tuple[int, str, bytes]] = []

    def syncer(project_id: int, name: str, content: bytes) -> None:
        syncs.append((project_id, name, content))
        if name == "boom.sql":
            raise DsClientError("DS_UNREACHABLE", "dolphinscheduler down", 502)

    app = FastAPI()
    app.include_router(
        build_resources_router(
            factory,
            token_service,
            tokens,
            lambda session, project_id, user, permission: None,
            script_syncer=syncer,
        ),
        prefix="/api/v1/rebuild/resources",
    )
    client = TestClient(app)

    def _token(username: str) -> str:
        with factory() as session:
            user = UserRepository(session).find_by_username(username)
            token = token_service.issue(user_id=user.id, username=user.username, role=Role(user.role))
        tokens.add(token)
        return token

    headers = {"token": _token("dev")}
    ok = client.post(
        "/api/v1/rebuild/resources/uploads",
        data={"project_id": "7", "kind": "sql"},
        files={"file": ("a.sql", b"select 1;", "text/plain")},
        headers=headers,
    )
    assert ok.status_code == 200 and ok.json()["code"] == 0
    assert syncs == [(7, "a.sql", b"select 1;")]

    boom = client.post(
        "/api/v1/rebuild/resources/uploads",
        data={"project_id": "7", "kind": "sql"},
        files={"file": ("boom.sql", b"select 2;", "text/plain")},
        headers=headers,
    )
    assert boom.status_code == 200 and boom.json()["code"] == 0  # 海豚故障不阻断保存
    assert len(syncs) == 2

    edited = client.post(
        "/api/v1/rebuild/resources/1/versions",
        data={"project_id": "7"},
        files={"file": ("ignored.sql", b"select 11;", "text/plain")},
        headers=headers,
    )
    assert edited.status_code == 200 and edited.json()["code"] == 0
    assert syncs[-1] == (7, "a.sql", b"select 11;")  # 编辑流按资源名（而非上传文件名）同步


def test_backfill_endpoint_admin_only_and_reports_items(tmp_path, monkeypatch):
    factory, tokens, token_service = _identity_factory(tmp_path, monkeypatch)
    with factory() as session:
        repo = ResourceRepository(session)
        repo.save_upload(1, "sql", "orders.sql", b"select 1;")
        session.commit()

    ds = FakeDs()
    ds.routes[("GET", "/resources/list")] = lambda q, f: {"totalList": []}
    ds.routes[("POST", "/resources")] = lambda q, f: None

    app = FastAPI()
    app.include_router(
        build_orchestration_router(
            factory,
            token_service,
            tokens,
            lambda session, project_id, user, permission: None,
            ds_client_factory=lambda: ds,
        )
    )
    client = TestClient(app)

    def _token(username: str) -> str:
        with factory() as session:
            user = UserRepository(session).find_by_username(username)
            token = token_service.issue(user_id=user.id, username=user.username, role=Role(user.role))
        tokens.add(token)
        return token

    denied = client.post(f"{BASE}/script-resources/sync", headers={"token": _token("dev")})
    assert denied.status_code == 403
    assert denied.json()["code"] == "ORCH_SCRIPT_SYNC_FORBIDDEN"

    ok = client.post(f"{BASE}/script-resources/sync", headers={"token": _token("root")})
    assert ok.status_code == 200
    body = ok.json()["data"]
    assert body["synced"] == 1 and body["failed"] == 0
    assert body["items"][0]["name"] == "orders.sql"
    assert body["items"][0]["action"] == "created"

    scoped = client.post(f"{BASE}/script-resources/sync", json={"projectId": 999}, headers={"token": _token("root")})
    assert scoped.status_code == 200
    assert scoped.json()["data"]["items"] == []
