"""Explicit, one-shot provisioning for the isolated rebuild admin account."""

from __future__ import annotations

import json
import logging
import os
import sys

from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from rebuild.common.db import configure_engine
from rebuild.governance.models import AuditEventRecord
from rebuild.identity.contracts import Role
from rebuild.identity.models import UserRecord
from rebuild.identity.repository import UserRepository
from rebuild.project.models import ProjectRecord  # noqa: F401 - registers audit FK target metadata

logger = logging.getLogger(__name__)
PROVISION_CONFIRMATION = "PROVISION ADMIN datara_rebuild_i0"
TARGET_DATABASE = "datara_rebuild_i0"
ADMIN_USERNAME = "admin"
MIN_PASSWORD_LENGTH = 16


def provision_admin(
    session: Session,
    *,
    database_name: str,
    password: str,
    confirmation: str,
) -> UserRecord:
    """Create exactly one persisted admin and its audit event in one transaction."""
    if database_name != TARGET_DATABASE:
        raise ValueError("admin provisioning is restricted to the isolated rebuild database")
    if confirmation != PROVISION_CONFIRMATION:
        raise ValueError("explicit admin provisioning confirmation is required")
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"admin password must contain at least {MIN_PASSWORD_LENGTH} characters")

    with session.begin():
        existing_admin = session.scalar(select(UserRecord).where(UserRecord.role == Role.ADMIN.value).limit(1))
        if existing_admin is not None:
            raise ValueError("an admin account already exists")

        existing_username = session.scalar(
            select(UserRecord).where(UserRecord.username == ADMIN_USERNAME).limit(1)
        )
        if existing_username is not None:
            raise ValueError("admin username already exists with a different role")

        record = UserRepository(session).create(username=ADMIN_USERNAME, password=password, role=Role.ADMIN)
        session.add(
            AuditEventRecord(
                actor_id=record.id,
                project_id=None,
                action="identity.admin_provisioned",
                resource_type="rebuild_user",
                resource_id=str(record.id),
                request_id="one-shot-admin-provisioning",
                before_json="{}",
                after_json=json.dumps({"username": ADMIN_USERNAME, "role": Role.ADMIN.value}, separators=(",", ":")),
            )
        )
        session.flush()

    logger.info(
        "rebuild_admin_provisioned database=%s user_id=%s username=%s role=%s",
        TARGET_DATABASE,
        record.id,
        ADMIN_USERNAME,
        Role.ADMIN.value,
    )
    return record


def main() -> int:
    """Run only when an operator explicitly injects the one-shot secret and confirmation."""
    database_url = os.environ.pop("REBUILD_DB_URL", "")
    password = os.environ.pop("REBUILD_ADMIN_PROVISION_PASSWORD", "")
    confirmation = os.environ.pop("REBUILD_ADMIN_PROVISION_CONFIRM", "")
    if not database_url or not password or not confirmation:
        print("REBUILD_DB_URL and one-shot admin provisioning inputs are required", file=sys.stderr)
        return 2

    try:
        url = make_url(database_url)
    except (TypeError, ValueError):
        print("invalid rebuild database configuration", file=sys.stderr)
        return 2
    if url.database != TARGET_DATABASE:
        print("admin provisioning target must be datara_rebuild_i0", file=sys.stderr)
        return 2

    engine = configure_engine(database_url)
    try:
        with Session(engine) as session:
            record = provision_admin(
                session,
                database_name=url.database,
                password=password,
                confirmation=confirmation,
            )
            user_id = record.id
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - never print DB driver details or connection values
        logger.error("rebuild_admin_provisioning_failed exception_type=%s", type(exc).__name__)
        print("admin provisioning failed; no credential or database details were emitted", file=sys.stderr)
        return 1
    finally:
        password = ""
        confirmation = ""
        database_url = ""
        engine.dispose()

    print(f"Provisioned isolated rebuild admin user_id={user_id}; no credentials were emitted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
