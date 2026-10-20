"""R5-B rb 域 API 挂载验收测试（P2-3 v3 阶段 A）。

覆盖：
- 4 端点挂载后可达：validate-policy / preview-impact / confirm / execution-records
- token 鉴权：无 token 401 + code 1001
- #22 validatePolicy：真实 PolicySnapshotService 全链路 RbEnvelope
- #23 previewImpact：真实 ImpactSnapshotService（无 analyzer → unknown_reasons）
- #24/#25 阶段 D 未交付 → 502 + CAPABILITY_UNSUPPORTED fail-closed
- #21 getDefinition 不在本 router 重复挂载（v3 §1.2 复用 R5-A shared read）
"""

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.project.repository import ProjectRepository
from rebuild.datasource.models import ProjectDatasourceRecord

BASE = "/api/v1/rebuild/sql-ide-ddl"

REQUEST = {
    "datasourceId": 101,
    "objectRef": {"database": "mydb", "schema": "public", "kind": "table", "name": "users"},
    "sourceVersion": "etag-abc123",
    "nextDdlText": "ALTER TABLE users ADD COLUMN email VARCHAR(255);",
}


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="r5b-ddl-test-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        user = UserRepository(session).create(username="dev", password="dev-pass", role=Role.DEVELOPER)
        project = ProjectRepository(session).create(name="rb-test", description="", owner_id=user.id)
        session.add(ProjectDatasourceRecord(
            id=101, project_id=project.id, name="test", kind="mysql", host="localhost", port=3306,
            database_name="test", username="test", password="",
        ))
        session.commit()
    response = client.post("/api/v1/rebuild/login", json={"username": "dev", "password": "dev-pass"})
    return client, {"token": response.json()["data"]["token"]}


def test_four_endpoints_mounted_and_get_definition_not_duplicated():
    """行为断言：路由匹配后返回 401（无 token 被守卫拦截）或 422（body 校验），

    两者都证明路由已挂载；404 = 未挂载。
    注：本仓 FastAPI 0.141/starlette 1.6 下 include_router 路由不出现在
    app.routes 内省中，故不使用路径集合断言。
    """
    client, _ = _client()
    try:
        for suffix in ("/validate-policy", "/preview-impact", "/confirm", "/execution-records"):
            response = client.post(f"{BASE}{suffix}", json={})
            assert response.status_code in (401, 422), f"{suffix} not mounted: {response.status_code}"
        # v3 §1.2：#21 复用 R5-A shared read，rb router 不重复挂载（404 = 不存在）
        response = client.post(f"{BASE}/definition", json={})
        assert response.status_code == 404
    finally:
        client.__exit__(None, None, None)


def test_endpoints_reject_missing_token():
    client, _ = _client()
    try:
        response = client.post(f"{BASE}/validate-policy", json=REQUEST)
        assert response.status_code == 401
        assert response.json()["code"] == 1001
    finally:
        client.__exit__(None, None, None)


def test_project_member_cannot_access_another_projects_rb_endpoints():
    client, headers = _client()
    try:
        with client.app.state.session_factory() as session:
            from rebuild.identity.models import UserRecord
            from rebuild.project.models import ProjectRecord
            from rebuild.datasource.models import ProjectDatasourceRecord

            user = session.query(UserRecord).filter_by(username="dev").one()
            other = ProjectRecord(name="other", description="", owner_id=user.id + 99)
            session.add(other)
            session.flush()
            session.add(ProjectDatasourceRecord(
                id=202, project_id=other.id, name="other", kind="mysql", host="localhost", port=3306,
                database_name="test", username="test", password="",
            ))
            session.commit()
        response = client.post(f"{BASE}/validate-policy", json={**REQUEST, "datasourceId": 202}, headers=headers)
        assert response.status_code == 403
        assert response.json()["code"] == 1003
    finally:
        client.__exit__(None, None, None)


def test_validate_policy_success_envelope():
    client, headers = _client()
    try:
        response = client.post(f"{BASE}/validate-policy", json=REQUEST, headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        assert body["msg"] == "ok"
        data = body["data"]
        assert data["snapshotId"]
        assert isinstance(data["findings"], list)
        assert isinstance(data["blocked"], bool)
    finally:
        client.__exit__(None, None, None)


def test_preview_impact_success_envelope():
    client, headers = _client()
    try:
        response = client.post(f"{BASE}/preview-impact", json=REQUEST, headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["snapshotId"]
        assert data["impacts"] == []
        assert data["unknownReasons"] == ["lineage_unavailable"]
    finally:
        client.__exit__(None, None, None)


def test_submit_confirm_fails_closed_until_stage_d():
    client, headers = _client()
    try:
        response = client.post(
            f"{BASE}/confirm",
            json={**REQUEST, "policySnapshotId": "uuid-x", "impactSnapshotId": "uuid-y", "confirmPhrase": "PHRASE"},
            headers=headers,
        )
        assert response.status_code == 502
        body = response.json()
        assert body["data"]["errorCode"] == "CAPABILITY_UNSUPPORTED"
    finally:
        client.__exit__(None, None, None)


def test_list_execution_records_fails_closed_until_stage_d():
    client, headers = _client()
    try:
        response = client.post(
            f"{BASE}/execution-records",
            json={"datasourceId": 101, "page": 1, "pageSize": 50},
            headers=headers,
        )
        assert response.status_code == 502
        body = response.json()
        assert body["data"]["errorCode"] == "CAPABILITY_UNSUPPORTED"
    finally:
        client.__exit__(None, None, None)
