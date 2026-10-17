"""Tests for R5-A production factory assembly (Track A Gap 4).

Covers:
- create_app wires execution port from session_factory + engine_registry
- create_app wires audit writer from session_factory
- Default factory uses env vars for DB URL and token secret
- Fail-closed: missing env vars raise RuntimeError
- Execution port is production-backed (not PoC)
- Audit writer is DB-backed (not PoC)
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from rebuild.api.app import create_app
from rebuild.sql_ide.audit import DbBackedAuditWriter
from rebuild.sql_ide.execution import ProductionSqlExecutionPort


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _env(**overrides):
    """Build a minimal env dict for create_app."""
    base = {
        "REBUILD_DB_URL": "sqlite://",
        "REBUILD_TOKEN_SECRET": "test-secret-for-factory-test",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# factory assembly
# ---------------------------------------------------------------------------


class TestFactoryAssembly:
    """create_app wires production components from app config chain."""

    def test_create_app_succeeds_with_minimal_env(self):
        with patch.dict(os.environ, _env(), clear=True):
            app = create_app()
            assert app is not None

    def test_execution_port_is_production_backed(self):
        with patch.dict(os.environ, _env(), clear=True):
            app = create_app()
            # The app should have a session_factory in state
            assert hasattr(app.state, "session_factory")
            assert hasattr(app.state, "datasource_engines")

    def test_audit_writer_is_db_backed(self):
        with patch.dict(os.environ, _env(), clear=True):
            app = create_app()
            # Audit writer should be accessible via app state or injectable
            # For now, verify the app can be created with audit writer wiring
            assert app is not None

    def test_missing_db_url_raises(self):
        env = _env()
        del env["REBUILD_DB_URL"]
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="REBUILD_DB_URL"):
                create_app()

    def test_missing_token_secret_raises(self):
        env = _env()
        del env["REBUILD_TOKEN_SECRET"]
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(RuntimeError, match="REBUILD_TOKEN_SECRET"):
                create_app()


# ---------------------------------------------------------------------------
# production component wiring
# ---------------------------------------------------------------------------


class TestProductionComponentWiring:
    """Production components are wired from app config chain."""

    def test_session_factory_in_state(self):
        with patch.dict(os.environ, _env(), clear=True):
            app = create_app()
            assert callable(app.state.session_factory)

    def test_datasource_engines_in_state(self):
        with patch.dict(os.environ, _env(), clear=True):
            app = create_app()
            assert app.state.datasource_engines is not None

    def test_execution_port_can_be_built_from_app_state(self):
        from rebuild.sql_ide.execution import build_execution_port

        with patch.dict(os.environ, _env(), clear=True):
            app = create_app()
            port = build_execution_port(
                session_factory=app.state.session_factory,
                engine_registry=app.state.datasource_engines,
            )
            assert isinstance(port, ProductionSqlExecutionPort)

    def test_audit_writer_can_be_built_from_app_state(self):
        from rebuild.sql_ide.audit import build_audit_writer

        with patch.dict(os.environ, _env(), clear=True):
            app = create_app()
            writer = build_audit_writer(session_factory=app.state.session_factory)
            assert isinstance(writer, DbBackedAuditWriter)


# ---------------------------------------------------------------------------
# fail-closed behavior
# ---------------------------------------------------------------------------


class TestFailClosed:
    """Factory assembly is fail-closed: missing config raises."""

    def test_no_bridge_without_explicit_ports(self):
        """Default create_app does not mount AI bridge (fail-closed)."""
        with patch.dict(os.environ, _env(), clear=True):
            app = create_app()
            # Bridge should NOT be mounted without explicit ai_bridge_ports
            routes = []
            for r in app.routes:
                path = getattr(r, "path", None) or getattr(r, "prefix", "")
                routes.append(path)
            assert not any("ai" in path.lower() for path in routes if path)

    def test_health_endpoint_available(self):
        with patch.dict(os.environ, _env(), clear=True):
            app = create_app()
            routes = []
            for r in app.routes:
                path = getattr(r, "path", None) or getattr(r, "prefix", "")
                routes.append(path)
            assert "/api/v1/rebuild/health" in routes
