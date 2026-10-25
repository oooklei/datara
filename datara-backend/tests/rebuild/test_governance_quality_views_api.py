import json

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.governance.models import QualityAlarmPolicyRecord, QualityExceptionRecord, QualityReportRecord
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.project.models import ProjectRecord


def test_quality_exception_report_and_alarm_views_are_project_scoped():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="quality-view-secret")
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            developer = UserRepository(session).create(username="quality-dev", password="dev-pass", role=Role.DEVELOPER)
            project = ProjectRecord(name="quality-project", description="", owner_id=developer.id)
            session.add(project)
            session.flush()
            session.add_all([
                QualityExceptionRecord(project_id=project.id, target="orders", sample_sql="select 1", hit_count=2, status="open"),
                QualityReportRecord(project_id=project.id, title="日报", scope="project", period="daily", content_json=json.dumps({"score": 98}), created_by="quality-dev"),
                QualityAlarmPolicyRecord(project_id=project.id, name="失败率", scope="project", metric="failure_rate", operator=">", threshold=5, enabled=True),
            ])
            session.commit()
            project_id = project.id

        login = client.post("/api/v1/rebuild/login", json={"username": "quality-dev", "password": "dev-pass"})
        headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}

        exceptions = client.get(f"/api/v1/rebuild/governance/projects/{project_id}/quality-exceptions", headers=headers)
        reports = client.get(f"/api/v1/rebuild/governance/projects/{project_id}/quality-reports", headers=headers)
        alarms = client.get(f"/api/v1/rebuild/governance/projects/{project_id}/quality-alarm-policies", headers=headers)

        assert exceptions.status_code == reports.status_code == alarms.status_code == 200
        assert exceptions.json()["data"]["list"][0]["hit_count"] == 2
        assert reports.json()["data"]["list"][0]["content"] == {"score": 98}
        assert alarms.json()["data"]["list"][0]["metric"] == "failure_rate"
