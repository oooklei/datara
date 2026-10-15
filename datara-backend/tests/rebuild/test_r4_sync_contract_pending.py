"""P1 pipeline contract RED; this test remains pending until R3 is accepted."""

import pytest

from rebuild.api.app import create_app


@pytest.mark.xfail(
    strict=False,
    reason="R4-SYNC contract pending acceptance; implementation is forbidden before R3 merge",
)
def test_r4_sync_plan_and_capability_routes_are_not_implemented_yet():
    app = create_app(
        "sqlite+pysqlite:///:memory:",
        token_secret="pending-r4-contract-test-secret",
        validation_key="pending-r4-contract-test-key",
    )
    registered = {
        (method, route.path)
        for route in app.routes
        if hasattr(route, "methods")
        for method in route.methods
    }

    assert ("GET", "/api/v1/rebuild/sync/capabilities") in registered
    assert ("POST", "/api/v1/rebuild/sync/plans") in registered
