"""WF-21 TrialPromoter tests — design §4.1/§3.1.

Covers: promote creates formal version from trial snapshot, idempotent re-promote,
digest mismatch rejection, non-TRIAL instance rejection.
"""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.execution.models import WorkflowInstanceRecord
from rebuild.trial.promote import PromoteError, TrialPromoter
from rebuild.trial.repository import TrialSnapshotRepository
from rebuild.trial.runner import TrialRunner
from rebuild.workflow.models import (
    WorkflowDefinitionRecord,
    WorkflowEdgeRecord,
    WorkflowNodeRecord,
    WorkflowVersionRecord,
)


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _make_definition(session, project_id=1):
    record = WorkflowDefinitionRecord(project_id=project_id, name="promote-test")
    session.add(record)
    session.flush()
    return record.id


def _add_node(session, definition_id, node_code, node_type="SQL", params=None):
    import json

    record = WorkflowNodeRecord(
        definition_id=definition_id,
        version_id=None,
        node_code=node_code,
        node_type=node_type,
        name=node_code,
        params_json=json.dumps(params or {}),
    )
    session.add(record)
    session.flush()


def _add_edge(session, definition_id, from_node, to_node):
    record = WorkflowEdgeRecord(
        definition_id=definition_id, version_id=None, from_node=from_node, to_node=to_node
    )
    session.add(record)
    session.flush()


def _setup_and_run(session):
    definition_id = _make_definition(session)
    _add_node(session, definition_id, "start", node_type="START")
    _add_node(session, definition_id, "extract", params={"sql": "SELECT 1"})
    _add_node(session, definition_id, "end", node_type="END")
    _add_edge(session, definition_id, "start", "extract")
    _add_edge(session, definition_id, "extract", "end")
    session.commit()

    snapshot = TrialSnapshotRepository(session).create_from_draft(definition_id)
    result = TrialRunner(session).run(
        definition_id=definition_id,
        snapshot_id=snapshot["snapshot_id"],
        project_id=1,
    )
    session.commit()
    return definition_id, result.instance_id, snapshot["snapshot_digest"]


def test_promote_creates_formal_version():
    session = _session()
    definition_id, instance_id, snapshot_digest = _setup_and_run(session)

    promoter = TrialPromoter(session)
    result = promoter.promote(
        definition_id=definition_id,
        instance_id=instance_id,
        project_id=1,
        remark="promote from trial",
    )
    session.commit()

    assert result["idempotent"] is False
    assert result["status"] == "PUBLISHED"
    assert result["snapshot_digest"] == snapshot_digest
    assert result["version"] == 1

    # Verify definition.current_version bumped.
    definition = session.get(WorkflowDefinitionRecord, definition_id)
    assert definition.current_version == 1

    # Verify version row exists.
    version = session.scalar(
        select(WorkflowVersionRecord).where(
            WorkflowVersionRecord.definition_id == definition_id,
            WorkflowVersionRecord.version == 1,
        )
    )
    assert version is not None
    assert version.status == "PUBLISHED"
    assert version.snapshot_digest == snapshot_digest


def test_promote_idempotent():
    session = _session()
    definition_id, instance_id, _ = _setup_and_run(session)

    promoter = TrialPromoter(session)
    first = promoter.promote(definition_id=definition_id, instance_id=instance_id, project_id=1)
    session.commit()

    second = promoter.promote(definition_id=definition_id, instance_id=instance_id, project_id=1)
    session.commit()

    assert first["idempotent"] is False
    assert second["idempotent"] is True
    assert second["version"] == first["version"]

    # Still only one version.
    count = session.scalar(
        select(WorkflowVersionRecord).where(
            WorkflowVersionRecord.definition_id == definition_id
        ).with_only_columns(WorkflowVersionRecord.id).count()
    ) if False else len(
        session.scalars(
            select(WorkflowVersionRecord).where(
                WorkflowVersionRecord.definition_id == definition_id
            )
        ).all()
    )
    assert count == 1


def test_promote_rejects_non_trial_instance():
    session = _session()
    definition_id = _make_definition(session)

    # Create a FORMAL instance manually.
    from rebuild.execution.repository import ExecutionRepository

    formal_instance = ExecutionRepository(session).create_workflow_instance(
        workflow_id=definition_id,
        workflow_version_id=0,
        instance_type="FORMAL",
    )
    session.commit()

    promoter = TrialPromoter(session)
    with pytest.raises(PromoteError) as excinfo:
        promoter.promote(
            definition_id=definition_id,
            instance_id=formal_instance.id,
            project_id=1,
        )
    assert excinfo.value.code == "WF_PROMOTE_NOT_TRIAL"


def test_promote_digest_mismatch_rejected():
    session = _session()
    definition_id, instance_id, _ = _setup_and_run(session)

    # Mutate the draft after the trial run.
    _add_node(session, definition_id, "extra", params={"sql": "SELECT 99"})
    session.commit()

    promoter = TrialPromoter(session)
    with pytest.raises(PromoteError) as excinfo:
        promoter.promote(definition_id=definition_id, instance_id=instance_id, project_id=1)
    assert excinfo.value.code == "WF_PROMOTE_DIGEST_MISMATCH"
