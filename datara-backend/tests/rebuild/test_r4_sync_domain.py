"""R4-SYNC domain tests — contract unlocked after R3 closure (大盘盘点 #21/#30).

Gate lineage: test_r4_sync_contract_pending.py was the pre-unlock route sentinel;
R3 closed via user ruling (e217ce3),
governance domain accepted (大盘盘点 #30: rebuild/governance 30+ modules GREEN +
R2-13 42-table evidence), so the domain implements the §6.4 contract:
- capabilities exposes the 同步表单 13 字段 + 映射 8 字段 contract surface;
- explore reuses the datasource domain metadata catalog (字段/类型探查, mocked here);
- auto mapping generates the name-matched §6.4 snapshot (8 fields per entry);
- plans save/user-adjust persist a version-bound snapshot (映射随版本引用),
  slot replacement on resave, contract validation with SYNC_* diagnostics;
- auth/permission reuse the host callbacks (401/403).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from rebuild.api.app import create_app
from rebuild.datasource.models import ProjectDatasourceRecord
from rebuild.identity.contracts import Role
from rebuild.identity.models import ProjectMemberRecord
from rebuild.identity.repository import UserRepository
from rebuild.project.models import ProjectRecord
from rebuild.sync.models import SyncTaskDefinitionRecord
from rebuild.sync.repository import MAPPING_FIELDS

SYNC = "/api/v1/rebuild/sync"


class _FakeCatalog:
    """Stand-in for the datasource domain metadata catalog (explore seam)."""

    def __init__(self, rows_by_object):
        self._rows_by_object = rows_by_object
        self.calls = []

    def columns(self, schema, object_name, *, limit=500):
        self.calls.append((schema, object_name, limit))
        return list(self._rows_by_object.get(object_name, []))


def _install_fake_catalog(monkeypatch, src_rows_by_object, tgt_rows_by_object):
    created: list[tuple[str, object]] = []

    def factory(draft, *, connector=None):
        catalog = _FakeCatalog(src_rows_by_object if draft.name == "src-db" else tgt_rows_by_object)
        created.append((draft.name, connector))
        return catalog

    monkeypatch.setattr("rebuild.sync.api.metadata_catalog_for", factory)
    return created


def _client(monkeypatch):
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="r4-sync-domain-test-secret")
    client = TestClient(app)
    client.__enter__()
    with app.state.session_factory() as session:
        dev = UserRepository(session).create(username="dev", password="dev-pass", role=Role.DEVELOPER)
        viewer = UserRepository(session).create(username="viewer", password="viewer-pass", role=Role.VIEWER)
        owned = ProjectRecord(name="r4-sync-owned", description="", owner_id=dev.id)
        session.add(owned)
        session.commit()
        project_id = owned.id
        src = ProjectDatasourceRecord(
            project_id=project_id,
            name="src-db",
            kind="mysql",
            host="127.0.0.1",
            port=3306,
            database_name="sales",
            username="reader",
            password="",
        )
        tgt = ProjectDatasourceRecord(
            project_id=project_id,
            name="tgt-db",
            kind="mysql",
            host="127.0.0.1",
            port=3306,
            database_name="dw",
            username="writer",
            password="",
        )
        session.add_all((src, tgt))
        session.commit()
        src_id, tgt_id = src.id, tgt.id
        session.add(ProjectMemberRecord(project_id=project_id, user_id=viewer.id, role="viewer"))
        session.commit()
    tokens = {}
    for username, password in (("dev", "dev-pass"), ("viewer", "viewer-pass")):
        response = client.post("/api/v1/rebuild/login", json={"username": username, "password": password})
        tokens[username] = {"Authorization": f"Bearer {response.json()['data']['token']}"}
    return client, app, project_id, src_id, tgt_id, tokens


def _mapping(source, target, status="AUTO", **overrides):
    entry = {
        "source_column": source,
        "target_column": target,
        "source_type": "int",
        "target_type": "int",
        "transform_expression": "",
        "nullable": True,
        "default_value": None,
        "mapping_status": status,
    }
    entry.update(overrides)
    return entry


def _plan_body(project_id, src_id, tgt_id, mappings=None, **overrides):
    body = {
        "project_id": project_id,
        "workflow_id": 10,
        "workflow_version": 3,
        "task_id": "sync-orders",
        "source": {"datasource_id": src_id, "schema": "sales", "object": "orders"},
        "target": {"datasource_id": tgt_id, "schema": "dw", "object": "orders_dw"},
        "mappings": mappings
        if mappings is not None
        else [_mapping("id", "id"), _mapping("name", "name", status="ADJUSTED")],
        "transform_config": {
            "filter_condition": "dt >= '2026-10-01'",
            "transform_expression": {"name": "upper(name)"},
        },
        "target_properties": {
            "primary_key_conflict": {"primary_key": ["id"], "conflict_strategy": "upsert"},
            "partition_incremental": {"partition_field": "dt", "incremental_field": "updated_at"},
            "batch_concurrency": {"batch_size": 1000, "concurrency": 4},
        },
    }
    body.update(overrides)
    return body


def test_capabilities_exposes_design_contract_and_unlocked_routes(monkeypatch):
    client, app, _project_id, _src_id, _tgt_id, tokens = _client(monkeypatch)
    response = client.get(f"{SYNC}/capabilities", headers=tokens["dev"])
    assert response.status_code == 200
    data = response.json()["data"]
    # §6.4 同步表单 13 字段 + 映射 8 字段 contract surface.
    assert data["form_fields"] == [
        "source_datasource", "source_object", "target_datasource", "target_object",
        "column_explore", "type_explore", "auto_mapping", "manual_mapping_adjust",
        "transform_expression", "filter_condition", "partition_incremental",
        "primary_key_conflict", "batch_concurrency",
    ]
    assert data["mapping_fields"] == [
        "source_column",
        "target_column",
        "source_type",
        "target_type",
        "transform_expression",
        "nullable",
        "default_value",
        "mapping_status",
    ]
    assert data["mapping_status"] == ["AUTO", "ADJUSTED", "UNMATCHED"]
    # The former gate routes are now part of the registered OpenAPI contract.
    # (include_router wraps mounted routes under _IncludedRouter with path=None,
    # so the app.routes set is no longer introspectable; the OpenAPI schema is
    # the authoritative contract surface and reflects the mounted routes.)
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/api/v1/rebuild/sync/capabilities" in paths
    assert "get" in paths["/api/v1/rebuild/sync/capabilities"]
    assert "/api/v1/rebuild/sync/plans" in paths
    assert "post" in paths["/api/v1/rebuild/sync/plans"]
    assert "post" in paths["/api/v1/rebuild/sync/mappings/auto"]


def test_explore_reuses_datasource_metadata_catalog(monkeypatch):
    client, _app, project_id, src_id, _tgt_id, tokens = _client(monkeypatch)
    rows = [
        {
            "column_name": "id",
            "data_type": "int",
            "column_type": "int(11)",
            "is_nullable": False,
            "column_key": "PRI",
            "column_comment": "pk",
        },
        {
            "column_name": "name",
            "data_type": "varchar",
            "column_type": "varchar(64)",
            "is_nullable": True,
            "column_key": "",
            "column_comment": "",
        },
    ]
    created = _install_fake_catalog(monkeypatch, {"orders": rows}, {})
    response = client.get(
        f"{SYNC}/explore",
        params={"project_id": project_id, "datasource_id": src_id, "schema": "sales", "object_name": "orders"},
        headers=tokens["dev"],
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["items"] == rows
    assert data["truncated"] is False
    # The datasource domain catalog was reused with the registered draft + pooled connector.
    assert created == [("src-db", created[0][1])]
    assert callable(created[0][1])
    assert created[0][0] == "src-db"


def test_auto_mapping_generates_name_matched_snapshot(monkeypatch):
    client, _app, project_id, src_id, tgt_id, tokens = _client(monkeypatch)
    _install_fake_catalog(
        monkeypatch,
        {
            "orders": [
                {"column_name": "id", "data_type": "int", "is_nullable": False},
                {"column_name": "name", "data_type": "varchar", "is_nullable": True},
                {"column_name": "amount", "data_type": "decimal", "is_nullable": True},
            ]
        },
        {
            "orders_dw": [
                {"column_name": "id", "data_type": "bigint", "is_nullable": False},
                {"column_name": "name", "data_type": "varchar", "is_nullable": True},
                {"column_name": "created_at", "data_type": "datetime", "is_nullable": True},
            ]
        },
    )
    response = client.post(
        f"{SYNC}/mappings/auto",
        json={
            "project_id": project_id,
            "source": {"datasource_id": src_id, "schema": "sales", "object": "orders"},
            "target": {"datasource_id": tgt_id, "schema": "dw", "object": "orders_dw"},
        },
        headers=tokens["dev"],
    )
    assert response.status_code == 200
    mappings = response.json()["data"]["mappings"]
    assert len(mappings) == 3
    for entry in mappings:
        assert set(entry) == set(MAPPING_FIELDS)
    by_source = {entry["source_column"]: entry for entry in mappings}
    assert by_source["id"]["mapping_status"] == "AUTO"
    assert by_source["id"]["target_column"] == "id"
    assert by_source["id"]["source_type"] == "int"
    assert by_source["id"]["target_type"] == "bigint"
    assert by_source["name"]["mapping_status"] == "AUTO"
    # Unmatched source column stays UNMATCHED for 用户调整映射.
    assert by_source["amount"]["mapping_status"] == "UNMATCHED"
    assert by_source["amount"]["target_column"] == ""


def test_save_plan_persists_snapshot_referenced_by_version(monkeypatch):
    client, app, project_id, src_id, tgt_id, tokens = _client(monkeypatch)
    body = _plan_body(project_id, src_id, tgt_id)
    response = client.post(f"{SYNC}/plans", json=body, headers=tokens["dev"])
    assert response.status_code == 200
    assert response.json()["data"] == {"saved": True, "workflow_version": 3, "task_id": "sync-orders"}
    listed = client.get(
        f"{SYNC}/plans",
        params={"project_id": project_id, "workflow_id": 10, "workflow_version": 3},
        headers=tokens["dev"],
    )
    assert listed.status_code == 200
    items = listed.json()["data"]["items"]
    assert len(items) == 1
    snapshot = items[0]
    assert snapshot["source"] == body["source"]
    assert snapshot["target"] == body["target"]
    assert snapshot["mappings"] == body["mappings"]
    assert snapshot["transform_config"] == body["transform_config"]
    assert snapshot["target_properties"] == body["target_properties"]
    # 映射随版本引用: another workflow version sees nothing.
    other_version = client.get(
        f"{SYNC}/plans",
        params={"project_id": project_id, "workflow_id": 10, "workflow_version": 4},
        headers=tokens["dev"],
    )
    assert other_version.json()["data"]["items"] == []
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(SyncTaskDefinitionRecord)) == 1


def test_resave_plan_replaces_slot(monkeypatch):
    client, app, project_id, src_id, tgt_id, tokens = _client(monkeypatch)
    first = _plan_body(project_id, src_id, tgt_id)
    second = _plan_body(
        project_id,
        src_id,
        tgt_id,
        mappings=[_mapping("id", "id"), _mapping("name", "full_name", status="ADJUSTED", target_type="varchar")],
    )
    assert client.post(f"{SYNC}/plans", json=first, headers=tokens["dev"]).status_code == 200
    assert client.post(f"{SYNC}/plans", json=second, headers=tokens["dev"]).status_code == 200
    listed = client.get(
        f"{SYNC}/plans",
        params={"project_id": project_id, "workflow_id": 10, "workflow_version": 3},
        headers=tokens["dev"],
    )
    items = listed.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["mappings"] == second["mappings"]
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(SyncTaskDefinitionRecord)) == 1


def test_save_plan_rejects_invalid_mapping_snapshot(monkeypatch):
    client, app, project_id, src_id, tgt_id, tokens = _client(monkeypatch)
    broken_field = _mapping("id", "id")
    del broken_field["target_type"]
    broken_status = _mapping("id", "id", mapping_status="MAGIC")
    unknown_field = _mapping("id", "id", extra_field=1)
    for mappings in ([broken_field], [broken_status], [unknown_field]):
        response = client.post(
            f"{SYNC}/plans",
            json=_plan_body(project_id, src_id, tgt_id, mappings=mappings),
            headers=tokens["dev"],
        )
        assert response.status_code == 400
        payload = response.json()
        assert payload["code"] == "SYNC_INVALID_MAPPING"
        assert payload["data"]["diagnostics"]
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(SyncTaskDefinitionRecord)) == 0


def test_sync_routes_enforce_auth_and_permission(monkeypatch):
    client, _app, project_id, src_id, _tgt_id, tokens = _client(monkeypatch)
    _install_fake_catalog(monkeypatch, {"orders": []}, {"orders_dw": []})
    # Missing token → 401 (capabilities and plans alike).
    assert client.get(f"{SYNC}/capabilities").status_code == 401
    assert client.post(f"{SYNC}/plans", json=_plan_body(project_id, src_id, 999)).status_code == 401
    # Viewer holds VIEW_ALL only: read allowed, save denied.
    viewer_read = client.get(
        f"{SYNC}/plans",
        params={"project_id": project_id, "workflow_id": 10, "workflow_version": 3},
        headers=tokens["viewer"],
    )
    assert viewer_read.status_code == 200
    viewer_save = client.post(
        f"{SYNC}/plans", json=_plan_body(project_id, src_id, 999), headers=tokens["viewer"]
    )
    assert viewer_save.status_code == 403
    viewer_auto = client.post(
        f"{SYNC}/mappings/auto",
        json={
            "project_id": project_id,
            "source": {"datasource_id": src_id, "schema": "sales", "object": "orders"},
            "target": {"datasource_id": 999, "schema": "dw", "object": "orders_dw"},
        },
        headers=tokens["viewer"],
    )
    assert viewer_auto.status_code == 403
    # Automatic mapping is an edit operation and also requires an active token.
    unauthenticated_auto = client.post(
        f"{SYNC}/mappings/auto",
        json={
            "project_id": project_id,
            "source": {"datasource_id": src_id, "schema": "sales", "object": "orders"},
            "target": {"datasource_id": src_id, "schema": "dw", "object": "orders_dw"},
        },
    )
    assert unauthenticated_auto.status_code == 401
    # Unknown datasource reference on explore → 404.
    missing = client.get(
        f"{SYNC}/explore",
        params={"project_id": project_id, "datasource_id": 9999, "schema": "sales", "object_name": "orders"},
        headers=tokens["dev"],
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == 4042


def test_auto_mapping_rejects_malformed_references(monkeypatch):
    client, _app, project_id, src_id, tgt_id, tokens = _client(monkeypatch)
    base = {
        "project_id": project_id,
        "source": {"datasource_id": src_id, "schema": "sales", "object": "orders"},
        "target": {"datasource_id": tgt_id, "schema": "dw", "object": "orders_dw"},
    }
    malformed = [
        {"project_id": project_id, "target": base["target"]},
        {"project_id": project_id, "source": base["source"]},
        {**base, "source": {**base["source"], "datasource_id": "not-an-int"}},
        {**base, "source": {**base["source"], "schema": "s" * 256}},
    ]
    for body in malformed:
        response = client.post(f"{SYNC}/mappings/auto", json=body, headers=tokens["dev"])
        assert response.status_code == 400
        assert response.json()["code"] == 4001


def test_explore_marks_truncated_at_max_page_size(monkeypatch):
    client, _app, project_id, src_id, _tgt_id, tokens = _client(monkeypatch)
    rows = [{"column_name": f"c{i}", "data_type": "int"} for i in range(501)]
    _install_fake_catalog(monkeypatch, {"large_table": rows}, {})
    response = client.get(
        f"{SYNC}/explore",
        params={"project_id": project_id, "datasource_id": src_id, "schema": "sales", "object_name": "large_table", "limit": 500},
        headers=tokens["dev"],
    )
    assert response.status_code == 200
    assert len(response.json()["data"]["items"]) == 500
    assert response.json()["data"]["truncated"] is True


def test_save_plan_rejects_malformed_frames_and_structured_config(monkeypatch):
    client, _app, project_id, src_id, tgt_id, tokens = _client(monkeypatch)
    malformed = [
        {key: value for key, value in _plan_body(project_id, src_id, tgt_id).items() if key != "workflow_id"},
        {key: value for key, value in _plan_body(project_id, src_id, tgt_id).items() if key != "workflow_version"},
        {**_plan_body(project_id, src_id, tgt_id), "task_id": "  "},
        {**_plan_body(project_id, src_id, tgt_id), "transform_config": []},
        {
            **_plan_body(project_id, src_id, tgt_id),
            "target_properties": {"batch_concurrency": {"batch_size": 10001, "concurrency": 33}},
        },
    ]
    expected_codes = [4001, 4001, 4001, "SYNC_INVALID_TRANSFORM", "SYNC_INVALID_TARGET_PROPS"]
    for body, expected in zip(malformed, expected_codes, strict=True):
        response = client.post(f"{SYNC}/plans", json=body, headers=tokens["dev"])
        assert response.status_code == 400
        payload = response.json()
        assert payload["code"] == expected
        if isinstance(expected, str):
            assert payload["data"]["diagnostics"]


@pytest.mark.parametrize(
    ("field", "value", "diagnostic"),
    [
        ("transform_config", {"transform_expression": ["bad"]}, "SYNC_INVALID_TRANSFORM"),
        ("transform_config", {"unexpected": True}, "SYNC_INVALID_TRANSFORM"),
        ("target_properties", {"batch_concurrency": {"batch_size": True}}, "SYNC_INVALID_TARGET_PROPS"),
        ("target_properties", {"primary_key_conflict": {"conflict_strategy": "truncate"}}, "SYNC_INVALID_TARGET_PROPS"),
    ],
)
def test_save_plan_rejects_invalid_structured_schema(monkeypatch, field, value, diagnostic):
    client, _app, project_id, src_id, tgt_id, tokens = _client(monkeypatch)
    body = _plan_body(project_id, src_id, tgt_id, **{field: value})
    response = client.post(f"{SYNC}/plans", json=body, headers=tokens["dev"])
    assert response.status_code == 400
    assert response.json()["code"] == diagnostic
    assert response.json()["data"]["diagnostics"]


def test_mapping_field_contract_is_frozen():
    """The §6.4 mapping 8 fields are the exact contract keys (imported surface)."""
    assert MAPPING_FIELDS == (
        "source_column",
        "target_column",
        "source_type",
        "target_type",
        "transform_expression",
        "nullable",
        "default_value",
        "mapping_status",
    )
