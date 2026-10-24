"""Execution increment 8.2: log-independent per-attempt statistics."""

import hashlib

from sqlalchemy import (
    Column,
    DateTime,
    Engine,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    func,
    inspect,
)

revision = "r9_0002_run_statistics"
down_revision = "r9_0001_execution_tables"
_DDL_MANIFEST = (
    "r9_0002 workflow_run_stat v2 per project/workflow/version/instance/task/attempt;"
    "workflow_run_reconcile_detail source,target,success,failure,skipped,difference"
)
checksum = hashlib.sha256(_DDL_MANIFEST.encode("utf-8")).hexdigest()

# A migration must not import mutable ORM metadata. These tables freeze the
# exact v2 per-attempt shape represented by the checksum above.
_metadata = MetaData()
Table("workflow_instance", _metadata, Column("id", Integer, primary_key=True))
_stat = Table(
    "workflow_run_stat",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("project_id", Integer, nullable=False),
    Column("workflow_id", Integer, nullable=False),
    Column("workflow_version_id", Integer, nullable=False),
    Column("workflow_instance_id", Integer, ForeignKey("workflow_instance.id", ondelete="CASCADE"), nullable=False),
    Column("task_instance_id", Integer, nullable=True),
    Column("task_identity", String(64), nullable=False),
    Column("attempt_no", Integer, nullable=False),
    Column("instance_type", String(16), nullable=False),
    Column("status", String(16), nullable=False),
    Column("source_count", Integer, nullable=True),
    Column("target_count", Integer, nullable=True),
    Column("success_count", Integer, nullable=False),
    Column("failure_count", Integer, nullable=False),
    Column("skipped_count", Integer, nullable=False),
    Column("started_at", DateTime, nullable=True),
    Column("finished_at", DateTime, nullable=True),
    Column("created_at", DateTime, nullable=False, server_default=func.current_timestamp()),
    Column("updated_at", DateTime, nullable=False, server_default=func.current_timestamp()),
    Column("generated_at", DateTime, nullable=False, server_default=func.current_timestamp()),
    UniqueConstraint("workflow_instance_id", "task_identity", "attempt_no", name="uq_wrs_instance_task_attempt"),
    Index("x_wrs_project_created", "project_id", "created_at"),
    Index("x_wrs_workflow_instance", "workflow_id", "workflow_instance_id"),
)
_detail = Table(
    "workflow_run_reconcile_detail",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_stat_id", Integer, ForeignKey("workflow_run_stat.id", ondelete="CASCADE"), nullable=False),
    Column("source_object", String(256), nullable=False),
    Column("target_object", String(256), nullable=False),
    Column("source_count", Integer, nullable=True),
    Column("target_count", Integer, nullable=True),
    Column("success_count", Integer, nullable=False),
    Column("failure_count", Integer, nullable=False),
    Column("skipped_count", Integer, nullable=False),
    Column("difference_count", Integer, nullable=True),
    Column("created_at", DateTime, nullable=False, server_default=func.current_timestamp()),
    Column("updated_at", DateTime, nullable=False, server_default=func.current_timestamp()),
    Column("generated_at", DateTime, nullable=False, server_default=func.current_timestamp()),
    UniqueConstraint("run_stat_id", "source_object", "target_object", name="uq_wrrd_object_pair"),
    Index("x_wrrd_run_stat", "run_stat_id"),
)
TABLES = (_stat, _detail)


def upgrade(engine: Engine) -> None:
    _metadata.create_all(bind=engine, tables=list(TABLES), checkfirst=True)


def postflight(engine: Engine) -> dict[str, object]:
    inspector = inspect(engine)
    required = {
        "workflow_run_stat": {
            "project_id", "workflow_id", "workflow_version_id", "workflow_instance_id",
            "task_instance_id", "task_identity", "attempt_no", "source_count", "target_count",
            "success_count", "failure_count", "skipped_count",
        },
        "workflow_run_reconcile_detail": {
            "run_stat_id", "source_object", "target_object", "source_count", "target_count",
            "success_count", "failure_count", "skipped_count", "difference_count",
        },
    }
    tables = set(inspector.get_table_names())
    ready = all(name in tables and columns <= {item["name"] for item in inspector.get_columns(name)}
                for name, columns in required.items())
    return {"verdict": "READY" if ready else "BLOCKED", "tables": sorted(required)}


def downgrade(engine: Engine) -> None:
    _detail.drop(bind=engine, checkfirst=True)
    _stat.drop(bind=engine, checkfirst=True)
