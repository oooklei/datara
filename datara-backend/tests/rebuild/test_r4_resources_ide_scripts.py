"""IDE 查询脚本投影（资源管理第二入口）— list/content/save 端点测试。

数据开发 IDE 的查询脚本存于 dbx saved-sql；脚本开发（资源管理）作为第二入口
读取同一真源。本文件断言：owner/连接可见性过滤与 dbx IDE 代理口径一致、
共享文件对非 owner 只读、保存写回 dbx（sql_loaded 置真）、以及 dbx 不可用时的降级。
"""

import pytest

from rebuild.api.app import create_app
from rebuild.dbx.client import DbxError
from rebuild.identity.contracts import Role
from rebuild.identity.models import ProjectMemberRecord, UserRecord
from rebuild.identity.repository import UserRepository
from rebuild.project.models import ProjectRecord

RESOURCES = "/api/v1/rebuild/resources"


class FakeDbx:
    def __init__(self, library=None, fail=False):
        self.library = library or {"folders": [], "files": []}
        self.fail = fail
        self.saved = []

    def list_saved_sql_library(self):
        if self.fail:
            raise DbxError()
        return self.library

    def load_saved_sql_file(self, file_id):
        if self.fail:
            raise DbxError()
        return next((item for item in self.library["files"] if item["id"] == file_id), None)

    def save_saved_sql_file(self, file):
        if self.fail:
            raise DbxError()
        self.saved.append(file)
        self.library["files"] = [item for item in self.library["files"] if item["id"] != file["id"]] + [file]
        return file


@pytest.fixture()
def ide_env(monkeypatch):
    """create_app + dbx saved-sql 桩：dev 拥有项目/连接/file-1，file-legacy 未认领。"""
    fake = FakeDbx(library={"folders": [], "files": [
        {"id": "file-1", "connectionId": "conn-1", "name": "query_1.sql", "database": "ec_retail",
         "schema": None, "sql": "select 1;", "sql_loaded": True, "createdAt": "t0", "updatedAt": "u0"},
        {"id": "file-legacy", "connectionId": "conn-1", "name": "legacy.sql", "database": "ec_retail",
         "schema": None, "sql": "select 2;", "sql_loaded": True, "createdAt": "t0", "updatedAt": "u0"},
        {"id": "file-hidden", "connectionId": "conn-2", "name": "hidden.sql", "database": "db",
         "schema": None, "sql": "select 3;", "sql_loaded": True, "createdAt": "t0", "updatedAt": "u0"},
    ]})
    monkeypatch.setattr("rebuild.resources.api.DbxClient", lambda: fake)

    app = create_app("sqlite+pysqlite:///:memory:", token_secret="ide-scripts-secret")
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        admin = UserRepository(session).create(username="admin", password="admin-pass", role=Role.ADMIN)
        dev = UserRepository(session).create(username="dev", password="dev-pass", role=Role.DEVELOPER)
        viewer = UserRepository(session).create(username="viewer", password="viewer-pass", role=Role.VIEWER)
        project = ProjectRecord(name="ide-scripts-project", description="", owner_id=dev.id)
        # conn-2/file-hidden 认领在另一项目，验证跨项目连接不可见。
        other = ProjectRecord(name="ide-scripts-other", description="", owner_id=admin.id)
        session.add_all((project, other))
        session.commit()
        project_id = project.id
        other_id = other.id
        session.add(ProjectMemberRecord(project_id=project_id, user_id=viewer.id, role="viewer"))

        from rebuild.dbx.access import DbxConnectionAccess, DbxObjectAccess

        connections = DbxConnectionAccess(session)
        connections.claim(connection_id="conn-1", project_id=project_id, owner_id=dev.id)
        connections.claim(connection_id="conn-2", project_id=other_id, owner_id=admin.id)
        DbxObjectAccess(session).claim(kind="sql-file", object_id="file-1", project_id=project_id,
                                       owner_id=dev.id, connection_id="conn-1")
        DbxObjectAccess(session).claim(kind="sql-file", object_id="file-hidden", project_id=other_id,
                                       owner_id=admin.id, connection_id="conn-2")
        session.commit()
    tokens = {}
    for username, password in (("admin", "admin-pass"), ("dev", "dev-pass"), ("viewer", "viewer-pass")):
        response = client.post("/api/v1/rebuild/login", json={"username": username, "password": password})
        tokens[username] = {"Authorization": f"Bearer {response.json()['data']['token']}"}
    try:
        yield client, fake, project_id, tokens
    finally:
        client.__exit__(None, None, None)


def test_list_filters_by_connection_and_ownership(ide_env):
    client, _fake, project_id, tokens = ide_env
    url = f"{RESOURCES}/ide-scripts"

    # admin 全见（含未认领 legacy），但隐藏连接上的文件必须属于可见连接；按 name 排序。
    admin_ids = [row["ide_file_id"] for row in client.get(url, headers=tokens["admin"], params={"project_id": project_id}).json()["data"]]
    assert admin_ids == ["file-legacy", "file-1"]

    # 非 admin 只见自己认领的文件；未认领 legacy 与他人文件隐藏。
    dev_ids = [row["ide_file_id"] for row in client.get(url, headers=tokens["dev"], params={"project_id": project_id}).json()["data"]]
    assert dev_ids == ["file-1"]

    # viewer 无任何 sql-file 归属 → 空列表。
    viewer_rows = client.get(url, headers=tokens["viewer"], params={"project_id": project_id}).json()["data"]
    assert viewer_rows == []

    # 缺 project_id → 4001。
    assert client.get(url, headers=tokens["dev"]).status_code == 400


def test_list_shared_file_visible_and_dbx_down_degrades(ide_env):
    client, fake, project_id, tokens = ide_env
    url = f"{RESOURCES}/ide-scripts"
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        from rebuild.dbx.access import DbxConnectionAccess, DbxObjectAccess

        DbxConnectionAccess(session).share(connection_id="conn-1", owner_id=2, user_id=3)
        DbxObjectAccess(session).share(kind="sql-file", object_id="file-1", owner_id=2, user_id=3)
        session.commit()

    shared = [row["ide_file_id"] for row in client.get(url, headers=tokens["viewer"], params={"project_id": project_id}).json()["data"]]
    assert shared == ["file-1"]

    # dbx 不可用 → 502，不影响主资源列表。
    fake.fail = True
    assert client.get(url, headers=tokens["dev"], params={"project_id": project_id}).status_code == 502
    fake.fail = False


def test_content_reads_sql_text_with_scope_rules(ide_env):
    client, _fake, project_id, tokens = ide_env
    url = f"{RESOURCES}/ide-scripts/file-1/content"

    owned = client.get(url, headers=tokens["dev"], params={"project_id": project_id})
    assert owned.status_code == 200
    assert owned.json()["data"]["content"] == "select 1;"
    assert owned.json()["data"]["name"] == "query_1.sql"

    # 未共享前 viewer 不可读。
    assert client.get(url, headers=tokens["viewer"], params={"project_id": project_id}).status_code == 403

    # 未认领 legacy 文件：admin 可读，非 admin 不可读。
    legacy = f"{RESOURCES}/ide-scripts/file-legacy/content"
    assert client.get(legacy, headers=tokens["admin"], params={"project_id": project_id}).status_code == 200
    assert client.get(legacy, headers=tokens["dev"], params={"project_id": project_id}).status_code == 403

    # dbx 中不存在的文件 → 404 RES_OBJECT_NOT_FOUND。
    missing = client.get(f"{RESOURCES}/ide-scripts/file-x/content", headers=tokens["admin"], params={"project_id": project_id})
    assert missing.status_code == 404 and missing.json()["code"] == "RES_OBJECT_NOT_FOUND"


def test_save_writes_back_to_dbx_and_enforces_owner(ide_env):
    client, fake, project_id, tokens = ide_env
    url = f"{RESOURCES}/ide-scripts/file-1"

    saved = client.post(url, headers=tokens["dev"], json={"project_id": project_id, "content": "select 42;"})
    assert saved.status_code == 200 and saved.json()["data"]["saved"] is True
    assert fake.saved[0]["sql"] == "select 42;" and fake.saved[0]["sql_loaded"] is True
    # 保存只改正文，不改变连接/库/名称等既有字段。
    assert fake.saved[0]["connectionId"] == "conn-1" and fake.saved[0]["name"] == "query_1.sql"

    # 非 owner（即使可见）不可保存：共享文件对 viewer 只读。
    with client.app.state.session_factory() as session:  # type: ignore[attr-defined]
        from rebuild.dbx.access import DbxConnectionAccess, DbxObjectAccess

        DbxConnectionAccess(session).share(connection_id="conn-1", owner_id=2, user_id=3)
        DbxObjectAccess(session).share(kind="sql-file", object_id="file-1", owner_id=2, user_id=3)
        session.commit()
    assert client.post(url, headers=tokens["viewer"], json={"project_id": project_id, "content": "select 0;"}).status_code == 403

    # 空 content → 4001；未认领 legacy 由 admin 保存。
    bad = client.post(url, headers=tokens["dev"], json={"project_id": project_id, "content": "   "})
    assert bad.status_code == 400 and bad.json()["code"] == 4001
    legacy_save = client.post(f"{RESOURCES}/ide-scripts/file-legacy", headers=tokens["admin"],
                              json={"project_id": project_id, "content": "select 3;"})
    assert legacy_save.status_code == 200

    # dbx 不存在的文件 → 404。
    missing = client.post(f"{RESOURCES}/ide-scripts/file-x", headers=tokens["admin"],
                          json={"project_id": project_id, "content": "select 1;"})
    assert missing.status_code == 404 and missing.json()["code"] == "RES_OBJECT_NOT_FOUND"


def test_anonymous_is_rejected(ide_env):
    client, _fake, project_id, _tokens = ide_env
    client.cookies.clear()
    response = client.get(f"{RESOURCES}/ide-scripts", params={"project_id": project_id})
    assert response.status_code == 401
