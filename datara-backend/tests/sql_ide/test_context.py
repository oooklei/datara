from __future__ import annotations

import pytest

from rebuild.sql_ide.context import (
    ObjectRef,
    SqlExecutionContext,
    build_execution_context,
    resolve_object_ref,
)


def test_resolve_object_ref_preserves_explicit_cross_schema_path() -> None:
    ref = ObjectRef(
        datasource_id=17,
        database="warehouse",
        catalog="analytics",
        schema="finance",
        kind="table",
        name="ledger",
    )

    resolved = resolve_object_ref(
        ref,
        default_catalog="default_catalog",
        default_schema="public",
    )

    assert resolved == ref
    assert (resolved.catalog, resolved.schema) == ("analytics", "finance")


def test_resolve_object_ref_uses_driver_default_schema_only_when_omitted() -> None:
    ref = {
        "datasourceId": 17,
        "database": "warehouse",
        "kind": "view",
        "name": "monthly_totals",
    }

    resolved = resolve_object_ref(ref, default_catalog="main", default_schema="public")

    assert resolved.datasource_id == 17
    assert resolved.catalog == "main"
    assert resolved.schema == "public"
    assert resolved.kind == "view"


def test_resolve_object_ref_fails_closed_when_schema_has_no_default() -> None:
    with pytest.raises(ValueError, match="schema is required"):
        resolve_object_ref(
            {
                "datasourceId": 17,
                "database": "warehouse",
                "kind": "table",
                "name": "ledger",
            },
            default_catalog=None,
            default_schema=None,
        )


def test_build_execution_context_keeps_object_path_separate_from_sql() -> None:
    context = build_execution_context(
        datasource_id=17,
        dialect="postgresql",
        object_ref={
            "datasourceId": 17,
            "database": "warehouse",
            "schema": "finance",
            "kind": "table",
            "name": "ledger",
        },
        default_schema="public",
    )

    assert context == SqlExecutionContext(
        datasource_id=17,
        dialect="postgresql",
        database="warehouse",
        catalog=None,
        schema="finance",
    )
    assert not hasattr(context, "sql")


def test_build_execution_context_rejects_mismatched_datasource() -> None:
    with pytest.raises(ValueError, match="datasource"):
        build_execution_context(
            datasource_id=99,
            dialect="postgresql",
            object_ref={
                "datasourceId": 17,
                "database": "warehouse",
                "schema": "finance",
                "kind": "table",
                "name": "ledger",
            },
            default_schema="public",
        )
