from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from rebuild.api.app import create_app
from rebuild.common.db import Base
from rebuild.governance.migrations import MigrationRunner, R3_GOVERNANCE_MIGRATIONS
from rebuild.governance.models import (
    AuditEventRecord,
    QualityExceptionRecord,
    QualityRunLegacyDetailsRecord,
    QualityRunRecord,
    QualityRuleRecord,
    SemanticMetricProfileRecord,
)
from rebuild.project.models import ProjectRecord


@contextmanager
def governance_client(quality_dbx_client_factory=None):
    app = create_app(
        "sqlite+pysqlite:///:memory:", token_secret="governance-api-test-secret", validation_key="governance-key",
        quality_dbx_client_factory=quality_dbx_client_factory,
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


def test_bound_quality_rule_uses_visible_dbx_connection_and_persists_real_counts():
    calls = []

    class FakeDbx:
        def execute_sql(self, **kwargs):
            calls.append(kwargs)
            return {"columns": ["checked_rows", "failed_rows"], "rows": [["60002", "2"]], "truncated": False}

    with governance_client(lambda: FakeDbx()) as (client, app, headers):
        from rebuild.dbx.access import DbxConnectionAccess

        project_id = client.get("/api/v1/rebuild/projects", headers=headers).json()["data"]["list"][0]["id"]
        asset = client.post(f"/api/v1/rebuild/governance/projects/{project_id}/assets", headers=headers, json={
            "source_system": "MySQL", "database_name": "ec_retail", "asset_name": "dim_user",
            "asset_type": "table", "fields": [{"field_name": "id_card", "ordinal_position": 1}],
        }).json()["data"]
        rule = client.post(f"/api/v1/rebuild/governance/projects/{project_id}/quality-rules", headers=headers, json={
            "asset_id": asset["id"], "name": "身份证格式", "expression": "LENGTH(TRIM(id_card)) = 18",
        }).json()["data"]
        denied = client.put(
            f"/api/v1/rebuild/governance/projects/{project_id}/assets/{asset['id']}/dbx-binding",
            headers=headers, json={"connection_id": "someone-else"},
        )
        with app.state.session_factory() as session:
            DbxConnectionAccess(session).claim(connection_id="customer-src", project_id=project_id, owner_id=1)
            session.commit()
        bound = client.put(
            f"/api/v1/rebuild/governance/projects/{project_id}/assets/{asset['id']}/dbx-binding",
            headers=headers, json={"connection_id": "customer-src"},
        )
        run = client.post(f"/api/v1/rebuild/governance/projects/{project_id}/quality-rules/{rule['id']}/run", headers=headers)
        unbound = client.put(
            f"/api/v1/rebuild/governance/projects/{project_id}/assets/{asset['id']}/dbx-binding",
            headers=headers, json={"connection_id": None},
        )

    assert denied.status_code == 403
    assert bound.status_code == 200
    assert bound.json()["data"]["dbx_connection_id"] == "customer-src"
    assert unbound.json()["data"]["dbx_connection_id"] is None
    assert run.status_code == 201
    result = run.json()["data"]
    assert result["status"] == "failed"
    assert (result["checked_rows"], result["failed_rows"], result["success_rows"]) == (60002, 2, 60000)
    assert result["summary"]["engine"] == "dbx"
    assert len(calls) == 1 and calls[0]["connection_id"] == "customer-src"
    assert "SELECT COUNT(*)" in calls[0]["sql"]


def test_admin_can_claim_an_existing_dbx_connection_when_binding_an_asset():
    from rebuild.identity.contracts import Role, TokenService
    from rebuild.identity.models import UserRecord
    from rebuild.dbx.models import DbxConnectionOwnershipRecord

    class FakeDbx:
        def list_connections(self):
            return [{"id": "legacy-src"}]

    with governance_client(lambda: FakeDbx()) as (client, app, headers):
        project_id = client.get("/api/v1/rebuild/projects", headers=headers).json()["data"]["list"][0]["id"]
        asset = client.post(f"/api/v1/rebuild/governance/projects/{project_id}/assets", headers=headers, json={
            "source_system": "MySQL", "database_name": "ec_retail", "asset_name": "dim_user",
            "asset_type": "table",
        }).json()["data"]
        with app.state.session_factory() as session:
            session.add(UserRecord(id=2, username="admin", role=Role.ADMIN, password_hash="x"))
            session.commit()
        temporary = client.post(
            "/api/v1/rebuild/validation-token",
            headers={"X-Backend-Validation-Key": "governance-key", "X-Backend-Validation-Scope": "high-priority-e2e"},
        ).json()["data"]["token"]
        temporary_denied = client.put(
            f"/api/v1/rebuild/governance/projects/{project_id}/assets/{asset['id']}/dbx-binding",
            headers={"Authorization": f"Bearer {temporary}"}, json={"connection_id": "legacy-src"},
        )
        token = TokenService(secret="governance-api-test-secret", ttl_seconds=3600).issue(
            user_id=2, username="admin", role=Role.ADMIN,
        )
        app.state.active_tokens.add(token, user_id=2, username="admin", role=Role.ADMIN.value)
        bound = client.put(
            f"/api/v1/rebuild/governance/projects/{project_id}/assets/{asset['id']}/dbx-binding",
            headers={"Authorization": f"Bearer {token}"}, json={"connection_id": "legacy-src"},
        )
        with app.state.session_factory() as session:
            owner = session.get(DbxConnectionOwnershipRecord, "legacy-src")
            assert owner is not None
            assert (owner.project_id, owner.owner_id) == (project_id, 2)
    assert bound.status_code == 200
    assert temporary_denied.status_code == 403


def test_asset_fields_can_be_replaced_with_project_permission_and_audit():
    with governance_client() as (client, _app, headers):
        project_id = client.get("/api/v1/rebuild/projects", headers=headers).json()["data"]["list"][0]["id"]
        asset = client.post(f"/api/v1/rebuild/governance/projects/{project_id}/assets", headers=headers, json={
            "source_system": "MySQL", "database_name": "ec_retail", "asset_name": "ods_order",
            "asset_type": "table",
        }).json()["data"]
        url = f"/api/v1/rebuild/governance/projects/{project_id}/assets/{asset['id']}/fields"
        invalid = client.put(url, headers=headers, json={"fields": [
            {"field_name": "order_no", "ordinal_position": 1},
            {"field_name": "ORDER_NO", "ordinal_position": 2},
        ]})
        saved = client.put(url, headers=headers, json={"fields": [
            {"field_name": "id", "ordinal_position": 1, "data_type": "bigint"},
            {"field_name": "order_no", "ordinal_position": 2, "data_type": "varchar(64)"},
        ]})
        denied = client.put(f"/api/v1/rebuild/governance/projects/2/assets/{asset['id']}/fields", headers=headers, json={
            "fields": [{"field_name": "id", "ordinal_position": 1}],
        })
        audit = client.get(f"/api/v1/rebuild/governance/projects/{project_id}/audit", headers=headers)
    assert invalid.status_code == 400
    assert saved.status_code == 200
    assert [field["field_name"] for field in saved.json()["data"]["fields"]] == ["id", "order_no"]
    assert denied.status_code == 403
    assert any(item["action"] == "asset.fields.replace" for item in audit.json()["data"]["list"])


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
        tag_listing = client.get(
            f"/api/v1/rebuild/governance/projects/{project_id}/tags", headers=headers,
        )
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
    assert tag_listing.json()["data"]["total"] == 1
    assert tag_listing.json()["data"]["list"][0]["id"] == tag_id
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


def test_quality_rule_run_requires_a_bound_connection():
    with governance_client() as (client, app, headers):
        project_id = client.get("/api/v1/rebuild/projects", headers=headers).json()["data"]["list"][0]["id"]
        asset = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/assets",
            headers=headers,
            json={
                "source_system": "mysql-src",
                "database_name": "warehouse",
                "schema_name": "dwd",
                "asset_name": "fact_orders_run",
                "asset_type": "table",
            },
        ).json()["data"]
        rule = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/quality-rules",
            headers=headers,
            json={"asset_id": asset["id"], "name": "run-ok", "expression": "order_id IS NOT NULL"},
        ).json()["data"]
        resp = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/quality-rules/{rule['id']}/run",
            headers=headers,
        )
        runs = client.get(f"/api/v1/rebuild/governance/projects/{project_id}/quality-runs", headers=headers)
        audit = client.get(f"/api/v1/rebuild/governance/projects/{project_id}/audit", headers=headers)

    assert resp.status_code == 409
    assert "bound dbx connection" in resp.json()["msg"]
    assert runs.json()["data"]["total"] == 0
    assert audit.json()["data"]["total"] == 2


def test_quality_rule_can_be_rebound_to_a_real_project_asset_with_audit():
    with governance_client() as (client, _app, headers):
        project_id = client.get("/api/v1/rebuild/projects", headers=headers).json()["data"]["list"][0]["id"]
        base = f"/api/v1/rebuild/governance/projects/{project_id}"
        assets = []
        for table in ("dwd_trade_order", "dim_user"):
            response = client.post(f"{base}/assets", headers=headers, json={
                "source_system": "mysql", "database_name": "ec_retail", "asset_name": table,
                "asset_type": "table",
            })
            assert response.status_code == 201
            assets.append(response.json()["data"]["id"])
        created = client.post(f"{base}/quality-rules", headers=headers, json={
            "asset_id": assets[0], "name": "手机号格式校验", "expression": "phone is not null",
        })
        assert created.status_code == 201
        rule_id = created.json()["data"]["id"]
        corrected = client.put(f"{base}/quality-rules/{rule_id}", headers=headers, json={
            "asset_id": assets[1], "name": "手机号格式校验", "expression": "LENGTH(phone) = 11", "severity": "error",
        })
        assert corrected.status_code == 200
        assert corrected.json()["data"]["asset_id"] == assets[1]
        assert corrected.json()["data"]["expression"] == "LENGTH(phone) = 11"
        assert client.put(f"{base}/quality-rules/{rule_id}", headers=headers, json={
            "asset_id": 99999, "name": "手机号格式校验", "expression": "1=1",
        }).status_code == 404
        listed = client.get(f"{base}/quality-rules", headers=headers).json()["data"]["list"]
        assert listed[0]["asset_id"] == assets[1]
        audit = client.get(f"{base}/audit", headers=headers).json()["data"]["list"]
        assert any(item["action"] == "quality_rule.update" and item["after"]["before"]["asset_id"] == assets[0] for item in audit)


def test_quality_rule_run_flags_forbidden_expression_as_failed():
    with governance_client() as (client, app, headers):
        project_id = client.get("/api/v1/rebuild/projects", headers=headers).json()["data"]["list"][0]["id"]
        asset = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/assets",
            headers=headers,
            json={
                "source_system": "mysql-src",
                "database_name": "warehouse",
                "schema_name": "dwd",
                "asset_name": "fact_orders_bad",
                "asset_type": "table",
            },
        ).json()["data"]
        rule = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/quality-rules",
            headers=headers,
            json={"asset_id": asset["id"], "name": "run-bad", "expression": "1=1; DROP TABLE t"},
        ).json()["data"]
        resp = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/quality-rules/{rule['id']}/run",
            headers=headers,
        )

    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["status"] == "failed"
    assert data["summary"]["issues"]


def test_quality_rule_run_guards_missing_and_disabled():
    with governance_client() as (client, app, headers):
        project_id = client.get("/api/v1/rebuild/projects", headers=headers).json()["data"]["list"][0]["id"]
        missing = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/quality-rules/99999/run",
            headers=headers,
        )
        asset = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/assets",
            headers=headers,
            json={
                "source_system": "mysql-src",
                "database_name": "warehouse",
                "schema_name": "dwd",
                "asset_name": "fact_orders_disabled",
                "asset_type": "table",
            },
        ).json()["data"]
        disabled = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/quality-rules",
            headers=headers,
            json={"asset_id": asset["id"], "name": "run-off", "expression": "1=1", "enabled": False},
        ).json()["data"]
        denied = client.post(
            f"/api/v1/rebuild/governance/projects/{project_id}/quality-rules/{disabled['id']}/run",
            headers=headers,
        )

    assert missing.status_code == 404
    assert denied.status_code == 409


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


def test_tag_delete_detaches_asset_and_does_not_cross_projects():
    with governance_client() as (client, app, headers):
        project_id = client.get("/api/v1/rebuild/projects", headers=headers).json()["data"]["list"][0]["id"]
        base = f"/api/v1/rebuild/governance/projects/{project_id}"
        asset = client.post(f"{base}/assets", headers=headers, json={
            "source_system": "sim", "database_name": "sim", "asset_name": "orders", "asset_type": "table",
        }).json()["data"]
        tag = client.post(f"{base}/tags", headers=headers, json={
            "namespace": "ECOM_SIM", "tag_key": "temporary", "display_name": "Temporary", "asset_id": asset["id"],
        }).json()["data"]
        endpoint = f"{base}/tags/{tag['id']}"
        other_id = client.post("/api/v1/rebuild/projects", headers=headers, json={"name": "tag-other"}).json()["data"]["id"]
        assert client.delete(endpoint.replace(f"projects/{project_id}", f"projects/{other_id}"), headers=headers).status_code == 404
        assert client.delete(endpoint).status_code == 401
        deleted = client.delete(endpoint, headers=headers)
        assert deleted.status_code == 200
        assert deleted.json()["data"] == {"deleted": True, "id": tag["id"]}
        assert client.get(f"{base}/tags", headers=headers).json()["data"]["total"] == 0
        detail = client.get(f"/api/v1/rebuild/governance/assets/{asset['id']}", headers=headers)
        assert detail.json()["data"]["tags"] == []
        assert client.delete(endpoint, headers=headers).status_code == 404


def test_simple_governance_deletes_are_project_scoped_and_audited():
    cases = (
        ("standards", {"code": "SIM_STD", "name": "Sim standard", "data_type": "string"}),
        ("metrics", {"code": "SIM_METRIC", "name": "Sim metric", "formula": "count(*)"}),
        ("quality-reports", {"title": "Sim report"}),
        ("quality-alarm-policies", {
            "name": "Sim alarm", "metric": "failed_rows", "operator": ">", "threshold": 0,
        }),
    )
    with governance_client() as (client, app, headers):
        project_id = client.get("/api/v1/rebuild/projects", headers=headers).json()["data"]["list"][0]["id"]
        base = f"/api/v1/rebuild/governance/projects/{project_id}"
        other_id = client.post("/api/v1/rebuild/projects", headers=headers, json={"name": "definition-other"}).json()["data"]["id"]
        for resource, payload in cases:
            created = client.post(f"{base}/{resource}", headers=headers, json=payload)
            assert created.status_code == 201
            record_id = created.json()["data"]["id"]
            endpoint = f"{base}/{resource}/{record_id}"
            assert client.delete(endpoint.replace(f"projects/{project_id}", f"projects/{other_id}"), headers=headers).status_code == 404
            assert client.delete(endpoint).status_code == 401
            deleted = client.delete(endpoint, headers=headers)
            assert deleted.status_code == 200
            assert deleted.json()["data"] == {"deleted": True, "id": record_id}
            assert client.get(f"{base}/{resource}", headers=headers).json()["data"]["total"] == 0
            assert client.delete(endpoint, headers=headers).status_code == 404
        with app.state.session_factory() as session:
            actions = set(session.scalars(select(AuditEventRecord.action)).all())
        assert {"standard.delete", "metric.delete", "quality_report.delete", "quality_alarm_policy.delete"} <= actions


def test_quality_rule_delete_retains_run_history_without_dangling_rule_id():
    with governance_client() as (client, app, headers):
        project_id = client.get("/api/v1/rebuild/projects", headers=headers).json()["data"]["list"][0]["id"]
        base = f"/api/v1/rebuild/governance/projects/{project_id}"
        asset = client.post(f"{base}/assets", headers=headers, json={
            "source_system": "sim", "database_name": "sim", "asset_name": "orders", "asset_type": "table",
        }).json()["data"]
        rule = client.post(f"{base}/quality-rules", headers=headers, json={
            "asset_id": asset["id"], "name": "SIM_QC", "expression": "amount >= 0",
        }).json()["data"]
        with app.state.session_factory() as session:
            session.add(QualityRunRecord(
                project_id=project_id, asset_id=asset["id"], rule_id=rule["id"], status="succeeded",
                checked_rows=1, success_rows=1, failed_rows=0, skipped_rows=0,
            ))
            session.commit()
        endpoint = f"{base}/quality-rules/{rule['id']}"
        assert client.delete(endpoint).status_code == 401
        other_id = client.post("/api/v1/rebuild/projects", headers=headers, json={"name": "rule-other"}).json()["data"]["id"]
        assert client.delete(endpoint.replace(f"projects/{project_id}", f"projects/{other_id}"), headers=headers).status_code == 404
        assert client.delete(endpoint, headers=headers).status_code == 200
        assert client.get(f"{base}/quality-rules", headers=headers).json()["data"]["total"] == 0
        with app.state.session_factory() as session:
            run = session.scalar(select(QualityRunRecord).where(QualityRunRecord.project_id == project_id))
            assert run is not None and run.rule_id is None


def test_project_delete_cleans_governance_graph_and_preserves_audit():
    with governance_client() as (client, app, headers):
        project_id = client.get("/api/v1/rebuild/projects", headers=headers).json()["data"]["list"][0]["id"]
        base = f"/api/v1/rebuild/governance/projects/{project_id}"
        asset = client.post(f"{base}/assets", headers=headers, json={
            "source_system": "sim", "database_name": "sim", "asset_name": "orders", "asset_type": "table",
        }).json()["data"]
        assert client.post(f"{base}/tags", headers=headers, json={
            "namespace": "ECOM_SIM", "tag_key": "temporary", "display_name": "Temporary", "asset_id": asset["id"],
        }).status_code == 201
        assert client.post(f"{base}/quality-rules", headers=headers, json={
            "asset_id": asset["id"], "name": "SIM_QC", "expression": "amount >= 0",
        }).status_code == 201
        assert client.post(f"{base}/standards", headers=headers, json={
            "code": "SIM_STD", "name": "Sim standard", "data_type": "string",
        }).status_code == 201
        metric = client.post(f"{base}/metrics", headers=headers, json={
            "code": "SIM_METRIC", "name": "Sim metric", "formula": "count(*)",
        })
        assert metric.status_code == 201
        assert client.post(f"{base}/quality-reports", headers=headers, json={"title": "Sim report"}).status_code == 201
        assert client.post(f"{base}/quality-alarm-policies", headers=headers, json={
            "name": "Sim alarm", "metric": "failed_rows", "operator": ">", "threshold": 0,
        }).status_code == 201
        with app.state.session_factory() as session:
            session.add(SemanticMetricProfileRecord(metric_id=metric.json()["data"]["id"]))
            run = QualityRunRecord(
                project_id=project_id, asset_id=asset["id"], status="succeeded",
                checked_rows=1, success_rows=1, failed_rows=0, skipped_rows=0,
            )
            session.add(run)
            session.flush()
            details = QualityRunLegacyDetailsRecord(quality_run_id=run.id)
            session.add(details)
            session.flush()
            session.add(QualityExceptionRecord(project_id=project_id, run_details_id=details.id))
            session.commit()
        deleted = client.delete(f"/api/v1/rebuild/projects/{project_id}", headers=headers)
        assert deleted.status_code == 200
        with app.state.session_factory() as session:
            assert session.get(ProjectRecord, project_id) is None
            for table in Base.metadata.tables.values():
                if table.name.startswith("rebuild_governance_") and "project_id" in table.c:
                    assert session.scalar(select(func.count()).select_from(table).where(table.c.project_id == project_id)) == 0, table.name
            assert session.scalar(select(func.count()).select_from(Base.metadata.tables["rebuild_governance_asset_tag"])) == 0
            assert session.scalar(select(func.count()).select_from(Base.metadata.tables["rebuild_governance_semantic_metric_profile"])) == 0
            assert session.scalar(select(func.count()).select_from(Base.metadata.tables["rebuild_governance_quality_run_legacy_details"])) == 0
            audit = session.scalars(select(AuditEventRecord)).all()
            assert audit and all(event.project_id is None for event in audit)


def test_project_delete_rejects_cross_project_governance_reference():
    with governance_client() as (client, app, headers):
        target = client.get("/api/v1/rebuild/projects", headers=headers).json()["data"]["list"][0]["id"]
        with app.state.session_factory() as session:
            other = session.scalar(select(ProjectRecord.id).where(ProjectRecord.name == "other-project"))
            assert other is not None
        asset = client.post(f"/api/v1/rebuild/governance/projects/{target}/assets", headers=headers, json={
            "source_system": "sim", "database_name": "sim", "asset_name": "shared_order", "asset_type": "table",
        }).json()["data"]
        with app.state.session_factory() as session:
            session.add(QualityRuleRecord(
                project_id=other, asset_id=asset["id"], name="foreign-rule",
                expression="amount >= 0", severity="warning", enabled=True,
            ))
            session.commit()
        deleted = client.delete(f"/api/v1/rebuild/projects/{target}", headers=headers)
        assert deleted.status_code == 409
        with app.state.session_factory() as session:
            assert session.get(ProjectRecord, target) is not None
            assert session.scalar(select(QualityRuleRecord).where(QualityRuleRecord.project_id == other)) is not None
