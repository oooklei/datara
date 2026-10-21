"""Fail-closed, capability-gated SQL metadata browsing."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from rebuild.sql_ide.capability import (
    CapabilityAccessError,
    CapabilityDeclaration,
    build_metadata_envelope,
)


METADATA_OBJECT_KINDS = frozenset(
    {
        "database",
        "schema",
        "table",
        "view",
        "column",
        "index",
        "function",
        "procedure",
        "trigger",
    }
)
DEFINITION_OBJECT_KINDS = frozenset(
    {"table", "view", "function", "procedure", "trigger"}
)


class MetadataPort(Protocol):
    """Read-only adapter boundary for metadata providers."""

    def list_objects(
        self,
        *,
        driver: str,
        object_kind: str,
        parent: Mapping[str, Any] | None,
        page_size: int,
        cursor: str | None,
    ) -> Mapping[str, Any]: ...

    def get_definition(
        self,
        *,
        driver: str,
        object_kind: str,
        object_ref: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class MetadataBrowser:
    """Expose the nine supported metadata tree kinds and shared definition read.

    A call reaches the adapter only when an evidence-backed declaration exists
    for the exact bound driver, object kind, and operation. This class has no
    mutation operation; definitions are retrieved through the read-only port.
    """

    def __init__(
        self,
        *,
        driver: str,
        port: MetadataPort,
        capabilities: Mapping[tuple[str, str, str], CapabilityDeclaration],
    ) -> None:
        if not isinstance(driver, str) or not driver.strip():
            raise ValueError("driver is required")
        self._driver = driver.strip().lower()
        self._port = port
        self._capabilities = capabilities

    def list_objects(
        self,
        object_kind: str,
        *,
        parent: Mapping[str, Any] | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        condition_met: bool = False,
    ) -> dict[str, Any]:
        """List one level of the metadata tree without inferring driver support."""

        self._validate_kind(object_kind)
        max_page_size = 500 if object_kind == "column" else 200
        default_page_size = 200 if object_kind == "column" else 100
        if page_size is None:
            page_size = default_page_size
        if (
            isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or page_size < 1
            or page_size > max_page_size
        ):
            raise ValueError(f"page_size must be an integer from 1 to {max_page_size}")
        if parent is not None and not isinstance(parent, Mapping):
            raise ValueError("parent must be an object")
        if cursor is not None and not isinstance(cursor, str):
            raise ValueError("cursor must be text")

        capability = self._require_capability(
            object_kind, "listObjects", condition_met=condition_met
        )
        payload = self._port.list_objects(
            driver=self._driver,
            object_kind=object_kind,
            parent=dict(parent) if parent is not None else None,
            page_size=page_size,
            cursor=cursor,
        )
        if not isinstance(payload, Mapping) or not isinstance(payload.get("items"), (list, tuple)):
            raise CapabilityAccessError("METADATA_PROVIDER_INVALID_RESPONSE")
        return build_metadata_envelope(
            items=payload["items"],
            capability=capability,
            condition_met=condition_met,
            next_cursor=payload.get("next_cursor"),
            has_more=payload.get("has_more", False),
        )

    def get_definition(
        self,
        object_kind: str,
        object_ref: Mapping[str, Any],
        *,
        condition_met: bool = False,
    ) -> dict[str, Any]:
        """Read an object's definition through the shared read-only operation."""

        self._validate_kind(object_kind)
        if object_kind not in DEFINITION_OBJECT_KINDS:
            raise CapabilityAccessError("CAPABILITY_UNSUPPORTED")
        if not isinstance(object_ref, Mapping) or not object_ref:
            raise ValueError("object_ref must be a non-empty object")

        capability = self._require_capability(
            object_kind, "getDefinition", condition_met=condition_met
        )
        payload = self._port.get_definition(
            driver=self._driver,
            object_kind=object_kind,
            object_ref=dict(object_ref),
        )
        if not isinstance(payload, Mapping) or not isinstance(payload.get("definition"), str):
            raise CapabilityAccessError("METADATA_PROVIDER_INVALID_RESPONSE")
        result: dict[str, Any] = {
            "definition": payload["definition"],
            "capability": capability.status,
            "constraints": list(capability.constraints),
        }
        # The DDL write chain snapshots a versioned definition. Forward the
        # provider's source marker verbatim; omitting it keeps the caller
        # fail-closed (no inferred or fabricated version leaves this layer).
        source_version = payload.get("source_version")
        if isinstance(source_version, str) and source_version.strip():
            result["source_version"] = source_version
        return result

    @staticmethod
    def _validate_kind(object_kind: str) -> None:
        if not isinstance(object_kind, str) or object_kind not in METADATA_OBJECT_KINDS:
            raise CapabilityAccessError("OBJECT_KIND_UNSUPPORTED")

    def _require_capability(
        self, object_kind: str, operation: str, *, condition_met: bool
    ) -> CapabilityDeclaration:
        key = (self._driver, object_kind, operation)
        capability = self._capabilities.get(key)
        if capability is None:
            raise CapabilityAccessError("CAPABILITY_UNKNOWN")
        if (
            capability.driver.strip().lower() != self._driver
            or capability.object_kind != object_kind
            or capability.operation != operation
        ):
            raise CapabilityAccessError("CAPABILITY_UNKNOWN")
        # Direct construction must not bypass evidence-backed observation.
        if capability.status in ("supported", "conditional") and not capability.evidence_ref:
            raise CapabilityAccessError("CAPABILITY_UNKNOWN")
        if capability.status == "conditional" and not capability.constraints:
            raise CapabilityAccessError("CAPABILITY_UNKNOWN")
        if capability.status == "unsupported":
            raise CapabilityAccessError("CAPABILITY_UNSUPPORTED")
        if capability.status == "unknown":
            raise CapabilityAccessError("CAPABILITY_UNKNOWN")
        if capability.status == "conditional" and condition_met is not True:
            raise CapabilityAccessError("CAPABILITY_CONDITION_NOT_MET")
        return capability
