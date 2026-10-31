"""Cascade project deletion into governance objects (C7).

Doc C 待办 #7：项目删除需级联清理其治理对象（标签/规则/标准/指标/报告/告警），
否则清理无法闭环。治理表均以 project_id 外键关联 rebuild_project，原 ondelete 默认
RESTRICT 会阻止项目删除。本修订将相关外键改为 ON DELETE CASCADE。

该修订对 MySQL 生效（SQLite 由模型层 ondelete 在 create_all 时处理）；幂等：
已为 CASCADE 的外键不会被重复改写。
"""
from sqlalchemy import Engine, text

revision = "r3_0005_governance_project_fk_cascade"
checksum = "a15c0005f1b0c7d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"

_GOVERNANCE_PROJECT_FK_QUERY = """
SELECT k.TABLE_NAME AS table_name, k.CONSTRAINT_NAME AS constraint_name,
       k.COLUMN_NAME AS column_name
FROM information_schema.KEY_COLUMN_USAGE k
JOIN information_schema.REFERENTIAL_CONSTRAINTS r
  ON k.CONSTRAINT_NAME = r.CONSTRAINT_NAME AND k.TABLE_SCHEMA = r.CONSTRAINT_SCHEMA
WHERE k.TABLE_SCHEMA = DATABASE()
  AND k.REFERENCED_TABLE_NAME = 'rebuild_project'
  AND k.TABLE_NAME LIKE 'rebuild\\_governance\\_%'
  AND r.DELETE_RULE != 'CASCADE'
"""


def upgrade(engine: Engine) -> None:
    if engine.dialect.name != "mysql":
        return
    from rebuild.governance.models import GOVERNANCE_TABLES

    allowed = {table.name for table in GOVERNANCE_TABLES}
    with engine.begin() as connection:
        rows = connection.execute(text(_GOVERNANCE_PROJECT_FK_QUERY)).mappings().all()
        for row in rows:
            table = row["table_name"]
            if table not in allowed:
                continue
            constraint = row["constraint_name"]
            column = row["column_name"]
            connection.execute(text(f"ALTER TABLE `{table}` DROP FOREIGN KEY `{constraint}`"))
            connection.execute(text(
                f"ALTER TABLE `{table}` ADD CONSTRAINT `{constraint}` "
                f"FOREIGN KEY (`{column}`) REFERENCES `rebuild_project` (`id`) ON DELETE CASCADE"
            ))
