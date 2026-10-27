"""Focused tests for the R5-B explicit confirmation gate."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from rebuild.rb.executor.confirm_gate import ConfirmGate
from rebuild.rb.errors.rb_errors import RbErrorCode
from rebuild.rb.models.rb_models import ObjectRef


def _ref() -> ObjectRef:
    return ObjectRef(7, "warehouse", None, "public", "table", "orders", None)


def _context() -> dict[str, object]:
    return {
        "project_id": 3,
        "datasource_id": 7,
        "object_ref": {
            "database": "warehouse",
            "catalog": None,
            "schema": "public",
            "kind": "table",
            "name": "orders",
            "parent": None,
        },
        "source_version": "etag-1",
        "next_ddl_digest": hashlib.sha256(b"ALTER TABLE orders ADD COLUMN note TEXT").hexdigest(),
        "policy_snapshot_id": "policy-1",
        "impact_snapshot_id": "impact-1",
        "actor_id": 11,
    }


def _validate(gate: ConfirmGate, phrase: str, **overrides):
    values = {
        "project_id": 3,
        "actor_id": 11,
        "object_ref": _ref(),
        "source_version": "etag-1",
        "next_ddl_text": "ALTER TABLE orders ADD COLUMN note TEXT",
        "policy_snapshot_id": "policy-1",
        "impact_snapshot_id": "impact-1",
        "confirm_phrase": phrase,
    }
    values.update(overrides)
    return gate.validate_confirmation(**values)


def test_compute_phrase_is_stable_context_bound_hmac():
    gate = ConfirmGate(lambda actor_id: f"secret-{actor_id}")
    canonical = json.dumps(_context(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    expected = hmac.new(b"secret-11", canonical.encode(), hashlib.sha256).hexdigest()

    assert gate._compute_phrase(_context()) == expected


def test_validate_confirmation_returns_metadata_without_phrase():
    gate = ConfirmGate(lambda _actor_id: "actor-secret")
    phrase = gate._compute_phrase(_context())

    confirmation = _validate(gate, phrase)

    assert confirmation.project_id == 3
    assert confirmation.actor_id == 11
    assert confirmation.context_digest
    assert not hasattr(confirmation, "confirm_phrase")


def test_validate_confirmation_rejects_any_context_drift():
    gate = ConfirmGate(lambda _actor_id: "actor-secret")
    phrase = gate._compute_phrase(_context())

    with pytest.raises(ValueError, match=RbErrorCode.CONFIRM_PHRASE_MISMATCH):
        _validate(gate, phrase, source_version="etag-2")


@pytest.mark.parametrize("phrase", ["", "   ", None])
def test_validate_confirmation_requires_explicit_phrase(phrase):
    gate = ConfirmGate(lambda _actor_id: "actor-secret")

    with pytest.raises(ValueError, match=RbErrorCode.CONFIRM_PHRASE_INVALID):
        _validate(gate, phrase)


@pytest.mark.parametrize(
    "overrides",
    [
        {"project_id": 0},
        {"actor_id": 0},
        {"source_version": ""},
        {"next_ddl_text": ""},
        {"policy_snapshot_id": ""},
        {"impact_snapshot_id": ""},
    ],
)
def test_validate_confirmation_rejects_incomplete_context(overrides):
    gate = ConfirmGate(lambda _actor_id: "actor-secret")

    with pytest.raises(ValueError, match=RbErrorCode.CONFIRM_PHRASE_INVALID):
        _validate(gate, "user-input", **overrides)


def test_validate_confirmation_fails_closed_when_secret_is_unavailable():
    gate = ConfirmGate(lambda _actor_id: "")

    with pytest.raises(RuntimeError, match="secret is unavailable"):
        _validate(gate, "user-input")
