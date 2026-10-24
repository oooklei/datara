import json

import pytest
from fastapi.testclient import TestClient

from common.models import Component, ComponentVersion
from rebuild.api.app import create_app
from rebuild.component_spec.catalogue import FORM_SECTIONS, WORKFLOW_COMPONENT_TYPES, validate_declaration
from rebuild.component_spec.service import ComponentSpecError, ComponentSpecService


@pytest.fixture
def app():
    application = create_app("sqlite+pysqlite:///:memory:", token_secret="catalogue-secret")
    with TestClient(application):
        yield application


def _add(session, identifier, type_name, *, execution_model="dag-engine", spec=None):
    session.add(
        Component(
            id=identifier,
            type=type_name,
            name=type_name,
            category="catalogue",
            profile="dag",
            scope="builtin",
            execution_model=execution_model,
            executable=True,
            state="published",
            published_version=1,
            draft_rev=0,
        )
    )
    session.add(
        ComponentVersion(
            id=identifier,
            component_id=identifier,
            type=type_name,
            version=1,
            state="published",
            spec_json=json.dumps(spec or {}),
            spec_hash="hash",
        )
    )


def test_exact_frozen_catalogue_sets():
    assert WORKFLOW_COMPONENT_TYPES == {
        "NORMAL": ("sql", "python", "shell", "dependent"),
        "SYNC": (
            "src_base_orch",
            "tgt_base_orch",
            "file_sync_orch",
            "endpoint_select",
            "field_map",
            "field_map_union",
            "condition_set",
        ),
        "STREAM": ("stream_input", "stream_fuse", "stream_output", "page_board"),
    }


def test_filtered_document_has_eight_sections_and_immutable_ref(app):
    with app.state.session_factory() as session:
        for offset, type_name in enumerate(WORKFLOW_COMPONENT_TYPES["NORMAL"]):
            _add(session, 901 + offset, type_name)
        _add(session, 910, "endpoint_select", execution_model="passthrough")
        _add(session, 911, "smoke")
        session.commit()
        payload = json.loads(ComponentSpecService(session).published_document("NORMAL").body)
    assert [item["type"] for item in payload["items"]] == list(WORKFLOW_COMPONENT_TYPES["NORMAL"])
    item = payload["items"][0]
    assert item["componentRef"] == {"type": "sql", "version": 1}
    assert tuple(item["form"]) == FORM_SECTIONS


def test_filtered_document_fails_closed_when_approved_group_is_incomplete(app):
    with app.state.session_factory() as session:
        _add(session, 951, "sql")
        session.commit()
        with pytest.raises(ComponentSpecError, match="NORMAL catalogue is incomplete"):
            ComponentSpecService(session).published_document("NORMAL")


@pytest.mark.parametrize(
    "spec",
    [
        {"form": {"params": []}},
        {"form": {name: [] for name in FORM_SECTIONS}, "extensions": {"hiddenInputs": ["password"]}},
        {"form": {name: [] for name in FORM_SECTIONS}, "refreshOptions": {"remote": "https://evil.invalid"}},
        {"form": {name: [] for name in FORM_SECTIONS}, "showIf": "x => true"},
        {"form": {name: [] for name in FORM_SECTIONS}, "onChange": "callback()"},
        {"form": {name: [] for name in FORM_SECTIONS}, "text": "javascript:alert(1)"},
        {"form": {name: [] for name in FORM_SECTIONS}, "callback": {"name": "run"}},
        {"form": {name: [] for name in FORM_SECTIONS}, "pick": "table"},
        {"form": {name: [] for name in FORM_SECTIONS}, "refreshOptions": {"remote": 123}},
    ],
)
def test_declaration_gates_reject_non_dsl_or_non_allowlisted_values(spec):
    assert validate_declaration(spec)
