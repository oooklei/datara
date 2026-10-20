import hashlib

from sqlalchemy import Engine, inspect, text


revision = "r2_0001_variable_runtime_timestamp"
checksum = hashlib.sha256(b"r2_0001 add database-generated timestamp to task variable runtime").hexdigest()


def upgrade(engine: Engine) -> None:
    from rebuild.common.db import Base
    from rebuild.variables.models import TaskInstanceVariableRuntimeRecord

    Base.metadata.create_all(bind=engine, tables=[TaskInstanceVariableRuntimeRecord.__table__], checkfirst=True)
    columns = {column["name"] for column in inspect(engine).get_columns("task_instance_variable_runtime")}
    if "generated_at" in columns:
        return
    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE task_instance_variable_runtime ADD COLUMN generated_at DATETIME"))
            connection.execute(text(
                "UPDATE task_instance_variable_runtime SET generated_at = CURRENT_TIMESTAMP WHERE generated_at IS NULL"
            ))
    else:
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE task_instance_variable_runtime ADD COLUMN generated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ))
