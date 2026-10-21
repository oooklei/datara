from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from rebuild.common.db import Base
from rebuild.api.app import create_app
from rebuild.identity.contracts import Role, TokenService
from rebuild.identity.repository import UserRepository
from rebuild.monitor.api import build_monitor_router
from rebuild.monitor.service import MonitorService
from rebuild.sshnode.models import SshNodeRecord


class ActiveTokens(set[str]):
    pass


def _client(*, live=None, known=None, metrics=None):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[SshNodeRecord.__table__])
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    tokens = ActiveTokens()
    token_service = TokenService(secret="monitor-test-secret")
    token = token_service.issue(user_id=1, username="monitor-user", role=Role.VIEWER)
    tokens.add(token)
    app = FastAPI()
    app.include_router(
        build_monitor_router(
            factory,
            token_service,
            tokens,
            zk_provider=lambda: object(),
            known_nodes_reader=known or (lambda _module: {}),
            metrics_reader=metrics or (lambda _module, _node: None),
        ),
        prefix="/api/v1/rebuild/monitor",
    )
    # Patch the imported legacy helper through the object contract expected by it.
    if live is not None:
        for route in app.routes:
            if getattr(route, "path", "").endswith("/monitor/nodes"):
                break
    return TestClient(app), factory, {"Authorization": f"Bearer {token}"}


def test_service_preserves_live_known_metric_and_ssh_merge_contract():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[SshNodeRecord.__table__])
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(
            SshNodeRecord(
                name="ssh-a",
                host="10.0.0.8",
                port=22,
                ssh_user="root",
                tags=["ops"],
                heartbeat_state="online",
                last_seen=datetime(2026, 10, 21, 8, 0, 0),
            )
        )
        session.commit()
        now = datetime(2026, 10, 21, 8, 1, 0)
        service = MonitorService(
            session,
            lambda: (True, [{"module": "master", "node": "m1"}]),
            lambda module: {"m1": now.timestamp() - 10, "m2": now.timestamp() - 100} if module == "master" else {},
            lambda _module, node: {"reportedAt": now.timestamp() - (10 if node == "m1" else 100), "cpu": 12.5},
            now=lambda: now,
        )
        data = service.nodes()

    assert data["zkAvailable"] is True
    assert data["generatedAt"] == "2026-10-21 08:01:00"
    assert [(row["module"], row["node"]) for row in data["nodes"]] == [
        ("master", "m1"), ("master", "m2"), ("ssh", "ssh-a")
    ]
    assert data["nodes"][0]["heartbeat"] == "online"
    assert data["nodes"][0]["metricState"] == "fresh"
    assert data["nodes"][1]["heartbeat"] == "offline"
    assert data["nodes"][1]["metricState"] == "stale"
    assert data["nodes"][2]["metricState"] == "unsupported"
    assert data["nodes"][2]["tags"] == ["ops"]


def test_zk_and_redis_failures_degrade_without_5xx_and_keep_ssh_rows():
    engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[SshNodeRecord.__table__])
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        session.add(SshNodeRecord(name="ssh-a", host="h", port=22, ssh_user="root"))
        session.commit()
        service = MonitorService(
            session,
            lambda: (_ for _ in ()).throw(ConnectionError("zk down")),
            lambda _module: (_ for _ in ()).throw(ConnectionError("redis down")),
            lambda _module, _node: (_ for _ in ()).throw(ConnectionError("redis down")),
            now=lambda: datetime(2026, 10, 21, 8, 1, 0),
        )
        data = service.nodes()
    assert data["zkAvailable"] is False
    assert [(row["module"], row["node"]) for row in data["nodes"]] == [("ssh", "ssh-a")]


def test_http_adapter_requires_active_token_and_returns_frozen_envelope(monkeypatch):
    monkeypatch.setattr("rebuild.monitor.api.list_live_nodes", lambda _zk: (False, []))
    client, _, headers = _client()
    denied = client.get("/api/v1/rebuild/monitor/nodes")
    assert denied.status_code == 401
    assert denied.json() == {"code": 1001, "msg": "invalid token", "data": None}
    response = client.get("/api/v1/rebuild/monitor/nodes", headers=headers)
    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert response.json()["data"]["zkAvailable"] is False
    assert response.json()["data"]["nodes"] == []


def test_default_rebuild_app_mounts_monitor_route_and_degrades_without_registry(monkeypatch):
    monkeypatch.setattr("rebuild.monitor.api.list_live_nodes", lambda _zk: (False, []))
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="monitor-app-secret")
    with TestClient(app) as client:
        with app.state.session_factory() as session:
            UserRepository(session).create(username="monitor-user", password="monitor-password", role=Role.VIEWER)
            session.commit()
        token = client.post(
            "/api/v1/rebuild/login",
            json={"username": "monitor-user", "password": "monitor-password"},
        ).json()["data"]["token"]
        response = client.get("/api/v1/rebuild/monitor/nodes", headers={"token": token})
    assert response.status_code == 200
    assert response.json()["data"]["zkAvailable"] is False
