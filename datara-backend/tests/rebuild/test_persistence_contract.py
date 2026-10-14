from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.identity.repository import UserRepository
from rebuild.identity.contracts import Role


def test_user_repository_persists_hashed_user_in_isolated_database():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        repository = UserRepository(session)
        created = repository.create(username="unit-dev", password="unit-test-password", role=Role.DEV)
        session.commit()
        loaded = repository.find_by_username("unit-dev")

    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.password_hash != "unit-test-password"
    assert loaded.role == Role.DEV.value

