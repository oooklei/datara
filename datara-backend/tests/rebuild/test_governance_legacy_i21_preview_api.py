from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import event, select

from rebuild.api.app import create_app
from rebuild.governance.legacy_source_reader import I21_SOURCE_COLUMNS
from rebuild.governance.migrations import MigrationRunner, R3_GOVERNANCE_MIGRATIONS
from rebuild.governance.models import (
    QualityReportRecord,
    QualityRuleDefinitionRecord,
    QualityTaskRecord,
    QualityTaskRuleRecord,
)


def _row(table, **values):
    columns = I21_SOURCE_COLUMNS[table][1]
    row = {column: None for column in columns}
    row.update(values)
    return {column: row[column] for column in columns}


def _snapshot(*, populated=False):
    rows = {table: [] for table in I21_SOURCE_COLUMNS}
    if populated:
        rows["t_qc_rule"].append(
            _row(
                "t_qc_rule",
                id=1,
                name="private quality rule",
                dim="完整性",
                rule_type="not_null",
                ds_id=7,
                db_name="ods",
                table_name="orders",
                column_name="order_id",
                params_json={"column": "private_col"},
                threshold=0,
                level="warning",
                status="enabled",
                owner="private owner",
                remark="private remark",
                create_time="2026-01-01T00:00:00",
            )
        )
        rows["t_qc_task"].append(
            _row(
                "t_qc_task",
                id=2,
                name="private task",
                crontab="0 0 * * * *",
                enabled=True,
                rule_ids=[1],
                status="idle",
                last_run_at="2026-01-02T00:00:00",
                last_result="success",
            )
        )
        rows["t_qc_run"].append(
            _row(
                "t_qc_run",
                id=3,
                task_id=2,
                trigger="manual",
                started_at="2026-01-02T00:00:00",
                finished_at="2026-01-02T00:01:00",
                result="success",
                score=99,
                stats_json={"checked_rows": 5},
            )
        )
        rows["t_qc_exception"].append(
            _row(
                "t_qc_exception",
                id=4,
                run_id=3,
                rule_id=1,
                task_id=2,
                target="ods.orders.order_id",
                sample_sql="private sample sql",
                hit_count=1,
                status="open",
                fix_note="private fix note",
                handled_at="2026-01-02T01:00:00",
            )
        )
        rows["t_qc_report"].append(
            _row(
                "t_qc_report",
                id=5,
                title="private report title",
                scope="orders",
                period="2026-01-02",
                content_json={"private": "report payload"},
                created_by="private reporter",
                create_time="2026-01-02T01:00:00",
            )
        )
        rows["t_qc_alarm_policy"].append(
            _row(
                "t_qc_alarm_policy",
                id=6,
                name="private alarm",
                scope="orders",
                metric="score",
                op="<",
                threshold=90,
                enabled=True,
                last_fired_at="2026-01-02T02:00:00",
            )
        )
    rows = {table: tuple(values) for table, values in rows.items()}
    return SimpleNamespace(
        schema="datara_meta",
        rows=rows,
        counts={table: len(values) for table, values in rows.items()},
        captured_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        digest="c" * 64,
    )


class _Reader:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.engine = None
        self.calls = 0

    def read_snapshot(self):
        self.calls += 1
        return self.snapshot


def _client(snapshot):
    reader = _Reader(snapshot)
    app = create_app(
        "sqlite+pysqlite:///:memory:",
        token_secret="legacy-i21-preview-test-secret",
        validation_key="legacy-i21-preview-validation-key",
        legacy_i21_source_reader_factory=lambda: reader,
    )
    client = TestClient(app)
    client.__enter__()
    MigrationRunner(app.state.session_factory.kw["bind"], R3_GOVERNANCE_MIGRATIONS).apply()
    token = client.post(
        "/api/v1/rebuild/validation-token",
        headers={"X-Backend-Validation-Key": "legacy-i21-preview-validation-key"},
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    project = client.post("/api/v1/rebuild/projects", headers=headers, json={"name": "I21 preview"})
    assert project.status_code == 200
    return client, app, reader, headers, project.json()["data"]["id"]


def test_i21_mapping_preview_is_project_scoped_payload_free_and_read_only():
    client, app, reader, headers, project_id = _client(_snapshot(populated=True))
    writes = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().split(maxsplit=1)[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
            writes.append(statement)

    event.listen(app.state.session_factory.kw["bind"], "before_cursor_execute", capture)
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i21/mapping-preview",
            headers=headers,
        )
        with app.state.session_factory() as session:
            target_reports = session.scalars(select(QualityReportRecord)).all()
    finally:
        event.remove(app.state.session_factory.kw["bind"], "before_cursor_execute", capture)
        client.__exit__(None, None, None)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["project_id"] == project_id
    assert data["source"]["schema"] == "datara_meta"
    assert data["source"]["counts"] == {table: 1 for table in I21_SOURCE_COLUMNS}
    assert data["target"]["captured_at"].endswith("+08:00")
    assert data["preview"]["counts"] == {
        "new_identity_candidate": 6,
        "target_identity_match": 0,
        "blocked": 0,
    }
    assert data["preview"]["parity_verified"] is False
    assert data["preview"]["import_enabled"] is False
    for private_value in (
        "private quality rule",
        "private sample sql",
        "private fix note",
        "report payload",
        "private reporter",
    ):
        assert private_value not in response.text
    assert target_reports == []
    assert writes == []
    assert reader.calls == 1


def test_i21_mapping_preview_rejects_unauthenticated_request_before_source_read():
    client, _app, reader, _headers, project_id = _client(_snapshot())
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i21/mapping-preview"
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 401
    assert reader.calls == 0


def test_i21_mapping_preview_rejects_missing_project_before_source_read():
    client, _app, reader, headers, _project_id = _client(_snapshot())
    try:
        response = client.post(
            "/api/v1/rebuild/governance/projects/999999/legacy/i21/mapping-preview",
            headers=headers,
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 404
    assert reader.calls == 0


def test_i21_target_provenance_match_is_counted_for_the_selected_project():
    client, app, reader, headers, project_id = _client(_snapshot(populated=True))
    try:
        with app.state.session_factory() as session:
            session.add(
                QualityReportRecord(
                    project_id=project_id,
                    title="target report",
                    scope="",
                    period="",
                    content_json="{}",
                    created_by="",
                    source_system="datara_meta",
                    source_table="t_qc_report",
                    source_id="5",
                )
            )
            session.commit()
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i21/mapping-preview",
            headers=headers,
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    preview = response.json()["data"]["preview"]
    report_entry = next(item for item in preview["entries"] if item["source_table"] == "t_qc_report")
    assert report_entry["disposition"] == "target_identity_match"
    assert report_entry["target_id"] > 0
    assert preview["counts"]["target_identity_match"] == 1
    assert reader.calls == 1


def test_i21_task_identity_requires_matching_target_task_rule_edges():
    client, app, reader, headers, project_id = _client(_snapshot(populated=True))
    try:
        with app.state.session_factory() as session:
            rule = QualityRuleDefinitionRecord(
                project_id=project_id,
                name="target rule",
                dimension="完整性",
                rule_type="not_null",
                target_database="ods",
                target_table="orders",
                target_column="order_id",
                params_json="{}",
                threshold=0,
                severity="warning",
                status="enabled",
                owner_name="",
                remark="",
                source_system="datara_meta",
                source_table="t_qc_rule",
                source_id="1",
            )
            task = QualityTaskRecord(
                project_id=project_id,
                name="target task",
                cron_expression="0 0 * * * *",
                enabled=True,
                status="idle",
                last_result="success",
                owner_name="",
                remark="",
                source_system="datara_meta",
                source_table="t_qc_task",
                source_id="2",
            )
            session.add_all([rule, task])
            session.flush()
            session.add(QualityTaskRuleRecord(task_id=task.id, rule_definition_id=rule.id, ordinal_position=2))
            session.commit()
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i21/mapping-preview",
            headers=headers,
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    data = response.json()["data"]
    task_entry = next(item for item in data["preview"]["entries"] if item["source_table"] == "t_qc_task")
    assert task_entry["disposition"] == "blocked"
    assert task_entry["issues"] == ["target_task_rule_links_mismatch"]
    assert data["target"]["counts"]["task_rule_links"] == 1




def test_i21_preview_target_identity_is_project_scoped_and_import_stays_disabled():
    client, app, reader, headers, project_id = _client(_snapshot(populated=True))
    try:
        other_project = client.post(
            "/api/v1/rebuild/projects", headers=headers, json={"name": "I21 unrelated project"}
        ).json()["data"]["id"]
        with app.state.session_factory() as session:
            session.add(
                QualityReportRecord(
                    project_id=other_project,
                    title="unrelated",
                    scope="",
                    period="",
                    content_json="{}",
                    created_by="",
                    source_system="datara_meta",
                    source_table="t_qc_report",
                    source_id="5",
                )
            )
            session.commit()
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i21/mapping-preview",
            headers=headers,
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    preview = response.json()["data"]["preview"]
    assert preview["counts"]["new_identity_candidate"] == 5
    assert preview["counts"]["blocked"] == 1
    assert preview["counts"]["target_identity_match"] == 0
    assert any(
        issue["code"] == "cross_project_target_identity"
        and issue["source_table"] == "t_qc_report"
        and issue["source_id"] == "5"
        for issue in response.json()["data"]["preview"]["issues"]
    )
    assert preview["import_enabled"] is False
    assert reader.calls == 1
