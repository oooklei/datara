"""Local migration coverage; real MySQL retry remains evidence for the final unified 1.9 integration."""

import hashlib
from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from rebuild.governance.migrations import MigrationApplyError, MigrationRunner, R3_GOVERNANCE_MIGRATIONS
from rebuild.governance.revisions import v0004_token_digest_hardening
from rebuild.identity.models import ActiveTokenRecord, UserRecord
from rebuild.project.models import ProjectRecord


def isolated_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    ProjectRecord.__table__.create(engine)
    UserRecord.__table__.create(engine)
    return engine


def _v0004_migration():
    return R3_GOVERNANCE_MIGRATIONS[3]


def _create_legacy_table(engine, *, digest_index_sql=""):
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE rebuild_active_token (token VARCHAR(512) PRIMARY KEY, user_id INTEGER NOT NULL, "
            "username VARCHAR(64) NOT NULL, role VARCHAR(32) NOT NULL, capability VARCHAR(128), "
            "issued_at DATETIME, expires_at DATETIME)"
        ))
        if digest_index_sql:
            connection.execute(text("ALTER TABLE rebuild_active_token ADD COLUMN token_digest CHAR(64)"))
            connection.execute(text(digest_index_sql))


def test_v0004_revision_and_checksum_are_frozen_literals():
    assert v0004_token_digest_hardening.revision == "r3_0004_token_digest_hardening"
    assert v0004_token_digest_hardening.checksum == "dafcd2eadd1c59829a11be05e5a0004566c6d2b90f539135521440859eabc4cb"
    assert hashlib.sha256(v0004_token_digest_hardening._DDL_MANIFEST.encode()).hexdigest() == (
        v0004_token_digest_hardening.checksum
    )


@pytest.mark.parametrize(
    ("state", "expected_actions"),
    [
        (
            {
                "columns": {"token", "user_id"},
                "digest_nullable": None,
                "user_nullable": False,
                "runner_zero_rows": True,
                "pk": ["token"],
                "index": None,
                "fk": False,
            },
            [
                "add_digest",
                "backfill_digest",
                "make_user_nullable",
                "canonicalize_runner",
                "make_digest_required",
                "promote_digest_pk",
                "drop_raw_token",
                "create_digest_index",
                "create_user_fk",
            ],
        ),
        (
            {
                "columns": {"token_digest", "user_id"},
                "digest_nullable": False,
                "user_nullable": True,
                "runner_zero_rows": False,
                "pk": ["token_digest"],
                "index": None,
                "fk": False,
            },
            ["create_digest_index", "create_user_fk"],
        ),
        (
            {
                "columns": {"token_digest", "user_id"},
                "digest_nullable": False,
                "user_nullable": True,
                "runner_zero_rows": False,
                "pk": ["token_digest"],
                "index": {"unique": True, "column_names": ["token_digest"]},
                "fk": False,
            },
            ["create_user_fk"],
        ),
        (
            {
                "columns": {"token_digest", "user_id"},
                "digest_nullable": False,
                "user_nullable": True,
                "runner_zero_rows": False,
                "pk": ["token_digest"],
                "index": {"unique": True, "column_names": ["token_digest"]},
                "fk": True,
            },
            [],
        ),
    ],
)
def test_mysql_partial_ddl_resume_plan_has_exact_ordered_remaining_steps(state, expected_actions):
    actions = [name for name, _sql in v0004_token_digest_hardening._mysql_upgrade_plan(**state)]
    assert actions == expected_actions


def test_fresh_schema_converges_on_digest_primary_identity():
    engine = isolated_engine()
    MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS).apply()
    inspector = inspect(engine)
    columns = {item["name"]: item for item in inspector.get_columns("rebuild_active_token")}
    indexes = {item["name"]: item for item in inspector.get_indexes("rebuild_active_token")}
    assert set(columns) == {"token_digest", "user_id", "username", "role", "capability", "issued_at", "expires_at"}
    assert getattr(columns["token_digest"]["type"], "length", None) == 64
    assert columns["token_digest"]["nullable"] is False
    assert columns["token_digest"]["primary_key"] == 1
    assert columns["user_id"]["nullable"] is True
    assert indexes["ix_rebuild_active_token_token_digest"]["column_names"] == ["token_digest"]
    assert bool(indexes["ix_rebuild_active_token_token_digest"]["unique"])


def test_legacy_schema_rebuilds_without_raw_tokens_and_preserves_runner():
    engine = isolated_engine()
    _create_legacy_table(engine)
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO rebuild_active_token (token, user_id, username, role, expires_at) VALUES "
            "('legacy-a', 0, 'validation-runner', 'viewer', '2026-12-31'), "
            "('legacy-b', 0, 'validation-runner', 'viewer', '2026-12-31')"
        ))
    first = MigrationRunner(engine, [_v0004_migration()]).apply()
    second = MigrationRunner(engine, [_v0004_migration()]).apply()
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT token_digest, user_id FROM rebuild_active_token")).fetchall()
    expected_digests = {hashlib.sha256(token.encode()).hexdigest() for token in ("legacy-a", "legacy-b")}
    assert {row[0] for row in rows} == expected_digests
    assert {row[1] for row in rows} == {None}
    assert "token" not in {item["name"] for item in inspect(engine).get_columns("rebuild_active_token")}
    assert first.applied == (v0004_token_digest_hardening.revision,)
    assert second.skipped == first.applied


def test_digest_primary_key_rejects_duplicates():
    engine = isolated_engine()
    MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS).apply()
    with Session(engine) as session:
        session.add(ActiveTokenRecord(
            token_digest="d" * 64, user_id=None, username="runner", role="viewer", expires_at=datetime(2026, 12, 31)
        ))
        session.commit()
        session.add(ActiveTokenRecord(
            token_digest="d" * 64, user_id=None, username="runner", role="viewer", expires_at=datetime(2026, 12, 31)
        ))
        with pytest.raises(IntegrityError):
            session.commit()


@pytest.mark.parametrize(
    "drift_sql",
    ["DROP INDEX ix_rebuild_active_token_token_digest", "UPDATE rebuild_active_token SET token_digest = 'bad'"],
)
def test_completed_revision_fails_closed_after_schema_or_data_drift(drift_sql):
    engine = isolated_engine()
    MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS).apply()
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO rebuild_active_token (token_digest, username, role, issued_at, expires_at) "
            "VALUES (:digest, 'runner', 'viewer', '2026-01-01', '2026-12-31')"
        ), {"digest": hashlib.sha256(b"safe").hexdigest()})
        connection.execute(text(drift_sql))
    with pytest.raises(MigrationApplyError, match="postflight"):
        MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS).apply()


def test_same_named_non_unique_wrong_column_index_is_replaced_not_skipped():
    engine = isolated_engine()
    _create_legacy_table(
        engine,
        digest_index_sql="CREATE INDEX ix_rebuild_active_token_token_digest ON rebuild_active_token (username)",
    )
    MigrationRunner(engine, [_v0004_migration()]).apply()
    index = {item["name"]: item for item in inspect(engine).get_indexes("rebuild_active_token")}
    assert bool(index["ix_rebuild_active_token_token_digest"]["unique"])
    assert index["ix_rebuild_active_token_token_digest"]["column_names"] == ["token_digest"]


def test_unrepairable_digest_only_structure_drift_fails_closed_on_first_apply():
    engine = isolated_engine()
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE rebuild_active_token (token_digest VARCHAR(32), user_id INTEGER NOT NULL, "
            "username VARCHAR(64), role VARCHAR(32), issued_at DATETIME, expires_at DATETIME)"
        ))
    with pytest.raises(MigrationApplyError, match="postflight"):
        MigrationRunner(engine, [_v0004_migration()]).apply()


class _MysqlReflectionShape:
    """Model MySQL reflection: PK lives in get_pk_constraint, not ReflectedColumn."""

    def __init__(self, delegate, primary_key):
        self._delegate = delegate
        self._primary_key = primary_key

    def get_columns(self, table):
        return [{key: value for key, value in item.items() if key != "primary_key"} for item in self._delegate.get_columns(table)]

    def get_pk_constraint(self, _table):
        return {"constrained_columns": self._primary_key}

    def __getattr__(self, name):
        return getattr(self._delegate, name)


@pytest.mark.parametrize(("primary_key", "verdict"), [(["token_digest"], "READY"), ([], "PENDING")])
def test_postflight_uses_mysql_primary_key_constraint_reflection(monkeypatch, primary_key, verdict):
    engine = isolated_engine()
    MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS).apply()
    reflected = _MysqlReflectionShape(inspect(engine), primary_key)
    monkeypatch.setattr(v0004_token_digest_hardening, "inspect", lambda _engine: reflected)

    report = v0004_token_digest_hardening.postflight(engine)

    assert report["verdict"] == verdict
    assert ("digest_not_primary_key" in report["problems"]) is (verdict == "PENDING")
