"""Evidence-backed driver capability declarations and metadata envelopes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal, Mapping

CapabilityStatus = Literal["supported", "conditional", "unsupported", "unknown"]


class CapabilityAccessError(RuntimeError):
    """A requested metadata operation cannot be represented as successful."""

    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


@dataclass(frozen=True)
class CapabilityDeclaration:
    driver: str
    object_kind: str
    operation: str
    status: CapabilityStatus
    evidence_ref: str | None = None
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"supported", "conditional", "unsupported", "unknown"}:
            raise ValueError("capability status is invalid")

    @classmethod
    def from_observation(
        cls,
        *,
        driver: str,
        object_kind: str,
        operation: str,
        status: CapabilityStatus,
        evidence_ref: str | None,
        constraints: Iterable[str] = (),
    ) -> "CapabilityDeclaration":
        constraints = tuple(constraints)
        # A declared positive capability without observed evidence is not proof.
        if status in ("supported", "conditional") and not evidence_ref:
            status = "unknown"
            constraints = ()
        if status == "conditional" and not constraints:
            raise ValueError("conditional capability requires constraints")
        if status == "conditional" and not evidence_ref:
            raise ValueError("conditional capability requires evidence")
        return cls(
            driver=driver,
            object_kind=object_kind,
            operation=operation,
            status=status,
            evidence_ref=evidence_ref,
            constraints=constraints,
        )


def build_metadata_envelope(
    *,
    items: Iterable[Mapping[str, Any]],
    capability: CapabilityDeclaration,
    condition_met: bool | None = None,
    next_cursor: str | None = None,
    has_more: bool = False,
) -> dict[str, Any]:
    """Return a page only when capability evidence permits the operation."""
    if capability.status == "unsupported":
        raise CapabilityAccessError("CAPABILITY_UNSUPPORTED")
    if capability.status == "unknown":
        raise CapabilityAccessError("CAPABILITY_UNKNOWN")
    if capability.status == "conditional" and condition_met is not True:
        raise CapabilityAccessError("CAPABILITY_CONDITION_NOT_MET")
    return {
        "items": [dict(item) for item in items],
        "capability": capability.status,
        "constraints": list(capability.constraints),
        "page": {"nextCursor": next_cursor, "hasMore": bool(has_more)},
    }
