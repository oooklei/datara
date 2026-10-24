"""Make the workflow/day aggregate an enforceable single-row identity."""

import hashlib

from sqlalchemy import Engine, inspect, text

revision = "r7_0002_workflow_result_unique"
down_revision = "r7_0001_metrics_runtime_timestamps"
_DDL_MANIFEST = "r7_0002 workflow_result_stat unique(workflow_id,run_date) merge legacy duplicates"
checksum = hashlib.sha256(_DDL_MANIFEST.encode("utf-8")).hexdigest()

_TABLE = "workflow_result_stat"
_UNIQUE = "uq_workflow_result_stat_workflow_run_date"


def _unique_ready(engine: Engine) -> bool:
    inspector = inspect(engine)
    expected = ("workflow_id", "run_date")
    constraints = {tuple(item["column_names"]) for item in inspector.get_unique_constraints(_TABLE)}
    indexes = {
        tuple(item["column_names"]) for item in inspector.get_indexes(_TABLE) if item.get("unique")
    }
    return expected in constraints | indexes


def upgrade(engine: Engine) -> None:
    if _unique_ready(engine):
        return
    with engine.begin() as connection:
        # A temporary rollup avoids MySQL error 1093 (read/write same target)
        # and keeps the DML transactional until the final guarded DDL.
        connection.execute(text(
            f"""CREATE TEMPORARY TABLE r7_0002_workflow_result_rollup AS
            SELECT MIN(id) keeper_id, workflow_id, run_date,
                   SUM(success_count) success_count, SUM(failure_count) failure_count,
                   SUM(skipped_count) skipped_count, SUM(retry_count) retry_count
            FROM {_TABLE} GROUP BY workflow_id, run_date"""
        ))
        if engine.dialect.name == "mysql":
            connection.execute(text(
                f"""UPDATE {_TABLE} target
                JOIN r7_0002_workflow_result_rollup rollup ON rollup.keeper_id=target.id
                SET target.success_count=rollup.success_count,
                    target.failure_count=rollup.failure_count,
                    target.skipped_count=rollup.skipped_count,
                    target.retry_count=rollup.retry_count"""
            ))
        elif engine.dialect.name == "sqlite":
            connection.execute(text(
                f"""UPDATE {_TABLE} SET
                success_count=(SELECT success_count FROM r7_0002_workflow_result_rollup WHERE keeper_id={_TABLE}.id),
                failure_count=(SELECT failure_count FROM r7_0002_workflow_result_rollup WHERE keeper_id={_TABLE}.id),
                skipped_count=(SELECT skipped_count FROM r7_0002_workflow_result_rollup WHERE keeper_id={_TABLE}.id),
                retry_count=(SELECT retry_count FROM r7_0002_workflow_result_rollup WHERE keeper_id={_TABLE}.id)
                WHERE id IN (SELECT keeper_id FROM r7_0002_workflow_result_rollup)"""
            ))
        else:
            raise RuntimeError(f"unsupported metrics migration dialect: {engine.dialect.name}")
        connection.execute(text(
            f"DELETE FROM {_TABLE} WHERE id NOT IN "
            "(SELECT keeper_id FROM r7_0002_workflow_result_rollup)"
        ))
        if engine.dialect.name == "sqlite":
            connection.execute(text(
                f"CREATE UNIQUE INDEX {_UNIQUE} ON {_TABLE} (workflow_id, run_date)"
            ))
        elif engine.dialect.name == "mysql":
            connection.execute(text(
                f"ALTER TABLE {_TABLE} ADD CONSTRAINT {_UNIQUE} UNIQUE (workflow_id, run_date)"
            ))


def postflight(engine: Engine) -> dict[str, object]:
    ready = _TABLE in inspect(engine).get_table_names() and _unique_ready(engine)
    return {"verdict": "READY" if ready else "BLOCKED", "table": _TABLE}
