"""Create stream tables and add the explicit legacy job crosswalk."""

from __future__ import annotations

import hashlib

from sqlalchemy import Engine, inspect, text

from rebuild.common.db import Base
from rebuild.stream.models import (
    StreamCheckpointRecord,
    StreamFailureEventRecord,
    StreamJobRecord,
    StreamMetricSnapshotRecord,
    StreamRecoveryEventRecord,
)


STREAM_TABLES = (
    StreamJobRecord.__table__,
    StreamCheckpointRecord.__table__,
    StreamMetricSnapshotRecord.__table__,
    StreamFailureEventRecord.__table__,
    StreamRecoveryEventRecord.__table__,
)


revision = "r8_0001_stream_legacy_job_mapping"
_DDL_MANIFEST = (
    "r8_0001 stream tables; stream_job.legacy_job_id nullable integer; "
    "unique index ix_stream_job_legacy_job_id"
)
checksum = hashlib.sha256(_DDL_MANIFEST.encode("utf-8")).hexdigest()


def upgrade(engine: Engine) -> None:
    """Create missing stream tables and upgrade a pre-crosswalk stream_job."""
    Base.metadata.create_all(bind=engine, tables=list(STREAM_TABLES), checkfirst=True)

    inspector = inspect(engine)
    if "stream_job" not in inspector.get_table_names():
        raise RuntimeError("stream_job table was not created")

    columns = {column["name"] for column in inspector.get_columns("stream_job")}
    if "legacy_job_id" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE stream_job ADD COLUMN legacy_job_id INTEGER NULL"))

    inspector = inspect(engine)
    indexes = inspector.get_indexes("stream_job")
    constraints = inspector.get_unique_constraints("stream_job")
    crosswalk_indexes = [
        index for index in indexes if tuple(index.get("column_names") or ()) == ("legacy_job_id",)
    ]
    crosswalk_constraints = [
        item for item in constraints if tuple(item.get("column_names") or ()) == ("legacy_job_id",)
    ]
    if any(index.get("unique") for index in crosswalk_indexes) or crosswalk_constraints:
        return

    index_name = "ix_stream_job_legacy_job_id"
    conflicting_index = next((index for index in indexes if index.get("name") == index_name), None)
    if conflicting_index is not None:
        raise RuntimeError(f"{index_name} exists without unique legacy_job_id semantics")

    preparer = engine.dialect.identifier_preparer
    table_name = preparer.quote("stream_job")
    quoted_index = preparer.quote(index_name)
    column_name = preparer.quote("legacy_job_id")
    with engine.begin() as connection:
        connection.execute(
            text(f"CREATE UNIQUE INDEX {quoted_index} ON {table_name} ({column_name})")
        )


def downgrade(engine: Engine) -> None:
    """Remove only the crosswalk index and column; retain stream domain tables."""
    inspector = inspect(engine)
    if "stream_job" not in inspector.get_table_names():
        return

    preparer = engine.dialect.identifier_preparer
    index_name = "ix_stream_job_legacy_job_id"
    if any(index.get("name") == index_name for index in inspector.get_indexes("stream_job")):
        index_sql = (
            f"DROP INDEX {preparer.quote(index_name)} ON {preparer.quote('stream_job')}"
            if engine.dialect.name == "mysql"
            else f"DROP INDEX {preparer.quote(index_name)}"
        )
        with engine.begin() as connection:
            connection.execute(text(index_sql))

    if "legacy_job_id" in {column["name"] for column in inspect(engine).get_columns("stream_job")}:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE stream_job DROP COLUMN legacy_job_id"))
