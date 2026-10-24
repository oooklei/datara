"""Persist the authoritative NORMAL/SYNC/STREAM workflow type."""

from __future__ import annotations

from sqlalchemy import Engine, String, inspect, text


revision = "workflow_0001_type"
MANIFEST = {
    "revision": revision,
    "table": "workflow_definition",
    "column": {"name": "workflow_type", "type": "VARCHAR(16)", "nullable": False, "default": "NORMAL"},
    "legacy_mapping": {"ETL": "NORMAL"},
    "legacy_inference": {"SYNC": "sync-design-types", "STREAM": "stream-design-types"},
    "mixed_evidence": "fail-closed",
}
checksum = "a3e983192e9fcca06bb8503b28d8c09154c90135694199b9568ba047dce36578"


def upgrade(engine: Engine) -> None:
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("workflow_definition")}
    tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        if "workflow_type" not in columns:
            connection.execute(
                text(
                    "ALTER TABLE workflow_definition ADD COLUMN "
                    "workflow_type VARCHAR(16) NOT NULL DEFAULT 'NORMAL'"
                )
            )
        connection.execute(
            text("UPDATE workflow_definition SET workflow_type='NORMAL' WHERE UPPER(TRIM(workflow_type))='ETL'")
        )
        if "workflow_node" in tables:
            sync_evidence = (
                "'SYNC','src_base_orch','tgt_base_orch','file_sync_orch','endpoint_select',"
                "'field_map','field_map_union','condition_set'"
            )
            stream_evidence = "'stream_input','stream_fuse','stream_output','page_board'"
            normal_evidence = "'SQL','PYTHON','SHELL','DEPENDENCY','sql','python','shell','dependent'"
            evidence_sql = (
                "EXISTS (SELECT 1 FROM workflow_node n "
                "WHERE n.definition_id=d.id AND n.node_type IN ({values}))"
            )
            mixed = connection.scalar(
                text(
                    "SELECT COUNT(*) FROM workflow_definition d WHERE "
                    f"(({evidence_sql.format(values=sync_evidence)}) + "
                    f" ({evidence_sql.format(values=stream_evidence)}) + "
                    f" ({evidence_sql.format(values=normal_evidence)})) > 1"
                )
            )
            if int(mixed or 0):
                raise RuntimeError("workflow definitions contain mixed NORMAL, SYNC, or STREAM component evidence")
            connection.execute(
                text(
                    "UPDATE workflow_definition SET workflow_type='SYNC' WHERE id IN ("
                    "SELECT DISTINCT definition_id FROM workflow_node WHERE node_type IN ("
                    "'SYNC','src_base_orch','tgt_base_orch','file_sync_orch','endpoint_select',"
                    "'field_map','field_map_union','condition_set'))"
                )
            )
            connection.execute(
                text(
                    "UPDATE workflow_definition SET workflow_type='STREAM' WHERE id IN ("
                    "SELECT DISTINCT definition_id FROM workflow_node WHERE node_type IN ("
                    "'stream_input','stream_fuse','stream_output','page_board'))"
                )
            )
    validate_schema(engine)


def validate_schema(engine: Engine) -> None:
    columns = {column["name"]: column for column in inspect(engine).get_columns("workflow_definition")}
    column = columns.get("workflow_type")
    column_type = column.get("type") if column is not None else None
    if column is None or column["nullable"] or not isinstance(column_type, String) or column_type.length != 16:
        raise RuntimeError("workflow_definition.workflow_type must be VARCHAR(16) NOT NULL")
    default = str(column.get("default") or "").strip("()'\"").upper()
    if default != "NORMAL":
        raise RuntimeError(f"workflow_definition.workflow_type default must be NORMAL, got {default or '<missing>'}")
    with engine.connect() as connection:
        invalid = connection.scalar(
            text(
                "SELECT COUNT(*) FROM workflow_definition "
                "WHERE workflow_type NOT IN ('NORMAL','SYNC','STREAM')"
            )
        )
    if int(invalid or 0):
        raise RuntimeError("workflow_definition contains unsupported workflow_type values")
