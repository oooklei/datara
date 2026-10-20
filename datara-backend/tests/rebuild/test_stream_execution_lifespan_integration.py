from fastapi.testclient import TestClient
from sqlalchemy import inspect

from rebuild.api.app import create_app
from rebuild.execution.models import EXECUTION_TABLES
from rebuild.stream.models import STREAM_TABLES


def test_app_lifespan_registers_stream_sync_execution_tables_and_routes():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="domain-lifespan-test-secret")
    with TestClient(app):
        engine = app.state.session_factory.kw["bind"]
        present = set(inspect(engine).get_table_names())
        required_tables = {table.name for table in (*EXECUTION_TABLES, *STREAM_TABLES)}
        assert required_tables <= present

        paths = set(app.openapi().get("paths", {}).keys())
        assert "/api/v1/rebuild/execution/runs" in paths
        assert "/api/v1/rebuild/sync/capabilities" in paths
        assert "/api/v1/rebuild/stream/jobs" in paths
