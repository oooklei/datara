"""Persist workflow category labels and custom category names."""
from sqlalchemy import Engine, inspect, text

revision = "workflow_0002_categories"
checksum = "c4b3c3f6b9c89a1d6a20c7e4db34a3d2e7a3c8f271c514f2d2d2e4d63a0b7f11"

def upgrade(engine: Engine) -> None:
    inspector = inspect(engine)
    columns = {c["name"] for c in inspector.get_columns("workflow_definition")}
    tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        if "tags_json" not in columns:
            conn.execute(text("ALTER TABLE workflow_definition ADD COLUMN tags_json TEXT NOT NULL DEFAULT '[]'"))
        if "workflow_category" not in tables:
            if engine.dialect.name in {"mysql", "mariadb"}:
                ddl = "CREATE TABLE workflow_category (id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, name VARCHAR(128) NOT NULL UNIQUE, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
            else:
                ddl = "CREATE TABLE workflow_category (id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(128) NOT NULL UNIQUE, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
            conn.execute(text(ddl))

def validate_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if "tags_json" not in {c["name"] for c in inspector.get_columns("workflow_definition")}:
        raise RuntimeError("workflow_definition.tags_json is required")
    if "workflow_category" not in set(inspector.get_table_names()):
        raise RuntimeError("workflow_category table is required")
