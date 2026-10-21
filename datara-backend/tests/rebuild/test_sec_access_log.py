"""Tests for the access-audit domain (rebuild/sec).

The sec router is not yet mounted on the application factory (route
registration is a pending single-writer-window integration step), so API
tests build a standalone FastAPI instance around ``build_sec_router`` with
an in-memory session factory, keeping the slice domain-self-contained.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from rebuild.common.db import Base
from rebuild.governance.migrations import MigrationRunner
from rebuild.governance.models import SchemaMigrationRecord
from rebuild.sec.api import build_sec_router
from rebuild.sec.middleware import SecAuditMiddleware, SecSqlAccessRecorder, install_sql_access_hook
from rebuild.sec.migrations import S1_SEC_MIGRATIONS
from rebuild.sec.models import SEC_TABLES, SecAccessLogRecord
from rebuild.sec.repository import SecRepository
from rebuild.sec.service import SecAccessRejected, SecService


def _memory_engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )


def _create_tables(engine) -> None:
    Base.metadata.create_all(bind=engine, tables=list(SEC_TABLES), checkfirst=True)


def test_model_persists_and_enforces_result_check():
    engine = _memory_engine()
    _create_tables(engine)
    with sessionmaker(bind=engine)() as session:
        session.add(
            SecAccessLogRecord(
                user_name="alice",
                action="query",
                target="orders",
                rows_seen=7,
                result="allow",
                reason="ok",
                request_id="req-1",
            )
        )
        session.commit()
        stored = session.scalar(select(SecAccessLogRecord))
        assert stored is not None
        assert stored.id == 1
        assert stored.rows_seen == 7
        assert stored.accessed_at is not None

        with pytest.raises(IntegrityError):
            session.add(
                SecAccessLogRecord(
                    user_name="bob",
                    action="query",
                    target="t2",
                    rows_seen=0,
                    result="denied",
                    reason="bad enum",
                )
            )
            session.commit()
        session.rollback()


def test_service_records_reject_and_denied_rows_are_force_zeroed():
    engine = _memory_engine()
    _create_tables(engine)
    factory = sessionmaker(bind=engine)
    with factory() as session:
        service = SecService(session)
        service.record_access(
            user_name="alice",
            action="query",
            target="orders",
            rows_seen=12,
            allowed=True,
            reason="ok",
            request_id="req-1",
        )
        service.record_access(
            user_name="bob",
            action="execute_sql",
            target="SELECT 1",
            rows_seen=5,
            allowed=False,
            reason="denied by rule",
        )
        service.record_access(user_name="alice", action="query", target="users", rows_seen=3, allowed=False)
        session.commit()

        with pytest.raises(SecAccessRejected):
            service.record_access(user_name="", action="query", target="x", rows_seen=1, allowed=True)
        with pytest.raises(SecAccessRejected):
            service.record_access(user_name="bob", action="query", target="x", rows_seen=-1, allowed=True)

        deny_rows, _total = SecRepository(session).query_access_logs(result="deny")
        assert [row.rows_seen for row in deny_rows] == [0, 0]

        rows, total = SecRepository(session).query_access_logs(user_name="alice")
        assert total == 2
        assert all(row.user_name == "alice" for row in rows)

        assert SecRepository(session).result_facets() == {"allow": 1, "deny": 2}


def test_query_pagination_orders_latest_first():
    engine = _memory_engine()
    _create_tables(engine)
    base = datetime(2026, 10, 22, 0, 0, 0)
    with sessionmaker(bind=engine)() as session:
        for i in range(5):
            session.add(
                SecAccessLogRecord(
                    user_name=f"u{i}",
                    action="query",
                    target=f"t{i}",
                    rows_seen=i,
                    result="allow",
                    reason="",
                    accessed_at=base + timedelta(minutes=i),
                )
            )
        session.commit()
        rows, total = SecRepository(session).query_access_logs(limit=2, offset=1)
        assert total == 5
        assert [row.target for row in rows] == ["t3", "t2"]


@contextmanager
def sec_api_client():
    engine = _memory_engine()
    _create_tables(engine)
    factory = sessionmaker(bind=engine)
    app = FastAPI()

    users = {
        "admin-token": {"user_id": 1, "username": "admin", "role": "admin"},
        "dev-token": {"user_id": 2, "username": "dev", "role": "developer"},
    }

    def current_user(authorization: str):
        name = authorization.removeprefix("Bearer ").strip()
        if not name or name not in users:
            raise ValueError("invalid token")
        return users[name]

    app.include_router(build_sec_router(factory, current_user))
    with TestClient(app) as client:
        with factory() as session:
            SecService(session).record_access(
                user_name="alice", action="query", target="orders", rows_seen=9, allowed=True, reason="ok"
            )
            SecService(session).record_access(
                user_name="mallory", action="query", target="secrets", rows_seen=1, allowed=False, reason="policy"
            )
            session.commit()
        yield client, factory


def test_access_logs_api_requires_valid_token():
    with sec_api_client() as (client, _factory):
        assert client.get("/api/v1/rebuild/sec/access-logs").status_code == 401
        ghost = client.get(
            "/api/v1/rebuild/sec/access-logs", headers={"Authorization": "Bearer ghost"}
        )
        assert ghost.status_code == 401
        assert ghost.json()["code"] == 1001


def test_access_logs_api_is_admin_only():
    with sec_api_client() as (client, _factory):
        response = client.get(
            "/api/v1/rebuild/sec/access-logs", headers={"Authorization": "Bearer dev-token"}
        )
    assert response.status_code == 403
    assert response.json()["code"] == 1003


def test_access_logs_api_returns_envelope_with_filters():
    with sec_api_client() as (client, _factory):
        headers = {"Authorization": "Bearer admin-token"}
        all_logs = client.get("/api/v1/rebuild/sec/access-logs", headers=headers)
        assert all_logs.status_code == 200
        payload = all_logs.json()
        assert payload["code"] == 0
        assert payload["msg"] == "success"
        assert payload["data"]["total"] == 2
        assert payload["data"]["facets"] == {"allow": 1, "deny": 1}
        assert len(payload["data"]["list"]) == 2

        denied = client.get(
            "/api/v1/rebuild/sec/access-logs", headers=headers, params={"result": "deny"}
        )
        assert denied.status_code == 200
        denied_list = denied.json()["data"]["list"]
        assert len(denied_list) == 1
        assert denied_list[0]["user_name"] == "mallory"
        assert denied_list[0]["rows_seen"] == 0
        assert denied_list[0]["result"] == "deny"
        assert denied_list[0]["accessed_at"] is not None

        bad = client.get(
            "/api/v1/rebuild/sec/access-logs", headers=headers, params={"result": "bogus"}
        )
        assert bad.status_code == 422
        assert bad.json()["code"] == 4221


def test_migration_runner_applies_sec_revision_idempotently(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'sec.db'}")
    try:
        runner = MigrationRunner(engine, S1_SEC_MIGRATIONS)
        result = runner.apply()
        assert result.applied == ("r10_0001_sec_access_log",)
        assert result.skipped == ()

        again = runner.apply()
        assert again.applied == ()
        assert again.skipped == ("r10_0001_sec_access_log",)

        with sessionmaker(bind=engine)() as session:
            record = session.scalar(
                select(SchemaMigrationRecord).where(
                    SchemaMigrationRecord.revision == "r10_0001_sec_access_log"
                )
            )
            assert record is not None
            assert record.status == "completed"
    finally:
        engine.dispose()


def test_sql_hook_buffers_digests_and_excludes_audit_table():
    engine = _memory_engine()
    _create_tables(engine)
    factory = sessionmaker(bind=engine)
    recorder = SecSqlAccessRecorder(factory)
    install_sql_access_hook(engine, recorder)

    with engine.connect() as connection:
        connection.execute(text("SELECT   1 AS probe FROM\n  sqlite_master LIMIT 1"))
        connection.execute(text("SELECT 1 FROM rebuild_sec_access_log"))
    assert recorder.pending_count() == 1

    assert recorder.flush() == 1
    assert recorder.flush() == 0
    assert recorder.pending_count() == 0

    with factory() as session:
        rows = session.scalars(select(SecAccessLogRecord)).all()
        assert len(rows) == 1
        assert rows[0].user_name == "system"
        assert rows[0].action == "execute_sql"
        assert rows[0].target == "SELECT 1 AS probe FROM sqlite_master LIMIT 1"
        assert rows[0].reason == "sql_execution_hook"


def test_http_middleware_records_audited_requests_and_skips_self():
    engine = _memory_engine()
    _create_tables(engine)
    factory = sessionmaker(bind=engine)

    app = FastAPI()

    @app.get("/api/v1/rebuild/orders")
    def list_orders():
        return {"ok": True}

    @app.get("/api/v1/rebuild/sec/access-logs")
    def sec_self():
        return {"ok": True}

    @app.post("/api/v1/rebuild/missing-scope")
    def denied():
        raise HTTPException(status_code=403, detail="denied")

    app.add_middleware(
        SecAuditMiddleware,
        session_factory=factory,
        user_extractor=lambda request: "audited-user",
    )

    with TestClient(app) as client:
        client.get("/api/v1/rebuild/orders")
        client.get("/api/v1/rebuild/sec/access-logs")
        client.post("/api/v1/rebuild/missing-scope")

    with factory() as session:
        rows = session.scalars(select(SecAccessLogRecord).order_by(SecAccessLogRecord.id)).all()
        assert len(rows) == 2
        first, second = rows
        assert (first.action, first.target, first.result, first.reason) == (
            "query",
            "/api/v1/rebuild/orders",
            "allow",
            "http_status_200",
        )
        assert (second.action, second.target, second.result, second.reason) == (
            "create",
            "/api/v1/rebuild/missing-scope",
            "deny",
            "http_status_403",
        )
        assert all(row.user_name == "audited-user" for row in rows)
