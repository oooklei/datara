from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import event, select

from rebuild.api.app import create_app
from rebuild.governance.legacy_source_reader import I20_SOURCE_COLUMNS
from rebuild.governance.migrations import MigrationRunner, R3_GOVERNANCE_MIGRATIONS
from rebuild.governance.models import SemanticMetricProfileRecord, SemanticMetricRecord


def _snapshot():
    rows = {table: [] for table in I20_SOURCE_COLUMNS}
    rows["t_indicator"].append(
        {
            "id": 73,
            "code": "private_metric_code",
            "name": "private_metric_name",
            "type": "原子",
            "biz_domain": "交易域",
            "biz_def": "private business definition",
            "tech_def": "private formula",
            "src_kind": "table",
            "src_ref": "private.schema.table",
            "src_field": "private_column",
            "out_table": "private_output",
            "out_task": "private_task",
            "period": "日",
            "dims": "private_dimensions",
            "unit": "元",
            "status": "draft",
            "version": 1,
            "owner": "private_owner",
            "base_metric_id": None,
            "agg_fn": None,
            "num_field": None,
            "time_field": None,
            "dim_field": None,
            "filter_cond": None,
            "create_time": None,
            "update_time": None,
        }
    )
    rows = {table: tuple(values) for table, values in rows.items()}
    return SimpleNamespace(
        schema="datara_meta",
        rows=rows,
        counts={table: len(values) for table, values in rows.items()},
        captured_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        digest="b" * 64,
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
        token_secret="legacy-i20-preview-test-secret",
        validation_key="legacy-i20-preview-validation-key",
        legacy_i20_source_reader_factory=lambda: reader,
    )
    client = TestClient(app)
    client.__enter__()
    MigrationRunner(app.state.session_factory.kw["bind"], R3_GOVERNANCE_MIGRATIONS).apply()
    token = client.post(
        "/api/v1/rebuild/validation-token",
        headers={"X-Backend-Validation-Key": "legacy-i20-preview-validation-key"},
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    project = client.post("/api/v1/rebuild/projects", headers=headers, json={"name": "I20 preview"})
    assert project.status_code == 200
    return client, app, reader, headers, project.json()["data"]["id"]


def test_i20_mapping_preview_is_project_scoped_payload_free_and_read_only():
    client, app, reader, headers, project_id = _client(_snapshot())
    writes = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().split(maxsplit=1)[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
            writes.append(statement)

    event.listen(app.state.session_factory.kw["bind"], "before_cursor_execute", capture)
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i20/mapping-preview",
            headers=headers,
        )
        with app.state.session_factory() as session:
            target_metrics = session.scalars(select(SemanticMetricRecord)).all()
    finally:
        event.remove(app.state.session_factory.kw["bind"], "before_cursor_execute", capture)
        client.__exit__(None, None, None)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["project_id"] == project_id
    assert data["source"]["counts"] == {table: len(rows) for table, rows in _snapshot().rows.items()}
    assert data["target"]["captured_at"].endswith("+08:00")
    assert data["preview"]["counts"] == {
        "new_identity_candidate": 1,
        "target_identity_match": 0,
        "blocked": 0,
    }
    assert data["preview"]["parity_verified"] is False
    assert data["preview"]["import_enabled"] is False
    assert "private_metric_code" not in response.text
    assert "private business definition" not in response.text
    assert "private formula" not in response.text
    assert len(target_metrics) == 0
    assert writes == []
    assert reader.calls == 1


def test_i20_mapping_preview_rejects_unauthenticated_request_before_source_read():
    client, _app, reader, _headers, project_id = _client(_snapshot())
    try:
        response = client.post(f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i20/mapping-preview")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 401
    assert reader.calls == 0


def test_i20_target_identity_lookup_does_not_cross_project_scope():
    client, app, reader, headers, project_id = _client(_snapshot())
    try:
        other = client.post(
            "/api/v1/rebuild/projects", headers=headers, json={"name": "I20 unrelated project"}
        ).json()["data"]["id"]
        with app.state.session_factory() as session:
            metric = SemanticMetricRecord(
                    project_id=other,
                    code="unrelated",
                    name="unrelated",
                    formula="",
                    description="",
                    status="draft",
                )
            session.add(metric)
            session.flush()
            session.add(
                SemanticMetricProfileRecord(
                    metric_id=metric.id,
                    source_system="datara_meta",
                    source_table="t_indicator",
                    source_id="73",
                )
            )
            session.commit()
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i20/mapping-preview",
            headers=headers,
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["target"]["counts"]["t_indicator"] == 0
    assert data["preview"]["counts"]["new_identity_candidate"] == 1
    assert data["preview"]["counts"]["target_identity_match"] == 0
    assert reader.calls == 1


def test_i20_orphan_version_is_blocked_and_raw_snapshot_is_not_returned():
    snapshot = _snapshot()
    rows = {table: list(values) for table, values in snapshot.rows.items()}
    version_columns = I20_SOURCE_COLUMNS["t_indicator_version"][1]
    version = {column: None for column in version_columns}
    version.update(
        {
            "id": 901,
            "indicator_id": 999,
            "version": 1,
            "snapshot_json": "private-version-payload",
            "change_note": "private-change-note",
            "created_by": "private-author",
        }
    )
    rows["t_indicator_version"].append(version)
    rows = {table: tuple(values) for table, values in rows.items()}
    snapshot.rows = rows
    snapshot.counts = {table: len(values) for table, values in rows.items()}
    client, _app, reader, headers, project_id = _client(snapshot)
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i20/mapping-preview",
            headers=headers,
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["preview"]["counts"]["blocked"] == 1
    assert any(item["code"] == "orphan_metric_version" for item in data["preview"]["issues"])
    assert "private-version-payload" not in response.text
    assert "private-change-note" not in response.text
    assert "private-author" not in response.text
    assert reader.calls == 1


def test_i20_duplicate_metric_identity_is_blocked_instead_of_counted_as_candidate():
    snapshot = _snapshot()
    rows = {table: list(values) for table, values in snapshot.rows.items()}
    rows["t_indicator"].append(dict(rows["t_indicator"][0]))
    rows = {table: tuple(values) for table, values in rows.items()}
    snapshot.rows = rows
    snapshot.counts = {table: len(values) for table, values in rows.items()}
    client, _app, reader, headers, project_id = _client(snapshot)
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i20/mapping-preview",
            headers=headers,
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    preview = response.json()["data"]["preview"]
    assert preview["counts"]["new_identity_candidate"] == 0
    assert preview["counts"]["blocked"] == 1
    assert any(issue["code"] == "duplicate_metric_identity" for issue in preview["issues"])
    assert preview["entries"][0]["disposition"] == "blocked"
    assert reader.calls == 1
