"""Persist the authoritative NORMAL/SYNC/STREAM workflow type."""

from __future__ import annotations

from sqlalchemy import Engine, String, inspect, text


revision = "workflow_0001_type"
MANIFEST = {
    "revision": revision,
    "table": "workflow_definition",
    "column": {"name": "workflow_type", "type": "VARCHAR(16)", "nullable": False, "default": "NORMAL"},
    "legacy_mapping": {"ETL": "NORMAL"},
}
checksum = "25bbc14f17ee6d8f099a639e2f099845a0c96484fa1cb84bd7e20d059e42c0d9"


def upgrade(engine: Engine) -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("workflow_definition")}
    with engine.begin() as connection:
        if "workflow_type" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE workflow_definition ADD COLUMN "
                    "workflow_type VARCHAR(16) NOT NULL DEFAULT 'NORMAL'"
                )
            )
        connection.execute(text("UPDATE workflow_definition SET workflow_type='NORMAL' WHERE workflow_type='ETL'"))
    validate_schema(engine)


def validate_schema(engine: Engine) -> None:
    columns = {column["name"]: column for column in inspect(engine).get_columns("workflow_definition")}
    column = columns.get("workflow_type")
    column_type = column.get("type") if column is not None else None
    if (
        column is None
        or column["nullable"]
        or not isinstance(column_type, String)
        or column_type.length != 16
        or column.get("default") is None
    ):
        raise RuntimeError("workflow_definition.workflow_type must be VARCHAR(16) NOT NULL with a default")
    with engine.connect() as connection:
        invalid = connection.scalar(
            text(
                "SELECT COUNT(*) FROM workflow_definition "
                "WHERE workflow_type NOT IN ('NORMAL','SYNC','STREAM')"
            )
        )
    if int(invalid or 0):
        raise RuntimeError("workflow_definition contains unsupported workflow_type values")
