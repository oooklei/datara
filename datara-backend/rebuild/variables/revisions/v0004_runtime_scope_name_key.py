"""Key variable snapshot rows by scope as well as name.

``task_instance_variable_runtime`` was unique on
``(instance_id, attempt_no, name)``.  A variable reference, however, is
``{scope}.{name}``: ``project.fixture_key`` and ``run.fixture_key`` are two
distinct references that must both survive in the immutable snapshot
(design §3.4).  With the name-only key the run-scope test override inserted
first and the resolver's persisted project-scope row was silently dropped,
so the snapshot no longer proved which value actually ran.

The upgrade only replaces the unique index.  No row is rewritten: the old key
was strictly narrower, therefore the existing rows are already unique under
the new one.
"""

import hashlib

from sqlalchemy import Engine, inspect, text


revision = "r2_0004_variable_runtime_scope_name_key"
checksum = hashlib.sha256(b"r2_0004 key variable runtime snapshot by scope and name").hexdigest()

_TABLE = "task_instance_variable_runtime"
_OLD_KEY = "uq_variable_runtime_instance_attempt_name"
_NEW_KEY = "uq_variable_runtime_instance_attempt_scope_name"
_INDEX = "ix_variable_runtime_instance_attempt"
_KEY_COLUMNS = ("instance_id", "attempt_no", "scope", "name")
# A table missing any of these is not the snapshot evidence table; leave it be.
_CORE_COLUMNS = frozenset({"id", "instance_id", "attempt_no", "expression", "scope", "name", "resolved_value", "source"})


def upgrade(engine: Engine) -> None:
    if _TABLE not in inspect(engine).get_table_names():
        from rebuild.common.db import Base
        from rebuild.variables.models import TaskInstanceVariableRuntimeRecord

        Base.metadata.create_all(bind=engine, tables=[TaskInstanceVariableRuntimeRecord.__table__], checkfirst=True)
        return
    existing = {column["name"] for column in inspect(engine).get_columns(_TABLE)}
    if not _CORE_COLUMNS.issubset(existing):
        return
    if _has_new_key(engine):
        return
    if engine.dialect.name == "sqlite":
        _upgrade_sqlite(engine)
    else:
        _upgrade_mysql(engine)


def _has_new_key(engine: Engine) -> bool:
    for index in inspect(engine).get_indexes(_TABLE):
        if index.get("name") == _NEW_KEY:
            return True
        if index.get("unique") and tuple(index.get("column_names") or ()) == _KEY_COLUMNS:
            return True
    for constraint in inspect(engine).get_unique_constraints(_TABLE):
        if constraint.get("name") == _NEW_KEY:
            return True
        if tuple(constraint.get("column_names") or ()) == _KEY_COLUMNS:
            return True
    return False


def _upgrade_sqlite(engine: Engine) -> None:
    from rebuild.variables.models import TaskInstanceVariableRuntimeRecord

    legacy = f"{_TABLE}_legacy"
    target_columns = [column.name for column in TaskInstanceVariableRuntimeRecord.__table__.columns]
    with engine.begin() as connection:
        existing = {column["name"] for column in inspect(engine).get_columns(_TABLE)}
        carried = [column for column in target_columns if column in existing]
        quoted = ",".join(f'"{column}"' for column in carried)
        connection.execute(text(f"ALTER TABLE {_TABLE} RENAME TO {legacy}"))
        # Index names are global in SQLite and survive the table rename.
        connection.execute(text(f"DROP INDEX IF EXISTS {_INDEX}"))
        connection.execute(text(f"DROP INDEX IF EXISTS {_OLD_KEY}"))
        connection.execute(text(f"DROP INDEX IF EXISTS {_NEW_KEY}"))
        TaskInstanceVariableRuntimeRecord.__table__.create(connection)
        connection.execute(text(f"INSERT INTO {_TABLE} ({quoted}) SELECT {quoted} FROM {legacy}"))
        connection.execute(text(f"DROP TABLE {legacy}"))


def _upgrade_mysql(engine: Engine) -> None:
    with engine.begin() as connection:
        for index in inspect(engine).get_indexes(_TABLE):
            name = index.get("name")
            if name == _OLD_KEY or (index.get("unique") and tuple(index.get("column_names") or ()) == _KEY_COLUMNS[:3]):
                connection.execute(text(f"ALTER TABLE {_TABLE} DROP INDEX `{name}`"))
        connection.execute(text(
            f"ALTER TABLE {_TABLE} ADD UNIQUE KEY `{_NEW_KEY}` (`instance_id`,`attempt_no`,`scope`,`name`)"
        ))


def postflight(engine: Engine) -> dict[str, object]:
    if _TABLE not in inspect(engine).get_table_names():
        return {"verdict": "READY", "key": list(_KEY_COLUMNS), "reason": "table absent"}
    existing = {column["name"] for column in inspect(engine).get_columns(_TABLE)}
    if not _CORE_COLUMNS.issubset(existing):
        return {"verdict": "READY", "key": list(_KEY_COLUMNS), "reason": "not a snapshot table"}
    ready = _has_new_key(engine)
    return {
        "verdict": "READY" if ready else "BLOCKED",
        "key": list(_KEY_COLUMNS),
        "new_key_present": ready,
    }
