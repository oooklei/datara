import hashlib
from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from rebuild.governance.migrations import MigrationRunner, R3_GOVERNANCE_MIGRATIONS
from rebuild.governance.revisions import v0004_token_digest_hardening
from rebuild.identity.models import ActiveTokenRecord, UserRecord
from rebuild.project.models import ProjectRecord


def isolated_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ProjectRecord.__table__.create(engine)
    UserRecord.__table__.create(engine)
    return engine


def _v0004_migration():
    entry = R3_GOVERNANCE_MIGRATIONS[3]
    assert entry.revision == v0004_token_digest_hardening.revision
    return entry


def test_v0004_revision_and_checksum_are_stable():
    assert v0004_token_digest_hardening.revision == "r3_0004_token_digest_hardening"
    assert (
        hashlib.sha256(v0004_token_digest_hardening._DDL_MANIFEST.encode()).hexdigest()
        == v0004_token_digest_hardening.checksum
    )


def test_fresh_schema_has_digest_column_and_unique_index():
    engine = isolated_engine()
    MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS).apply()

    columns = {item["name"]: item for item in inspect(engine).get_columns("rebuild_active_token")}
    indexes = {item["name"]: item for item in inspect(engine).get_indexes("rebuild_active_token")}
    assert getattr(columns["token_digest"]["type"], "length", None) == 64
    assert columns["token_digest"]["nullable"] is False
    assert bool(indexes["ix_rebuild_active_token_token_digest"]["unique"])


def test_legacy_tokens_are_backfilled_and_reapply_is_idempotent():
    engine = isolated_engine()
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE rebuild_active_token (token VARCHAR(512) PRIMARY KEY, user_id INTEGER NOT NULL, "
            "username VARCHAR(64) NOT NULL, role VARCHAR(32) NOT NULL, capability VARCHAR(128), "
            "issued_at DATETIME, expires_at DATETIME)"
        ))
        connection.execute(text(
            "INSERT INTO rebuild_active_token "
            "(token, user_id, username, role, expires_at) VALUES "
            "('legacy-a', 1, 'admin', 'admin', '2026-12-31'), "
            "('legacy-b', 2, 'dev', 'developer', '2026-12-31')"
        ))

    first = MigrationRunner(engine, [_v0004_migration()]).apply()
    second = MigrationRunner(engine, [_v0004_migration()]).apply()
    with engine.connect() as connection:
        rows = dict(connection.execute(text("SELECT token, token_digest FROM rebuild_active_token")))

    assert rows == {token: hashlib.sha256(token.encode()).hexdigest() for token in ("legacy-a", "legacy-b")}
    assert first.applied == (v0004_token_digest_hardening.revision,)
    assert second.skipped == first.applied


def test_unique_digest_index_rejects_duplicates():
    engine = isolated_engine()
    MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS).apply()
    with Session(engine) as session:
        for token in ("a", "b"):
            session.add(ActiveTokenRecord(
                token=token,
                token_digest="d" * 64,
                user_id=None,
                username="runner",
                role="viewer",
                expires_at=datetime(2026, 12, 31),
            ))
            if token == "a":
                session.commit()
        with pytest.raises(IntegrityError):
            session.commit()
