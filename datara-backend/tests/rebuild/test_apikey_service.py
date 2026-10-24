from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from rebuild.apikey.models import ApiKeyRecord
from rebuild.apikey.service import ApiKeyAuthError, ApiKeyVerifier, _digest
from rebuild.common.db import Base


def _fixture():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[ApiKeyRecord.__table__])
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    plain = "dk_live_test-secret"
    with factory() as session:
        session.add(ApiKeyRecord(
            name="etl", key_hash=_digest(plain), key_prefix=plain[:16],
            scopes_json='{"permissions":["workflow:run"],"projectIds":[7]}',
            created_by="admin",
        ))
        session.commit()
    return engine, factory, plain


def test_verifier_checks_hash_and_scopes_and_updates_last_used():
    engine, factory, plain = _fixture()
    try:
        principal = ApiKeyVerifier(factory).verify(plain, permission="workflow:run", project_id=7)
        assert principal.key_id == 1
        with factory() as session:
            assert session.get(ApiKeyRecord, 1).last_used_at is not None
        with pytest.raises(ApiKeyAuthError, match="scope"):
            ApiKeyVerifier(factory).verify(plain, permission="workflow:write", project_id=7)
        with pytest.raises(ApiKeyAuthError, match="scope"):
            ApiKeyVerifier(factory).verify(plain, permission="workflow:run", project_id=8)
    finally:
        engine.dispose()


@pytest.mark.parametrize("mutator, message", [
    (lambda row: setattr(row, "status", "revoked"), "not active"),
    (lambda row: setattr(row, "expires_at", datetime.utcnow() - timedelta(seconds=1)), "expired"),
])
def test_verifier_rejects_lifecycle_states(mutator, message):
    engine, factory, plain = _fixture()
    try:
        with factory() as session:
            mutator(session.get(ApiKeyRecord, 1))
            session.commit()
        with pytest.raises(ApiKeyAuthError, match=message):
            ApiKeyVerifier(factory).verify(plain)
    finally:
        engine.dispose()


def test_verifier_rejects_malformed_or_wrong_key():
    engine, factory, plain = _fixture()
    try:
        verifier = ApiKeyVerifier(factory)
        for value in ("", "wrong", plain + "-tampered"):
            with pytest.raises(ApiKeyAuthError):
                verifier.verify(value)
    finally:
        engine.dispose()
