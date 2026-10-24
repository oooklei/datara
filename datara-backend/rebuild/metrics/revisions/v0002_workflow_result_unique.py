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
        # Preserve totals before deleting duplicate physical rows.
        connection.execute(text(
            f"""UPDATE {_TABLE} AS target SET
            success_count=(SELECT SUM(source.success_count) FROM {_TABLE} source
                           WHERE source.workflow_id=target.workflow_id AND source.run_date=target.run_date),
            failure_count=(SELECT SUM(source.failure_count) FROM {_TABLE} source
                           WHERE source.workflow_id=target.workflow_id AND source.run_date=target.run_date),
            skipped_count=(SELECT SUM(source.skipped_count) FROM {_TABLE} source
                           WHERE source.workflow_id=target.workflow_id AND source.run_date=target.run_date),
            retry_count=(SELECT SUM(source.retry_count) FROM {_TABLE} source
                         WHERE source.workflow_id=target.workflow_id AND source.run_date=target.run_date)
            WHERE target.id=(SELECT MIN(keeper.id) FROM {_TABLE} keeper
                             WHERE keeper.workflow_id=target.workflow_id AND keeper.run_date=target.run_date)"""
        ))
        connection.execute(text(
            f"DELETE FROM {_TABLE} WHERE id NOT IN "
            f"(SELECT keeper_id FROM (SELECT MIN(id) AS keeper_id FROM {_TABLE} "
            "GROUP BY workflow_id, run_date) AS keepers)"
        ))
        if engine.dialect.name == "sqlite":
            connection.execute(text(
                f"CREATE UNIQUE INDEX {_UNIQUE} ON {_TABLE} (workflow_id, run_date)"
            ))
        elif engine.dialect.name == "mysql":
            connection.execute(text(
                f"ALTER TABLE {_TABLE} ADD CONSTRAINT {_UNIQUE} UNIQUE (workflow_id, run_date)"
            ))
        else:
            raise RuntimeError(f"unsupported metrics migration dialect: {engine.dialect.name}")


def postflight(engine: Engine) -> dict[str, object]:
    ready = _TABLE in inspect(engine).get_table_names() and _unique_ready(engine)
    return {"verdict": "READY" if ready else "BLOCKED", "table": _TABLE}
