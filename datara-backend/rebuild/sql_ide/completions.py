"""Capability-gated completion candidates and definition hover data."""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class MetadataBrowserPort(Protocol):
    """Read-only metadata operations used by the completion service."""

    def list_objects(
        self,
        object_kind: str,
        *,
        parent: Mapping[str, Any] | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        condition_met: bool = False,
    ) -> dict[str, Any]: ...

    def get_definition(
        self,
        object_kind: str,
        object_ref: Mapping[str, Any],
        *,
        condition_met: bool = False,
    ) -> dict[str, Any]: ...


class CompletionService:
    """Expose metadata candidates and definition hover through existing gates.

    Object-kind validation, capability checks, paging, and provider response
    validation remain owned by ``MetadataBrowser``. This layer forwards those
    existing results without adding API fields or completion rules.
    """

    def __init__(self, metadata_browser: MetadataBrowserPort) -> None:
        self._metadata_browser = metadata_browser

    def complete(
        self,
        object_kind: str,
        *,
        parent: Mapping[str, Any] | None = None,
        page_size: int | None = None,
        cursor: str | None = None,
        condition_met: bool = False,
    ) -> dict[str, Any]:
        """Return candidates from one of the browser's nine metadata kinds."""

        return self._metadata_browser.list_objects(
            object_kind,
            parent=parent,
            page_size=page_size,
            cursor=cursor,
            condition_met=condition_met,
        )

    def hover(
        self,
        object_kind: str,
        object_ref: Mapping[str, Any],
        *,
        condition_met: bool = False,
    ) -> dict[str, Any]:
        """Return the existing capability-gated definition for hover display."""

        return self._metadata_browser.get_definition(
            object_kind,
            object_ref,
            condition_met=condition_met,
        )
