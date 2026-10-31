"""§10.10 / §10.11 / §10.5 B 编排网关代理端点测试。

覆盖：owner 可见性过滤、写权限门禁、显式共享、CONFIG 来源分组只读、
海豚业务码透传、心跳离线判定、分析时间窗校验，以及运行监控
（工作流实例 / 任务实例 / 日志 / 启动与控制，§10.7 B1）的代理契约。
"""

import json
import base64
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from rebuild.common.db import Base
from rebuild.dbx.access import DbxConnectionAccess
from rebuild.dbx.models import DbxConnectionOwnershipRecord, DbxConnectionShareRecord
from rebuild.identity.contracts import Role, TokenService
from rebuild.identity.models import ProjectMemberRecord, UserRecord
from rebuild.identity.repository import UserRepository
from rebuild.orchestration.api import build_orchestration_router
from rebuild.orchestration.ds_client import DsClientError
from rebuild.orchestration.governance import (
    KIND_RESOURCE_FILE,
    KIND_WORKER_GROUP,
    OrchestrationResourceAccess,
    OrchestrationResourceOwnershipRecord,
    OrchestrationResourceShareRecord,
)
from rebuild.project.models import ProjectRecord


BASE = "/api/v1/rebuild/orchestration"


class FakeDs:
    """按 (method, path) 分派的假海豚；未登记路由抛 DsClientError。"""

    admin_user = "admin"

    def __init__(self, routes=None, projects=None):
        self.routes = routes or {}
        self.projects = projects or {}
        self.calls = []

    def call(self, method, path, *, query=None, form=None, files=None):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "query": query or {},
                "form": form or {},
                "files": files or {},
            }
        )
        handler = self.routes.get((method, path))
        if handler is None:
            raise DsClientError("DS_API_ERROR", f"no fake route for {method} {path}", 502)
        return handler(query or {}, form or {})

    def download(self, path, *, query=None):
        """二进制下载替身：返回 (正文字节, Content-Type)，与真客户端同签名。"""
        self.calls.append({"method": "GET", "path": path, "query": query or {}, "form": {}, "files": {}})
        handler = self.routes.get(("GET", path))
        if handler is None:
            raise DsClientError("DS_API_ERROR", f"no fake route for GET {path}", 502)
        return handler(query or {}, {}), "application/octet-stream"

    def ensure_project(self, name, description=""):
        return self.projects.get(name, {"code": 123456, "name": name})


def _worker_group(name, *, group_id=1, source=None, system_default=False):
    return {
        "id": group_id,
        "name": name,
        "addrList": "172.23.0.4:1234",
        "description": "",
        "systemDefault": system_default,
        "source": source,
        "createTime": "2026-10-29 00:00:00",
        "updateTime": "2026-10-29 00:00:00",
    }


class Harness:
    def __init__(self, fake, *, users=(), project=True, dbx=None):
        self.fake = fake
        self.dbx = dbx
        self.engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            self.engine,
            tables=[
                UserRecord.__table__,
                ProjectRecord.__table__,
                ProjectMemberRecord.__table__,
                OrchestrationResourceOwnershipRecord.__table__,
                OrchestrationResourceShareRecord.__table__,
                DbxConnectionOwnershipRecord.__table__,
                DbxConnectionShareRecord.__table__,
            ],
        )
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.tokens = set()
        self.token_service = TokenService(secret="orchestration-test-secret")
        with self.factory() as session:
            for username, role in users:
                UserRepository(session).create(username=username, password="pw", role=role)
            session.commit()
            if project:
                session.add(ProjectRecord(name="demo", description="demo project", owner_id=1))
                session.commit()

    def token(self, username):
        with self.factory() as session:
            user = UserRepository(session).find_by_username(username)
            assert user is not None
            claims = {"user_id": user.id, "username": user.username, "role": Role(user.role)}
        token = self.token_service.issue(**claims)
        self.tokens.add(token)
        return token

    def client(self, *, peer="testclient"):
        app = FastAPI()
        app.include_router(
            build_orchestration_router(
                self.factory,
                self.token_service,
                self.tokens,
                lambda session, project_id, user, permission: None,
                ds_client_factory=lambda: self.fake,
                dbx_client_factory=lambda: self.dbx,
            )
        )
        return TestClient(app, client=(peer, 50000))


def _harness(*, fake, users=(("owner", Role.DEVELOPER), ("other", Role.DEVELOPER), ("root", Role.ADMIN))):
    return Harness(fake, users=users)


def test_orchestration_datasources_uses_owner_visible_dbx_connections_without_secrets():
    class FakeDbx:
        def list_connections(self):
            return [
                {"id": "mine", "name": "Orders", "db_type": "mysql", "host": "db",
                 "database": "sales", "password": "secret"},
                {"id": "other", "name": "Other", "db_type": "postgres", "host": "db2",
                 "database": "hr", "password": "other-secret"},
                {"id": "unsupported", "name": "Unknown", "db_type": "unknown"},
            ]

    h = Harness(FakeDs(), users=(("owner", Role.DEVELOPER), ("other", Role.DEVELOPER),
                                 ("root", Role.ADMIN)), dbx=FakeDbx())
    with h.factory() as session:
        access = DbxConnectionAccess(session)
        access.claim(connection_id="mine", project_id=1, owner_id=1)
        access.claim(connection_id="other", project_id=1, owner_id=2)
        session.commit()
    owner = h.client().get(f"{BASE}/datasources?project_id=1", headers={"token": h.token("owner")})
    assert owner.status_code == 200
    assert owner.json()["data"] == [{
        "id": "mine", "name": "Orders", "type": "MYSQL", "host": "db",
        "database": "sales", "project_id": 1,
    }]
    assert "secret" not in owner.text
    with h.factory() as session:
        DbxConnectionAccess(session).share(connection_id="other", owner_id=2, user_id=1)
        session.commit()
    shared = h.client().get(f"{BASE}/datasources?project_id=1", headers={"token": h.token("owner")})
    assert [item["id"] for item in shared.json()["data"]] == ["mine", "other"]
    assert shared.json()["data"][1]["type"] == "POSTGRESQL"
    admin = h.client().get(f"{BASE}/datasources?project_id=1", headers={"token": h.token("root")})
    assert [item["id"] for item in admin.json()["data"]] == ["mine", "other"]


def test_workflow_schedules_list_and_state_use_project_code_and_write_gate():
    fake = FakeDs(routes={
        ("GET", "/projects/123456/schedules"): lambda q, f: {
            "total": 1, "totalList": [{
                "id": 7, "workflowDefinitionCode": 88, "workflowDefinitionName": "orders",
                "crontab": "0 0 * * * ?", "releaseState": "OFFLINE",
            }],
        },
        ("POST", "/projects/123456/schedules/7/online"): lambda q, f: {"ok": True},
    })
    h = Harness(fake, users=(("owner", Role.DEVELOPER), ("viewer", Role.VIEWER)))
    client = h.client()
    listed = client.get(f"{BASE}/workflow-schedules?project_id=1&page_no=2&page_size=5",
                        headers={"token": h.token("owner")})
    assert listed.status_code == 200
    assert listed.json()["data"]["list"][0]["workflowDefinitionCode"] == 88
    assert fake.calls[-1]["query"] == {"pageNo": 2, "pageSize": 5}
    denied = client.post(f"{BASE}/workflow-schedules/7/online?project_id=1",
                         headers={"token": h.token("viewer")})
    assert denied.status_code == 403
    assert not any(call["method"] == "POST" for call in fake.calls)
    updated = client.post(f"{BASE}/workflow-schedules/7/online?project_id=1",
                          headers={"token": h.token("owner")})
    assert updated.status_code == 200
    assert fake.calls[-1]["path"] == "/projects/123456/schedules/7/online"
    missing = client.get(f"{BASE}/workflow-schedules?project_id=999",
                         headers={"token": h.token("owner")})
    assert missing.status_code == 404


def test_internal_connection_params_reads_only_project_claimed_dbx_connection(monkeypatch):
    class FakeDbx:
        def __init__(self):
            self.reads = []

        def internal_connection(self, connection_id):
            self.reads.append(connection_id)
            return {"id": connection_id, "db_type": "mysql", "host": "db", "port": 3306,
                    "database": "sales", "username": "etl", "password": "secret"}

    fake_dbx = FakeDbx()
    h = Harness(FakeDs(), users=(("owner", Role.DEVELOPER), ("other", Role.DEVELOPER)), dbx=fake_dbx)
    with h.factory() as session:
        DbxConnectionAccess(session).claim(connection_id="dbx-uuid", project_id=1, owner_id=1)
        session.commit()
    monkeypatch.setenv("DATARA_INTERNAL_TOKEN", "a" * 32)
    client = h.client(peer="127.0.0.1")
    path = "/internal/dbx/connections/dbx-uuid/params?project_id=1"
    assert client.get(path).status_code == 401
    headers = {"X-Datara-Internal-Token": "a" * 32, "X-Datara-User": "owner"}
    assert client.get(path, headers={"X-Datara-Internal-Token": "a" * 32}).status_code == 404
    response = client.get(path, headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["type"] == "MYSQL"
    assert json.loads(response.json()["data"]["connectionParams"])["password"] == "secret"
    assert fake_dbx.reads == ["dbx-uuid"]
    other_headers = {**headers, "X-Datara-User": "other"}
    assert client.get(path, headers=other_headers).status_code == 404
    with h.factory() as session:
        DbxConnectionAccess(session).share(connection_id="dbx-uuid", owner_id=1, user_id=2)
        session.commit()
    assert client.get(path, headers=other_headers).status_code == 200
    with h.factory() as session:
        DbxConnectionAccess(session).unshare(connection_id="dbx-uuid", owner_id=1, user_id=2)
        session.commit()
    assert client.get(path, headers=other_headers).status_code == 404
    denied = client.get("/internal/dbx/connections/other/params?project_id=1",
                        headers=headers)
    assert denied.status_code == 404
    assert fake_dbx.reads == ["dbx-uuid", "dbx-uuid"]


def test_embed_session_issues_short_lived_signed_token_not_internal_secret(monkeypatch):
    monkeypatch.setenv("DATARA_DS_EMBED_SECRET", "s" * 32)
    monkeypatch.setenv("DATARA_INTERNAL_TOKEN", "i" * 32)
    h = Harness(FakeDs(), users=(("owner", Role.DEVELOPER),))
    response = h.client().get(f"{BASE}/session?project_id=1", headers={"token": h.token("owner")})
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["token"] != "i" * 32
    claims = json.loads(base64.urlsafe_b64decode(payload["token"].split(".")[0] + "=="))
    assert claims["p"] == "123456"
    assert claims["d"] == 1
    assert claims["u"] == payload["user"]
    post_response = h.client().post(
        "/api/v1/rebuild/embed/session?project_id=1",
        headers={"token": h.token("owner")},
    )
    assert post_response.status_code == 200
    assert post_response.json()["data"]["projectId"] == 1


def test_worker_group_list_filters_by_owner_and_admin_sees_all():
    fake = FakeDs(
        routes={
            ("GET", "/worker-groups"): lambda q, f: {
                "totalList": [
                    _worker_group("default", group_id=None, source="CONFIG", system_default=True),
                    _worker_group("mine", group_id=7),
                    _worker_group("theirs", group_id=8),
                ]
            }
        }
    )
    h = _harness(fake=fake)
    with h.factory() as session:
        OrchestrationResourceAccess(session).claim(KIND_WORKER_GROUP, "theirs", 2)
        session.commit()

    mine = h.client().get(f"{BASE}/worker-groups", headers={"token": h.token("owner")}).json()
    assert mine["code"] == 0
    names = [row["name"] for row in mine["data"]]
    # 未登记归属的 default 对所有登录用户只读可见；theirs 被别人占用 → 不可见。
    assert names == ["default", "mine"]
    assert mine["data"][0]["systemDefault"] is True
    assert mine["data"][0]["ownerId"] is None
    assert mine["data"][0]["canManage"] is False

    admin = h.client().get(f"{BASE}/worker-groups", headers={"token": h.token("root")}).json()
    assert [row["name"] for row in admin["data"]] == ["default", "mine", "theirs"]


def test_worker_group_create_claims_owner_and_config_group_is_readonly():
    created = {}

    def create(q, f):
        created.update(f)
        return {"id": 42, "name": f.get("name")}

    fake = FakeDs(
        routes={
            ("GET", "/worker-groups"): lambda q, f: {"totalList": [_worker_group("default", group_id=None, source="CONFIG")]},
            ("POST", "/worker-groups"): create,
        }
    )
    h = _harness(fake=fake)
    client = h.client()
    headers = {"token": h.token("owner")}

    response = client.post(f"{BASE}/worker-groups", json={"name": "alpha", "addrList": "10.0.0.1:1234"}, headers=headers)
    assert response.json()["code"] == 0, response.text
    assert created["name"] == "alpha"
    with h.factory() as session:
        assert OrchestrationResourceAccess(session).owner_of(KIND_WORKER_GROUP, "alpha") == 1

    readonly = client.put(f"{BASE}/worker-groups/default", json={"name": "default", "addrList": ""}, headers=headers)
    assert readonly.status_code == 400
    assert readonly.json()["code"] == "ORCH_WORKER_GROUP_READONLY"

    denied = client.delete(f"{BASE}/worker-groups/alpha", headers={"token": h.token("other")})
    assert denied.status_code == 404


def test_deleted_owner_token_cannot_create_unowned_worker_group():
    fake = FakeDs(routes={("POST", "/worker-groups"): lambda q, f: {"id": 42, "name": f["name"]}})
    h = _harness(fake=fake)
    stale_token = h.token_service.issue(user_id=999, username="deleted", role=Role.DEVELOPER)
    h.tokens.add(stale_token)

    response = h.client().post(
        f"{BASE}/worker-groups",
        json={"name": "orphan", "addrList": "10.0.0.1:1234"},
        headers={"token": stale_token},
    )
    assert response.status_code == 401
    assert fake.calls == []
    with h.factory() as session:
        access = OrchestrationResourceAccess(session)
        try:
            access.claim(KIND_WORKER_GROUP, "orphan", 999)
        except PermissionError:
            pass
        else:
            raise AssertionError("missing owner must be rejected")
        assert access.owner_of(KIND_WORKER_GROUP, "orphan") is None


def test_worker_group_rename_migrates_ownership():
    fake = FakeDs(
        routes={
            ("GET", "/worker-groups"): lambda q, f: {"totalList": [_worker_group("alpha", group_id=7)]},
            ("POST", "/worker-groups"): lambda q, f: {"id": f.get("id"), "name": f.get("name")},
        }
    )
    h = _harness(fake=fake)
    client = h.client()
    headers = {"token": h.token("owner")}
    assert client.put(f"{BASE}/worker-groups/alpha", json={"name": "beta", "addrList": ""}, headers=headers).json()["code"] == 0
    with h.factory() as session:
        access = OrchestrationResourceAccess(session)
        assert access.owner_of(KIND_WORKER_GROUP, "alpha") is None
        assert access.owner_of(KIND_WORKER_GROUP, "beta") == 1


def test_queue_and_cluster_writes_require_admin():
    fake = FakeDs(
        routes={
            ("GET", "/queues/list"): lambda q, f: [{"id": 1, "queue": "default", "queueName": "default"}],
            ("GET", "/cluster/query-cluster-list"): lambda q, f: [],
            ("POST", "/queues"): lambda q, f: {"id": 2},
            ("POST", "/cluster/create"): lambda q, f: {"code": 999},
        }
    )
    h = _harness(fake=fake)
    client = h.client()
    developer = {"token": h.token("owner")}

    assert client.post(f"{BASE}/queues", json={"queue": "q", "queueName": "Q"}, headers=developer).status_code == 403
    assert client.post(f"{BASE}/clusters", json={"name": "c"}, headers=developer).status_code == 403

    # 读路径对所有登录用户开放。
    assert client.get(f"{BASE}/queues", headers=developer).json()["code"] == 0
    assert client.get(f"{BASE}/clusters", headers=developer).json()["code"] == 0

    admin = {"token": h.token("root")}
    assert client.post(f"{BASE}/queues", json={"queue": "q", "queueName": "Q"}, headers=admin).json()["code"] == 0
    assert client.post(f"{BASE}/clusters", json={"name": "c"}, headers=admin).json()["code"] == 0


def test_environment_payload_serializes_worker_groups_as_json_array():
    captured = {}

    def create(q, f):
        captured.update(f)
        return {"code": 188267047667200}

    fake = FakeDs(routes={("POST", "/environment/create"): create})
    h = _harness(fake=fake)
    client = h.client()
    response = client.post(
        f"{BASE}/environments",
        json={"name": "dev", "config": "c", "description": "d", "workerGroups": ["default"]},
        headers={"token": h.token("owner")},
    )
    assert response.json()["code"] == 0, response.text
    assert captured["workerGroups"] == '["default"]'


def test_share_grants_visibility_and_only_owner_can_share():
    fake = FakeDs(
        routes={
            ("GET", "/worker-groups"): lambda q, f: {"totalList": [_worker_group("alpha", group_id=7)]}
        }
    )
    h = _harness(fake=fake)
    with h.factory() as session:
        OrchestrationResourceAccess(session).claim(KIND_WORKER_GROUP, "alpha", 1)
        session.commit()

    client = h.client()
    assert client.get(f"{BASE}/worker-groups", headers={"token": h.token("other")}).json()["data"] == []

    forbidden = client.post(
        f"{BASE}/resources/{KIND_WORKER_GROUP}/alpha/share",
        json={"username": "other"},
        headers={"token": h.token("other")},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "ORCH_SHARE_FORBIDDEN"

    ok = client.post(
        f"{BASE}/resources/{KIND_WORKER_GROUP}/alpha/share",
        json={"username": "other"},
        headers={"token": h.token("owner")},
    )
    assert ok.json()["code"] == 0, ok.text

    shared = client.get(f"{BASE}/worker-groups", headers={"token": h.token("other")}).json()
    assert [row["name"] for row in shared["data"]] == ["alpha"]
    assert shared["data"][0]["canManage"] is False

    unshared = client.delete(
        f"{BASE}/resources/{KIND_WORKER_GROUP}/alpha/share?username=other",
        headers={"token": h.token("owner")},
    )
    assert unshared.json()["code"] == 0
    assert client.get(f"{BASE}/worker-groups", headers={"token": h.token("other")}).json()["data"] == []

    missing = client.post(
        f"{BASE}/resources/{KIND_WORKER_GROUP}/alpha/share",
        json={"username": "ghost"},
        headers={"token": h.token("owner")},
    )
    assert missing.status_code == 404
    bad_kind = client.post(
        "/api/v1/rebuild/orchestration/resources/bogus/alpha/share",
        json={"username": "other"},
        headers={"token": h.token("owner")},
    )
    assert bad_kind.status_code == 400


def test_ds_business_error_is_passthrough():
    fake = FakeDs()  # 未登记路由 → 502
    h = _harness(fake=fake)
    response = h.client().get(f"{BASE}/worker-groups", headers={"token": h.token("owner")})
    assert response.status_code == 502
    assert response.json()["code"] == "DS_API_ERROR"


def test_monitor_server_heartbeat_offline_and_invalid_node_type():
    now = datetime.now()
    stale = (now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    fresh = (now - timedelta(seconds=5)).strftime("%Y-%m-%d %H:%M:%S")

    def servers(q, f):
        return [
            {
                "id": 1,
                "host": "172.23.0.4",
                "port": 1234,
                "serverDirectory": "/ds",
                "heartBeatInfo": '{"cpuUsage": 12.5, "memoryUsage": 40.0, "diskUsage": 30.0, "processId": 1}',
                "createTime": stale,
                "lastHeartbeatTime": stale,
            },
            {
                "id": 2,
                "host": "172.23.0.5",
                "port": 1234,
                "serverDirectory": "/ds",
                "heartBeatInfo": '{"cpuUsage": 1.0, "memoryUsage": 2.0, "diskUsage": 3.0}',
                "createTime": fresh,
                "lastHeartbeatTime": fresh,
            },
        ]

    fake = FakeDs(routes={("GET", "/monitor/WORKER"): servers})
    h = _harness(fake=fake)
    client = h.client()
    headers = {"token": h.token("owner")}

    data = client.get(f"{BASE}/monitor/WORKER", headers=headers).json()
    assert data["code"] == 0
    first, second = data["data"]
    assert first["heartbeatState"] == "offline"
    assert first["heartbeatAgeSeconds"] > 200
    assert first["cpuUsage"] == 12.5
    assert first["loadAverage"] is None
    assert second["heartbeatState"] == "online"

    invalid = client.get(f"{BASE}/monitor/BOGUS", headers=headers)
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "ORCH_MONITOR_NODE_TYPE_INVALID"

    # 具体路由必须先于 {node_type} 注册，否则会被通配路径截获为 400。
    databases = FakeDs(
        routes={
            ("GET", "/monitor/WORKER"): servers,
            ("GET", "/monitor/databases"): lambda q, f: [{"dbType": "POSTGRE_SQL", "state": "YES"}],
        }
    )
    h2 = _harness(fake=databases)
    db = h2.client().get(f"{BASE}/monitor/databases", headers={"token": h2.token("owner")}).json()
    assert db["code"] == 0
    assert db["data"][0]["state"] == "YES"


def test_analysis_window_validation_and_project_code_resolution():
    seen = {}

    def task_state(q, f):
        seen.update(q)
        return {"totalCount": 0, "taskInstanceStatusCounts": []}

    fake = FakeDs(routes={("GET", "/projects/analysis/task-state-count"): task_state})
    h = _harness(fake=fake)
    client = h.client()
    headers = {"token": h.token("owner")}

    bad = client.get(f"{BASE}/monitor/task-state-count?project_id=1&start_date=nope", headers=headers)
    assert bad.status_code == 400
    assert bad.json()["code"] == "ORCH_MONITOR_DATE_INVALID"

    reversed_window = client.get(
        f"{BASE}/monitor/task-state-count?project_id=1&start_date=2026-10-29 10:00:00&end_date=2026-10-29 09:00:00",
        headers=headers,
    )
    assert reversed_window.status_code == 400

    ok = client.get(f"{BASE}/monitor/task-state-count?project_id=1", headers=headers)
    assert ok.json()["code"] == 0, ok.text
    assert seen["projectCode"] == 123456
    assert seen["startDate"].endswith("00:00:00")

    missing_project = client.get(f"{BASE}/monitor/workflow-state-count?project_id=999", headers=headers)
    assert missing_project.status_code == 404


def test_monitor_requires_active_token():
    h = _harness(fake=FakeDs())
    denied = h.client().get(f"{BASE}/monitor/WORKER")
    assert denied.status_code == 401
    assert denied.json() == {"code": "1001", "msg": "invalid token", "data": None}


# -- §10.5 B 运行监控：工作流实例 / 任务实例 / 日志 / 启动与控制 --------------

PROJECT_CODE = 123456


def _instance_row(instance_id=101, definition_code=9001):
    return {
        "id": instance_id,
        "name": "wf-20261030",
        "workflowDefinitionCode": definition_code,
        "workflowDefinitionVersion": 3,
        "state": "SUCCESS",
        "recovery": "NO",
        "startTime": "2026-10-30 08:00:00",
        "endTime": "2026-10-30 08:00:10",
        "duration": 10000,
        "runTimes": 1,
        "host": "172.23.0.4:1234",
        "executorName": "datara-owner",
    }


def test_workflow_instance_list_passes_paging_and_whitelisted_filters():
    fake = FakeDs(
        routes={
            ("GET", f"/projects/{PROJECT_CODE}/workflow-instances"): lambda q, f: {
                "totalList": [_instance_row()],
                "total": 1,
            }
        }
    )
    h = _harness(fake=fake)
    headers = {"token": h.token("owner")}

    ok = h.client().get(
        f"{BASE}/workflow-instances"
        "?project_id=1&page_no=2&page_size=20&workflow_definition_code=9001"
        "&search_val=wf&state_type=SUCCESS&host=172.23.0.4&executor_name=datara-owner"
        "&start_date=2026-10-30%2000:00:00&end_date=2026-10-30%2023:59:59&ignored=drop",
        headers=headers,
    ).json()
    assert ok["code"] == 0, ok
    assert ok["data"]["total"] == 1
    assert ok["data"]["pageNo"] == 2
    assert ok["data"]["pageSize"] == 20
    assert ok["data"]["list"][0]["workflowDefinitionCode"] == 9001

    query = fake.calls[-1]["query"]
    assert query["pageNo"] == 2 and query["pageSize"] == 20
    # 海豚侧过滤键按白名单映射，宿主未声明的参数不得透传。
    assert query["searchVal"] == "wf"
    assert query["stateType"] == "SUCCESS"
    assert query["executorName"] == "datara-owner"
    assert query["workflowDefinitionCode"] == 9001
    assert "ignored" not in query

    # 未传 definition code 时不下发（0 在海豚侧等价于不过滤，但省略更明确）。
    h.client().get(f"{BASE}/workflow-instances?project_id=1", headers=headers)
    assert "workflowDefinitionCode" not in fake.calls[-1]["query"]

    bad = h.client().get(f"{BASE}/workflow-instances?project_id=1&page_size=500", headers=headers)
    assert bad.status_code == 400
    assert bad.json()["code"] == "ORCH_INVALID_PAGE"


def test_instance_detail_tasks_gantt_and_variables_paths():
    def any_ok(q, f):
        return {"ok": True}

    fake = FakeDs(
        routes={
            ("GET", f"/projects/{PROJECT_CODE}/workflow-instances/101"): any_ok,
            ("GET", f"/projects/{PROJECT_CODE}/workflow-instances/101/tasks"): any_ok,
            ("GET", f"/projects/{PROJECT_CODE}/workflow-instances/101/view-gantt"): any_ok,
            ("GET", f"/projects/{PROJECT_CODE}/workflow-instances/101/view-variables"): any_ok,
        }
    )
    h = _harness(fake=fake)
    headers = {"token": h.token("owner")}

    for suffix in ("", "/tasks", "/gantt", "/variables"):
        body = h.client().get(f"{BASE}/workflow-instances/101{suffix}?project_id=1", headers=headers).json()
        assert body["code"] == 0, (suffix, body)

    # 宿主词形 gantt/variables → 海豚 view-gantt/view-variables。
    assert fake.calls[-1]["path"].endswith("/view-variables")
    assert fake.calls[-2]["path"].endswith("/view-gantt")

    missing = h.client().get(f"{BASE}/workflow-instances/101?project_id=999", headers=headers)
    assert missing.status_code == 404
    assert missing.json()["code"] == "ORCH_PROJECT_NOT_FOUND"


def test_task_instance_list_and_log_proxy():
    fake = FakeDs(
        routes={
            ("GET", f"/projects/{PROJECT_CODE}/task-instances"): lambda q, f: {
                "totalList": [{"id": 501, "name": "shell_a1", "state": "SUCCESS"}],
                "total": 1,
            },
            ("GET", "/log/detail"): lambda q, f: {"lineNum": 2, "message": "hello\nworld"},
        }
    )
    h = _harness(fake=fake)
    headers = {"token": h.token("owner")}

    body = h.client().get(
        f"{BASE}/task-instances?project_id=1&workflow_instance_id=101&task_name=shell_a1&task_code=188299446205952",
        headers=headers,
    ).json()
    assert body["code"] == 0, body
    assert body["data"]["list"][0]["id"] == 501
    query = fake.calls[-1]["query"]
    assert query["workflowInstanceId"] == 101
    assert query["taskName"] == "shell_a1"
    assert query["taskCode"] == "188299446205952"

    log = h.client().get(f"{BASE}/task-instances/501/log?project_id=1&skip_line_num=10&limit=50", headers=headers).json()
    assert log["code"] == 0, log
    # 海豚 {lineNum, message}（message 含分行）→ 前端契约 TaskInstanceLog[]。
    assert log["data"] == [
        {"lineNum": 2, "message": "hello"},
        {"lineNum": 3, "message": "world"},
    ]
    log_query = fake.calls[-1]["query"]
    assert fake.calls[-1]["path"] == "/log/detail"
    assert log_query == {"taskInstanceId": 501, "skipLineNum": 10, "limit": 50}

    bad = h.client().get(f"{BASE}/task-instances/501/log?project_id=1&limit=5000", headers=headers)
    assert bad.status_code == 400
    assert bad.json()["code"] == "ORCH_INVALID_LOG_RANGE"


def test_start_workflow_instance_maps_dry_run_and_start_params():
    fake = FakeDs(
        routes={("POST", f"/projects/{PROJECT_CODE}/executors/start-workflow-instance"): lambda q, f: "ok"}
    )
    h = _harness(fake=fake)
    headers = {"token": h.token("owner")}

    response = h.client().post(
        f"{BASE}/workflow-instances/start",
        json={
            "projectId": 1,
            "workflowDefinitionCode": 9001,
            "dryRun": True,
            "startParams": {"biz_date": "2026-10-30", "n": 1},
        },
        headers=headers,
    )
    assert response.json()["code"] == 0, response.text
    query = fake.calls[-1]["query"]
    assert query["workflowDefinitionCode"] == 9001
    assert query["dryRun"] == 1
    assert query["scheduleTime"] == ""
    assert query["failureStrategy"] == "CONTINUE"
    assert query["warningType"] == "NONE"
    assert json.loads(query["startParams"]) == [
        {"prop": "biz_date", "value": "2026-10-30"},
        {"prop": "n", "value": 1},
    ]

    bad_strategy = h.client().post(
        f"{BASE}/workflow-instances/start",
        json={"projectId": 1, "workflowDefinitionCode": 9001, "failureStrategy": "RETRY"},
        headers=headers,
    )
    assert bad_strategy.status_code == 400
    assert bad_strategy.json()["code"] == "ORCH_INVALID_FAILURE_STRATEGY"


def test_control_workflow_instance_whitelists_execute_types():
    fake = FakeDs(
        routes={("POST", f"/projects/{PROJECT_CODE}/executors/execute"): lambda q, f: "ok"}
    )
    h = _harness(fake=fake)
    headers = {"token": h.token("owner")}

    for execute_type in ("STOP", "PAUSE", "RECOVER_SUSPENDED_PROCESS", "START_FAILURE_TASK_PROCESS", "REPEAT_RUNNING"):
        body = h.client().post(
            f"{BASE}/workflow-instances/101/control",
            json={"projectId": 1, "executeType": execute_type},
            headers=headers,
        ).json()
        assert body["code"] == 0, (execute_type, body)
        assert fake.calls[-1]["query"] == {"workflowInstanceId": 101, "executeType": execute_type}

    rejected = h.client().post(
        f"{BASE}/workflow-instances/101/control",
        json={"projectId": 1, "executeType": "EXECUTE_TASK"},
        headers=headers,
    )
    assert rejected.status_code == 400
    assert rejected.json()["code"] == "ORCH_INVALID_EXECUTE_TYPE"

    viewer = _harness(fake=fake, users=(("viewer", Role.VIEWER),))
    denied = viewer.client().post(
        f"{BASE}/workflow-instances/101/control",
        json={"projectId": 1, "executeType": "STOP"},
        headers={"token": viewer.token("viewer")},
    )
    assert denied.status_code == 403


# -- §10.10 R9 部署运维：资源文件（海豚 ResourcesController 代理） -----------

def _resource_node(name, full_name, *, current_dir="", is_dir=False, children=None):
    """构造海豚 ``ResourceComponent``（``isDirctory`` 是 DS 源码的拼写）。"""
    return {
        "name": name,
        "currentDir": current_dir,
        "fullName": full_name,
        "isDirctory": is_dir,
        "type": "FILE",
        "children": children or [],
    }


def _resource_tree():
    return [
        _resource_node(
            "lib",
            "/lib",
            is_dir=True,
            children=[
                _resource_node("a.sh", "/lib/a.sh", current_dir="/lib"),
                _resource_node("b.sh", "/lib/b.sh", current_dir="/lib"),
            ],
        ),
        _resource_node(
            "conf",
            "/conf",
            is_dir=True,
            children=[_resource_node("c.sh", "/conf/c.sh", current_dir="/conf")],
        ),
    ]


def _resource_fake(nodes=None):
    return FakeDs(routes={("GET", "/resources/list"): lambda q, f: nodes if nodes is not None else _resource_tree()})


def test_resource_file_list_prunes_tree_by_owner_and_admin_sees_all():
    fake = _resource_fake()
    h = _harness(fake=fake)
    with h.factory() as session:
        access = OrchestrationResourceAccess(session)
        access.claim(KIND_RESOURCE_FILE, "/lib/a.sh", 2)
        access.claim(KIND_RESOURCE_FILE, "/lib/b.sh", 1)
        access.claim(KIND_RESOURCE_FILE, "/conf/c.sh", 1)
        session.commit()

    def children_of(body, name):
        for node in body["data"]:
            if node["name"] == name:
                return [child["name"] for child in node["children"]]
        return None

    mine = h.client().get(f"{BASE}/resources", headers={"token": h.token("owner")}).json()
    assert mine["code"] == 0, mine
    # 目录本身无归属 → 随可见子节点保留；a.sh 归属他人被裁剪。
    assert children_of(mine, "lib") == ["b.sh"]
    assert children_of(mine, "conf") == ["c.sh"]

    theirs = h.client().get(f"{BASE}/resources", headers={"token": h.token("other")}).json()
    assert children_of(theirs, "lib") == ["a.sh"]
    assert children_of(theirs, "conf") == []

    admin = h.client().get(f"{BASE}/resources", headers={"token": h.token("root")}).json()
    assert children_of(admin, "lib") == ["a.sh", "b.sh"]
    assert children_of(admin, "conf") == ["c.sh"]


def test_resource_file_upload_passthrough_and_claims_owner():
    nodes = _resource_tree() + [_resource_node("new.sh", "/lib/new.sh", current_dir="/lib")]
    fake = _resource_fake(nodes)
    fake.routes[("POST", "/resources")] = lambda q, f: {"code": 1}
    h = _harness(fake=fake)
    client = h.client()
    headers = {"token": h.token("owner")}

    response = client.post(
        f"{BASE}/resources",
        data={"name": "new.sh", "current_dir": "/lib"},
        files={"file": ("new.sh", b"#!/bin/sh\necho hi\n", "text/x-sh")},
        headers=headers,
    )
    assert response.json()["code"] == 0, response.text

    upload = [call for call in fake.calls if call["method"] == "POST" and call["path"] == "/resources"][0]
    assert upload["form"]["type"] == "FILE"
    assert upload["form"]["currentDir"] == "/lib"
    assert upload["files"]["file"][0] == "new.sh"
    assert upload["files"]["file"][1] == b"#!/bin/sh\necho hi\n"

    with h.factory() as session:
        assert OrchestrationResourceAccess(session).owner_of(KIND_RESOURCE_FILE, "/lib/new.sh") == 1


def test_resource_file_directory_requires_edit_definition():
    fake = _resource_fake()
    fake.routes[("POST", "/resources/directory")] = lambda q, f: {"code": 1}
    h = _harness(fake=fake, users=(("viewer", Role.VIEWER),))
    client = h.client()

    # 建目录走 /resources/directory，无 file 字段。
    denied = client.post(
        f"{BASE}/resources",
        data={"name": "lib"},
        headers={"token": h.token("viewer")},
    )
    assert denied.status_code == 403

    # 缺 name 的表单在鉴权之前被 FastAPI 拦为 422。
    missing = client.post(f"{BASE}/resources", data={}, headers={"token": h.token("viewer")})
    assert missing.status_code == 422


def test_resource_file_rename_migrates_ownership():
    nodes = _resource_tree() + [_resource_node("new.sh", "/lib/new.sh", current_dir="/lib")]
    fake = _resource_fake(nodes)
    fake.routes[("PUT", "/resources")] = lambda q, f: {"code": 1}
    h = _harness(fake=fake)
    with h.factory() as session:
        OrchestrationResourceAccess(session).claim(KIND_RESOURCE_FILE, "/lib/old.sh", 1)
        session.commit()

    client = h.client()
    response = client.put(
        f"{BASE}/resources",
        json={"fullName": "/lib/old.sh", "name": "new.sh"},
        headers={"token": h.token("owner")},
    )
    assert response.json()["code"] == 0, response.text
    rename = [call for call in fake.calls if call["method"] == "PUT" and call["path"] == "/resources"][0]
    assert rename["form"] == {"fullName": "/lib/old.sh", "name": "new.sh"}

    with h.factory() as session:
        access = OrchestrationResourceAccess(session)
        assert access.owner_of(KIND_RESOURCE_FILE, "/lib/old.sh") is None
        assert access.owner_of(KIND_RESOURCE_FILE, "/lib/new.sh") == 1

    forbidden = client.put(
        f"{BASE}/resources",
        json={"fullName": "/lib/new.sh", "name": "x.sh"},
        headers={"token": h.token("other")},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["code"] == "ORCH_RESOURCE_FILE_FORBIDDEN"


def test_resource_file_delete_releases_children_ownership():
    fake = _resource_fake()
    fake.routes[("DELETE", "/resources")] = lambda q, f: {"code": 1}
    h = _harness(fake=fake)
    with h.factory() as session:
        access = OrchestrationResourceAccess(session)
        access.claim(KIND_RESOURCE_FILE, "/lib", 1)
        access.claim(KIND_RESOURCE_FILE, "/lib/b.sh", 1)
        access.claim(KIND_RESOURCE_FILE, "/conf/c.sh", 1)
        session.commit()

    client = h.client()
    response = client.delete(f"{BASE}/resources?full_name=/lib", headers={"token": h.token("owner")})
    assert response.json()["code"] == 0, response.text
    assert fake.calls[-1]["query"] == {"fullName": "/lib"}

    with h.factory() as session:
        access = OrchestrationResourceAccess(session)
        # 海豚目录删除是递归的 → 目录与其下子资源归属一并释放。
        assert access.owner_of(KIND_RESOURCE_FILE, "/lib") is None
        assert access.owner_of(KIND_RESOURCE_FILE, "/lib/b.sh") is None
        # 前缀释放不越界：/conf 下的归属保持不变。
        assert access.owner_of(KIND_RESOURCE_FILE, "/conf/c.sh") == 1

    denied = client.delete(f"{BASE}/resources?full_name=/conf", headers={"token": h.token("other")})
    assert denied.status_code == 403


def test_resource_file_download_returns_binary_and_gates_visibility():
    fake = _resource_fake()
    fake.routes[("GET", "/resources/download")] = lambda q, f: b"#!/bin/sh\necho hi\n"
    # viewer 持 VIEW_ALL，但资源归属他人 → 仍不可下载。
    h = _harness(
        fake=fake,
        users=(("owner", Role.DEVELOPER), ("other", Role.DEVELOPER), ("viewer", Role.VIEWER)),
    )
    with h.factory() as session:
        access = OrchestrationResourceAccess(session)
        access.claim(KIND_RESOURCE_FILE, "/lib/a.sh", 1)
        access.claim(KIND_RESOURCE_FILE, "/lib/b.sh", 1)
        session.commit()

    client = h.client()
    ok = client.get(f"{BASE}/resources/download?full_name=/lib/a.sh", headers={"token": h.token("owner")})
    assert ok.status_code == 200
    assert ok.content == b"#!/bin/sh\necho hi\n"
    assert ok.headers["content-disposition"] == 'attachment; filename="a.sh"'

    forbidden = client.get(f"{BASE}/resources/download?full_name=/lib/b.sh", headers={"token": h.token("other")})
    assert forbidden.status_code == 403

    denied = client.get(f"{BASE}/resources/download?full_name=/lib/a.sh", headers={"token": h.token("viewer")})
    assert denied.status_code == 403
