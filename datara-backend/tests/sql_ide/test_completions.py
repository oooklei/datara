from __future__ import annotations

import pytest

from rebuild.sql_ide.capability import CapabilityAccessError
from rebuild.sql_ide.completions import CompletionService


class FakeMetadataBrowser:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def list_objects(self, object_kind: str, **kwargs) -> dict:
        self.calls.append(("complete", object_kind, kwargs))
        return {
            "items": [{"name": "orders", "kind": object_kind}],
            "capability": "supported",
            "constraints": [],
            "page": {"nextCursor": None, "hasMore": False},
        }

    def get_definition(self, object_kind: str, object_ref, **kwargs) -> dict:
        self.calls.append(("hover", object_kind, {"object_ref": object_ref, **kwargs}))
        return {"definition": "CREATE TABLE orders (id INTEGER)", "capability": "supported", "constraints": []}


def test_completion_candidates_and_hover_summary_delegate_to_metadata_browser() -> None:
    browser = FakeMetadataBrowser()
    service = CompletionService(browser)

    candidates = service.complete("table", parent={"schema": "public"}, page_size=20)
    summary = service.hover("table", {"schema": "public", "name": "orders"})

    assert candidates["items"] == [{"name": "orders", "kind": "table"}]
    assert summary["definition"] == "CREATE TABLE orders (id INTEGER)"
    assert browser.calls == [
        (
            "complete",
            "table",
            {
                "parent": {"schema": "public"},
                "page_size": 20,
                "cursor": None,
                "condition_met": False,
            },
        ),
        (
            "hover",
            "table",
            {
                "object_ref": {"schema": "public", "name": "orders"},
                "condition_met": False,
            },
        ),
    ]


def test_capability_denial_from_metadata_browser_is_preserved() -> None:
    class DeniedBrowser(FakeMetadataBrowser):
        def list_objects(self, object_kind: str, **kwargs) -> dict:
            raise CapabilityAccessError("CAPABILITY_UNKNOWN")

    service = CompletionService(DeniedBrowser())

    with pytest.raises(CapabilityAccessError, match="CAPABILITY_UNKNOWN"):
        service.complete("table")


@pytest.mark.parametrize(
    "kind",
    ["database", "schema", "table", "view", "column", "index", "function", "procedure", "trigger"],
)
def test_completion_candidates_forward_all_nine_metadata_kinds(kind: str) -> None:
    browser = FakeMetadataBrowser()
    service = CompletionService(browser)

    result = service.complete(kind, parent={"database": "analytics"}, cursor="next")

    assert result["items"] == [{"name": "orders", "kind": kind}]
    assert browser.calls == [
        (
            "complete",
            kind,
            {
                "parent": {"database": "analytics"},
                "page_size": None,
                "cursor": "next",
                "condition_met": False,
            },
        )
    ]


def test_hover_forwards_conditional_capability_and_returns_definition_summary() -> None:
    browser = FakeMetadataBrowser()
    service = CompletionService(browser)

    result = service.hover(
        "view",
        {"database": "analytics", "schema": "public", "name": "orders_view"},
        condition_met=True,
    )

    assert result == {
        "definition": "CREATE TABLE orders (id INTEGER)",
        "capability": "supported",
        "constraints": [],
    }
    assert browser.calls == [
        (
            "hover",
            "view",
            {
                "object_ref": {"database": "analytics", "schema": "public", "name": "orders_view"},
                "condition_met": True,
            },
        )
    ]


def test_definition_capability_denial_from_metadata_browser_is_preserved() -> None:
    class DeniedBrowser(FakeMetadataBrowser):
        def get_definition(self, object_kind: str, object_ref, **kwargs) -> dict:
            raise CapabilityAccessError("CAPABILITY_CONDITION_NOT_MET")

    service = CompletionService(DeniedBrowser())

    with pytest.raises(CapabilityAccessError, match="CAPABILITY_CONDITION_NOT_MET"):
        service.hover("table", {"name": "orders"})

