from __future__ import annotations

import base64
import hashlib
import json

import pytest
from sqlalchemy import MetaData, String, create_engine, inspect, select, text
from sqlalchemy.dialects import mysql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateIndex

from rebuild.governance.migrations import MigrationApplyError, MigrationChecksumConflict
from rebuild.governance.models import SchemaMigrationRecord
from rebuild.llm.crypto import LlmCredentialCipher, mask_api_key
from rebuild.llm.migrations import LLM_MIGRATIONS, apply_llm_migrations
from rebuild.llm.models import LlmModelRecord
from rebuild.llm.repository import LlmModelRepository
from rebuild.llm.revisions import v0001_llm_model as revision


def test_aes_gcm_cipher_is_randomized_tamper_evident_and_fail_closed(monkeypatch) -> None:
    key = bytes(range(32))
    monkeypatch.setenv("LLM_ENCRYPTION_KEY", base64.urlsafe_b64encode(key).decode().rstrip("="))
    cipher = LlmCredentialCipher.from_env()
    first = cipher.encrypt("secret-provider-key")
    second = cipher.encrypt("secret-provider-key")
    assert first != second
    assert "secret-provider-key" not in first
    assert cipher.decrypt(first) == "secret-provider-key"
    version, nonce, ciphertext = first.split(".")
    damaged = ".".join((version, nonce, ("A" if ciphertext[0] != "A" else "B") + ciphertext[1:]))
    with pytest.raises(ValueError, match="invalid or tampered"):
        cipher.decrypt(damaged)
    monkeypatch.delenv("LLM_ENCRYPTION_KEY")
    with pytest.raises(RuntimeError, match="must be configured"):
        LlmCredentialCipher.from_env()


def test_mask_never_returns_full_key() -> None:
    assert mask_api_key("short") == "*****"
    assert mask_api_key("provider-secret-1234").endswith("1234")
    assert mask_api_key("provider-secret-1234") != "provider-secret-1234"


def test_revision_is_frozen_and_preserves_released_checksum() -> None:
    assert revision.LLM_TABLES[0] is not LlmModelRecord.__table__
    encoded = json.dumps(revision.SCHEMA_MANIFEST, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "ascii"
    )
    assert hashlib.sha256(encoded).hexdigest() == "59a6e43877cb7ea8479c3800636038da0175a6f87085252f1c33c741dcd69f8f"
    assert revision.checksum == "4221daed1b1f59837008d1b89e0153f6b15a26b20e5814d23b1df1917af3cb5f"
    columns = {item["name"]: item for item in revision.SCHEMA_MANIFEST["tables"][0]["columns"]}
    assert columns["id"]["autoincrement"] is True
    assert columns["api_key_cipher"]["type"][1] == 512
    assert columns["created_at"]["server_default"] == "current_timestamp"
    assert columns["updated_at"]["server_default"] == "current_timestamp"


def test_mysql_reflection_type_families_are_normalized() -> None:
    dialect = mysql.dialect()
    assert revision._type_contract(mysql.DECIMAL(3, 2), dialect)[0] == "NUMERIC"
    assert revision._type_contract(mysql.INTEGER(), dialect)[0] == "INTEGER"


def test_model_migration_and_repository_default_guards() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    first_migration = apply_llm_migrations(engine)
    second_migration = apply_llm_migrations(engine)
    assert first_migration.applied == ("i15_0001_llm_model",)
    assert second_migration.skipped == first_migration.applied
    columns = {item["name"]: item for item in inspect(engine).get_columns("rebuild_llm_model")}
    assert columns["api_key_cipher"]["nullable"] is False
    assert {"created_at", "updated_at"} <= columns.keys()
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type = 'index' "
                    "AND name = 'uq_rebuild_llm_model_single_default'"
                )
            )
            == 1
        )
    with Session(engine) as session:
        tracked = session.scalar(
            select(SchemaMigrationRecord).where(SchemaMigrationRecord.revision == "i15_0001_llm_model")
        )
        assert tracked is not None and tracked.checksum == LLM_MIGRATIONS[0].checksum
    with Session(engine) as session, session.begin():
        repo = LlmModelRepository(session)
        first = repo.add(_record("first", default=True))
        second = repo.add(_record("second"))
        repo.set_default(second.id)
        assert first.is_default is False and second.is_default is True
        with pytest.raises(ValueError, match="cannot be deleted"):
            repo.delete(second.id)


def test_inactive_model_cannot_be_default_and_database_rejects_two_defaults() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    apply_llm_migrations(engine)
    with Session(engine) as session, session.begin():
        with pytest.raises(ValueError, match="inactive"):
            LlmModelRepository(session).add(_record("disabled", default=True, active=False))
    with Session(engine) as session:
        session.add_all((_record("first", default=True), _record("second", default=True)))
        with pytest.raises(IntegrityError):
            session.commit()


def test_migration_checksum_conflict_and_schema_drift_fail_closed() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    apply_llm_migrations(engine)
    with Session(engine) as session, session.begin():
        tracked = session.scalar(
            select(SchemaMigrationRecord).where(SchemaMigrationRecord.revision == "i15_0001_llm_model")
        )
        tracked.checksum = "0" * 64
    with pytest.raises(MigrationChecksumConflict, match="checksum changed"):
        apply_llm_migrations(engine)

    drifted = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    table = revision.LLM_TABLES[0].to_metadata(metadata)
    table.columns.api_key_cipher.type = String(511)
    metadata.create_all(drifted)
    with pytest.raises(MigrationApplyError, match="failed"):
        apply_llm_migrations(drifted)

    missing_default = create_engine("sqlite+pysqlite:///:memory:")
    missing_default_metadata = MetaData()
    missing_default_table = revision.LLM_TABLES[0].to_metadata(missing_default_metadata)
    missing_default_table.columns.created_at.server_default = None
    missing_default_metadata.create_all(missing_default)
    with pytest.raises(MigrationApplyError, match="failed"):
        apply_llm_migrations(missing_default)

    completed_then_drifted = create_engine("sqlite+pysqlite:///:memory:")
    apply_llm_migrations(completed_then_drifted)
    with completed_then_drifted.begin() as connection:
        connection.execute(text("DROP INDEX uq_rebuild_llm_model_single_default"))
    with pytest.raises(MigrationApplyError, match="schema validation failed"):
        apply_llm_migrations(completed_then_drifted)


@pytest.mark.parametrize(
    "replacement",
    (
        "CREATE INDEX uq_rebuild_llm_model_single_default ON rebuild_llm_model (is_default)",
        "CREATE UNIQUE INDEX uq_rebuild_llm_model_single_default ON rebuild_llm_model (is_default)",
    ),
)
def test_default_index_same_name_with_wrong_contract_is_rejected(replacement: str) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    apply_llm_migrations(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX uq_rebuild_llm_model_single_default"))
        connection.execute(text(replacement))
    with pytest.raises(MigrationApplyError, match="schema validation failed"):
        apply_llm_migrations(engine)


def test_mysql_reflected_default_index_requires_unique_nullif_expression() -> None:
    dialect = mysql.dialect()
    valid = {
        "name": "uq_rebuild_llm_model_single_default",
        "unique": True,
        "column_names": [None],
        "expressions": ["nullif(`is_default`, false)"],
    }
    revision._validate_default_index_contract(valid, dialect)
    with pytest.raises(RuntimeError, match="incompatible default index"):
        revision._validate_default_index_contract({**valid, "unique": False}, dialect)
    with pytest.raises(RuntimeError, match="incompatible default index"):
        revision._validate_default_index_contract({**valid, "expressions": ["is_default"]}, dialect)
    ddl = str(CreateIndex(next(iter(revision.llm_model_table.indexes))).compile(dialect=dialect)).lower()
    assert "create unique index" in ddl
    assert "nullif(is_default, false)" in ddl


def _record(name: str, *, default: bool = False, active: bool = True) -> LlmModelRecord:
    return LlmModelRecord(
        name=name,
        display_name=name.title(),
        provider="siliconflow",
        api_base="https://example.invalid/v1",
        model_id="test-model",
        api_key_cipher="v1.nonce.ciphertext",
        is_active=active,
        is_default=default,
    )
