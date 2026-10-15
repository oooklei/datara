import logging

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.governance.models import AuditEventRecord
from rebuild.identity.models import UserRecord
from rebuild.identity.provision_admin import PROVISION_CONFIRMATION, provision_admin


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_provision_admin_creates_one_hashed_admin_and_audit_event(session, caplog):
    password = "test-only-admin-password-2026"

    with caplog.at_level(logging.INFO):
        record = provision_admin(
            session,
            database_name="datara_rebuild_i0",
            password=password,
            confirmation=PROVISION_CONFIRMATION,
        )

    assert record.username == "admin"
    assert record.role == "admin"
    assert record.status == "enabled"
    assert record.password_hash != password
    assert password not in caplog.text
    assert session.scalar(select(UserRecord).where(UserRecord.role == "admin")).id == record.id
    audit = session.scalar(select(AuditEventRecord))
    assert audit is not None
    assert audit.actor_id == record.id
    assert audit.project_id is None
    assert audit.action == "identity.admin_provisioned"
    assert audit.generated_at is not None
    assert password not in audit.before_json + audit.after_json


@pytest.mark.parametrize(
    ("database_name", "confirmation"),
    [
        ("datara_meta", PROVISION_CONFIRMATION),
        ("datara_rebuild_i0", ""),
    ],
)
def test_provision_admin_rejects_wrong_target_or_missing_confirmation_without_writes(
    session, database_name, confirmation
):
    with pytest.raises(ValueError):
        provision_admin(
            session,
            database_name=database_name,
            password="test-only-admin-password-2026",
            confirmation=confirmation,
        )

    assert session.scalar(select(UserRecord)) is None
    assert session.scalar(select(AuditEventRecord)) is None


def test_provision_admin_fails_closed_if_admin_already_exists(session):
    session.add(UserRecord(username="admin", password_hash="existing", role="admin", status="enabled"))
    session.commit()

    with pytest.raises(ValueError, match="already exists"):
        provision_admin(
            session,
            database_name="datara_rebuild_i0",
            password="test-only-admin-password-2026",
            confirmation=PROVISION_CONFIRMATION,
        )

    assert session.scalar(select(UserRecord).where(UserRecord.username == "admin")).password_hash == "existing"
    assert session.scalar(select(AuditEventRecord)) is None


def test_provision_admin_rejects_existing_username_with_non_admin_role(session):
    session.add(UserRecord(username="admin", password_hash="existing", role="dev", status="enabled"))
    session.commit()

    with pytest.raises(ValueError, match="username already exists"):
        provision_admin(
            session,
            database_name="datara_rebuild_i0",
            password="test-only-admin-password-2026",
            confirmation=PROVISION_CONFIRMATION,
        )

    assert session.scalar(select(AuditEventRecord)) is None
