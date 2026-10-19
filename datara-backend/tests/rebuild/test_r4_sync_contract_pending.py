"""SYNC contract routes are now part of the accepted OpenAPI surface."""

from rebuild.api.app import create_app


def test_r4_sync_contract_routes_are_registered():
    app = create_app(
        "sqlite+pysqlite:///:memory:",
        token_secret="pending-r4-contract-test-secret",
        validation_key="pending-r4-contract-test-key",
    )
    paths = app.openapi()["paths"]
    assert "get" in paths["/api/v1/rebuild/sync/capabilities"]
    assert "post" in paths["/api/v1/rebuild/sync/plans"]
    assert "post" in paths["/api/v1/rebuild/sync/mappings/auto"]
