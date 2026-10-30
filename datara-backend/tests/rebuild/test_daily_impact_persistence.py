from datetime import date

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from rebuild.common.db import Base
from rebuild.dbx.access import DbxConnectionAccess
from rebuild.dbx.models import DbxConnectionOwnershipRecord, DbxConnectionShareRecord
from rebuild.identity.models import UserRecord
from rebuild.impact.models import DailyImpactRecord, DailyImpactRunRecord
from rebuild.impact.service import refresh_daily_impact


class FakeHistory:
    def __init__(self):
        self.fail = False

    def search_history(self, **_kwargs):
        if self.fail:
            raise RuntimeError("upstream failed")
        return {"entries": [
            {"id": "h1", "connection_id": "owned", "database": "sales", "sql": "insert into report select * from orders", "executed_at": "2026-10-28T12:00:00+08:00", "success": True},
            {"id": "h2", "connection_id": "other", "database": "hr", "sql": "delete from employees", "executed_at": "2026-10-28T12:00:00+08:00", "success": True},
        ], "next_cursor": None}


def test_daily_refresh_is_project_scoped_idempotent_and_preserves_previous_on_failure():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[UserRecord.__table__, DbxConnectionOwnershipRecord.__table__, DbxConnectionShareRecord.__table__, DailyImpactRecord.__table__, DailyImpactRunRecord.__table__])
    factory = sessionmaker(bind=engine)
    with Session(engine) as session:
        session.add(UserRecord(id=2, username="owner", password_hash="x", role="developer"))
        session.flush()
        DbxConnectionAccess(session).claim(connection_id="owned", project_id=7, owner_id=2)
        session.commit()

    dbx = FakeHistory()
    day = date(2026, 10, 28)
    assert refresh_daily_impact(day, 7, factory, dbx) == 1
    assert refresh_daily_impact(day, 7, factory, dbx) == 1
    with Session(engine) as session:
        rows = session.scalars(select(DailyImpactRecord)).all()
        assert len(rows) == 1
        assert rows[0].reads == ["sales.orders"]
        assert rows[0].writes == ["sales.report"]
        assert session.scalar(select(DailyImpactRunRecord)).row_count == 1
    dbx.fail = True
    try:
        refresh_daily_impact(day, 7, factory, dbx)
        assert False, "upstream failure must surface"
    except RuntimeError:
        pass
    with Session(engine) as session:
        assert session.scalar(select(DailyImpactRecord)).history_id == "h1"
