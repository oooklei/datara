"""Regression coverage for the variable snapshot provenance column width.

Design §3.4 keeps an immutable variable snapshot per run.  Provenance is stored as
``{scope}.{name}``, which is longer than a bare scope enum, so the column must hold
the qualified reference (``project.fixture_key`` = 18 characters) and the migration
must widen pre-existing deployments without losing snapshot rows.
"""

from sqlalchemy import create_engine, inspect, text

from rebuild.variables.migrations import VARIABLE_MIGRATIONS, apply_variable_migrations
from rebuild.variables.revisions import v0003_runtime_source_width


def _legacy_runtime_table(engine) -> None:
    """Create the pre-r2_0003 shape: ``source VARCHAR(16)`` with one snapshot row."""
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE task_instance_variable_runtime ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, instance_id INTEGER NOT NULL, project_id INTEGER, "
            "attempt_no INTEGER NOT NULL DEFAULT 1, expression TEXT NOT NULL, scope VARCHAR(16) NOT NULL, "
            "name VARCHAR(128) NOT NULL, resolved_value TEXT NOT NULL, "
            "value_type VARCHAR(16) NOT NULL DEFAULT 'string', source VARCHAR(16) NOT NULL, "
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
            "VALUES (7,35,1,'${project.fixture_key}','project','fixture_key','INFRA-DATA-01','string','project')"
        ))


def test_runtime_source_width_is_declared_for_scope_qualified_references():
    from rebuild.variables.models import TaskInstanceVariableRuntimeRecord

    column = TaskInstanceVariableRuntimeRecord.__table__.columns["source"]
    assert column.type.length >= len("project.fixture_key")


def test_revision_checksum_is_a_frozen_literal():
    assert v0003_runtime_source_width.checksum == (
        "00d8785d1a57ada8245053512b11f5b856b26fef1ef0380bfb44a2922a67aaa3"
    )


def test_upgrade_widens_legacy_column_and_preserves_snapshot_rows():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _legacy_runtime_table(engine)
    assert v0003_runtime_source_width._current_length(engine) == 16

    v0003_runtime_source_width.upgrade(engine)

    assert v0003_runtime_source_width._current_length(engine) >= 160
    assert v0003_runtime_source_width.postflight(engine)["verdict"] == "READY"
    with engine.begin() as connection:
        row = connection.execute(text(
            "SELECT instance_id,scope,name,resolved_value,source FROM task_instance_variable_runtime"
        )).mappings().one()
        assert dict(row) == {
            "instance_id": 7,
            "scope": "project",
            "name": "fixture_key",
            "resolved_value": "INFRA-DATA-01",
            "source": "project",
        }
        # The widened column must accept a scope-qualified reference.
        connection.execute(text(
            "INSERT INTO task_instance_variable_runtime "
            "(instance_id,project_id,attempt_no,expression,scope,name,resolved_value,value_type,source) "
            "VALUES (8,35,1,'${project.fixture_key}','project','fixture_key','INFRA-DATA-01',"
            "'string','project.fixture_key')"
        ))
        stored = connection.scalar(text(
            "SELECT source FROM task_instance_variable_runtime WHERE instance_id=8"
        ))
        assert stored == "project.fixture_key"


def test_upgrade_is_idempotent_and_registered_last():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _legacy_runtime_table(engine)

    result = apply_variable_migrations(engine)
    assert v0003_runtime_source_width.revision in result.applied
    assert apply_variable_migrations(engine).skipped == result.applied
    assert v0003_runtime_source_width.postflight(engine)["verdict"] == "READY"


def test_postflight_blocks_when_column_stays_narrow():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _legacy_runtime_table(engine)

    verdict = v0003_runtime_source_width.postflight(engine)

    assert verdict["verdict"] == "BLOCKED"
    assert verdict["length"] == 16
    assert verdict["required"] == 160


def test_migration_registry_keeps_revisions_unique_and_ordered():
    revisions = [migration.revision for migration in VARIABLE_MIGRATIONS]
    assert len(revisions) == len(set(revisions))
    assert revisions == sorted(revisions)
    assert "r2_0003_variable_runtime_source_width" in revisions
