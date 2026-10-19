from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import event

from rebuild.api.app import create_app
from rebuild.governance.legacy_source_reader import I19_SOURCE_COLUMNS
from rebuild.governance.migrations import MigrationRunner, R3_GOVERNANCE_MIGRATIONS
from rebuild.governance.models import AssetMetadataExtensionRecord, AssetRecord


def _snapshot(**table_rows):
    rows = {table: tuple(table_rows.get(table, ())) for table in I19_SOURCE_COLUMNS}
    return SimpleNamespace(
        schema="datara_meta",
        rows=rows,
        counts={table: len(values) for table, values in rows.items()},
        captured_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
        digest="a" * 64,
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
        token_secret="legacy-i19-preview-test-secret",
        validation_key="legacy-i19-preview-validation-key",
        legacy_i19_source_reader_factory=lambda: reader,
    )
    client = TestClient(app)
    client.__enter__()
    MigrationRunner(app.state.session_factory.kw["bind"], R3_GOVERNANCE_MIGRATIONS).apply()
    from rebuild.identity.contracts import Role, TokenService
    from rebuild.identity.models import UserRecord

    svc = TokenService(secret="legacy-i19-preview-test-secret", ttl_seconds=3600)
    with app.state.session_factory() as session:
        session.add(UserRecord(id=1, username="i19-preview-admin", role=Role.DEVELOPER, password_hash="x"))
        session.commit()
    token = svc.issue(user_id=1, username="i19-preview-admin", role=Role.DEVELOPER)
    app.state.active_tokens.add(token, user_id=1, username="i19-preview-admin", role=Role.DEVELOPER.value)
    headers = {"Authorization": f"Bearer {token}"}
    project = client.post("/api/v1/rebuild/projects", headers=headers, json={"name": "I19 preview"})
    assert project.status_code == 200
    return client, app, reader, headers, project.json()["data"]["id"]


def test_i19_mapping_preview_is_project_scoped_read_only_and_import_disabled():
    client, app, reader, headers, project_id = _client(_snapshot())
    writes = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().split(maxsplit=1)[0].upper() in {"INSERT", "UPDATE", "DELETE", "REPLACE"}:
            writes.append(statement)

    event.listen(app.state.session_factory.kw["bind"], "before_cursor_execute", capture)
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i19/mapping-preview",
            headers=headers,
        )
    finally:
        event.remove(app.state.session_factory.kw["bind"], "before_cursor_execute", capture)
        client.__exit__(None, None, None)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["project_id"] == project_id
    assert data["source"]["counts"] == {table: 0 for table in I19_SOURCE_COLUMNS}
    assert data["target"]["captured_at"].endswith("+08:00")
    assert len(data["target"]["identity_digest"]) == 64
    assert data["preview"]["counts"] == {
        "new_identity_candidate": 0,
        "target_identity_match": 0,
        "blocked": 0,
    }
    assert data["preview"]["parity_verified"] is False
    assert data["preview"]["import_enabled"] is False
    assert writes == []
    assert reader.calls == 1


def test_i19_mapping_preview_rejects_unauthenticated_request_before_source_read():
    client, _app, reader, _headers, project_id = _client(_snapshot())
    try:
        response = client.post(f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i19/mapping-preview")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 401
    assert reader.calls == 0


def test_i19_preview_never_reuses_another_projects_asset_mapping_or_returns_source_values():
    from datetime import datetime

    source_row = {
        "id": 41,
        "ds_id": 9,
        "db_name": "legacy_warehouse",
        "table_name": "private_customer_snapshot",
        "biz_domain": "internal_only_domain",
        "security_level": "L2",
        "owner": "internal_only_owner",
        "remark": "internal_only_note",
        "create_time": datetime(2026, 10, 15),
        "update_time": datetime(2026, 10, 15),
    }
    client, app, reader, headers, project_id = _client(_snapshot(t_meta_table_ext=(source_row,)))
    try:
        other_project = client.post(
            "/api/v1/rebuild/projects", headers=headers, json={"name": "I19 other project"}
        ).json()["data"]["id"]
        with app.state.session_factory() as session:
            asset = AssetRecord(
                project_id=other_project,
                source_system="legacy",
                database_name="legacy_warehouse",
                schema_name="",
                asset_name="private_customer_snapshot",
                asset_type="table",
            )
            session.add(asset)
            session.flush()
            session.add(
                AssetMetadataExtensionRecord(
                    asset_id=asset.id,
                    legacy_datasource_id=9,
                    database_name="legacy_warehouse",
                    table_name="private_customer_snapshot",
                    source_system="datara_meta",
                    source_table="t_meta_table_ext",
                    source_id="41",
                )
            )
            session.commit()

        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i19/mapping-preview",
            headers=headers,
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["target"]["counts"]["t_meta_table_ext"] == 0
    assert data["preview"]["counts"] == {
        "new_identity_candidate": 0,
        "target_identity_match": 0,
        "blocked": 1,
    }
    assert data["preview"]["issues"][0]["code"] == "unresolved_asset_identity"
    for private_value in (
        "private_customer_snapshot",
        "internal_only_domain",
        "internal_only_owner",
        "internal_only_note",
    ):
        assert private_value not in response.text
    assert reader.calls == 1
