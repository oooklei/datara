"""Make (project_id, user_id) unique on rebuild_project_member.

并发添加同一成员可产生重复行，导致「同一用户既是成员又不是成员」的不一致判定。
本修订在 MySQL 上先去重（保留每个 (project_id, user_id) 中 id 最小的一行），再补唯一索引；
SQLite 上若历史库缺该唯一约束则重建表（新库由 ``create_all`` 依模型层 ``__table_args__`` 直接建约束）。
"""

from typing import Any

from sqlalchemy import Engine, inspect, text

revision = "i1_0005_project_member_unique"
_DDL_MANIFEST = (
    "i1_0005 rebuild_project_member: dedupe (project_id,user_id) then create unique index "
    "uq_rebuild_project_member_project_user"
)
checksum = "4aad8b47ce3c54b9718c1bf8c75bcd7595e689f2e06e29a66f26e77ebede1f20"

_TABLE = "rebuild_project_member"
_INDEX = "uq_rebuild_project_member_project_user"


def upgrade(engine: Engine) -> None:
    if _TABLE not in inspect(engine).get_table_names():
        from rebuild.identity.models import ProjectMemberRecord

        ProjectMemberRecord.__table__.create(engine, checkfirst=True)
        return
    if engine.dialect.name == "mysql":
        _upgrade_mysql(engine)
    elif engine.dialect.name == "sqlite":
        _upgrade_sqlite(engine)


def _upgrade_mysql(engine: Engine) -> None:
    with engine.begin() as connection:
        # 保留每组最小 id 的行；重复行删除后其成员关系仍由保留行表达。
        connection.execute(text(
            f"DELETE m FROM {_TABLE} m JOIN ("
            f"  SELECT project_id, user_id, MIN(id) AS keep_id FROM {_TABLE}"
            f"  GROUP BY project_id, user_id HAVING COUNT(*) > 1"
            f") d ON m.project_id = d.project_id AND m.user_id = d.user_id AND m.id > d.keep_id"
        ))
        connection.execute(text(f"CREATE UNIQUE INDEX {_INDEX} ON {_TABLE} (project_id, user_id)"))


def _has_sqlite_unique(engine: Engine) -> bool:
    constraints = inspect(engine).get_unique_constraints(_TABLE)
    return any(
        set(item.get("column_names") or []) == {"project_id", "user_id"}
        for item in constraints
    )


def _upgrade_sqlite(engine: Engine) -> None:
    if _has_sqlite_unique(engine):
        return
    with engine.begin() as connection:
        rows = connection.execute(text(f"SELECT * FROM {_TABLE}")).mappings().all()
        connection.execute(text(
            f"CREATE TABLE {_TABLE}_v0005 ("
            "id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "
            "project_id INTEGER NOT NULL, user_id INTEGER NOT NULL, "
            "role VARCHAR(32) NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, "
            f"CONSTRAINT {_INDEX} UNIQUE (project_id, user_id), "
            "FOREIGN KEY(project_id) REFERENCES rebuild_project (id), "
            "FOREIGN KEY(user_id) REFERENCES rebuild_user (id))"
        ))
        for row in rows:
            connection.execute(text(
                f"INSERT OR IGNORE INTO {_TABLE}_v0005 "
                "(id, project_id, user_id, role, created_at, updated_at) VALUES "
                "(:id, :project_id, :user_id, :role, :created_at, :updated_at)"
            ), {
                "id": row["id"],
                "project_id": row["project_id"],
                "user_id": row["user_id"],
                "role": row.get("role") or "viewer",
                "created_at": row.get("created_at") or "1970-01-01 00:00:00",
                "updated_at": row.get("updated_at") or "1970-01-01 00:00:00",
            })
        connection.execute(text(f"DROP TABLE {_TABLE}"))
        connection.execute(text(f"ALTER TABLE {_TABLE}_v0005 RENAME TO {_TABLE}"))
        connection.execute(text(f"CREATE INDEX ix_{_TABLE}_project_id ON {_TABLE} (project_id)"))
        connection.execute(text(f"CREATE INDEX ix_{_TABLE}_user_id ON {_TABLE} (user_id)"))


def postflight(engine: Engine) -> dict[str, Any]:
    inspector = inspect(engine)
    if _TABLE not in inspector.get_table_names():
        return {"revision": revision, "verdict": "PENDING", "problems": ["table_missing"]}

    problems: list[str] = []
    if engine.dialect.name == "sqlite":
        if not _has_sqlite_unique(engine):
            problems.append("project_member_unique_index_invalid")
    else:
        indexes = {item["name"]: item for item in inspector.get_indexes(_TABLE)}
        unique_index = indexes.get(_INDEX)
        if (
            not unique_index
            or not bool(unique_index.get("unique"))
            or set(unique_index.get("column_names") or []) != {"project_id", "user_id"}
        ):
            problems.append("project_member_unique_index_invalid")

    with engine.connect() as connection:
        duplicates = connection.scalar(text(
            f"SELECT COUNT(*) FROM ("
            f"  SELECT project_id, user_id FROM {_TABLE} GROUP BY project_id, user_id HAVING COUNT(*) > 1"
            f") d"
        ))
    if duplicates:
        problems.append("duplicate_member_rows_present")
    return {"revision": revision, "verdict": "READY" if not problems else "PENDING", "problems": problems}
