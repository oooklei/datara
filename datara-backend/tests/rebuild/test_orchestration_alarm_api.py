"""§10.10 R6 告警桥接测试。

覆盖：datara 项目级告警规则 CRUD 校验（触发条件 / 通道 / 超时必填 / 唯一键）、
触发记录查询、内部扫描端点的三重守卫，以及 ``dispatch_alarm_scan`` 对海豚
实例 FAILURE 的感知 → 命中规则 → 写触发记录（审计 D2）。
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
from rebuild.orchestration.alarm import (
    CHANNEL_SYSTEM,
    TRIGGER_FAILURE,
    TRIGGER_TIMEOUT,
    OrchestrationAlarmRecord,
    OrchestrationAlarmRepository,
    OrchestrationAlarmRuleRecord,
    dispatch_alarm_scan,
)
from rebuild.orchestration.api import build_orchestration_router
from rebuild.orchestration.ds_client import DsClientError
from rebuild.project.models import ProjectRecord
from rebuild.sec.models import SecAccessLogRecord

BASE = "/api/v1/rebuild/orchestration"
INTERNAL = "/internal/alarm/dispatch"
INTERNAL_TOKEN = "alarm-internal-test-token"


class FakeDs:
    """最小假海豚：只实现 ensure_project 与 workflow-instances 列表。"""

    def __init__(self, *, project_code=123456, instances=None, fail=False):
        self.project_code = project_code
        self.instances = instances or []
        self.fail = fail
        self.calls = []

    def call(self, method, path, *, query=None, form=None, files=None):
        self.calls.append({"method": method, "path": path, "query": query or {}})
        if self.fail:
            raise DsClientError("DS_API_ERROR", "dolphinscheduler unavailable", 502)
        return {"totalList": list(self.instances), "total": len(self.instances)}

    def ensure_project(self, name, description=""):
        return {"code": self.project_code, "name": name}


class Harness:
    def __init__(self, fake, *, users=(), project=True):
        self.fake = fake
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
                OrchestrationAlarmRuleRecord.__table__,
                OrchestrationAlarmRecord.__table__,
                SecAccessLogRecord.__table__,
            ],
        )
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.tokens = set()
        self.token_service = TokenService(secret="alarm-test-secret")
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

    def client(self):
        app = FastAPI()
        app.include_router(
            build_orchestration_router(
                self.factory,
                self.token_service,
                self.tokens,
                lambda session, project_id, user, permission: None,
                ds_client_factory=lambda: self.fake,
            )
        )
        return TestClient(app, client=("127.0.0.1", 50000))


def _harness(fake, *, users=(("owner", Role.DEVELOPER), ("root", Role.ADMIN))):
    return Harness(fake, users=users)


# -- 规则 CRUD ---------------------------------------------------------------

def test_alarm_rule_crud_roundtrip_and_list():
    harness = _harness(FakeDs())
    client = harness.client()
    token = harness.token("owner")
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        f"{BASE}/alarm-rules",
        json={"projectId": 1, "workflowDefinitionCode": 0, "trigger": "failure", "channel": "system"},
        headers=headers,
    )
    assert created.status_code == 200, created.text
    rule = created.json()["data"]
    assert rule["id"] > 0
    assert rule["trigger"] == TRIGGER_FAILURE
    assert rule["channel"] == CHANNEL_SYSTEM
    assert rule["enabled"] is True
    rule_id = rule["id"]

    listed = client.get(f"{BASE}/alarm-rules?project_id=1", headers=headers)
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()["data"]] == [rule_id]

    updated = client.put(
        f"{BASE}/alarm-rules/{rule_id}",
        json={"channel": "email", "enabled": False},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()["data"]
    assert body["channel"] == "email"
    assert body["enabled"] is False
    assert body["trigger"] == TRIGGER_FAILURE  # 未提交字段保持不变

    removed = client.delete(f"{BASE}/alarm-rules/{rule_id}", headers=headers)
    assert removed.status_code == 200
    assert client.get(f"{BASE}/alarm-rules?project_id=1", headers=headers).json()["data"] == []


def test_alarm_rule_rejects_invalid_trigger_channel_and_duplicate():
    harness = _harness(FakeDs())
    client = harness.client()
    headers = {"Authorization": f"Bearer {harness.token('owner')}"}

    invalid_trigger = client.post(
        f"{BASE}/alarm-rules",
        json={"projectId": 1, "trigger": "retry_exhausted", "channel": "system"},
        headers=headers,
    )
    assert invalid_trigger.status_code == 400
    assert invalid_trigger.json()["code"] == "ORCH_ALARM_TRIGGER_INVALID"

    invalid_channel = client.post(
        f"{BASE}/alarm-rules",
        json={"projectId": 1, "trigger": "failure", "channel": "sms"},
        headers=headers,
    )
    assert invalid_channel.status_code == 400
    assert invalid_channel.json()["code"] == "ORCH_ALARM_CHANNEL_INVALID"

    missing_timeout = client.post(
        f"{BASE}/alarm-rules",
        json={"projectId": 1, "trigger": "timeout", "channel": "system"},
        headers=headers,
    )
    assert missing_timeout.status_code == 422
    assert missing_timeout.json()["code"] == "ORCH_ALARM_TIMEOUT_REQUIRED"

    assert client.post(
        f"{BASE}/alarm-rules",
        json={"projectId": 1, "trigger": "failure", "channel": "system"},
        headers=headers,
    ).status_code == 200
    duplicate = client.post(
        f"{BASE}/alarm-rules",
        json={"projectId": 1, "trigger": "failure", "channel": "webhook"},
        headers=headers,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "ORCH_ALARM_RULE_DUPLICATE"


def test_alarm_rule_requires_token_and_write_permission():
    harness = _harness(FakeDs())
    client = harness.client()

    assert client.post(
        f"{BASE}/alarm-rules",
        json={"projectId": 1, "trigger": "failure", "channel": "system"},
    ).status_code == 401

    viewer = Harness(FakeDs(), users=(("viewer", Role.VIEWER),))
    viewer_client = viewer.client()
    viewer_headers = {"Authorization": f"Bearer {viewer.token('viewer')}"}
    denied = viewer_client.post(
        f"{BASE}/alarm-rules",
        json={"projectId": 1, "trigger": "failure", "channel": "system"},
        headers=viewer_headers,
    )
    assert denied.status_code == 403
    assert denied.json()["code"] == "1003"

    # VIEWER 可读规则与触发记录
    assert viewer_client.get(f"{BASE}/alarm-rules?project_id=1", headers=viewer_headers).status_code == 200
    assert viewer_client.get(f"{BASE}/alarm-records?project_id=1", headers=viewer_headers).status_code == 200


# -- 内部扫描端点 -----------------------------------------------------------

def test_internal_alarm_dispatch_requires_token(monkeypatch):
    monkeypatch.delenv("DATARA_INTERNAL_TOKEN", raising=False)
    harness = _harness(FakeDs())
    client = harness.client()
    assert client.post(INTERNAL).status_code == 503

    monkeypatch.setenv("DATARA_INTERNAL_TOKEN", INTERNAL_TOKEN)
    assert client.post(INTERNAL).status_code == 401
    assert client.post(INTERNAL, headers={"X-Datara-Internal-Token": "wrong"}).status_code == 401


def test_internal_alarm_dispatch_scans_and_writes_records():
    monkeypatch_env = pytest.MonkeyPatch()
    monkeypatch_env.setenv("DATARA_INTERNAL_TOKEN", INTERNAL_TOKEN)
    try:
        instance = {
            "id": 9001,
            "name": "demo-wf",
            "workflowDefinitionCode": 555,
            "state": "FAILURE",
            "startTime": "2026-10-30 10:00:00",
        }
        fake = FakeDs(instances=[instance])
        harness = _harness(fake)
        with harness.factory() as session:
            OrchestrationAlarmRepository(session).create_rule(
                project_id=1,
                workflow_definition_code=0,
                trigger=TRIGGER_FAILURE,
                channel=CHANNEL_SYSTEM,
                timeout_minutes=None,
                owner_id=1,
            )
            session.commit()

        client = harness.client()
        response = client.post(
            INTERNAL,
            headers={"X-Datara-Internal-Token": INTERNAL_TOKEN, "X-Datara-User": "ds-master"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"] == {"rules": 1, "sent": 1, "failed": 0}

        records = client.get(
            f"{BASE}/alarm-records?project_id=1",
            headers={"Authorization": f"Bearer {harness.token('owner')}"},
        ).json()["data"]
        assert len(records) == 1
        assert records[0]["instanceId"] == 9001
        assert records[0]["trigger"] == TRIGGER_FAILURE
        assert records[0]["state"] == "sent"

        # 幂等：同一规则对同一实例只发一次
        again = client.post(
            INTERNAL,
            headers={"X-Datara-Internal-Token": INTERNAL_TOKEN, "X-Datara-User": "ds-master"},
        )
        assert again.json()["data"] == {"rules": 0, "sent": 0, "failed": 0}
        assert len(fake.calls) == 2  # 第二次扫描仍只查一次列表
    finally:
        monkeypatch_env.undo()


def test_dispatch_alarm_scan_tolerates_project_failure():
    harness = _harness(FakeDs(fail=True))
    with harness.factory() as session:
        OrchestrationAlarmRepository(session).create_rule(
            project_id=1,
            workflow_definition_code=0,
            trigger=TRIGGER_FAILURE,
            channel=CHANNEL_SYSTEM,
            timeout_minutes=None,
            owner_id=1,
        )
        session.commit()

    counts = dispatch_alarm_scan(harness.factory, lambda: harness.fake)
    assert counts == {"rules": 0, "sent": 0, "failed": 0}
