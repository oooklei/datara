"""Initial execution-domain tables (design §9), frozen independently of ORM metadata."""

import hashlib

from sqlalchemy import Column, DateTime, Engine, Index, Integer, MetaData, String, Table, Text, UniqueConstraint, func

revision = "r9_0001_execution_tables"
_DDL_MANIFEST = (
    "r9_0001 execution tables v1: workflow_instance,task_instance,"
    "task_instance_attempt,task_instance_log,task_instance_output,execution_event;"
    "attempt isolation, state stamps, result-stat receipt index"
)
checksum = hashlib.sha256(_DDL_MANIFEST.encode("utf-8")).hexdigest()

_metadata = MetaData()


def _timestamps() -> tuple[Column, Column, Column]:
    return (
        Column("created_at", DateTime, nullable=False, server_default=func.current_timestamp()),
        Column("updated_at", DateTime, nullable=False, server_default=func.current_timestamp()),
        Column("generated_at", DateTime, nullable=False, server_default=func.current_timestamp()),
    )


_workflow_instance = Table(
    "workflow_instance", _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("workflow_id", Integer, nullable=False, index=True),
    Column("workflow_version_id", Integer, nullable=False),
    Column("trial_snapshot_id", Integer, nullable=True, index=True),
    Column("instance_type", String(16), nullable=False),
    Column("status", String(16), nullable=False),
    Column("trigger_type", String(16), nullable=True),
    Column("started_at", DateTime, nullable=True),
    Column("finished_at", DateTime, nullable=True),
    *_timestamps(),
    Index("x_wi_workflow_type", "workflow_id", "instance_type"),
)
_task_instance = Table(
    "task_instance", _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("workflow_instance_id", Integer, nullable=False, index=True),
    Column("task_id", String(128), nullable=False),
    Column("status", String(16), nullable=False),
    Column("current_attempt_no", Integer, nullable=False),
    Column("started_at", DateTime, nullable=True),
    Column("finished_at", DateTime, nullable=True),
    *_timestamps(),
    UniqueConstraint("workflow_instance_id", "task_id", name="uq_ti_instance_task"),
)
_task_attempt = Table(
    "task_instance_attempt", _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("task_instance_id", Integer, nullable=False, index=True),
    Column("attempt_no", Integer, nullable=False),
    Column("status", String(16), nullable=False),
    Column("started_at", DateTime, nullable=True),
    Column("finished_at", DateTime, nullable=True),
    *_timestamps(),
    UniqueConstraint("task_instance_id", "attempt_no", name="uq_tia_task_attempt"),
)
_run_log = Table(
    "task_instance_log", _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("task_instance_id", Integer, nullable=False),
    Column("attempt_no", Integer, nullable=False),
    Column("level", String(16), nullable=False),
    Column("message", Text, nullable=False),
    *_timestamps(),
    Index("x_til_task_attempt", "task_instance_id", "attempt_no"),
)
_run_output = Table(
    "task_instance_output", _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("task_instance_id", Integer, nullable=False),
    Column("attempt_no", Integer, nullable=False),
    Column("output_json", Text, nullable=False),
    *_timestamps(),
    Index("x_tio_task_attempt", "task_instance_id", "attempt_no"),
)
_execution_event = Table(
    "execution_event", _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("workflow_instance_id", Integer, nullable=False),
    Column("task_instance_id", Integer, nullable=True),
    Column("attempt_no", Integer, nullable=True),
    Column("event_kind", String(32), nullable=False),
    Column("payload_json", Text, nullable=True),
    Column("event_time", DateTime, nullable=False, server_default=func.current_timestamp()),
    *_timestamps(),
    Index("x_ee_instance_kind", "workflow_instance_id", "event_kind"),
)

TABLES = (
    _workflow_instance, _task_instance, _task_attempt, _run_log, _run_output, _execution_event,
)


def upgrade(engine: Engine) -> None:
    _metadata.create_all(bind=engine, tables=list(TABLES), checkfirst=True)


def downgrade(engine: Engine) -> None:
    for table in reversed(TABLES):
        table.drop(bind=engine, checkfirst=True)
