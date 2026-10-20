"""R7 metrics API contract tests — frozen FE contract (metricsApi.ts / Task 5).

Key assertions: token-header auth, {code,msg,data} envelope, all-POST six
methods, MetricValue verbatim passthrough (A7 Step 1), kind filter, window
validation, snake_case keys.
"""

from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.identity.contracts import Role
from rebuild.identity.repository import UserRepository
from rebuild.project.repository import ProjectRepository


def _client():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="r7-metrics-test-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        user = UserRepository(session).create(username="dev", password="dev-pass", role=Role.DEVELOPER)
        ProjectRepository(session).create(name="metrics-test", description="", owner_id=user.id)
        session.commit()
    response = client.post("/api/v1/rebuild/login", json={"username": "dev", "password": "dev-pass"})
    headers = {"token": response.json()["data"]["token"]}
    return client, app, headers


WINDOW = {"project_id": 1, "from": "2026-10-01T00:00:00", "to": "2026-10-31T23:59:59", "offset": 0, "limit": 100}


def _seed(app):
    from datetime import datetime

    from rebuild.metrics.models import (
        LineageWritebackRecord,
        QualityRuleResultLinkRecord,
        TaskDataErrorSampleRecord,
        TaskDataStatSegmentRecord,
        TaskInstanceDataStatRecord,
        WorkflowResultStatRecord,
    )
    from rebuild.execution.models import WorkflowInstanceRecord
    from rebuild.workflow.models import WorkflowDefinitionRecord

    with app.state.session_factory() as session:
        session.add_all(
            (
                WorkflowDefinitionRecord(id=7, project_id=1, name="metrics-workflow", description="", current_version=None),
                WorkflowInstanceRecord(
                    id=501, workflow_id=7, workflow_version_id=1, instance_type="FORMAL", status="SUCCEEDED",
                    trigger_type="MANUAL",
                ),
                WorkflowResultStatRecord(
                    workflow_id=7, run_date=datetime(2026, 10, 15).date(),
                    success_count=10, failure_count=2, skipped_count=1, retry_count=3,
                ),
                TaskInstanceDataStatRecord(
                    instance_id=501, task_id="extract",
                    rows_in='{"value": 0, "known": false, "estimated": false}',
                    rows_out='{"value": 420, "known": true, "estimated": false}',
                    error_rows='{"value": 12, "known": true, "estimated": true}',
                    elapsed_ms='{"value": 9900, "known": true, "estimated": false}',
                ),
                TaskDataStatSegmentRecord(
                    instance_id=501, task_id="extract", segment_key="region=east",
                    row_count='{"value": 210, "known": true, "estimated": false}',
                ),
                TaskDataErrorSampleRecord(
                    instance_id=501, task_id="extract", error_type="NOT_NULL_VIOLATION",
                    sample_data='{"col": "email", "row": 17}', captured_at=datetime(2026, 10, 15, 12, 0, 0),
                ),
                QualityRuleResultLinkRecord(
                    project_id=1, rule_id=3, rule_name="email_not_null", stat_ref="task_instance_data_stat:501",
                    alert_sent=True, result_at=datetime(2026, 10, 15, 12, 5, 0),
                ),
                LineageWritebackRecord(
                    project_id=1, run_id="9001", run_kind="sql", source_entity="ods.orders",
                    target_entity="dws.orders_daily", writeback_at=datetime(2026, 10, 15, 12, 10, 0),
                ),
            )
        )
        session.commit()


def test_all_six_endpoints_contract_shape_and_passthrough():
    client, app, headers = _client()
    try:
        _seed(app)
        cases = [
            ("/api/v1/rebuild/metrics/workflow-result-stats", lambda r: (
                r[0]["workflow_id"] == 7 and r[0]["run_date"] == "2026-10-15"
                and r[0]["retry_count"] == 3 and r[0]["failure_count"] == 2
            )),
            ("/api/v1/rebuild/metrics/task-instance-data-stats", lambda r: (
                r[0]["instance_id"] == 501 and r[0]["rows_in"] == {"value": 0, "known": False, "estimated": False}
                and r[0]["error_rows"]["estimated"] is True and r[0]["task_id"] == "extract"
            )),
            ("/api/v1/rebuild/metrics/task-data-stat-segments", lambda r: (
                r[0]["segment_key"] == "region=east" and r[0]["row_count"]["value"] == 210
            )),
            ("/api/v1/rebuild/metrics/task-data-error-samples", lambda r: (
                r[0]["error_type"] == "NOT_NULL_VIOLATION" and r[0]["captured_at"].startswith("2026-10-15T12:00:00")
            )),
            ("/api/v1/rebuild/metrics/quality-rule-links", lambda r: (
                r[0]["rule_id"] == 3 and r[0]["stat_ref"] == "task_instance_data_stat:501"
                and r[0]["alert_sent"] is True
            )),
            ("/api/v1/rebuild/metrics/lineage-writebacks", lambda r: (
                r[0]["run_id"] == "9001" and r[0]["run_kind"] == "sql"
                and r[0]["target_entity"] == "dws.orders_daily"
            )),
        ]
        for path, check in cases:
            response = client.post(path, headers=headers, json=WINDOW)
            assert response.status_code == 200, path
            body = response.json()
            assert body["code"] == 0 and body["msg"] == "success", path
            assert check(body["data"]), path
    finally:
        client.__exit__(None, None, None)


def test_lineage_kind_filter_and_validation():
    client, app, headers = _client()
    try:
        _seed(app)
        sync_only = client.post(
            "/api/v1/rebuild/metrics/lineage-writebacks", headers=headers, json={**WINDOW, "kind": "sync"}
        )
        assert sync_only.status_code == 200 and sync_only.json()["data"] == []

        bad_kind = client.post(
            "/api/v1/rebuild/metrics/lineage-writebacks", headers=headers, json={**WINDOW, "kind": "nonsense"}
        )
        assert bad_kind.status_code == 400 and bad_kind.json()["code"] == 4001

        inverted = client.post(
            "/api/v1/rebuild/metrics/lineage-writebacks",
            headers=headers,
            json={**WINDOW, "from": "2026-11-01T00:00:00", "to": "2026-10-01T00:00:00"},
        )
        assert inverted.status_code == 400 and inverted.json()["code"] == 4001
    finally:
        client.__exit__(None, None, None)


def test_anonymous_is_401_and_bearer_fallback():
    client, app, headers = _client()
    try:
        anonymous = client.post("/api/v1/rebuild/metrics/workflow-result-stats", json=WINDOW)
        assert anonymous.status_code == 401 and anonymous.json()["code"] == 1001
        bearer = client.post(
            "/api/v1/rebuild/metrics/workflow-result-stats",
            headers={"Authorization": f"Bearer {headers['token']}"},
            json=WINDOW,
        )
        assert bearer.status_code == 200
        empty = bearer.json()["data"]
        assert empty == []
    finally:
        client.__exit__(None, None, None)


def test_metrics_endpoints_require_project_access():
    client, app, headers = _client()
    try:
        from rebuild.project.models import ProjectRecord

        with app.state.session_factory() as session:
            foreign = ProjectRecord(name="foreign", description="", owner_id=999)
            session.add(foreign)
            session.commit()
            foreign_id = foreign.id
        response = client.post(
            "/api/v1/rebuild/metrics/workflow-result-stats",
            headers=headers,
            json={**WINDOW, "project_id": foreign_id},
        )
        assert response.status_code == 403 and response.json()["code"] == 1003
    finally:
        client.__exit__(None, None, None)
