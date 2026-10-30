import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.dbx.access import DbxConnectionAccess
from rebuild.dbx.models import DbxConnectionOwnershipRecord, DbxConnectionShareRecord
from rebuild.identity.models import UserRecord


def test_owner_visibility_and_explicit_share():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[UserRecord.__table__, DbxConnectionOwnershipRecord.__table__, DbxConnectionShareRecord.__table__])
    with Session(engine) as session:
        session.add_all([UserRecord(id=1, username="owner", password_hash="x", role="admin"), UserRecord(id=2, username="reader", password_hash="x", role="viewer")])
        session.flush()
        access = DbxConnectionAccess(session)
        access.claim(connection_id="conn-1", project_id=10, owner_id=1)
        assert access.visible_ids(project_id=10, user_id=1) == {"conn-1"}
        assert access.visible_ids(project_id=10, user_id=2) == set()
        assert access.visible_ids(project_id=10, user_id=2, is_admin=True) == {"conn-1"}
        with pytest.raises(PermissionError):
            access.share(connection_id="conn-1", owner_id=2, user_id=2)
        access.share(connection_id="conn-1", owner_id=1, user_id=2)
        session.flush()
        assert access.visible_ids(project_id=10, user_id=2) == {"conn-1"}
        assert access.visible_ids(project_id=11, user_id=2, is_admin=True) == set()
        with pytest.raises(PermissionError):
            access.claim(connection_id="conn-1", project_id=11, owner_id=2)
