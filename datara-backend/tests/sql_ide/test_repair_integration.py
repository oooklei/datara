"""Tests for Track A repair: schema migration + create_app DI + run_sql runtime.

TDD repair tests (Codex #280 FAIL → supervisor #283 dispatch):
- Gap3: audit table exists after lifespan + DB integration (real ORM)
- Gap4: create_app instantiates execution port + audit writer + mounts run_sql runtime
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from rebuild.common.db import Base
from rebuild.sql_ide.audit import SqlIdeAuditRecord, build_audit_writer
from rebuild.sql_ide.execution import build_execution_port


def _make_app():
    """Create app with TestClient-triggered lifespan (in-memory sqlite)."""
    from rebuild.api.app import create_app

    with patch.dict(os.environ, {
        "REBUILD_DB_URL": "sqlite:///:memory:",
        "REBUILD_TOKEN_SECRET": "test-secret",
    }, clear=True):
        app = create_app()
        with TestClient(app):
            pass
        return app


def _make_file_app():
    """Create app with temp-file sqlite DB (persists after TestClient exits)."""
    from rebuild.api.app import create_app

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_url = f"sqlite:///{tmp.name}"
    with patch.dict(os.environ, {
        "REBUILD_DB_URL": db_url,
        "REBUILD_TOKEN_SECRET": "test-secret",
    }, clear=True):
        app = create_app()
        with TestClient(app):
            pass
        return app, tmp.name


def _dispose_app(app):
    """Dispose the app's engine to release file locks on Windows."""
    engine = app.state.session_factory.kw["bind"]
    engine.dispose()


# ---------------------------------------------------------------------------
# Gap3: schema migration
# ---------------------------------------------------------------------------


class TestSchemaMigration:
    """Audit table is created by create_app lifespan."""

    def test_audit_table_exists_after_lifespan(self):
        """SqlIdeAuditRecord.__table__ must be in lifespan create_all."""
        from rebuild.api.app import create_app

        with patch.dict(os.environ, {
            "REBUILD_DB_URL": "sqlite:///:memory:",
            "REBUILD_TOKEN_SECRET": "test-secret",
        }, clear=True):
            app = create_app()
            # Check tables INSIDE TestClient context (before engine.dispose)
            with TestClient(app):
                engine = app.state.session_factory.kw["bind"]
                inspector = inspect(engine)
                table_names = inspector.get_table_names()
                assert "rebuild_sql_ide_audit" in table_names

    def test_audit_table_has_required_columns(self):
        """Audit table has all required columns."""
        from rebuild.api.app import create_app

        with patch.dict(os.environ, {
            "REBUILD_DB_URL": "sqlite:///:memory:",
            "REBUILD_TOKEN_SECRET": "test-secret",
        }, clear=True):
            app = create_app()
            with TestClient(app):
                engine = app.state.session_factory.kw["bind"]
                inspector = inspect(engine)
                columns = {col["name"] for col in inspector.get_columns("rebuild_sql_ide_audit")}
                required = {
                    "audit_id", "project_id", "user_id", "datasource_id",
                    "sql_digest", "task_id", "status", "stmt_count",
                    "elapsed_ms", "error_code", "created_at", "updated_at",
                }
                assert required.issubset(columns)


# ---------------------------------------------------------------------------
# Gap3: DB integration (real ORM, not mock)
# ---------------------------------------------------------------------------


class TestDbIntegration:
    """Real DB integration tests for audit writer."""

    def test_write_execution_start_persists_to_real_db(self):
        """write_execution_start inserts a real row."""
        app, db_path = _make_file_app()
        try:
            writer = build_audit_writer(session_factory=app.state.session_factory)
            audit_id = writer.write_execution_start(
                project_id=1,
                user_id=42,
                datasource_id=7,
                sql_digest="abc123",
                task_id="task-001",
            )
            # Verify the row exists in the real DB
            with app.state.session_factory() as session:
                record = session.scalar(
                    select(SqlIdeAuditRecord).where(SqlIdeAuditRecord.audit_id == audit_id)
                )
                assert record is not None
                assert record.project_id == 1
                assert record.user_id == 42
                assert record.datasource_id == 7
                assert record.sql_digest == "abc123"
                assert record.task_id == "task-001"
                assert record.status == "running"
        finally:
            _dispose_app(app)
            os.unlink(db_path)

    def test_write_execution_end_updates_real_db(self):
        """write_execution_end updates the real row."""
        app, db_path = _make_file_app()
        try:
            writer = build_audit_writer(session_factory=app.state.session_factory)
            audit_id = writer.write_execution_start(
                project_id=1, user_id=1, datasource_id=1,
                sql_digest="x", task_id="t1",
            )
            writer.write_execution_end(
                audit_id=audit_id,
                status="success",
                stmt_count=3,
                elapsed_ms=1500,
            )
            with app.state.session_factory() as session:
                record = session.scalar(
                    select(SqlIdeAuditRecord).where(SqlIdeAuditRecord.audit_id == audit_id)
                )
                assert record.status == "success"
                assert record.stmt_count == 3
                assert record.elapsed_ms == 1500
                assert record.error_code is None
        finally:
            _dispose_app(app)
            os.unlink(db_path)

    def test_write_execution_end_with_error_code(self):
        """write_execution_end with error_code persists."""
        app, db_path = _make_file_app()
        try:
            writer = build_audit_writer(session_factory=app.state.session_factory)
            audit_id = writer.write_execution_start(
                project_id=1, user_id=1, datasource_id=1,
                sql_digest="x", task_id="t1",
            )
            writer.write_execution_end(
                audit_id=audit_id,
                status="failed",
                stmt_count=1,
                elapsed_ms=500,
                error_code="EXECUTION_FAILED",
            )
            with app.state.session_factory() as session:
                record = session.scalar(
                    select(SqlIdeAuditRecord).where(SqlIdeAuditRecord.audit_id == audit_id)
                )
                assert record.status == "failed"
                assert record.error_code == "EXECUTION_FAILED"
        finally:
            _dispose_app(app)
            os.unlink(db_path)


# ---------------------------------------------------------------------------
# Gap4: create_app DI
# ---------------------------------------------------------------------------


class TestCreateAppDI:
    """create_app instantiates production execution port and audit writer."""

    def test_execution_port_in_app_state(self):
        """create_app saves execution port to app.state."""
        app = _make_app()
        assert hasattr(app.state, "execution_port")
        assert app.state.execution_port is not None

    def test_audit_writer_in_app_state(self):
        """create_app saves audit writer to app.state."""
        app = _make_app()
        assert hasattr(app.state, "audit_writer")
        assert app.state.audit_writer is not None

    def test_execution_port_is_production(self):
        """app.state.execution_port is ProductionSqlExecutionPort."""
        from rebuild.sql_ide.execution import ProductionSqlExecutionPort

        app = _make_app()
        assert isinstance(app.state.execution_port, ProductionSqlExecutionPort)

    def test_audit_writer_is_db_backed(self):
        """app.state.audit_writer is DbBackedAuditWriter."""
        from rebuild.sql_ide.audit import DbBackedAuditWriter

        app = _make_app()
        assert isinstance(app.state.audit_writer, DbBackedAuditWriter)


# ---------------------------------------------------------------------------
# Gap4: run_sql runtime mounted
# ---------------------------------------------------------------------------


class TestRunSqlRuntime:
    """create_app mounts run_sql runtime when ai_bridge_ports provided."""

    def test_bridge_mounted_with_explicit_ports(self):
        """AI bridge is mounted when ai_bridge_ports is provided."""
        from rebuild.api.app import create_app
        from rebuild.ai_bridge import AiBridgePorts

        with patch.dict(os.environ, {
            "REBUILD_DB_URL": "sqlite:///:memory:",
            "REBUILD_TOKEN_SECRET": "test-secret",
        }, clear=True):
            ports = AiBridgePorts(
                handlers={},
                audit_writer=MagicMock(),
            )
            app = create_app(ai_bridge_ports=ports)
            # Check routes inside TestClient context
            with TestClient(app) as client:
                response = client.get("/api/v1/rebuild/ai/tools")
                # Should get 401 (unauthorized) not 404 (not found)
                assert response.status_code == 401

    def test_bridge_not_mounted_without_explicit_ports(self):
        """AI bridge is NOT mounted without explicit ports (fail-closed)."""
        from rebuild.api.app import create_app

        with patch.dict(os.environ, {
            "REBUILD_DB_URL": "sqlite:///:memory:",
            "REBUILD_TOKEN_SECRET": "test-secret",
        }, clear=True):
            app = create_app()
            with TestClient(app) as client:
                response = client.get("/api/v1/rebuild/ai/tools")
                # Should get 404 (not found) - bridge not mounted
                assert response.status_code == 404

    def test_execution_port_available_for_runtime(self):
        """app.state.execution_port is available for runtime wiring."""
        app = _make_app()
        assert hasattr(app.state, "execution_port")
        assert app.state.execution_port is not None
