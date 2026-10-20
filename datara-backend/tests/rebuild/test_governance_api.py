from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from rebuild.api.app import create_app
from rebuild.governance.migrations import MigrationRunner, R3_GOVERNANCE_MIGRATIONS
from rebuild.governance.models import AuditEventRecord
from rebuild.project.models import ProjectRecord


@contextmanager
def governance_client():
    app = create_app(
        "sqlite+pysqlite:///:memory:", token_secret="governance-api-test-secret", validation_key="governance-key"
    )
    with TestClient(app) as client:
        MigrationRunner(app.state.session_factory.kw["bind"], R3_GOVERNANCE_MIGRATIONS).apply()
        from rebuild.identity.contracts import Role, TokenService
        from rebuild.identity.models import UserRecord
        svc = TokenService(secret="governance-api-test-secret", ttl_seconds=3600)
        with app.state.session_factory() as session:
            session.add(UserRecord(id=1, username="gov-admin", role=Role.DEVELOPER, password_hash="x"))
            session.commit()
        token = svc.issue(user_id=1, username="gov-admin", role=Role.DEVELOPER)
        app.state.active_tokens.add(token, user_id=1, username="gov-admin", role=Role.DEVELOPER.value)
        headers = {"Authorization": f"Bearer {token}"}
        for name in ("governance-project", "other-project"):
            client.post("/api/v1/rebuild/projects", headers=headers, json={"name": name})
        with app.state.session_factory() as session:
            other = session.scalar(select(ProjectRecord).where(ProjectRecord.name == "other-project"))
            assert other is not None
            other.owner_id = 999
            session.commit()
        yield client, app, headers


def test_governance_routes_require_bearer_token():
    with governance_client() as (client, _app, _headers):
        response = client.get("/api/v1/rebuild/governance/projects/1/assets")

    assert response.status_code == 401


def test_assets_tags_lineage_and_pagination_are_persisted_and_project_scoped():
    with governance_client() as (client, app, headers):
        project_id = client.get("/api/v1/rebuild/projects", headers=headers).json()["data"]["list"][0]["id"]
        source = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/assets",
            headers=headers,
            json={
                "source_system": "mysql-src",
                "database_name": "warehouse",
                "schema_name": "ods",
                "asset_name": "orders",
                "asset_type": "table",
                "fields": [{"field_name": "order_id", "ordinal_position": 1, "data_type": "BIGINT"}],
            },
        )
        target = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/assets",
            headers=headers,
            json={
                "source_system": "mysql-src",
                "database_name": "warehouse",
                "schema_name": "dwd",
                "asset_name": "fact_orders",
                "asset_type": "table",
            },
        )
        assert source.status_code == 201
        assert target.status_code == 201
        source_id = source.json()["data"]["id"]
        target_id = target.json()["data"]["id"]
        tag = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/tags",
            headers=headers,
            json={"namespace": "domain", "tag_key": "sales", "display_name": "Sales"},
        )
        tag_id = tag.json()["data"]["id"]
        linked = client.put(
            f"/api/v1/rebuild/governance/assets/{source_id}/tags",
            headers=headers,
            json={"tag_ids": [tag_id]},
        )
        edge = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/lineage",
            headers=headers,
            json={
                "external_id": "etl:orders-to-fact-orders",
                "source_asset_id": source_id,
                "target_asset_id": target_id,
                "source_field_name": "order_id",
                "target_field_name": "order_id",
                "lineage_type": "transformation",
            },
        )
        listing = client.get(
            f"/api/v1/rebuild/governance/projects/{project_id}/assets?tag=sales&page=1&page_size=1",
            headers=headers,
        )
        detail = client.get(f"/api/v1/rebuild/governance/assets/{source_id}", headers=headers)
        lineage = client.get(
            f"/api/v1/rebuild/governance/assets/{source_id}/lineage?direction=downstream&depth=2",
            headers=headers,
        )
        denied = client.get("/api/v1/rebuild/governance/projects/2/assets", headers=headers)
        with app.state.session_factory() as session:
            audit_count = session.scalar(select(func.count()).select_from(AuditEventRecord))

    assert linked.status_code == 200
    assert edge.status_code == 201
    assert listing.status_code == 200
    assert listing.json()["data"]["total"] == 1
    assert listing.json()["data"]["list"][0]["id"] == source_id
    assert detail.json()["data"]["fields"][0]["field_name"] == "order_id"
    assert lineage.json()["data"]["edges"][0]["target_asset_id"] == target_id
    assert denied.status_code == 403
    assert audit_count == 5
    timestamps = detail.json()["data"]
    assert timestamps["created_at"] and timestamps["updated_at"]


def test_quality_standards_metrics_are_real_records_and_mutations_audited():
    with governance_client() as (client, app, headers):
        project_id = client.get("/api/v1/rebuild/projects", headers=headers).json()["data"]["list"][0]["id"]
        asset = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/assets",
            headers=headers,
            json={
                "source_system": "mysql-src",
                "database_name": "warehouse",
                "schema_name": "dwd",
                "asset_name": "fact_orders",
                "asset_type": "table",
            },
        ).json()["data"]
        rule = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/quality-rules",
            headers=headers,
            json={"asset_id": asset["id"], "name": "non-empty", "expression": "order_id IS NOT NULL"},
        )
        standard = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/standards",
            headers=headers,
            json={"code": "ORDER_ID", "name": "订单标识", "data_type": "BIGINT"},
        )
        metric = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/metrics",
            headers=headers,
            json={"code": "ORDER_COUNT", "name": "订单数", "formula": "count(order_id)"},
        )
        rules = client.get(f"/api/v1/rebuild/governance/projects/{project_id}/quality-rules", headers=headers)
        standards = client.get(f"/api/v1/rebuild/governance/projects/{project_id}/standards", headers=headers)
        metrics = client.get(f"/api/v1/rebuild/governance/projects/{project_id}/metrics", headers=headers)
        audit = client.get(f"/api/v1/rebuild/governance/projects/{project_id}/audit", headers=headers)
        with app.state.session_factory() as session:
            generated = session.scalar(select(AuditEventRecord.generated_at).limit(1))

    assert rule.status_code == standard.status_code == metric.status_code == 201
    assert rules.json()["data"]["list"][0]["expression"] == "order_id IS NOT NULL"
    assert standards.json()["data"]["list"][0]["status"] == "draft"
    assert metrics.json()["data"]["list"][0]["formula"] == "count(order_id)"
    assert audit.json()["data"]["total"] == 4
    assert isinstance(generated, datetime)


def test_failed_tag_assignment_rolls_back_without_audit_event():
    with governance_client() as (client, app, headers):
        project_id = client.get("/api/v1/rebuild/projects", headers=headers).json()["data"]["list"][0]["id"]
        asset = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/assets",
            headers=headers,
            json={
                "source_system": "mysql-src",
                "database_name": "warehouse",
                "schema_name": "ods",
                "asset_name": "orders",
                "asset_type": "table",
            },
        ).json()["data"]
        result = client.put(
            f"/api/v1/rebuild/governance/assets/{asset['id']}/tags",
            headers=headers,
            json={"tag_ids": [987654]},
        )
        with app.state.session_factory() as session:
            audit_count = session.scalar(select(func.count()).select_from(AuditEventRecord))

    assert result.status_code == 404
    assert audit_count == 1


def test_tag_creation_can_atomically_attach_to_asset_and_audit_both_records():
    with governance_client() as (client, app, headers):
        project_id = client.get("/api/v1/rebuild/projects", headers=headers).json()["data"]["list"][0]["id"]
        asset = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/assets",
            headers=headers,
            json={
                "source_system": "mysql-src",
                "database_name": "warehouse",
                "schema_name": "ods",
                "asset_name": "orders",
                "asset_type": "table",
            },
        ).json()["data"]
        tag = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/tags",
            headers=headers,
            json={
                "namespace": "domain",
                "tag_key": "sales",
                "display_name": "Sales",
                "asset_id": asset["id"],
            },
        )
        detail = client.get(f"/api/v1/rebuild/governance/assets/{asset['id']}", headers=headers)
        with app.state.session_factory() as session:
            audit_count = session.scalar(select(func.count()).select_from(AuditEventRecord))

    assert tag.status_code == 201
    assert [item["tag_key"] for item in detail.json()["data"]["tags"]] == ["sales"]
    assert audit_count == 2
