"""WF-13 TrialValidator tests — design §4.1.

Covers: valid draft passes; orphan nodes detected; cycles detected;
START/END missing detected; DEPENDENCY target missing detected;
required params missing detected.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from rebuild.common.db import Base
from rebuild.trial.validator import TrialValidator
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
    record = WorkflowDefinitionRecord(project_id=project_id, name="validator-test")
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


def test_valid_draft_passes():
    session = _session()
    definition_id = _make_definition(session)
    _add_node(session, definition_id, "start", node_type="START")
    _add_node(session, definition_id, "extract", params={"sql": "SELECT 1"})
    _add_node(session, definition_id, "end", node_type="END")
    _add_edge(session, definition_id, "start", "extract")
    _add_edge(session, definition_id, "extract", "end")
    session.commit()

    errors = TrialValidator(session).validate(definition_id)
    assert errors == []


def test_component_ref_graph_without_legacy_sentinels_passes():
    """The current palette graph uses natural roots/leaves, not START/END nodes."""
    session = _session()
    definition_id = _make_definition(session)
    _add_node(session, definition_id, "sql", node_type="sql", params={"sql": "SELECT 1"})
    _add_node(session, definition_id, "python", node_type="python", params={"script": "print(1)"})
    _add_node(session, definition_id, "shell", node_type="shell", params={"script": "printf ok"})
    _add_node(session, definition_id, "dependent", node_type="dependent", params={})
    _add_edge(session, definition_id, "sql", "python")
    _add_edge(session, definition_id, "python", "shell")
    _add_edge(session, definition_id, "shell", "dependent")
    session.commit()

    assert TrialValidator(session).validate(definition_id) == []


def test_orphan_node_detected():
    session = _session()
    definition_id = _make_definition(session)
    _add_node(session, definition_id, "start", node_type="START")
    _add_node(session, definition_id, "orphan", params={"sql": "SELECT 1"})
    _add_node(session, definition_id, "end", node_type="END")
    _add_edge(session, definition_id, "start", "end")
    session.commit()

    errors = TrialValidator(session).validate(definition_id)
    orphan_errors = [e for e in errors if "orphan" in e.message]
    assert len(orphan_errors) >= 1
    assert any(e.node_code == "orphan" for e in orphan_errors)


def test_cycle_detected():
    session = _session()
    definition_id = _make_definition(session)
    _add_node(session, definition_id, "start", node_type="START")
    _add_node(session, definition_id, "a", params={"sql": "SELECT 1"})
    _add_node(session, definition_id, "b", params={"sql": "SELECT 2"})
    _add_node(session, definition_id, "end", node_type="END")
    _add_edge(session, definition_id, "start", "a")
    _add_edge(session, definition_id, "a", "b")
    _add_edge(session, definition_id, "b", "a")  # cycle
    _add_edge(session, definition_id, "b", "end")
    session.commit()

    errors = TrialValidator(session).validate(definition_id)
    cycle_errors = [e for e in errors if "cycle" in e.message]
    assert len(cycle_errors) == 1


def test_component_graph_does_not_require_start_and_end():
    session = _session()
    definition_id = _make_definition(session)
    _add_node(session, definition_id, "a", params={"sql": "SELECT 1"})
    _add_node(session, definition_id, "b", params={"sql": "SELECT 2"})
    _add_edge(session, definition_id, "a", "b")
    session.commit()

    errors = TrialValidator(session).validate(definition_id)
    assert errors == []


def test_dependency_missing_target():
    session = _session()
    definition_id = _make_definition(session)
    _add_node(session, definition_id, "start", node_type="START")
    _add_node(session, definition_id, "dep", node_type="DEPENDENCY", params={"dependency_id": 9999})
    _add_node(session, definition_id, "end", node_type="END")
    _add_edge(session, definition_id, "start", "dep")
    _add_edge(session, definition_id, "dep", "end")
    session.commit()

    errors = TrialValidator(session).validate(definition_id)
    dep_errors = [e for e in errors if "dependency" in e.message.lower()]
    assert len(dep_errors) == 1
    assert dep_errors[0].node_code == "dep"


def test_required_params_missing():
    session = _session()
    definition_id = _make_definition(session)
    _add_node(session, definition_id, "start", node_type="START")
    _add_node(session, definition_id, "bad_sql", node_type="SQL", params={})
    _add_node(session, definition_id, "end", node_type="END")
    _add_edge(session, definition_id, "start", "bad_sql")
    _add_edge(session, definition_id, "bad_sql", "end")
    session.commit()

    errors = TrialValidator(session).validate(definition_id)
    param_errors = [e for e in errors if "required param" in e.message]
    assert len(param_errors) == 1
    assert param_errors[0].node_code == "bad_sql"


def test_empty_draft_rejected():
    session = _session()
    definition_id = _make_definition(session)
    errors = TrialValidator(session).validate(definition_id)
    assert len(errors) == 1
    assert errors[0].code == "WF_TRIAL_INVALID"
