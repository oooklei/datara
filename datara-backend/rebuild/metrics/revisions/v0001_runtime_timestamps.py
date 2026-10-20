import hashlib

from sqlalchemy import Engine, inspect, text


revision = "r7_0001_metrics_runtime_timestamps"
checksum = hashlib.sha256(b"r7_0001 add runtime timestamps and project scope to metrics tables").hexdigest()
_TABLES = (
    "workflow_result_stat",
    "task_instance_data_stat",
    "task_data_stat_segment",
    "task_data_error_sample",
)


def upgrade(engine: Engine) -> None:
    from rebuild.metrics.models import (
        LineageWritebackRecord,
        QualityRuleResultLinkRecord,
        TaskDataErrorSampleRecord,
        TaskDataStatSegmentRecord,
        TaskInstanceDataStatRecord,
        WorkflowResultStatRecord,
    )

    from rebuild.common.db import Base

    tables = [
        WorkflowResultStatRecord.__table__,
        TaskInstanceDataStatRecord.__table__,
        TaskDataStatSegmentRecord.__table__,
        TaskDataErrorSampleRecord.__table__,
        LineageWritebackRecord.__table__,
        QualityRuleResultLinkRecord.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables, checkfirst=True)
    for table_name in _TABLES:
        columns = {column["name"] for column in inspect(engine).get_columns(table_name)}
        if "generated_at" in columns:
            continue
        if engine.dialect.name == "sqlite":
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN generated_at DATETIME"))
                connection.execute(text(f"UPDATE {table_name} SET generated_at = CURRENT_TIMESTAMP WHERE generated_at IS NULL"))
        else:
            with engine.begin() as connection:
                connection.execute(text(
                    f"ALTER TABLE {table_name} ADD COLUMN generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
                ))
    columns = {column["name"] for column in inspect(engine).get_columns(LineageWritebackRecord.__tablename__)}
    if "project_id" not in columns:
        with engine.begin() as connection:
            connection.execute(text(
                f"ALTER TABLE {LineageWritebackRecord.__tablename__} ADD COLUMN project_id INTEGER"
            ))
    columns = {column["name"] for column in inspect(engine).get_columns(QualityRuleResultLinkRecord.__tablename__)}
    if "project_id" not in columns:
        with engine.begin() as connection:
            connection.execute(text(
                f"ALTER TABLE {QualityRuleResultLinkRecord.__tablename__} ADD COLUMN project_id INTEGER"
            ))
