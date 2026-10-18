from __future__ import annotations

import pytest

from rebuild.sql_ide.capability import (
    CapabilityAccessError,
    CapabilityDeclaration,
    build_metadata_envelope,
)


def test_unverified_supported_observation_is_downgraded_to_unknown() -> None:
    capability = CapabilityDeclaration.from_observation(
        driver="postgresql",
        object_kind="table",
        operation="listRelations",
        status="supported",
        evidence_ref=None,
    )

    assert capability.status == "unknown"


def test_capability_rejects_status_outside_frozen_enum() -> None:
    with pytest.raises(ValueError, match="status"):
        CapabilityDeclaration.from_observation(
            driver="postgresql",
            object_kind="table",
            operation="listRelations",
            status="best_effort",  # type: ignore[arg-type]
            evidence_ref="run-123",
        )


def test_conditional_capability_requires_constraints_and_evidence() -> None:
    with pytest.raises(ValueError, match="constraints"):
        CapabilityDeclaration.from_observation(
            driver="postgresql",
            object_kind="table",
            operation="getDefinition",
            status="conditional",
            evidence_ref="run-123",
            constraints=(),
        )


def test_unverified_conditional_observation_is_downgraded_to_unknown() -> None:
    capability = CapabilityDeclaration.from_observation(
        driver="postgresql",
        object_kind="table",
        operation="getDefinition",
        status="conditional",
        evidence_ref=None,
        constraints=("driver supports table definitions",),
    )

    assert capability.status == "unknown"
    assert capability.constraints == ()


def test_supported_capability_returns_successful_empty_page() -> None:
    capability = CapabilityDeclaration.from_observation(
        driver="postgresql",
        object_kind="table",
        operation="listRelations",
        status="supported",
        evidence_ref="run-123",
    )

    assert build_metadata_envelope(items=[], capability=capability) == {
        "items": [],
        "capability": "supported",
        "constraints": [],
        "page": {"nextCursor": None, "hasMore": False},
    }


@pytest.mark.parametrize(
    ("status", "error_code"),
    [("unsupported", "CAPABILITY_UNSUPPORTED"), ("unknown", "CAPABILITY_UNKNOWN")],
)
def test_non_supported_capability_cannot_masquerade_as_empty_success(status, error_code) -> None:
    capability = CapabilityDeclaration.from_observation(
        driver="postgresql",
        object_kind="table",
        operation="listRelations",
        status=status,
        evidence_ref="run-123" if status == "unsupported" else None,
    )

    with pytest.raises(CapabilityAccessError) as caught:
        build_metadata_envelope(items=[], capability=capability)

    assert caught.value.error_code == error_code


def test_conditional_constraint_failure_has_stable_error() -> None:
    capability = CapabilityDeclaration.from_observation(
        driver="postgresql",
        object_kind="table",
        operation="getDefinition",
        status="conditional",
        evidence_ref="run-123",
        constraints=("driver supports table definitions",),
    )

    with pytest.raises(CapabilityAccessError) as caught:
        build_metadata_envelope(items=[], capability=capability, condition_met=False)

    assert caught.value.error_code == "CAPABILITY_CONDITION_NOT_MET"


def test_conditional_capability_returns_successful_page_when_condition_is_met() -> None:
    capability = CapabilityDeclaration.from_observation(
        driver="postgresql",
        object_kind="table",
        operation="getDefinition",
        status="conditional",
        evidence_ref="run-123",
        constraints=("driver supports table definitions",),
    )

    assert build_metadata_envelope(
        items=[{"name": "orders"}],
        capability=capability,
        condition_met=True,
    ) == {
        "items": [{"name": "orders"}],
        "capability": "conditional",
        "constraints": ["driver supports table definitions"],
        "page": {"nextCursor": None, "hasMore": False},
    }
