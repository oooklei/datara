"""Idempotent daily collection, scoped to connections claimed by a project."""

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from rebuild.dbx import DbxClient
from rebuild.dbx.access import DbxConnectionAccess
from .daily import analyze_daily_history, collect_daily_history
from .models import DailyImpactRecord, DailyImpactRunRecord


def refresh_daily_impact(day: date, project_id: int, session_factory: sessionmaker, client: DbxClient) -> int:
    with session_factory() as session:
        allowed = DbxConnectionAccess(session).project_ids(project_id)
    # Fetch first. An upstream failure leaves the previous successful result intact.
    entries = collect_daily_history(day, client, connection_ids=allowed) if allowed else []
    rows = analyze_daily_history(entries, allowed_connection_ids=allowed)
    with session_factory() as session:
        session.execute(delete(DailyImpactRecord).where(DailyImpactRecord.project_id == project_id, DailyImpactRecord.day == day))
        for row in rows:
            session.add(DailyImpactRecord(project_id=project_id, day=day, **row))
        run = session.scalar(select(DailyImpactRunRecord).where(DailyImpactRunRecord.project_id == project_id, DailyImpactRunRecord.day == day))
        if run is None:
            session.add(DailyImpactRunRecord(project_id=project_id, day=day, row_count=len(rows)))
        else:
            run.row_count = len(rows)
        session.commit()
    return len(rows)
