"""Execution increment 8.2: one authoritative snapshot per workflow run."""

import hashlib

from sqlalchemy import Engine, inspect

from rebuild.execution.models import WorkflowRunReconcileDetailRecord, WorkflowRunStatRecord

revision = "r9_0002_run_statistics"
down_revision = "r9_0001_execution_tables"
_DDL_MANIFEST = (
    "r9_0002 workflow_run_stat v3 one-row-per-instance bigint checked counts;"
    "workflow_run_reconcile_detail bounded reconciliation;result receipt uniqueness"
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
            "project_id",
            "workflow_id",
            "workflow_version_id",
            "workflow_instance_id",
            "instance_type",
            "status",
            "dag_name",
            "data_param_json",
            "source_count",
            "target_count",
            "success_count",
            "failure_count",
            "skipped_count",
            "total_count",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
            "generated_at",
        },
        "workflow_run_reconcile_detail": {
            "run_stat_id",
            "source_object",
            "target_object",
            "source_count",
            "target_count",
            "success_count",
            "failure_count",
            "skipped_count",
            "difference_count",
            "data_param_json",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
            "generated_at",
        },
    }
    tables = set(inspector.get_table_names())
    ready = all(
        name in tables and columns <= {item["name"] for item in inspector.get_columns(name)}
        for name, columns in required.items()
    )
    if ready:
        stat_columns = {item["name"]: item for item in inspector.get_columns("workflow_run_stat")}
        ready = all(
            not stat_columns[name]["nullable"]
            for name in (
                "project_id",
                "workflow_id",
                "workflow_version_id",
                "workflow_instance_id",
                "instance_type",
                "status",
                "dag_name",
                "success_count",
                "failure_count",
                "skipped_count",
                "total_count",
                "started_at",
            )
        )
        unique_sets = {tuple(item["column_names"]) for item in inspector.get_unique_constraints("workflow_run_stat")}
        indexes = {tuple(item["column_names"]) for item in inspector.get_indexes("workflow_run_stat")}
        foreign_keys = {
            tuple(item["constrained_columns"]) for item in inspector.get_foreign_keys("workflow_run_reconcile_detail")
        }
        checks = inspector.get_check_constraints("workflow_run_stat")
        ready = ready and ("workflow_instance_id",) in unique_sets
        ready = (
            ready
            and {("project_id", "created_at"), ("workflow_id", "started_at"), ("instance_type", "started_at")}
            <= indexes
        )
        ready = ready and ("run_stat_id",) in foreign_keys and len(checks) >= 4
        ready = ready and all(
            stat_columns[name]["default"] is not None
            for name in ("success_count", "failure_count", "skipped_count", "total_count")
        )
    return {"verdict": "READY" if ready else "BLOCKED", "tables": sorted(required)}


def downgrade(engine: Engine) -> None:
    WorkflowRunReconcileDetailRecord.__table__.drop(bind=engine, checkfirst=True)
    WorkflowRunStatRecord.__table__.drop(bind=engine, checkfirst=True)
