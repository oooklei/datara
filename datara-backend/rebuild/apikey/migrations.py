"""Idempotent schema bootstrap for the API-key domain."""

from sqlalchemy import inspect, text

from rebuild.apikey.models import ApiKeyRecord

_TABLE = "rebuild_api_key"
_CREATOR_COLUMN = "created_by_user_id"
_CREATOR_INDEX = "ix_rebuild_api_key_created_by_user_id"
_CREATOR_FK = "fk_rebuild_api_key_creator"


def apply_apikey_migrations(engine):
    """建表 + i15_0003：把 created_by 用户名归属收敛为用户 ID 外键并回填。

    新库由模型直接建出 created_by_user_id；历史库先补列，再按用户名回填，
    回填不到的（用户已改名/已删除）保留 NULL，不臆造归属。
    """
    inspector = inspect(engine)
    created = False
    if _TABLE not in inspector.get_table_names():
        ApiKeyRecord.__table__.create(bind=engine)
        created = True
    else:
        _ensure_creator_column(engine)
    backfilled = _backfill_creator_user(engine)
    return {
        "created": created,
        "backfilled": backfilled,
        "revision": "i15_0003_api_key_creator_user",
    }


def _ensure_creator_column(engine) -> None:
    columns = {item["name"] for item in inspect(engine).get_columns(_TABLE)}
    if _CREATOR_COLUMN in columns:
        return
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {_TABLE} ADD COLUMN {_CREATOR_COLUMN} INTEGER NULL"))
        connection.execute(
            text(f"CREATE INDEX {_CREATOR_INDEX} ON {_TABLE} ({_CREATOR_COLUMN})")
        )


def _backfill_creator_user(engine) -> int:
    """按用户名快照回填 created_by_user_id；幂等，只填 NULL 行。"""
    if "rebuild_user" not in inspect(engine).get_table_names():
        return 0
    with engine.begin() as connection:
        result = connection.execute(
            text(
                f"UPDATE {_TABLE} SET {_CREATOR_COLUMN} = ("
                f"  SELECT u.id FROM rebuild_user u WHERE u.username = {_TABLE}.created_by"
                f") WHERE {_CREATOR_COLUMN} IS NULL"
                f" AND created_by IS NOT NULL AND created_by <> ''"
            )
        )
        backfilled = result.rowcount or 0
        if engine.dialect.name == "mysql":
            _ensure_creator_fk(connection)
    return backfilled


def _ensure_creator_fk(connection) -> None:
    """MySQL 历史库补外键；SQLite 不支持 ALTER 加约束，由模型建表时承担。"""
    existing = {
        item.get("name") for item in inspect(connection).get_foreign_keys(_TABLE)
    }
    if _CREATOR_FK in existing:
        return
    connection.execute(
        text(
            f"ALTER TABLE {_TABLE} ADD CONSTRAINT {_CREATOR_FK} "
            f"FOREIGN KEY ({_CREATOR_COLUMN}) REFERENCES rebuild_user (id)"
        )
    )
