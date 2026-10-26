"""Regression coverage for the variable snapshot unique key.

Design §3.4 requires an immutable per-run variable snapshot.  A reference is
``{scope}.{name}``, so ``project.fixture_key`` and ``run.fixture_key`` are two
different references.  The table was unique on
``(instance_id, attempt_no, name)``; the run-scope test override inserted first
and the resolver's project-scope row was silently dropped, leaving the snapshot
unable to prove which value actually ran.
"""

from sqlalchemy import create_engine, inspect, text

from rebuild.variables.migrations import VARIABLE_MIGRATIONS, apply_variable_migrations
from rebuild.variables.revisions import v0004_runtime_scope_name_key


def _legacy_runtime_table(engine) -> None:
    """Create the pre-r2_0004 shape: unique on (instance, attempt, name)."""
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE task_instance_variable_runtime ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, instance_id INTEGER NOT NULL, project_id INTEGER, "
            "attempt_no INTEGER NOT NULL DEFAULT 1, expression TEXT NOT NULL, scope VARCHAR(16) NOT NULL, "
            "name VARCHAR(128) NOT NULL, resolved_value TEXT NOT NULL, "
            "value_type VARCHAR(16) NOT NULL DEFAULT 'string', source VARCHAR(160) NOT NULL, "
            "resolved_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
            "generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "CONSTRAINT uq_variable_runtime_instance_attempt_name UNIQUE(instance_id,attempt_no,name))"
        ))
        connection.execute(text(
            "CREATE INDEX ix_variable_runtime_instance_attempt "
            "ON task_instance_variable_runtime (instance_id,attempt_no)"
        ))
        connection.execute(text(
            "INSERT INTO task_instance_variable_runtime "
            "(instance_id,project_id,attempt_no,expression,scope,name,resolved_value,value_type,source) "
            "VALUES (19,35,1,'${project.fixture_key}','project','fixture_key','INFRA-DATA-01',"
            "'string','project.fixture_key')"
        ))


def test_model_keys_snapshot_rows_by_scope_and_name():
    from rebuild.variables.models import TaskInstanceVariableRuntimeRecord

    table = TaskInstanceVariableRuntimeRecord.__table__
    unique_sets = {
        tuple(sorted(constraint.columns.keys()))
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert ("attempt_no", "instance_id", "name", "scope") in unique_sets


def test_revision_checksum_is_a_frozen_literal():
    assert v0004_runtime_scope_name_key.checksum == (
        "a694d1f9f1a72d62e029484f6584855a355b17515ead88433370c8eb1e5c2ca0"
    )


def test_upgrade_allows_same_name_in_two_scopes_and_keeps_rows():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _legacy_runtime_table(engine)
    # The legacy key rejects a second row with the same name in another scope.
    with engine.begin() as connection:
        try:
            connection.execute(text(
                "INSERT INTO task_instance_variable_runtime "
                "(instance_id,project_id,attempt_no,expression,scope,name,resolved_value,value_type,source) "
                "VALUES (19,35,1,'${run.fixture_key}','run','fixture_key','gate7-run-scope-value',"
                "'string','test_override')"
            ))
            legacy_rejected = False
        except Exception:
            legacy_rejected = True
    assert legacy_rejected is True

    v0004_runtime_scope_name_key.upgrade(engine)

    assert v0004_runtime_scope_name_key.postflight(engine)["verdict"] == "READY"
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO task_instance_variable_runtime "
            "(instance_id,project_id,attempt_no,expression,scope,name,resolved_value,value_type,source) "
            "VALUES (19,35,1,'${run.fixture_key}','run','fixture_key','gate7-run-scope-value',"
            "'string','test_override')"
        ))
        rows = connection.execute(text(
            "SELECT scope,name,resolved_value,source FROM task_instance_variable_runtime "
            "WHERE instance_id=19 ORDER BY id"
        )).mappings().all()
    assert [dict(row) for row in rows] == [
        {
            "scope": "project",
            "name": "fixture_key",
            "resolved_value": "INFRA-DATA-01",
            "source": "project.fixture_key",
        },
        {
            "scope": "run",
            "name": "fixture_key",
            "resolved_value": "gate7-run-scope-value",
            "source": "test_override",
        },
    ]


def test_upgrade_is_idempotent_and_registered_last():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _legacy_runtime_table(engine)

    result = apply_variable_migrations(engine)
    assert result.applied[-1] == v0004_runtime_scope_name_key.revision
    assert apply_variable_migrations(engine).skipped == result.applied
    assert v0004_runtime_scope_name_key.postflight(engine)["verdict"] == "READY"


def test_upgrade_leaves_unrelated_placeholder_table_untouched():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE task_instance_variable_runtime (id INTEGER PRIMARY KEY)"))

    v0004_runtime_scope_name_key.upgrade(engine)

    assert v0004_runtime_scope_name_key.postflight(engine)["verdict"] == "READY"
    with engine.begin() as connection:
        columns = {column["name"] for column in inspect(engine).get_columns("task_instance_variable_runtime")}
    assert columns == {"id"}
