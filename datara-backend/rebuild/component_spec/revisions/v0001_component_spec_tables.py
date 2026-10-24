"""Create component definitions, immutable versions, and publication records."""

from __future__ import annotations

import hashlib

from sqlalchemy import Engine, inspect

from common.models import Component, ComponentLog, ComponentVersion


revision = "i4_0001_component_catalog"
checksum = hashlib.sha256(
    b"i4_0001 t_component t_component_version t_component_log catalog"
).hexdigest()

COMPONENT_TABLES = (
    Component.__table__,
    ComponentVersion.__table__,
    ComponentLog.__table__,
)


def _column_signature(table) -> dict[str, tuple[bool, bool]]:
    return {
        column.name: (column.nullable, column.primary_key)
        for column in table.columns
    }


def _validate_existing_table(engine: Engine, table) -> None:
    inspector = inspect(engine)
    primary_key_columns = set(
        inspector.get_pk_constraint(table.name).get("constrained_columns") or ()
    )
    actual_columns = {
        column["name"]: (column["nullable"], column["name"] in primary_key_columns)
        for column in inspector.get_columns(table.name)
    }
    if actual_columns != _column_signature(table):
        raise RuntimeError(f"existing table {table.name} has an incompatible column layout")

    actual_indexes = {
        index["name"]: tuple(index["column_names"])
        for index in inspector.get_indexes(table.name)
        if index.get("name")
    }
    expected_indexes = {
        index.name: tuple(column.name for column in index.columns)
        for index in table.indexes
        if index.name
    }
    if any(actual_indexes.get(name) != columns for name, columns in expected_indexes.items()):
        raise RuntimeError(f"existing table {table.name} is missing a required index")

    actual_unique_sets = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table.name)
    }
    actual_unique_sets.update(
        tuple(index["column_names"])
        for index in inspector.get_indexes(table.name)
        if index.get("unique")
    )
    expected_unique_sets = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    if not expected_unique_sets <= actual_unique_sets:
        raise RuntimeError(f"existing table {table.name} is missing a required unique constraint")


def upgrade(engine: Engine) -> None:
    expected = {table.name for table in COMPONENT_TABLES}
    existing = expected.intersection(inspect(engine).get_table_names())
    if existing and existing != expected:
        raise RuntimeError("partial component catalog schema exists")
    for table in COMPONENT_TABLES:
        if table.name in existing:
            _validate_existing_table(engine, table)
    for table in COMPONENT_TABLES:
        table.create(bind=engine, checkfirst=True)
        _validate_existing_table(engine, table)


def validate_schema(engine: Engine) -> None:
    """Verify the complete post-migration schema without repairing drift."""
    existing = set(inspect(engine).get_table_names())
    missing = [table.name for table in COMPONENT_TABLES if table.name not in existing]
    if missing:
        raise RuntimeError(
            "component catalog migration is recorded but tables are missing: "
            + ", ".join(missing)
        )
    for table in COMPONENT_TABLES:
        _validate_existing_table(engine, table)
