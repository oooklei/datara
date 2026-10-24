from sqlalchemy import create_engine, inspect, text

from rebuild.metrics.migrations import METRICS_MIGRATIONS, apply_metrics_migrations
from rebuild.variables.migrations import VARIABLE_MIGRATIONS, apply_variable_migrations


def test_metrics_and_variables_runtime_migrations_are_versioned_and_idempotent():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    legacy_tables = (
        "workflow_result_stat",
        "task_instance_data_stat",
        "task_data_stat_segment",
        "task_data_error_sample",
        "quality_rule_result_link",
        "lineage_writeback",
        "task_instance_variable_runtime",
    )
    with engine.begin() as connection:
        for table in legacy_tables:
            if table == "workflow_result_stat":
                connection.execute(text(
                    "CREATE TABLE workflow_result_stat (id INTEGER PRIMARY KEY, "
                    "workflow_id INTEGER NOT NULL, run_date DATE NOT NULL, "
                    "success_count INTEGER NOT NULL DEFAULT 0, failure_count INTEGER NOT NULL DEFAULT 0, "
                    "skipped_count INTEGER NOT NULL DEFAULT 0, retry_count INTEGER NOT NULL DEFAULT 0)"
                ))
                connection.execute(text(
                    "INSERT INTO workflow_result_stat (id,workflow_id,run_date) VALUES (1,1,'2026-10-24')"
                ))
            else:
                connection.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)"))
                connection.execute(text(f"INSERT INTO {table} (id) VALUES (1)"))

    metrics = apply_metrics_migrations(engine)
    variables = apply_variable_migrations(engine)
    assert metrics.applied == tuple(migration.revision for migration in METRICS_MIGRATIONS)
    assert variables.applied == (VARIABLE_MIGRATIONS[0].revision,)
    assert apply_metrics_migrations(engine).skipped == metrics.applied
    assert apply_variable_migrations(engine).skipped == variables.applied

    for table in legacy_tables[:4] + ("task_instance_variable_runtime",):
        columns = {column["name"]: column for column in inspect(engine).get_columns(table)}
        assert "generated_at" in columns
        assert connection_has_rows_without_null(engine, table) is True
    for table in ("quality_rule_result_link", "lineage_writeback"):
        assert "project_id" in {column["name"] for column in inspect(engine).get_columns(table)}


def connection_has_rows_without_null(engine, table: str) -> bool:
    with engine.connect() as connection:
        return connection.scalar(text(f"SELECT COUNT(*) FROM {table} WHERE generated_at IS NULL")) == 0
