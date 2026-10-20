"""Initial execution-domain tables (design §9)."""

import hashlib

from sqlalchemy import Engine

from rebuild.execution.models import EXECUTION_TABLES


revision = "r9_0001_execution_tables"
_DDL_MANIFEST = (
    "r9_0001 execution tables v1: workflow_instance,task_instance,"
    "task_instance_attempt,task_instance_log,task_instance_output,execution_event;"
    "attempt isolation, state stamps, result-stat receipt index"
)
checksum = hashlib.sha256(_DDL_MANIFEST.encode("utf-8")).hexdigest()


def upgrade(engine: Engine) -> None:
    from rebuild.common.db import Base

    Base.metadata.create_all(bind=engine, tables=list(EXECUTION_TABLES), checkfirst=True)


def downgrade(engine: Engine) -> None:
    for table in reversed(EXECUTION_TABLES):
        table.drop(bind=engine, checkfirst=True)
