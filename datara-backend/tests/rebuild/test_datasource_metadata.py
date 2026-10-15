from __future__ import annotations

import pytest

from rebuild.datasource.contracts import DataSourceDraft
from rebuild.datasource.metadata import MySQLMetadataCatalog


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.statement = ""
        self.parameters = ()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, parameters=()):
        self.statement = statement
        self.parameters = parameters
        self.connection.executions.append((statement, parameters))

    def fetchall(self):
        if "information_schema.schemata" in self.statement:
            return [("analytics",), ("shared",)]
        if "information_schema.tables" in self.statement:
            return [("orders", "BASE TABLE"), ("orders_view", "VIEW")]
        if "information_schema.columns" in self.statement:
            return [("order_id", "bigint", "bigint unsigned", "NO", "PRI", "identifier")]
        return []


class FakeConnection:
    def __init__(self):
        self.executions = []
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def begin(self):
        self.executions.append(("BEGIN", ()))

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _draft(kind="mysql"):
    return DataSourceDraft(
        name="catalog",
        kind=kind,
        host="fixture",
        port=3306,
        database="default_schema",
        username="readonly",
        password="fixture-only",
    )


def test_lists_visible_schemas_and_closes_read_only_connection():
    connection = FakeConnection()
    catalog = MySQLMetadataCatalog(_draft(), connector=lambda _draft: connection)

    schemas = catalog.schemas()

    assert schemas == ["analytics", "shared"]
    assert connection.executions[0] == ("SET TRANSACTION READ ONLY", ())
    assert connection.rolled_back is True
    assert connection.closed is True


def test_object_names_are_schema_qualified_and_schema_is_a_bound_parameter():
    connection = FakeConnection()
    catalog = MySQLMetadataCatalog(_draft(), connector=lambda _draft: connection)

    objects = catalog.objects("shared", after="ord", limit=75)

    statement, parameters = next(item for item in connection.executions if "information_schema.tables" in item[0])
    assert "table_schema = %s" in statement
    assert "table_name > %s" in statement
    assert parameters == ("shared", "ord", 76)
    assert objects == [
        {"schema": "shared", "name": "orders", "type": "table"},
        {"schema": "shared", "name": "orders_view", "type": "view"},
    ]
    assert connection.closed is True


def test_column_contract_preserves_schema_and_column_semantics():
    connection = FakeConnection()
    catalog = MySQLMetadataCatalog(_draft(), connector=lambda _draft: connection)

    columns = catalog.columns("analytics", "orders")

    assert columns == [
        {
            "schema": "analytics",
            "object": "orders",
            "name": "order_id",
            "data_type": "bigint",
            "database_type": "bigint unsigned",
            "nullable": False,
            "primary_key": True,
            "comment": "identifier",
        }
    ]
    _statement, parameters = next(item for item in connection.executions if "information_schema.columns" in item[0])
    assert parameters == ("analytics", "orders", 501)
    assert connection.closed is True


@pytest.mark.parametrize("requested, expected", [(0, 2), (75, 76), (1000, 201)])
def test_object_page_size_is_bounded_and_uses_lookahead(requested, expected):
    connection = FakeConnection()
    catalog = MySQLMetadataCatalog(_draft(), connector=lambda _draft: connection)

    catalog.objects("analytics", limit=requested)

    _statement, parameters = next(item for item in connection.executions if "information_schema.tables" in item[0])
    assert parameters[-1] == expected


def test_schema_filter_value_is_never_interpolated_into_metadata_sql():
    connection = FakeConnection()
    catalog = MySQLMetadataCatalog(_draft(), connector=lambda _draft: connection)
    hostile_schema = "x' OR '1'='1"

    catalog.objects(hostile_schema)

    statement, parameters = next(item for item in connection.executions if "information_schema.tables" in item[0])
    assert hostile_schema not in statement
    assert parameters[0] == hostile_schema


def test_unsupported_runtime_database_is_rejected_before_connecting():
    connected = False

    def connector(_draft):
        nonlocal connected
        connected = True
        raise AssertionError("unsupported connector must not run")

    catalog = MySQLMetadataCatalog(_draft(kind="postgresql"), connector=connector)

    with pytest.raises(ValueError, match="mysql only"):
        catalog.schemas()
    assert connected is False
