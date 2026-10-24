"""Create the frozen encrypted LLM model registry schema."""

import hashlib
import json

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Engine,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    func,
    inspect,
    text,
)

revision = "i15_0001_llm_model"
_metadata = MetaData()
llm_model_table = Table(
    "rebuild_llm_model",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(64), nullable=False, unique=True),
    Column("display_name", String(64), nullable=False),
    Column("provider", String(32), nullable=False),
    Column("api_base", String(255), nullable=False),
    Column("model_id", String(128), nullable=False),
    Column("api_key_cipher", String(512), nullable=False),
    Column("max_tokens", Integer, nullable=False),
    Column("temperature", Numeric(3, 2), nullable=False),
    Column("is_active", Boolean, nullable=False),
    Column("is_default", Boolean, nullable=False),
    Column("sort_order", Integer, nullable=False),
    Column("created_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")),
)
Index("uq_rebuild_llm_model_single_default", func.nullif(llm_model_table.c.is_default, False), unique=True)
LLM_TABLES = (llm_model_table,)


def _declared_autoincrement(column) -> bool:
    return column.autoincrement is True or (
        column.autoincrement == "auto" and column.primary_key and issubclass(column.type._type_affinity, Integer)
    )


def _type_contract(type_, dialect):
    value = dialect.type_descriptor(type_)
    compiled = dialect.type_compiler.process(value).upper().replace(" ", "")
    family = compiled.split("(", 1)[0]
    if family in {"BOOL", "BOOLEAN"} or (dialect.name == "mysql" and compiled == "TINYINT(1)"):
        family = "BOOLEAN"
    elif family == "INT":
        family = "INTEGER"
    return (
        family,
        getattr(value, "length", None),
        getattr(value, "precision", None),
        getattr(value, "scale", None),
        bool(getattr(value, "unsigned", False)),
        bool(getattr(value, "timezone", False)),
    )


def _manifest():
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
                        "autoincrement": _declared_autoincrement(column),
                        "type": (
                            str(column.type).upper().split("(", 1)[0],
                            getattr(column.type, "length", None),
                            getattr(column.type, "precision", None),
                            getattr(column.type, "scale", None),
                        ),
                    }
                    for column in table.columns
                ],
                "indexes": sorted(
                    (index.name, tuple(column.name for column in index.columns), index.unique)
                    for index in table.indexes
                ),
                "unique": sorted(
                    tuple(column.name for column in constraint.columns)
                    for constraint in table.constraints
                    if constraint.__class__.__name__ == "UniqueConstraint"
                ),
            }
            for table in LLM_TABLES
        ],
    }


SCHEMA_MANIFEST = _manifest()
checksum = hashlib.sha256(
    json.dumps(SCHEMA_MANIFEST, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii")
).hexdigest()


def _validate(engine: Engine, table) -> None:
    inspector = inspect(engine)
    pk = set(inspector.get_pk_constraint(table.name).get("constrained_columns") or ())
    actual = {
        item["name"]: (
            item["nullable"],
            item["name"] in pk,
            bool(item.get("autoincrement")) if engine.dialect.name == "mysql" else None,
            *_type_contract(item["type"], engine.dialect),
        )
        for item in inspector.get_columns(table.name)
    }
    expected = {
        column.name: (
            column.nullable,
            column.primary_key,
            _declared_autoincrement(column) if engine.dialect.name == "mysql" else None,
            *_type_contract(column.type, engine.dialect),
        )
        for column in table.columns
    }
    if actual != expected:
        raise RuntimeError(f"existing table {table.name} has an incompatible column layout")
    indexes = {item["name"] for item in inspector.get_indexes(table.name)}
    if engine.dialect.name == "sqlite":
        with engine.connect() as connection:
            indexes.update(
                connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = :table"),
                    {"table": table.name},
                ).scalars()
            )
    if not {item.name for item in table.indexes} <= indexes:
        raise RuntimeError(f"existing table {table.name} is missing a required index")
    unique = {tuple(item["column_names"]) for item in inspector.get_unique_constraints(table.name)}
    unique.update(tuple(item["column_names"]) for item in inspector.get_indexes(table.name) if item.get("unique"))
    if ("name",) not in unique:
        raise RuntimeError(f"existing table {table.name} is missing a required unique constraint")


def upgrade(engine: Engine) -> None:
    existing = set(inspect(engine).get_table_names())
    if llm_model_table.name in existing:
        _validate(engine, llm_model_table)
    llm_model_table.create(bind=engine, checkfirst=True)
    _validate(engine, llm_model_table)


def validate_schema(engine: Engine) -> None:
    if llm_model_table.name not in inspect(engine).get_table_names():
        raise RuntimeError("LLM migration is recorded but table is missing")
    _validate(engine, llm_model_table)
