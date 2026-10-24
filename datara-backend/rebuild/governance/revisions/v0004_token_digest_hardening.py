"""Add and backfill the active-token SHA-256 digest."""

import hashlib

from sqlalchemy import Engine, inspect, text

revision = "r3_0004_token_digest_hardening"
_DDL_MANIFEST = (
    "r3_0004 rebuild_active_token: add token_digest CHAR(64), backfill sha256, "
    "create unique index ix_rebuild_active_token_token_digest"
)
checksum = hashlib.sha256(_DDL_MANIFEST.encode("utf-8")).hexdigest()

_TABLE = "rebuild_active_token"
_INDEX = "ix_rebuild_active_token_token_digest"


def upgrade(engine: Engine) -> None:
    from rebuild.identity.models import ActiveTokenRecord

    if _TABLE not in inspect(engine).get_table_names():
        ActiveTokenRecord.__table__.create(engine, checkfirst=True)
        return

    columns = {column["name"] for column in inspect(engine).get_columns(_TABLE)}
    with engine.begin() as connection:
        if "token_digest" not in columns:
            connection.execute(text(f"ALTER TABLE {_TABLE} ADD COLUMN token_digest CHAR(64)"))

        # Re-inspection matters for legacy SQLite connections: the ALTER must be
        # visible before selecting and updating the newly added column.
        if "token_digest" not in {column["name"] for column in inspect(connection).get_columns(_TABLE)}:
            raise RuntimeError("token_digest column was not created")
        rows = connection.execute(
            text(f"SELECT token FROM {_TABLE} WHERE token_digest IS NULL OR token_digest = ''")
        ).scalars()
        connection.execute(
            text(f"UPDATE {_TABLE} SET token_digest = :digest WHERE token = :token"),
            [
                {"token": token, "digest": hashlib.sha256(str(token).encode("utf-8")).hexdigest()}
                for token in rows
            ],
        )

        indexes = {index["name"] for index in inspect(connection).get_indexes(_TABLE)}
        if _INDEX not in indexes:
            connection.execute(text(f"CREATE UNIQUE INDEX {_INDEX} ON {_TABLE} (token_digest)"))


def postflight(engine: Engine) -> dict[str, object]:
    inspector = inspect(engine)
    columns = {column["name"]: column for column in inspector.get_columns(_TABLE)}
    indexes = {index["name"]: index for index in inspector.get_indexes(_TABLE)}
    with engine.connect() as connection:
        pending = int(connection.scalar(text(
            f"SELECT COUNT(*) FROM {_TABLE} WHERE token_digest IS NULL OR token_digest = ''"
        )) or 0)
    limitations = [] if pending == 0 else ["digest_backfill_pending"]
    return {
        "revision": revision,
        "token_digest_column_present": "token_digest" in columns,
        "unique_index_present": _INDEX in indexes and bool(indexes[_INDEX].get("unique")),
        "digest_pending_rows": pending,
        "limitations": limitations,
        "verdict": "READY" if not limitations else "PENDING",
    }
