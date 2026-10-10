"""I13 smoke checks that do not require pytest.

This script is intentionally small and dependency-free so it can run inside the
runtime image when dev-only test packages are unavailable.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.dialects.mysql import LONGTEXT, MEDIUMTEXT
from sqlalchemy.ext.compiler import compiles
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.auth import get_current_user
from api.alerts import list_alerts
from api.baseline import baseline_progress
from api.health import health
from api.lineage import lineage_graph, lineage_stats
from api.main import app
from api.component import component_stats, raw_catalog
from api.monitor import monitor_nodes
from common import models
from common.db import get_db
from common.monitor import known_nodes_key, metrics_key
from common.resp import (
    COMP_SPEC_INVALID,
    WF_GRAPH_RULE_FAILED,
    WF_RELEASED_LOCKED,
    fail,
)


@compiles(LONGTEXT, "sqlite")
def _sqlite_longtext(_type, compiler, **kw) -> str:  # noqa: ANN001, ARG001
    return "TEXT"


@compiles(MEDIUMTEXT, "sqlite")
def _sqlite_mediumtext(_type, compiler, **kw) -> str:  # noqa: ANN001, ARG001
    return "TEXT"


def _session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    models.Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _client():
    from fastapi.testclient import TestClient

    SessionLocal = _session_factory()

    def override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_user():
        return SimpleNamespace(id=1, user_name="smoke", user_role="admin", state="enabled")

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return TestClient(app)


def _assert_ok(response, path: str) -> dict:
    assert response.status_code == 200, f"{path} status={response.status_code} body={response.text}"
    body = response.json()
    assert body["code"] == 0, f"{path} code={body.get('code')} body={body}"
    return body["data"]


def _route_probe() -> dict:
    client = _client()
    _assert_ok(client.get("/api/v1/health"), "/api/v1/health")
    comp_stats = _assert_ok(client.get("/api/v1/components/stats"), "/api/v1/components/stats")
    assert comp_stats["stats"]["total"] >= 35
    baseline = _assert_ok(client.get("/api/v1/components/baseline/progress"), "/api/v1/components/baseline/progress")
    assert baseline["stats"]["total"] == 36
    lin_stats = _assert_ok(client.get("/api/v1/lineage/stats"), "/api/v1/lineage/stats")
    assert {"edgeCount", "fieldCount", "tableCount", "wfCount", "lastTime"}.issubset(lin_stats)
    lin_graph = _assert_ok(client.get("/api/v1/lineage/graph"), "/api/v1/lineage/graph")
    assert lin_graph == {"nodes": [], "edges": [], "opaques": [], "truncated": False}
    mon = _assert_ok(client.get("/api/v1/monitor/nodes"), "/api/v1/monitor/nodes")
    assert {"zkAvailable", "generatedAt", "nodes"}.issubset(mon)
    alerts = _assert_ok(client.get("/api/v1/alerts"), "/api/v1/alerts")
    assert alerts == []
    return {"baseline": baseline, "lineageStats": lin_stats, "monitor": mon, "mode": "route"}


def _direct_probe() -> dict:
    SessionLocal = _session_factory()
    db = SessionLocal()
    try:
        fake_user = SimpleNamespace(id=1, user_name="smoke", user_role="admin", state="enabled")
        fake_request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(registry=None)))
        assert health(fake_request, db)["data"]["status"] == "UP"
        comp_stats = component_stats()["data"]
        assert comp_stats["stats"]["total"] >= 35
        baseline = baseline_progress(user=fake_user, db=db)["data"]
        assert baseline["stats"]["total"] == 36
        lin_stats = lineage_stats(user=fake_user, db=db)["data"]
        assert {"edgeCount", "fieldCount", "tableCount", "wfCount", "lastTime"}.issubset(lin_stats)
        lin_graph = lineage_graph(
            level="table",
            source="all",
            wf_code=None,
            table=None,
            direction="both",
            depth=0,
            limit=200,
            user=fake_user,
            db=db,
        )
        assert lin_graph["data"] == {"nodes": [], "edges": [], "opaques": [], "truncated": False}
        mon = monitor_nodes(fake_request, user=fake_user, db=db)["data"]
        assert {"zkAvailable", "generatedAt", "nodes"}.issubset(mon)
        assert list_alerts(limit=20, user=fake_user, db=db)["data"] == []
        return {"baseline": baseline, "lineageStats": lin_stats, "monitor": mon, "mode": "direct"}
    finally:
        db.close()


def _api_probe() -> dict:
    try:
        return _route_probe()
    except RuntimeError as exc:
        if "testclient" not in str(exc).lower() and "httpx" not in str(exc).lower():
            raise
        return _direct_probe()


def main() -> None:
    assert len(app.routes) > 0
    assert WF_GRAPH_RULE_FAILED == 2006
    assert WF_RELEASED_LOCKED == 2007
    assert COMP_SPEC_INVALID == 6008
    assert fail(1, data={"x": 1})["data"]["x"] == 1
    assert metrics_key("api", "n1") == "monitor:api:n1"
    assert known_nodes_key("worker") == "monitor:known:worker"
    catalog = raw_catalog()["data"]
    assert catalog.get("components")
    stats = component_stats()["data"]
    assert stats.get("stats") is not None

    probe = _api_probe()
    baseline = probe["baseline"]
    lin_stats = probe["lineageStats"]
    monitor = probe["monitor"]

    print(
        "i13_smoke_ok",
        {
            "routes": len(app.routes),
            "catalogItems": len(catalog["components"]),
            "catalogHash": catalog.get("catalogHash"),
            "baselineTotal": baseline["stats"]["total"],
            "lineageEdges": lin_stats["edgeCount"],
            "monitorNodes": len(monitor["nodes"]),
            "probeMode": probe["mode"],
        },
    )


if __name__ == "__main__":
    main()
