from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from rebuild.api.app import create_app
from rebuild.governance.legacy_source_reader import LEGACY_SCHEMA, I18_SOURCE_COLUMNS, LegacyI18SourceSnapshot
from rebuild.governance.migrations import MigrationRunner, R3_GOVERNANCE_MIGRATIONS
from rebuild.governance.models import (
    GovernanceDomainRecord,
    MigrationBatchRecord,
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


def _client(monkeypatch, *, import_enabled=None):
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
        legacy_i18_import_enabled=import_enabled,
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


def _import_request(project_id, source_digest, target_digest):
    return {
        "source_digest": source_digest,
        "target_digest": target_digest,
        "idempotency_key": "test-i18-import-key",
        "confirmation": f"IMPORT I18 {project_id} {source_digest} {target_digest}",
    }


def test_i18_import_api_is_disabled_before_opening_source_or_target_write(monkeypatch):
    monkeypatch.delenv("REBUILD_LEGACY_I18_IMPORT_ENABLED", raising=False)
    client, app, headers, project_id, _denied_project_id = _client(monkeypatch)
    from rebuild.governance.legacy_source_reader import LegacyI18SourceReader
    from rebuild.governance import api as governance_api

    def must_not_open(_cls):
        raise AssertionError("disabled import API must not construct a source reader")

    def must_not_import(*_args, **_kwargs):
        raise AssertionError("disabled import API must not invoke the importer")

    monkeypatch.setattr(LegacyI18SourceReader, "from_runtime_env", classmethod(must_not_open))
    monkeypatch.setattr(governance_api, "execute_i18_legacy_import", must_not_import, raising=False)
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i18/import",
            headers=headers,
            json=_import_request(project_id, "a" * 64, "b" * 64),
        )
        with app.state.session_factory() as session:
            batch_count = session.scalar(select(func.count()).select_from(MigrationBatchRecord))
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 503
    assert response.json()["code"] == 5034
    assert batch_count == 0


def test_validation_runner_cannot_execute_enabled_i18_import(monkeypatch):
    client, _app, headers, project_id, _denied_project_id = _client(monkeypatch, import_enabled=True)
    from rebuild.governance.legacy_source_reader import LegacyI18SourceReader

    def must_not_open(_cls):
        raise AssertionError("validation runner must be rejected before source access")

    monkeypatch.setattr(LegacyI18SourceReader, "from_runtime_env", classmethod(must_not_open))
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i18/import",
            headers=headers,
            json=_import_request(project_id, "a" * 64, "b" * 64),
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 403
    assert response.json()["code"] == 1003


def test_i18_import_rejects_unapproved_project_before_opening_source(monkeypatch):
    client, _app, _validation_headers, _project_id, other_project_id = _client(
        monkeypatch, import_enabled=True
    )
    from rebuild.governance.legacy_source_reader import LegacyI18SourceReader
    from rebuild.identity.models import UserRecord
    from rebuild.identity.passwords import hash_password

    with _app.state.session_factory() as session, session.begin():
        session.add(
            UserRecord(
                id=76,
                username="approved-scope-operator",
                password_hash=hash_password("scope-test-password"),
                role="admin",
            )
        )
    login = client.post(
        "/api/v1/rebuild/login",
        json={"username": "approved-scope-operator", "password": "scope-test-password"},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}

    def must_not_open(_cls):
        raise AssertionError("unapproved project must be rejected before source access")

    monkeypatch.setattr(LegacyI18SourceReader, "from_runtime_env", classmethod(must_not_open))
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{other_project_id}/legacy/i18/import",
            headers=headers,
            json=_import_request(other_project_id, "a" * 64, "b" * 64),
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 409
    assert response.json()["code"] == 4099


def test_i18_import_api_checks_project_edit_before_opening_source(monkeypatch):
    client, app, _validation_headers, _project_id, _denied_project_id = _client(
        monkeypatch, import_enabled=True
    )
    from rebuild.governance.legacy_source_reader import LegacyI18SourceReader
    from rebuild.identity.models import UserRecord
    from rebuild.identity.passwords import hash_password

    with app.state.session_factory() as session, session.begin():
        session.add_all(
            [
                UserRecord(
                    id=78,
                    username="project-owner",
                    password_hash=hash_password("owner-password"),
                    role="admin",
                ),
                UserRecord(
                    id=79,
                    username="read-only-operator",
                    password_hash=hash_password("viewer-password"),
                    role="viewer",
                ),
            ]
        )
    owner_login = client.post(
        "/api/v1/rebuild/login",
        json={"username": "project-owner", "password": "owner-password"},
    )
    owner_headers = {"Authorization": f"Bearer {owner_login.json()['data']['token']}"}
    project = client.post(
        "/api/v1/rebuild/projects",
        headers=owner_headers,
        json={"name": "owner-only import scope"},
    )
    project_id = project.json()["data"]["id"]
    viewer_login = client.post(
        "/api/v1/rebuild/login",
        json={"username": "read-only-operator", "password": "viewer-password"},
    )
    viewer_headers = {"Authorization": f"Bearer {viewer_login.json()['data']['token']}"}

    def must_not_open(_cls):
        raise AssertionError("project permission must be checked before source access")

    monkeypatch.setattr(LegacyI18SourceReader, "from_runtime_env", classmethod(must_not_open))
    try:
        response = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i18/import",
            headers=viewer_headers,
            json=_import_request(project_id, "a" * 64, "b" * 64),
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 403
    assert response.json()["code"] == 1003


def test_enabled_i18_import_api_requires_fresh_digests_and_calls_service(monkeypatch):
    client, app, _validation_headers, _project_id, _denied_project_id = _client(
        monkeypatch, import_enabled=True
    )
    from rebuild.governance import api as governance_api
    from rebuild.governance.snapshot_repository import LegacyI18TargetSnapshotRepository
    from rebuild.identity.models import UserRecord
    from rebuild.identity.passwords import hash_password

    with app.state.session_factory() as session, session.begin():
        session.add(
            UserRecord(
                id=77,
                username="migration-operator",
                password_hash=hash_password("local-test-password"),
                role="admin",
            )
        )
    login = client.post(
        "/api/v1/rebuild/login",
        json={"username": "migration-operator", "password": "local-test-password"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}
    project_response = client.post(
        "/api/v1/rebuild/projects",
        headers=headers,
        json={"name": "I18 import operator project"},
    )
    assert project_response.status_code == 200
    project_id = project_response.json()["data"]["id"]
    assert project_id == 3

    with app.state.session_factory() as session:
        target_digest = LegacyI18TargetSnapshotRepository(session).read_project_snapshot(project_id).digest
    importer_calls = []
    approved_plan = SimpleNamespace(
        project_id=project_id,
        source_count=45,
        counts={"create": 44, "unchanged": 0, "skipped": 1, "conflict": 0, "blocked": 0},
        entries=[SimpleNamespace(disposition="create") for _ in range(44)]
        + [
            SimpleNamespace(
                source_table="t_dw_model_version",
                source_id="1",
                disposition="skipped",
                disposition_reason="approved_missing_model_reference",
            )
        ],
        ready_to_import=True,
    )
    monkeypatch.setattr(
        governance_api,
        "build_i18_legacy_dry_run",
        lambda *_args: SimpleNamespace(plan=approved_plan),
    )
    monkeypatch.setattr(
        governance_api,
        "execute_i18_legacy_import",
        lambda *args, **kwargs: importer_calls.append((args, kwargs))
        or SimpleNamespace(
            batch_id=71,
            status="completed",
            expected_count=45,
            imported_count=44,
            skipped_count=1,
            error_count=0,
        ),
    )
    try:
        bad_confirmation_body = _import_request(project_id, "b" * 64, target_digest)
        bad_confirmation_body["confirmation"] = "IMPORT I18 wrong-digest"
        bad_confirmation = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i18/import",
            headers=headers,
            json=bad_confirmation_body,
        )
        assert importer_calls == []
        stale = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i18/import",
            headers=headers,
            json=_import_request(project_id, "c" * 64, target_digest),
        )
        assert importer_calls == []
        stale_target = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i18/import",
            headers=headers,
            json=_import_request(project_id, "b" * 64, "f" * 64),
        )
        assert importer_calls == []
        with monkeypatch.context() as patcher:
            patcher.setattr(
                governance_api,
                "build_i18_legacy_dry_run",
                lambda *_args: SimpleNamespace(
                    plan=SimpleNamespace(**{**vars(approved_plan), "ready_to_import": False})
                ),
            )
            blocked = client.post(
                f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i18/import",
                headers=headers,
                json=_import_request(project_id, "b" * 64, target_digest),
            )
        assert importer_calls == []
        valid = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/legacy/i18/import",
            headers=headers,
            json=_import_request(project_id, "b" * 64, target_digest),
        )
    finally:
        client.__exit__(None, None, None)

    assert bad_confirmation.status_code == 409
    assert bad_confirmation.json()["code"] == 4094
    assert stale.status_code == 409
    assert stale_target.status_code == 409
    assert blocked.status_code == 409
    assert blocked.json()["code"] == 4096
    assert valid.status_code == 200, valid.json()
    assert valid.json()["data"] == {
        "batch_id": 71,
        "status": "completed",
        "expected_count": 45,
        "imported_count": 44,
        "skipped_count": 1,
        "error_count": 0,
    }
    assert len(importer_calls) == 1
    kwargs = importer_calls[0][1]
    assert kwargs["project_id"] == project_id
    assert kwargs["actor_id"] == 77
    assert kwargs["idempotency_key"] == "test-i18-import-key"
    assert kwargs["source_snapshot"].digest == "b" * 64
    assert kwargs["target_snapshot"].digest == target_digest


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
