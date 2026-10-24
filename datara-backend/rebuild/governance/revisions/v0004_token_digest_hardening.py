"""Converge active tokens on a digest-only database identity."""

import hashlib
import re
from typing import Any

from sqlalchemy import Engine, inspect, text

revision = "r3_0004_token_digest_hardening"
_DDL_MANIFEST = (
    "r3_0004 rebuild_active_token: resumable mysql steps, token_digest CHAR(64) primary identity, "
    "nullable user_id, discard legacy raw token, preserve identity fields and foreign key"
)
checksum = "dafcd2eadd1c59829a11be05e5a0004566c6d2b90f539135521440859eabc4cb"

_TABLE = "rebuild_active_token"
_INDEX = "ix_rebuild_active_token_token_digest"
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def upgrade(engine: Engine) -> None:
    from rebuild.identity.models import ActiveTokenRecord

    if _TABLE not in inspect(engine).get_table_names():
        ActiveTokenRecord.__table__.create(engine, checkfirst=True)
        return
    columns = {column["name"] for column in inspect(engine).get_columns(_TABLE)}
    if engine.dialect.name == "sqlite":
        if "token" in columns:
            _rebuild_sqlite(engine)
    elif engine.dialect.name == "mysql":
        _upgrade_mysql(engine)
    else:
        raise RuntimeError(f"unsupported token migration dialect: {engine.dialect.name}")


def _rebuild_sqlite(engine: Engine) -> None:
    with engine.begin() as connection:
        rows = connection.execute(text(f"SELECT * FROM {_TABLE}")).mappings().all()
        connection.execute(text(
            "CREATE TABLE rebuild_active_token_v0004 ("
            "token_digest CHAR(64) NOT NULL PRIMARY KEY, user_id INTEGER NULL, "
            "username VARCHAR(64) NOT NULL, role VARCHAR(32) NOT NULL, capability VARCHAR(128), "
            "issued_at DATETIME NOT NULL, expires_at DATETIME NOT NULL, "
            "FOREIGN KEY(user_id) REFERENCES rebuild_user (id))"
        ))
        payload = []
        for row in rows:
            raw_token = str(row["token"])
            payload.append({
                "token_digest": hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
                "user_id": None if row["user_id"] == 0 else row["user_id"],
                "username": row["username"],
                "role": row["role"],
                "capability": row.get("capability"),
                "issued_at": row.get("issued_at") or "1970-01-01 00:00:00",
                "expires_at": row["expires_at"],
            })
        if payload:
            connection.execute(text(
                "INSERT INTO rebuild_active_token_v0004 "
                "(token_digest, user_id, username, role, capability, issued_at, expires_at) VALUES "
                "(:token_digest, :user_id, :username, :role, :capability, :issued_at, :expires_at)"
            ), payload)
        connection.execute(text(f"DROP TABLE {_TABLE}"))
        connection.execute(text(f"ALTER TABLE rebuild_active_token_v0004 RENAME TO {_TABLE}"))
        connection.execute(text(f"CREATE UNIQUE INDEX {_INDEX} ON {_TABLE} (token_digest)"))
        connection.execute(text(f"CREATE INDEX ix_{_TABLE}_user_id ON {_TABLE} (user_id)"))


def _mysql_upgrade_plan(
    *,
    columns: set[str],
    digest_nullable: bool | None,
    pk: list[str],
    index: dict[str, Any] | None,
    fk: bool,
) -> list[tuple[str, str]]:
    actions: list[tuple[str, str]] = []
    if "token_digest" not in columns:
        if "token" not in columns:
            return actions
        actions.append(("add_digest", f"ALTER TABLE {_TABLE} ADD COLUMN token_digest CHAR(64) NULL"))
    if "token" in columns:
        actions.append(("backfill_digest", f"UPDATE {_TABLE} SET token_digest = LOWER(SHA2(token, 256))"))
    actions.append(("canonicalize_runner", f"UPDATE {_TABLE} SET user_id = NULL WHERE user_id = 0"))
    if digest_nullable is not False:
        actions.append(("make_digest_required", f"ALTER TABLE {_TABLE} MODIFY token_digest CHAR(64) NOT NULL"))
    if pk != ["token_digest"]:
        primary_key_clause = "ADD PRIMARY KEY (token_digest)"
        if pk:
            primary_key_clause = f"DROP PRIMARY KEY, {primary_key_clause}"
        actions.append((
            "promote_digest_pk",
            f"ALTER TABLE {_TABLE} {primary_key_clause}",
        ))
    if "token" in columns:
        actions.append(("drop_raw_token", f"ALTER TABLE {_TABLE} DROP COLUMN token"))
    if index and (not bool(index.get("unique")) or index.get("column_names") != ["token_digest"]):
        actions.append(("drop_bad_digest_index", f"DROP INDEX {_INDEX} ON {_TABLE}"))
        index = None
    if not index:
        actions.append(("create_digest_index", f"CREATE UNIQUE INDEX {_INDEX} ON {_TABLE} (token_digest)"))
    if not fk:
        actions.append((
            "create_user_fk",
            f"ALTER TABLE {_TABLE} ADD CONSTRAINT fk_rebuild_active_token_user_id "
            "FOREIGN KEY (user_id) REFERENCES rebuild_user (id)",
        ))
    return actions


def _upgrade_mysql(engine: Engine) -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        column_info = {item["name"]: item for item in inspector.get_columns(_TABLE)}
        indexes = {item["name"]: item for item in inspector.get_indexes(_TABLE)}
        foreign_keys = inspector.get_foreign_keys(_TABLE)
        state = {
            "columns": set(column_info),
            "digest_nullable": column_info.get("token_digest", {}).get("nullable"),
            "pk": inspector.get_pk_constraint(_TABLE).get("constrained_columns") or [],
            "index": indexes.get(_INDEX),
            "fk": any(
                item.get("constrained_columns") == ["user_id"]
                and item.get("referred_table") == "rebuild_user"
                and item.get("referred_columns") == ["id"]
                for item in foreign_keys
            ),
        }
        if not bool(column_info.get("user_id", {}).get("nullable")):
            connection.execute(text(f"ALTER TABLE {_TABLE} MODIFY user_id INT NULL"))
        for _name, statement in _mysql_upgrade_plan(**state):
            connection.execute(text(statement))


def postflight(engine: Engine) -> dict[str, Any]:
    problems: list[str] = []
    inspector = inspect(engine)
    if _TABLE not in inspector.get_table_names():
        return {"revision": revision, "verdict": "PENDING", "problems": ["table_missing"]}

    columns = {column["name"]: column for column in inspector.get_columns(_TABLE)}
    digest = columns.get("token_digest")
    if digest is None:
        problems.append("digest_column_missing")
    else:
        if getattr(digest.get("type"), "length", None) != 64:
            problems.append("digest_type_invalid")
        if bool(digest.get("nullable")):
            problems.append("digest_nullable")
        if not bool(digest.get("primary_key")):
            problems.append("digest_not_primary_key")
    if "token" in columns:
        problems.append("raw_token_column_present")
    if not bool(columns.get("user_id", {}).get("nullable")):
        problems.append("user_id_not_nullable")

    indexes = {item["name"]: item for item in inspector.get_indexes(_TABLE)}
    digest_index = indexes.get(_INDEX)
    if not digest_index or not bool(digest_index.get("unique")) or digest_index.get("column_names") != ["token_digest"]:
        problems.append("digest_unique_index_invalid")

    foreign_keys = inspector.get_foreign_keys(_TABLE)
    if not any(
        item.get("constrained_columns") == ["user_id"]
        and item.get("referred_table") == "rebuild_user"
        and item.get("referred_columns") == ["id"]
        for item in foreign_keys
    ):
        problems.append("user_foreign_key_invalid")

    if digest is not None:
        with engine.connect() as connection:
            values = connection.execute(text(f"SELECT token_digest FROM {_TABLE}")).scalars()
            if any(not isinstance(value, str) or not _DIGEST_RE.fullmatch(value) for value in values):
                problems.append("digest_data_invalid")
    return {"revision": revision, "verdict": "READY" if not problems else "PENDING", "problems": problems}
