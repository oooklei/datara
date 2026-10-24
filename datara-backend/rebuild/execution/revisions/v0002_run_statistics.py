"""Execution increment 8.2: log-independent per-attempt statistics."""

import hashlib

from sqlalchemy import Engine, inspect

from rebuild.execution.models import WorkflowRunReconcileDetailRecord, WorkflowRunStatRecord

revision = "r9_0002_run_statistics"
down_revision = "r9_0001_execution_tables"
_DDL_MANIFEST = (
    "r9_0002 workflow_run_stat v2 per project/workflow/version/instance/task/attempt;"
    "workflow_run_reconcile_detail source,target,success,failure,skipped,difference"
)
checksum = hashlib.sha256(_DDL_MANIFEST.encode("utf-8")).hexdigest()


def upgrade(engine: Engine) -> None:
    from rebuild.common.db import Base
    Base.metadata.create_all(
        bind=engine,
        tables=[WorkflowRunStatRecord.__table__, WorkflowRunReconcileDetailRecord.__table__],
        checkfirst=True,
    )


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
    WorkflowRunReconcileDetailRecord.__table__.drop(bind=engine, checkfirst=True)
    WorkflowRunStatRecord.__table__.drop(bind=engine, checkfirst=True)
