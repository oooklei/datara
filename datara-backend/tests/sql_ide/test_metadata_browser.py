from __future__ import annotations

import pytest

from rebuild.sql_ide.capability import CapabilityAccessError, CapabilityDeclaration
from rebuild.sql_ide.metadata_browser import MetadataBrowser


class FakeMetadataPort:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict]] = []

    def list_objects(self, *, driver, object_kind, parent, page_size, cursor):
        self.calls.append(("list", object_kind, {"driver": driver, "parent": parent, "page_size": page_size}))
        return {"items": [{"kind": object_kind, "name": "sample"}], "next_cursor": None, "has_more": False}

    def get_definition(self, *, driver, object_kind, object_ref):
        self.calls.append(("definition", object_kind, {"driver": driver, "object_ref": object_ref}))
        return {"definition": "CREATE TABLE sample (id INTEGER)"}


def declaration(driver: str, kind: str, operation: str, status: str = "supported") -> CapabilityDeclaration:
    return CapabilityDeclaration.from_observation(
        driver="postgresql",
        object_kind=kind,
        operation=operation,
        status=status,
        evidence_ref="verified-run-1" if status == "supported" else None,
    )


@pytest.mark.parametrize(
    "kind",
    ["database", "schema", "table", "view", "column", "index", "function", "procedure", "trigger"],
)
def test_list_objects_gates_all_tree_kinds_by_exact_driver_kind_operation(kind: str) -> None:
    port = FakeMetadataPort()
    browser = MetadataBrowser(
        driver="postgresql",
        port=port,
        capabilities={("postgresql", kind, "listObjects"): declaration("postgresql", kind, "listObjects")},
    )

    result = browser.list_objects(kind, parent={"database": "db"})

    assert result["items"] == [{"kind": kind, "name": "sample"}]
    expected_page_size = 200 if kind == "column" else 100
    assert port.calls == [
        (
            "list",
            kind,
            {"driver": "postgresql", "parent": {"database": "db"}, "page_size": expected_page_size},
        )
    ]


def test_column_list_default_page_size_is_200() -> None:
    port = FakeMetadataPort()
    browser = MetadataBrowser(
        driver="postgresql",
        port=port,
        capabilities={("postgresql", "column", "listObjects"): declaration("postgresql", "column", "listObjects")},
    )

    browser.list_objects("column")

    assert port.calls[0][2]["page_size"] == 200


@pytest.mark.parametrize(("kind", "page_size"), [("table", 201), ("column", 501)])
def test_page_size_above_kind_limit_rejected_before_capability_or_port(kind: str, page_size: int) -> None:
    port = FakeMetadataPort()
    browser = MetadataBrowser(driver="postgresql", port=port, capabilities={})

    with pytest.raises(ValueError, match="page_size"):
        browser.list_objects(kind, page_size=page_size)

    assert port.calls == []


def test_shared_get_definition_is_readonly_and_returns_definition_for_each_kind() -> None:
    port = FakeMetadataPort()
    browser = MetadataBrowser(
        driver="postgresql",
        port=port,
        capabilities={("postgresql", "table", "getDefinition"): declaration("postgresql", "table", "getDefinition")},
    )

    result = browser.get_definition("table", {"database": "db", "schema": "public", "name": "sample"})

    assert result == {
        "definition": "CREATE TABLE sample (id INTEGER)",
        "capability": "supported",
        "constraints": [],
    }
    assert port.calls[0][0] == "definition"


@pytest.mark.parametrize("kind", ["database", "schema", "column", "index"])
def test_get_definition_rejects_non_definition_kinds_before_port_call(kind: str) -> None:
    port = FakeMetadataPort()
    browser = MetadataBrowser(
        driver="postgresql",
        port=port,
        capabilities={("postgresql", kind, "getDefinition"): declaration("postgresql", kind, "getDefinition")},
    )

    with pytest.raises(CapabilityAccessError, match="CAPABILITY_UNSUPPORTED"):
        browser.get_definition(kind, {"name": "sample"})

    assert port.calls == []


@pytest.mark.parametrize("status", ["unsupported", "unknown"])
def test_unsupported_or_unknown_capability_fails_closed_without_port_call(status: str) -> None:
    port = FakeMetadataPort()
    browser = MetadataBrowser(
        driver="postgresql",
        port=port,
        capabilities={("postgresql", "table", "listObjects"): declaration("postgresql", "table", "listObjects", status)},
    )

    with pytest.raises(CapabilityAccessError):
        browser.list_objects("table")

    assert port.calls == []


@pytest.mark.parametrize(
    ("driver", "kind", "operation"),
    [("mysql", "table", "listObjects"), ("postgresql", "view", "listObjects"), ("postgresql", "table", "getDefinition")],
)
def test_missing_exact_capability_for_driver_kind_operation_fails_closed(driver, kind, operation) -> None:
    port = FakeMetadataPort()
    browser = MetadataBrowser(
        driver=driver,
        port=port,
        capabilities={("postgresql", "table", "listObjects"): declaration("postgresql", "table", "listObjects")},
    )

    with pytest.raises(CapabilityAccessError):
        if operation == "listObjects":
            browser.list_objects(kind)
        else:
            browser.get_definition(kind, {"name": "x"})

    assert port.calls == []


def test_event_routine_is_not_a_supported_metadata_tree_kind() -> None:
    port = FakeMetadataPort()
    browser = MetadataBrowser(driver="postgresql", port=port, capabilities={})

    with pytest.raises(CapabilityAccessError, match="OBJECT_KIND_UNSUPPORTED"):
        browser.list_objects("event")

    assert port.calls == []


def test_conditional_capability_requires_explicit_condition() -> None:
    port = FakeMetadataPort()
    conditional = CapabilityDeclaration.from_observation(
        driver="postgresql",
        object_kind="table",
        operation="listObjects",
        status="conditional",
        evidence_ref="verified-run-2",
        constraints=("metadata role enabled",),
    )
    browser = MetadataBrowser(
        driver="postgresql",
        port=port,
        capabilities={("postgresql", "table", "listObjects"): conditional},
    )

    with pytest.raises(CapabilityAccessError, match="CAPABILITY_CONDITION_NOT_MET"):
        browser.list_objects("table")
    assert port.calls == []

    result = browser.list_objects("table", condition_met=True)
    assert result["capability"] == "conditional"
