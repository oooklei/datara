"""Make the persisted ``env`` namespace an explicit project environment group."""

import hashlib

from sqlalchemy import Engine, inspect, text


revision = "r2_0002_environment_group_scope"
checksum = hashlib.sha256(b"r2_0002 persist project environment group variable scope").hexdigest()


def upgrade(engine: Engine) -> None:
    if "rebuild_variable_definition" not in inspect(engine).get_table_names():
        from rebuild.variables.models import VariableDefinitionRecord

        VariableDefinitionRecord.__table__.create(engine, checkfirst=True)
        return
    if _supports_env_scope(engine):
        return
    if engine.dialect.name == "sqlite":
        _upgrade_sqlite(engine)
    else:
        _upgrade_mysql(engine)


def _supports_env_scope(engine: Engine) -> bool:
    try:
        with engine.begin() as connection:
            connection.execute(text("SAVEPOINT variable_env_probe"))
            connection.execute(text(
                "INSERT INTO rebuild_variable_definition "
                "(scope,project_id,owner_key,name,value_type,value_json,`sensitive`,description,nullable) "
                "VALUES ('env',2147483000,'env:2147483000:1','__migration_probe__','string','x',0,'',1)"
            ))
            connection.execute(text("ROLLBACK TO SAVEPOINT variable_env_probe"))
            connection.execute(text("RELEASE SAVEPOINT variable_env_probe"))
        return True
    except Exception:
        return False


def _upgrade_sqlite(engine: Engine) -> None:
    from rebuild.variables.models import VariableDefinitionRecord

    columns = [column["name"] for column in inspect(engine).get_columns("rebuild_variable_definition")]
    target_columns = [column.name for column in VariableDefinitionRecord.__table__.columns]
    common = [column for column in target_columns if column in columns]
    quoted = ",".join(f'"{column}"' for column in common)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE rebuild_variable_definition RENAME TO rebuild_variable_definition_legacy"))
        # Explicit indexes retain their global names after a SQLite table rename.
        connection.execute(text("DROP INDEX IF EXISTS ix_variable_project_name"))
        connection.execute(text("DROP INDEX IF EXISTS uq_variable_owner_name"))
        VariableDefinitionRecord.__table__.create(connection)
        connection.execute(text(
            f"INSERT INTO rebuild_variable_definition ({quoted}) "
            f"SELECT {quoted} FROM rebuild_variable_definition_legacy"
        ))
        connection.execute(text("DROP TABLE rebuild_variable_definition_legacy"))


def _upgrade_mysql(engine: Engine) -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("rebuild_variable_definition")}
    missing_column_ddl = {
        "default_value": "ADD COLUMN default_value TEXT NULL",
        "nullable": "ADD COLUMN `nullable` BOOLEAN NOT NULL DEFAULT 1",
        "format": "ADD COLUMN `format` VARCHAR(64) NULL",
        "timezone": "ADD COLUMN timezone VARCHAR(64) NULL",
        "business_calendar": "ADD COLUMN business_calendar VARCHAR(64) NULL",
    }
    with engine.begin() as connection:
        # Early R2 deployments created the variable table before these form
        # fields existed.  The env-scope probe references ``nullable``, so the
        # additive columns must be restored before probing or changing checks.
        for name, ddl in missing_column_ddl.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE rebuild_variable_definition {ddl}"))
        connection.execute(text("ALTER TABLE rebuild_variable_definition DROP CHECK ck_variable_scope"))
        connection.execute(text("ALTER TABLE rebuild_variable_definition DROP CHECK ck_variable_owner_scope"))
        connection.execute(text(
            "ALTER TABLE rebuild_variable_definition ADD CONSTRAINT ck_variable_scope "
            "CHECK (scope IN ('global','project','env','tmp','workflow','task'))"
        ))
        connection.execute(text(
            "ALTER TABLE rebuild_variable_definition ADD CONSTRAINT ck_variable_owner_scope CHECK ("
            "(scope='global' AND project_id IS NULL) OR "
            "(scope IN ('project','env','tmp','workflow','task') AND project_id IS NOT NULL))"
        ))


def postflight(engine: Engine) -> dict[str, object]:
    if not _supports_env_scope(engine):
        raise RuntimeError("rebuild_variable_definition does not accept env scope")
    return {"verdict": "READY", "env_scope": True}
