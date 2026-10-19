"""WF-10 workflow_draft_snapshot model tests — design §4.1/§3.1/§9.

Covers: table creation, UniqueConstraint(definition_id, snapshot_digest),
column presence, DB-generated timestamps, and __table__ identity.
"""

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.trial.models import WorkflowDraftSnapshotRecord


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[WorkflowDraftSnapshotRecord.__table__])
    return Session(engine)


def test_table_creates_with_zero_rows():
    session = _session()
    count = session.scalar(select(func.count()).select_from(WorkflowDraftSnapshotRecord))
    assert count == 0


def test_unique_constraint_definition_digest():
    table = WorkflowDraftSnapshotRecord.__table__
    constraints = [c.name for c in table.constraints if c.name == "uq_wds_definition_digest"]
    assert constraints == ["uq_wds_definition_digest"]
    cols = {c.name for c in table.constraints.__iter__().__next__().columns} if False else None
    uq = next(c for c in table.constraints if c.name == "uq_wds_definition_digest")
    assert {c.name for c in uq.columns} == {"definition_id", "snapshot_digest"}


def test_columns_and_defaults():
    table = WorkflowDraftSnapshotRecord.__table__
    col_names = {c.name for c in table.columns}
    assert {
        "id", "definition_id", "snapshot_digest", "node_snapshot_json",
        "edge_snapshot_json", "status", "created_by", "created_at", "updated_at",
    } <= col_names
    status_col = table.c.status
    assert status_col.default.arg == "ACTIVE"


def test_insert_and_db_generated_timestamps():
    session = _session()
    record = WorkflowDraftSnapshotRecord(
        definition_id=1,
        snapshot_digest="a" * 64,
        node_snapshot_json='{"nodes":[]}',
        edge_snapshot_json='{"edges":[]}',
        status="ACTIVE",
    )
    session.add(record)
    session.flush()
    assert record.id is not None
    assert record.created_at is not None
    assert record.updated_at is not None
    session.rollback()


def test_table_name():
    assert WorkflowDraftSnapshotRecord.__tablename__ == "workflow_draft_snapshot"
