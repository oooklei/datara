from __future__ import annotations

from rebuild.datasource.contracts import DataSourceDraft, validate_datasource
from rebuild.datasource.metadata import PostgreSQLMetadataCatalog, metadata_catalog_for


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.statement = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, parameters=()):
        self.statement = statement
        self.connection.executions.append((statement, parameters))

    def fetchall(self):
        if "information_schema.schemata" in self.statement:
            return [("analytics",), ("shared",)]
        if "information_schema.tables" in self.statement:
            return [("orders", "BASE TABLE"), ("v_orders", "VIEW")]
        if "information_schema.columns" in self.statement:
            return [("order_id", "bigint", "int8", "NO", True, "identifier")]
        return []


class FakeConnection:
    def __init__(self):
        self.executions = []
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _draft():
    return DataSourceDraft(
        name="postgres-test",
        kind="postgresql",
        host="postgres-test",
        port=5432,
        database="warehouse",
        username="reader",
        password="test-only",
    )


def test_postgresql_capabilities_advertise_only_metadata_and_cross_schema():
    assert validate_datasource(_draft()).capabilities == {"metadata", "cross_schema"}


def test_catalog_factory_dispatches_postgresql_profiles_to_postgresql_adapter():
    catalog = metadata_catalog_for(_draft(), connector=lambda _draft: FakeConnection())

    assert isinstance(catalog, PostgreSQLMetadataCatalog)


def test_postgresql_catalog_lists_non_system_schemas_and_returns_read_only_results():
    connection = FakeConnection()
    catalog = PostgreSQLMetadataCatalog(_draft(), connector=lambda _draft: connection)

    assert catalog.schemas(after="analytics") == ["analytics", "shared"]
    assert "schema_name > %s" in connection.executions[-1][0]
    assert connection.executions[-1][1][0] == "analytics"
    assert connection.executions[0][0] == "BEGIN READ ONLY"
    assert connection.rolled_back is True
    assert connection.closed is True


def test_postgresql_schema_query_escapes_literal_percent_for_psycopg_binding():
    connection = FakeConnection()
    catalog = PostgreSQLMetadataCatalog(_draft(), connector=lambda _draft: connection)

    catalog.schemas()
    statement = connection.executions[-1][0]

    assert "schema_name NOT LIKE 'pg_toast%%'" in statement
    assert "schema_name NOT LIKE 'pg_temp_%%'" in statement


def test_postgresql_catalog_qualifies_objects_and_preserves_shared_column_contract():
    connection = FakeConnection()
    catalog = PostgreSQLMetadataCatalog(_draft(), connector=lambda _draft: connection)

    assert catalog.objects("shared") == [
        {"schema": "shared", "name": "orders", "type": "table"},
        {"schema": "shared", "name": "v_orders", "type": "view"},
    ]
    assert catalog.columns("analytics", "orders") == [
        {
            "schema": "analytics",
            "object": "orders",
            "name": "order_id",
            "data_type": "bigint",
            "database_type": "int8",
            "nullable": False,
            "primary_key": True,
            "comment": "identifier",
        }
    ]
    assert connection.rolled_back is True
    assert connection.closed is True
