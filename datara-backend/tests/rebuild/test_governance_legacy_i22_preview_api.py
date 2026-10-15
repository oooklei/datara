from types import SimpleNamespace
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from rebuild.api.app import create_app
from rebuild.governance.legacy_source_reader import I22_SOURCE_COLUMNS
from rebuild.governance.migrations import MigrationRunner, R3_GOVERNANCE_MIGRATIONS
from rebuild.governance.models import StandardApprovalRecord, StandardElementRecord


def _source_snapshot():
    captured = datetime(2026, 10, 15)
    snapshot_time = captured.replace(tzinfo=timezone.utc)
    rows = {table: [] for table in I22_SOURCE_COLUMNS}
    rows["t_std_code"].append(
        {
            "id": 1,
            "code": "C1",
            "name": "Status",
            "remark": "",
            "status": "draft",
            "version": 1,
            "create_time": captured,
        }
    )
    rows["t_std_code_value"].append(
        {"id": 1, "std_code_id": 1, "c": "A", "n": "Active", "seq": 1, "remark": ""}
    )
    rows["t_std_approval"].append(
        {
            "id": 1,
            "biz_type": "code",
            "biz_id": 2,
            "action": "submit",
            "payload_json": {"opaque": "SECRET_PAYLOAD"},
            "status": "review",
            "opinion": "",
            "create_time": captured,
        }
    )
    rows["t_std_element"].append(
        {
            "id": 1,
            "code": "E1",
            "cn": "状态",
            "en": "Status",
            "data_type": "varchar",
            "length": 16,
            "status": "draft",
            "version": 1,
            "owner": "",
            "remark": "",
            "create_time": captured,
            "update_time": captured,
        }
    )
    rows["t_std_naming_rule"].append(
        {"id": 1, "name": "snake", "rule_type": "regex", "pattern": "^[a-z]+$", "target": "field", "enabled": 1}
    )
    rows["t_std_mapping"].append(
        {
            "id": 1,
            "name": "source-map",
            "target": "orders.status",
            "element_id": 1,
            "code_id": 1,
            "status": "open",
            "diff": "",
        }
    )
    rows["t_std_check_report"].append(
        {
            "id": 1,
            "scope": "project",
            "summary_json": "{}",
            "issues_json": "[]",
            "status": "done",
            "create_time": captured,
        }
    )
    rows = {table: tuple(values) for table, values in rows.items()}
    counts = {table: len(rows[table]) for table in I22_SOURCE_COLUMNS}
    return SimpleNamespace(
        schema="datara_meta",
        rows=rows,
        counts=counts,
        captured_at=snapshot_time,
        digest="d" * 64,
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
        token_secret="legacy-i22-preview-test-secret",
        validation_key="legacy-i22-preview-validation-key",
        legacy_i22_source_reader_factory=lambda: reader,
    )
    client = TestClient(app)
    client.__enter__()
    MigrationRunner(app.state.session_factory.kw["bind"], R3_GOVERNANCE_MIGRATIONS).apply()
    token = client.post(
        "/api/v1/rebuild/validation-token",
        headers={"X-Backend-Validation-Key": "legacy-i22-preview-validation-key"},
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    project = client.post("/api/v1/rebuild/projects", headers=headers, json={"name": "I22 preview"})
    assert project.status_code == 200
    return client, app, reader, headers, project.json()["data"]["id"]


def test_i22_mapping_preview_is_project_scoped_payload_free_and_read_only():
    snapshot = _source_snapshot()
    client, app, reader, headers, project_id = _client(snapshot)
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i22/mapping-preview",
            headers=headers,
        )
        with app.state.session_factory() as session:
            approval_rows = session.scalar(select(func.count()).select_from(StandardApprovalRecord))
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source"]["counts"]["t_std_approval"] == 1
    assert data["preview"]["counts"] == {
        "new_identity_candidate": 6,
        "target_identity_match": 0,
        "blocked": 1,
    }
    assert data["preview"]["parity_verified"] is False
    assert data["preview"]["import_enabled"] is False
    assert data["preview"]["issues"][0]["code"] == "unresolved_reference"
    assert "payload_json" not in response.text
    assert "Status" not in response.text
    assert approval_rows == 0
    assert reader.calls == 1


def test_i22_mapping_preview_rejects_unauthenticated_request_before_reader():
    client, _app, reader, _headers, project_id = _client(_source_snapshot())
    try:
        response = client.post(f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i22/mapping-preview")
    finally:
        client.__exit__(None, None, None)
    assert response.status_code == 401
    assert reader.calls == 0


def test_i22_target_identity_lookup_cannot_cross_project_boundary():
    client, app, _reader, headers, project_id = _client(_source_snapshot())
    try:
        foreign_project = client.post(
            "/api/v1/rebuild/projects", headers=headers, json={"name": "I22 other project"}
        ).json()["data"]["id"]
        with app.state.session_factory() as session:
            session.add(
                StandardElementRecord(
                    project_id=foreign_project,
                    code="OTHER",
                    chinese_name="其他项目元素",
                    english_name="Other project element",
                    data_type="varchar",
                    source_system="datara_meta",
                    source_table="t_std_element",
                    source_id="1",
                )
            )
            session.commit()
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i22/mapping-preview",
            headers=headers,
        )
    finally:
        client.__exit__(None, None, None)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["target"]["counts"]["t_std_element"] == 0
    element = next(item for item in data["preview"]["entries"] if item["source_table"] == "t_std_element")
    assert element["disposition"] == "new_identity_candidate"
