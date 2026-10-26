"""Widen the variable snapshot provenance column to hold scope-qualified references.

``TaskInstanceVariableRuntimeRecord.source`` was declared ``String(16)``, which is
only wide enough for a bare scope enum.  The resolver persists provenance as
``{scope}.{name}`` (design §3.4 keeps the immutable snapshot per reference), so any
cross-scope reference such as ``project.fixture_key`` exceeded the column width and
aborted the run with a MySQL ``Data too long`` error.

The snapshot table is append-only evidence, therefore the upgrade is a pure widening
``MODIFY``/table rebuild and never rewrites row values.
"""

import hashlib

from sqlalchemy import Engine, inspect, text


revision = "r2_0003_variable_runtime_source_width"
checksum = hashlib.sha256(b"r2_0003 widen task variable runtime source column to 160").hexdigest()

_TABLE = "task_instance_variable_runtime"
_COLUMN = "source"
_WIDTH = 160
# Snapshot evidence columns the widening must preserve; a table missing any of
# them is not the r2_0001 shape and is left untouched.
_CORE_COLUMNS = frozenset({
    "id", "instance_id", "attempt_no", "expression", "scope",
    "name", "resolved_value", "value_type", _COLUMN,
})


def upgrade(engine: Engine) -> None:
    if _TABLE not in inspect(engine).get_table_names():
        from rebuild.common.db import Base
        from rebuild.variables.models import TaskInstanceVariableRuntimeRecord

        Base.metadata.create_all(bind=engine, tables=[TaskInstanceVariableRuntimeRecord.__table__], checkfirst=True)
        return
    existing = {column["name"] for column in inspect(engine).get_columns(_TABLE)}
    # Only widen an existing, fully-shaped provenance table.  A table created by
    # r2_0001 already uses the current model shape, and a degenerate placeholder
    # table has no snapshot rows to preserve.
    if not _CORE_COLUMNS.issubset(existing):
        return
    if _current_length(engine) >= _WIDTH:
        return
    if engine.dialect.name == "sqlite":
        _upgrade_sqlite(engine)
    else:
        _upgrade_mysql(engine)


def _current_length(engine: Engine) -> int:
    for column in inspect(engine).get_columns(_TABLE):
        if column["name"] == _COLUMN:
            return int(getattr(column["type"], "length", 0) or 0)
    return 0


def _upgrade_sqlite(engine: Engine) -> None:
    from rebuild.variables.models import TaskInstanceVariableRuntimeRecord

    legacy = f"{_TABLE}_legacy"
    target_columns = [column.name for column in TaskInstanceVariableRuntimeRecord.__table__.columns]
    with engine.begin() as connection:
        existing = {column["name"] for column in inspect(engine).get_columns(_TABLE)}
        carried = [column for column in target_columns if column in existing]
        quoted = ",".join(f'"{column}"' for column in carried)
        connection.execute(text(f'ALTER TABLE {_TABLE} RENAME TO {legacy}'))
        # Index names are global in SQLite and survive the table rename.
        connection.execute(text("DROP INDEX IF EXISTS ix_variable_runtime_instance_attempt"))
        connection.execute(text("DROP INDEX IF EXISTS uq_variable_runtime_instance_attempt_name"))
        TaskInstanceVariableRuntimeRecord.__table__.create(connection)
        connection.execute(text(f"INSERT INTO {_TABLE} ({quoted}) SELECT {quoted} FROM {legacy}"))
        connection.execute(text(f"DROP TABLE {legacy}"))


def _upgrade_mysql(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text(
            f"ALTER TABLE {_TABLE} MODIFY COLUMN `{_COLUMN}` VARCHAR({_WIDTH}) NOT NULL"
        ))


def postflight(engine: Engine) -> dict[str, object]:
    if _TABLE not in inspect(engine).get_table_names():
        return {"verdict": "READY", "column": _COLUMN, "length": 0, "required": _WIDTH, "reason": "table absent"}
    existing = {column["name"] for column in inspect(engine).get_columns(_TABLE)}
    if not _CORE_COLUMNS.issubset(existing):
        # Placeholder/partial tables are not the snapshot evidence table; the
        # revision deliberately leaves them untouched.
        return {
            "verdict": "READY",
            "column": _COLUMN,
            "length": 0,
            "required": _WIDTH,
            "reason": "not a snapshot table",
        }
    width = _current_length(engine)
    return {
        "verdict": "READY" if width >= _WIDTH else "BLOCKED",
        "column": _COLUMN,
        "length": width,
        "required": _WIDTH,
    }
