"""Create component definitions, immutable versions, and publication records."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Engine,
    Index,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    inspect,
)
from sqlalchemy.dialects.mysql import LONGTEXT


revision = "i4_0001_component_catalog"

_metadata = MetaData()

component_table = Table(
    "t_component",
    _metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("type", String(64), nullable=False, unique=True),
    Column("name", String(128), nullable=False),
    Column("category", String(64), nullable=True),
    Column("profile", String(32), nullable=False),
    Column("scope", String(16), nullable=False),
    Column("execution_model", String(32), nullable=False),
    Column("executor", String(64), nullable=True),
    Column("executable", Boolean, nullable=False),
    Column("state", String(16), nullable=False),
    Column("published_version", Integer, nullable=True),
    Column("draft_rev", Integer, nullable=False),
    Column("description", String(512), nullable=True),
    Column("tags", JSON, nullable=True),
    Column("owner_id", Integer, nullable=True),
    Column("create_time", DateTime, nullable=False),
    Column("update_time", DateTime, nullable=False),
    Index("idx_comp_profile_state", "profile", "state"),
)

component_version_table = Table(
    "t_component_version",
    _metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("component_id", BigInteger, nullable=False),
    Column("type", String(64), nullable=False),
    Column("version", Integer, nullable=False),
    Column("state", String(16), nullable=False),
    Column("spec_json", LONGTEXT, nullable=False),
    Column("spec_hash", String(64), nullable=False),
    Column("remark", String(512), nullable=True),
    Column("published_by", String(64), nullable=True),
    Column("published_time", DateTime, nullable=True),
    Column("create_time", DateTime, nullable=False),
    Column("update_time", DateTime, nullable=False),
    UniqueConstraint("type", "version", name="uk_comp_type_ver"),
    Index("idx_compver_comp", "component_id", "version"),
)

component_log_table = Table(
    "t_component_log",
    _metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("component_id", BigInteger, nullable=False),
    Column("type", String(64), nullable=False),
    Column("version", Integer, nullable=False),
    Column("action", String(32), nullable=False),
    Column("spec_hash", String(64), nullable=True),
    Column("operator", String(64), nullable=True),
    Column("remark", String(512), nullable=True),
    Column("operate_time", DateTime, nullable=False),
    Column("create_time", DateTime, nullable=False),
    Column("update_time", DateTime, nullable=False),
    Index("idx_complog_comp", "component_id", "version"),
)

COMPONENT_TABLES = (
    component_table,
    component_version_table,
    component_log_table,
)


def _type_contract(type_, dialect) -> tuple[object, ...]:
    """Normalize reflected/declared types while preserving storage semantics."""
    implementation = dialect.type_descriptor(type_)
    compiled = dialect.type_compiler.process(implementation).upper().replace(" ", "")
    # MySQL reflection may append ``COLLATE...`` to LONGTEXT/TEXT type names;
    # collation is table metadata, not a storage-layout difference.
    compiled = compiled.split("COLLATE", 1)[0]
    family = compiled.split("(", 1)[0]
    if family in {"BOOL", "BOOLEAN"} or (dialect.name == "mysql" and compiled == "TINYINT(1)"):
        family = "BOOLEAN"
    elif family.endswith("TEXT") and dialect.name != "mysql":
        family = "TEXT"
    elif family == "INT":
        family = "INTEGER"
    return (
        family,
        getattr(implementation, "length", None),
        getattr(implementation, "precision", None),
        getattr(implementation, "scale", None),
        bool(getattr(implementation, "unsigned", False)),
        bool(getattr(implementation, "timezone", False)),
    )


def _declared_auto_increment(column) -> bool:
    return column.autoincrement is True or (
        column.autoincrement == "auto" and column.primary_key and issubclass(column.type._type_affinity, Integer)
    )


def _column_signature(table, dialect) -> dict[str, tuple[object, ...]]:
    return {
        column.name: (
            column.nullable,
            column.primary_key,
            _declared_auto_increment(column) if dialect.name == "mysql" else None,
            *_type_contract(column.type, dialect),
        )
        for column in table.columns
    }


def _schema_manifest() -> dict[str, object]:
    return {
        "revision": revision,
        "tables": [
            {
                "name": table.name,
                "columns": [
                    {
                        "name": column.name,
                        "nullable": column.nullable,
                        "primary_key": column.primary_key,
                        "autoincrement": _declared_auto_increment(column),
                        "type": (
                            str(column.type).upper().split("(", 1)[0],
                            getattr(column.type, "length", None),
                            getattr(column.type, "precision", None),
                            getattr(column.type, "scale", None),
                            bool(getattr(column.type, "unsigned", False)),
                            bool(getattr(column.type, "timezone", False)),
                        ),
                    }
                    for column in table.columns
                ],
                "indexes": sorted(
                    (index.name, tuple(column.name for column in index.columns))
                    for index in table.indexes
                    if index.name
                ),
                "unique": sorted(
                    tuple(column.name for column in constraint.columns)
                    for constraint in table.constraints
                    if constraint.__class__.__name__ == "UniqueConstraint"
                ),
            }
            for table in COMPONENT_TABLES
        ],
    }


SCHEMA_MANIFEST = _schema_manifest()
checksum = hashlib.sha256(
    json.dumps(
        SCHEMA_MANIFEST,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
).hexdigest()


def _validate_existing_table(engine: Engine, table) -> None:
    inspector = inspect(engine)
    primary_key_columns = set(inspector.get_pk_constraint(table.name).get("constrained_columns") or ())
    actual_columns = {
        column["name"]: (
            column["nullable"],
            column["name"] in primary_key_columns,
            bool(column.get("autoincrement")) if engine.dialect.name == "mysql" else None,
            *_type_contract(column["type"], engine.dialect),
        )
        for column in inspector.get_columns(table.name)
    }
    if actual_columns != _column_signature(table, engine.dialect):
        raise RuntimeError(f"existing table {table.name} has an incompatible column layout")

    actual_indexes = {
        index["name"]: tuple(index["column_names"]) for index in inspector.get_indexes(table.name) if index.get("name")
    }
    expected_indexes = {
        index.name: tuple(column.name for column in index.columns) for index in table.indexes if index.name
    }
    if any(actual_indexes.get(name) != columns for name, columns in expected_indexes.items()):
        raise RuntimeError(f"existing table {table.name} is missing a required index")

    actual_unique_sets = {
        tuple(constraint["column_names"]) for constraint in inspector.get_unique_constraints(table.name)
    }
    actual_unique_sets.update(
        tuple(index["column_names"]) for index in inspector.get_indexes(table.name) if index.get("unique")
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
        raise RuntimeError("component catalog migration is recorded but tables are missing: " + ", ".join(missing))
    for table in COMPONENT_TABLES:
        _validate_existing_table(engine, table)
