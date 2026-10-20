"""9-01 rebuild schedule endpoint, policy, envelope, and permission tests."""

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.models import ProjectMemberRecord
from rebuild.identity.repository import UserRepository
from rebuild.project.models import ProjectRecord


def fixture():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="schedule-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        dev = UserRepository(session).create(username="dev", password="dev-pass", role=Role.DEVELOPER)
        viewer = UserRepository(session).create(username="viewer", password="viewer-pass", role=Role.VIEWER)
        project = ProjectRecord(name="schedule-project", description="", owner_id=dev.id)
        session.add(project); session.commit()
        session.add(ProjectMemberRecord(project_id=project.id, user_id=viewer.id, role="viewer")); session.commit()
    headers = {}
    for user in ("dev", "viewer"):
        token = client.post("/api/v1/rebuild/login", json={"username": user, "password": f"{user}-pass"}).json()["data"]["token"]
        headers[user] = {"Authorization": f"Bearer {token}"}
    created = client.post("/api/v1/rebuild/workflows", headers=headers["dev"], json={"project_id": project.id, "name": "scheduled"})
    return client, project.id, created.json()["data"]["definition_id"], headers


def schedule_body(**overrides):
    body = {"name": "daily", "crontab": "0 0 1 * * *", "misfirePolicy": "FIRE_ONCE", "concurrencyPolicy": "ALLOW", "maxRunningInstances": 1, "timezone": "Asia/Shanghai"}
    body.update(overrides)
    return body


def test_seven_endpoints_and_policy_payload():
    client, project_id, workflow_id, headers = fixture()
    try:
        preview = client.post("/api/v1/rebuild/crontab-preview", headers=headers["dev"], json={"projectId": project_id, "crontab": "0 0 1 * * *", "timezone": "Asia/Shanghai"})
        assert preview.status_code == 200 and len(preview.json()["data"]["nextFireTimes"]) == 3
        created = client.post(f"/api/v1/rebuild/workflow-definitions/{workflow_id}/schedules", headers=headers["dev"], json=schedule_body(concurrencyPolicy="QUEUE", maxRunningInstances=2))
        assert created.status_code == 200 and created.json()["data"]["state"] == "offline"
        row = created.json()["data"]; schedule_id = row["id"]
        assert row["misfirePolicy"] == "FIRE_ONCE" and row["concurrencyPolicy"] == "QUEUE" and row["maxRunningInstances"] == 2
        listing = client.get(f"/api/v1/rebuild/workflow-definitions/{workflow_id}/schedules", headers=headers["viewer"])
        assert listing.status_code == 200 and [item["id"] for item in listing.json()["data"]] == [schedule_id]
        updated = client.put(f"/api/v1/rebuild/schedules/{schedule_id}", headers=headers["dev"], json=schedule_body(misfirePolicy="SKIP", timezone="UTC"))
        assert updated.json()["data"]["misfirePolicy"] == "SKIP" and updated.json()["data"]["timezone"] == "UTC"
        online = client.post(f"/api/v1/rebuild/schedules/{schedule_id}/online", headers=headers["dev"])
        assert online.json()["data"]["state"] == "online"
        offline = client.post(f"/api/v1/rebuild/schedules/{schedule_id}/offline", headers=headers["dev"])
        assert offline.json()["data"]["state"] == "offline"
        deleted = client.delete(f"/api/v1/rebuild/schedules/{schedule_id}", headers=headers["dev"])
        assert deleted.json() == {"code": 0, "msg": "success", "data": True}
    finally:
        client.__exit__(None, None, None)


def test_auth_permissions_and_policy_validation():
    client, project_id, workflow_id, headers = fixture()
    try:
        anonymous = client.get(f"/api/v1/rebuild/workflow-definitions/{workflow_id}/schedules")
        assert anonymous.status_code == 401 and anonymous.json()["code"] == 1001
        denied = client.post(f"/api/v1/rebuild/workflow-definitions/{workflow_id}/schedules", headers=headers["viewer"], json=schedule_body())
        assert denied.status_code == 403 and denied.json()["code"] == 1003
        invalid = client.post(f"/api/v1/rebuild/workflow-definitions/{workflow_id}/schedules", headers=headers["dev"], json=schedule_body(maxRunningInstances=0))
        assert invalid.status_code == 400 and invalid.json()["code"] == 4001 and invalid.json()["data"] is None
        preview_denied = client.post("/api/v1/rebuild/crontab-preview", headers=headers["viewer"], json={"projectId": project_id, "crontab": "0 0 1 * * *"})
        assert preview_denied.status_code == 403
    finally:
        client.__exit__(None, None, None)
