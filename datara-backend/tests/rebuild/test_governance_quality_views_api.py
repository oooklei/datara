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


def test_quality_batch_b_write_actions_persist_and_are_visible():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="quality-write-secret")
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            developer = UserRepository(session).create(username="quality-writer", password="dev-pass", role=Role.DEVELOPER)
            project = ProjectRecord(name="quality-write-project", description="", owner_id=developer.id)
            session.add(project)
            session.flush()
            exception = QualityExceptionRecord(
                project_id=project.id,
                target="orders.amount",
                sample_sql="select * from orders where amount < 0",
                hit_count=3,
                status="open",
            )
            session.add(exception)
            session.commit()
            project_id, exception_id = project.id, exception.id

        login = client.post("/api/v1/rebuild/login", json={"username": "quality-writer", "password": "dev-pass"})
        headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}

        handled = client.patch(
            f"/api/v1/rebuild/governance/projects/{project_id}/quality-exceptions/{exception_id}",
            headers=headers,
            json={"status": "resolved", "fix_note": "已回填负值订单"},
        )
        assert handled.status_code == 200
        assert handled.json()["data"]["status"] == "resolved"
        assert handled.json()["data"]["handled_by"] == "quality-writer"
        assert handled.json()["data"]["handled_at"]

        report = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/quality-reports",
            headers=headers,
            json={"title": "质量日报", "scope": "project", "period": "daily"},
        )
        assert report.status_code == 201
        assert report.json()["data"]["content"] == {
            "run_count": 0,
            "checked_rows": 0,
            "success_rows": 0,
            "failed_rows": 0,
            "skipped_rows": 0,
        }

        alarm = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/quality-alarm-policies",
            headers=headers,
            json={
                "name": "失败行告警",
                "scope": "project",
                "metric": "failed_rows",
                "operator": ">",
                "threshold": 0,
                "enabled": True,
            },
        )
        assert alarm.status_code == 201
        alarm_id = alarm.json()["data"]["id"]
        disabled = client.patch(
            f"/api/v1/rebuild/governance/projects/{project_id}/quality-alarm-policies/{alarm_id}/enabled",
            headers=headers,
            json={"enabled": False},
        )
        assert disabled.status_code == 200
        assert disabled.json()["data"]["enabled"] is False

        reports = client.get(
            f"/api/v1/rebuild/governance/projects/{project_id}/quality-reports", headers=headers
        ).json()["data"]["list"]
        alarms = client.get(
            f"/api/v1/rebuild/governance/projects/{project_id}/quality-alarm-policies", headers=headers
        ).json()["data"]["list"]
        assert reports[0]["title"] == "质量日报"
        assert alarms[0]["name"] == "失败行告警"
