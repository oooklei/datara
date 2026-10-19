"""WF-11 TrialSnapshotRepository tests — design §4.1.

Covers: create_from_draft captures current draft, idempotent re-create (same
digest → no new row), digest changes when draft changes, get returns parsed
JSON, stale demotion on new digest.
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.trial.models import WorkflowDraftSnapshotRecord
from rebuild.trial.repository import TrialSnapshotDomainError, TrialSnapshotRepository
from rebuild.workflow.models import (
    WorkflowDefinitionRecord,
    WorkflowEdgeRecord,
    WorkflowNodeRecord,
)


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    return session


def _make_definition(session, project_id=1):
    record = WorkflowDefinitionRecord(project_id=project_id, name="test-flow")
    session.add(record)
    session.flush()
    return record.id


def _add_draft_node(session, definition_id, node_code, node_type="SQL", name=None, params=None):
    record = WorkflowNodeRecord(
        definition_id=definition_id,
        version_id=None,
        node_code=node_code,
        node_type=node_type,
        name=name or node_code,
        params_json='{"sql": "SELECT 1"}' if params is None else __import__("json").dumps(params),
    )
    session.add(record)
    session.flush()


def _add_draft_edge(session, definition_id, from_node, to_node):
    record = WorkflowEdgeRecord(
        definition_id=definition_id, version_id=None, from_node=from_node, to_node=to_node
    )
    session.add(record)
    session.flush()


def test_create_from_draft_empty_draft():
    session = _session()
    definition_id = _make_definition(session)
    repo = TrialSnapshotRepository(session)
    snapshot = repo.create_from_draft(definition_id)
    assert snapshot["definition_id"] == definition_id
    assert snapshot["status"] == "ACTIVE"
    assert len(snapshot["snapshot_digest"]) == 64
    assert snapshot["node_snapshot_json"] == []
    assert snapshot["edge_snapshot_json"] == []


def test_create_from_draft_captures_nodes_and_edges():
    session = _session()
    definition_id = _make_definition(session)
    _add_draft_node(session, definition_id, "extract", params={"sql": "SELECT * FROM t"})
    _add_draft_node(session, definition_id, "load", node_type="PYTHON")
    _add_draft_edge(session, definition_id, "extract", "load")
    session.commit()

    repo = TrialSnapshotRepository(session)
    snapshot = repo.create_from_draft(definition_id, created_by=42)
    assert len(snapshot["node_snapshot_json"]) == 2
    assert snapshot["node_snapshot_json"][0]["node_code"] == "extract"
    assert snapshot["node_snapshot_json"][0]["params"] == {"sql": "SELECT * FROM t"}
    assert snapshot["node_snapshot_json"][1]["node_type"] == "PYTHON"
    assert len(snapshot["edge_snapshot_json"]) == 1
    assert snapshot["edge_snapshot_json"][0]["from_node"] == "extract"
    assert snapshot["created_by"] == 42


def test_create_idempotent_same_digest_no_new_row():
    from sqlalchemy import func

    session = _session()
    definition_id = _make_definition(session)
    _add_draft_node(session, definition_id, "a")
    _add_draft_node(session, definition_id, "b")
    session.commit()

    repo = TrialSnapshotRepository(session)
    first = repo.create_from_draft(definition_id)
    second = repo.create_from_draft(definition_id)
    assert first["snapshot_digest"] == second["snapshot_digest"]
    assert first["snapshot_id"] == second["snapshot_id"]
    count = session.scalar(
        select(func.count()).select_from(WorkflowDraftSnapshotRecord)
    )
    assert count == 1


def test_digest_changes_when_draft_changes():
    session = _session()
    definition_id = _make_definition(session)
    _add_draft_node(session, definition_id, "a")
    session.commit()

    repo = TrialSnapshotRepository(session)
    first = repo.create_from_draft(definition_id)

    _add_draft_node(session, definition_id, "b")
    session.commit()
    second = repo.create_from_draft(definition_id)

    assert first["snapshot_digest"] != second["snapshot_digest"]
    assert first["snapshot_id"] != second["snapshot_id"]


def test_old_snapshots_marked_stale_on_new_digest():
    session = _session()
    definition_id = _make_definition(session)
    _add_draft_node(session, definition_id, "a")
    session.commit()

    repo = TrialSnapshotRepository(session)
    first = repo.create_from_draft(definition_id)
    assert first["status"] == "ACTIVE"

    _add_draft_node(session, definition_id, "b")
    session.commit()
    second = repo.create_from_draft(definition_id)
    assert second["status"] == "ACTIVE"

    session.expire_all()
    old_row = session.get(WorkflowDraftSnapshotRecord, first["snapshot_id"])
    assert old_row.status == "STALE"


def test_get_returns_parsed_json_and_404():
    session = _session()
    definition_id = _make_definition(session)
    _add_draft_node(session, definition_id, "x")
    session.commit()

    repo = TrialSnapshotRepository(session)
    created = repo.create_from_draft(definition_id)
    fetched = repo.get(created["snapshot_id"])
    assert fetched["snapshot_id"] == created["snapshot_id"]
    assert isinstance(fetched["node_snapshot_json"], list)
    assert isinstance(fetched["edge_snapshot_json"], list)

    with pytest.raises(TrialSnapshotDomainError) as excinfo:
        repo.get(99999)
    assert excinfo.value.code == "WF_SNAPSHOT_NOT_FOUND"
    assert excinfo.value.status == 404
