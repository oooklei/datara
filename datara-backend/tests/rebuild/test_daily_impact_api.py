from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from rebuild.common.db import Base
from rebuild.dbx.access import DbxConnectionAccess
from rebuild.dbx.models import DbxConnectionOwnershipRecord, DbxConnectionShareRecord
from rebuild.identity.models import UserRecord
from rebuild.impact.api import build_impact_router
from rebuild.impact.models import DailyImpactRecord, DailyImpactRunRecord


def test_daily_results_follow_connection_visibility():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[UserRecord.__table__, DbxConnectionOwnershipRecord.__table__, DbxConnectionShareRecord.__table__, DailyImpactRecord.__table__, DailyImpactRunRecord.__table__])
    factory = sessionmaker(bind=engine)
    with Session(engine) as session:
        session.add_all([
            UserRecord(id=1, username="admin", password_hash="x", role="admin"),
            UserRecord(id=2, username="owner", password_hash="x", role="developer"),
            UserRecord(id=3, username="other", password_hash="x", role="developer"),
        ])
        session.flush()
        DbxConnectionAccess(session).claim(connection_id="owned", project_id=7, owner_id=2)
        session.add(DailyImpactRunRecord(project_id=7, day=date(2026, 10, 28), row_count=1))
        session.add(DailyImpactRecord(project_id=7, day=date(2026, 10, 28), history_id="h1", connection_id="owned", database="sales", executed_at="2026-10-28T12:00:00+08:00", success=True, status="ok", reads=["sales.orders"], writes=["sales.report"]))
        session.commit()

    users = {"admin": {"user_id": 1, "role": "admin"}, "owner": {"user_id": 2, "role": "developer"}, "other": {"user_id": 3, "role": "developer"}}
    def current_user(header):
        user = users.get(header.removeprefix("Bearer "))
        if user is None:
            raise ValueError("invalid token")
        return user

    app = FastAPI()
    app.include_router(build_impact_router(factory, current_user, lambda *args: None))
    client = TestClient(app)
    url = "/api/v1/rebuild/projects/7/impact/daily?day=2026-10-28"
    owner = client.get(url, headers={"Authorization": "Bearer owner"}).json()["data"]
    assert owner["collected"] is True
    assert [row["history_id"] for row in owner["items"]] == ["h1"]
    assert client.get(url, headers={"Authorization": "Bearer other"}).json()["data"]["items"] == []
    assert client.get(url, headers={"Authorization": "Bearer admin"}).json()["data"]["items"][0]["writes"] == ["sales.report"]
    assert client.get(url).status_code == 401
