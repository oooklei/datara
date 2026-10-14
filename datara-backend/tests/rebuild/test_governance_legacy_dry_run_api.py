from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from rebuild.api.app import create_app
from rebuild.governance.legacy_source_reader import LEGACY_SCHEMA, I18_SOURCE_COLUMNS, LegacyI18SourceSnapshot
from rebuild.governance.migrations import MigrationRunner, R3_GOVERNANCE_MIGRATIONS
from rebuild.governance.models import (
    GovernanceDomainRecord,
    ModelEngineRecord,
    WarehouseLayerRecord,
    WarehouseModelFieldRecord,
    WarehouseModelRecord,
    WarehouseModelRelationRecord,
    WarehouseModelVersionRecord,
)
from rebuild.project.models import ProjectRecord


class FakeLegacySourceReader:
    def read_snapshot(self):
        return LegacyI18SourceSnapshot(
            schema=LEGACY_SCHEMA,
            captured_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
            digest="b" * 64,
            counts={table: 0 for table in I18_SOURCE_COLUMNS},
            rows={table: () for table in I18_SOURCE_COLUMNS},
        )


def _client(monkeypatch):
    from rebuild.governance.legacy_source_reader import LegacyI18SourceReader

    monkeypatch.setattr(
        LegacyI18SourceReader,
        "from_runtime_env",
        classmethod(lambda _cls: FakeLegacySourceReader()),
    )
    app = create_app(
        "sqlite+pysqlite:///:memory:",
        token_secret="legacy-dry-run-api-test-secret",
        validation_key="legacy-dry-run-api-key",
    )
    client = TestClient(app)
    client.__enter__()
    MigrationRunner(app.state.session_factory.kw["bind"], R3_GOVERNANCE_MIGRATIONS).apply()
    token = client.post(
        "/api/v1/rebuild/validation-token",
        headers={"X-Backend-Validation-Key": "legacy-dry-run-api-key"},
    ).json()["data"]["token"]
    headers = {"Authorization": f"Bearer {token}"}
    first = client.post("/api/v1/rebuild/projects", headers=headers, json={"name": "I18 target"})
    second = client.post("/api/v1/rebuild/projects", headers=headers, json={"name": "I18 denied"})
    assert first.status_code == second.status_code == 200
    return client, app, headers, first.json()["data"]["id"], second.json()["data"]["id"]


def test_i18_dry_run_api_returns_snapshot_evidence_and_plan_without_mutation(monkeypatch):
    client, app, headers, project_id, _denied_project_id = _client(monkeypatch)
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i18/dry-run",
            headers=headers,
        )
        with app.state.session_factory() as session:
            source_entities = sum(
                session.scalar(select(func.count()).select_from(model)) or 0
                for model in (
                    GovernanceDomainRecord,
                    WarehouseLayerRecord,
                    ModelEngineRecord,
                    WarehouseModelRecord,
                    WarehouseModelFieldRecord,
                    WarehouseModelRelationRecord,
                    WarehouseModelVersionRecord,
                )
            )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["project_id"] == project_id
    assert data["source"]["schema"] == LEGACY_SCHEMA
    assert data["source"]["digest"] == "b" * 64
    assert data["target"]["project_id"] == project_id
    assert data["plan"]["counts"] == {
        "create": 0,
        "unchanged": 0,
        "conflict": 0,
        "blocked": 0,
        "skipped": 0,
    }
    assert data["plan"]["ready_to_import"] is True
    assert source_entities == 0


def test_i18_dry_run_api_serializes_approved_skip_and_mapping_notes(monkeypatch):
    from rebuild.governance import api as governance_api
    from rebuild.governance.legacy_dry_run import DryRunEntry, I18DryRunPlan
    from rebuild.governance.legacy_migration_service import I18LegacyDryRunResult

    client, app, headers, project_id, _denied_project_id = _client(monkeypatch)
    captured_at = datetime(2026, 10, 15, tzinfo=timezone.utc)
    plan = I18DryRunPlan(
        project_id=project_id,
        source_count=2,
        counts={"create": 1, "unchanged": 0, "conflict": 0, "blocked": 0, "skipped": 1},
        entries=(
            DryRunEntry(
                "t_dw_model_relation",
                "1",
                "create",
                "a" * 64,
                mapping_notes=({"endpoint": "source", "from": "order_id", "to": "order_no"},),
            ),
            DryRunEntry(
                "t_dw_model_version",
                "1",
                "skipped",
                "b" * 64,
                disposition_reason="approved_missing_model_reference",
            ),
        ),
        import_order=(("t_dw_model_relation", "1"),),
        blocking_issues=(),
        snapshot_digest="c" * 64,
        snapshot_captured_at=captured_at,
    )
    monkeypatch.setattr(
        governance_api,
        "build_i18_legacy_dry_run",
        lambda project_id, source_snapshot, target_snapshot: I18LegacyDryRunResult(
            source_digest=source_snapshot.digest,
            source_captured_at=source_snapshot.captured_at,
            target_digest=target_snapshot.digest,
            target_captured_at=target_snapshot.captured_at,
            plan=plan,
        ),
    )
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i18/dry-run",
            headers=headers,
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    serialized_plan = response.json()["data"]["plan"]
    assert serialized_plan["counts"]["skipped"] == 1
    assert serialized_plan["entries"][0]["mapping_notes"] == [
        {"endpoint": "source", "from": "order_id", "to": "order_no"}
    ]
    assert serialized_plan["entries"][1]["disposition"] == "skipped"
    assert serialized_plan["entries"][1]["disposition_reason"] == "approved_missing_model_reference"


def test_i18_dry_run_api_checks_project_permission_before_opening_source(monkeypatch):
    client, app, headers, _project_id, denied_project_id = _client(monkeypatch)
    from rebuild.governance.legacy_source_reader import LegacyI18SourceReader

    def source_must_not_open(_cls):
        raise AssertionError("source reader opened before project authorization")

    monkeypatch.setattr(LegacyI18SourceReader, "from_runtime_env", classmethod(source_must_not_open))
    with app.state.session_factory() as session:
        denied = session.get(ProjectRecord, denied_project_id)
        assert denied is not None
        denied.owner_id = 999
        session.commit()
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{denied_project_id}/legacy/i18/dry-run",
            headers=headers,
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 403
