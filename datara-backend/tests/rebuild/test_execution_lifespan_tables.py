from sqlalchemy import inspect
from fastapi.testclient import TestClient

from rebuild.api.app import create_app
from rebuild.execution.models import EXECUTION_TABLES


def test_app_lifespan_creates_all_execution_tables():
    app = create_app("sqlite+pysqlite:///:memory:", token_secret="execution-lifespan-test-secret")
    with TestClient(app):
        engine = app.state.session_factory.kw["bind"]
        present = set(inspect(engine).get_table_names())
        assert {table.name for table in EXECUTION_TABLES} <= present
