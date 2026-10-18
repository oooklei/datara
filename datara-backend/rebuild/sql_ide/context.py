"""Resolve ObjectRef paths into explicit SQL execution context.

This module carries schema/catalog selection as execution parameters. It does
not rewrite SQL text or infer a different object path from query strings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ObjectRef:
    """Complete read-side object identity from the SQL IDE contract."""

    datasource_id: int
    database: str
    kind: str
    name: str
    catalog: str | None = None
    schema: str | None = None
    parent: str | None = None

    @classmethod
    def from_value(cls, value: ObjectRef | Mapping[str, Any]) -> ObjectRef:
        if isinstance(value, cls):
            return value
        if not isinstance(value, Mapping):
            raise ValueError("ObjectRef must be an object")

        datasource_id = value.get("datasource_id", value.get("datasourceId"))
        return cls(
            datasource_id=datasource_id,
            database=value.get("database"),
            catalog=value.get("catalog"),
            schema=value.get("schema"),
            kind=value.get("kind"),
            name=value.get("name"),
            parent=value.get("parent"),
        )


@dataclass(frozen=True)
class SqlExecutionContext:
    """Resolved database selection, kept separate from user SQL text."""

    datasource_id: int
    dialect: str
    database: str
    catalog: str | None
    schema: str

    def connection_options(self) -> dict[str, str | None]:
        """Return explicit driver context without changing a SQL statement."""

        return {
            "database": self.database,
            "catalog": self.catalog,
            "schema": self.schema,
        }


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"ObjectRef {field} is required")
    return value.strip()


def resolve_object_ref(
    value: ObjectRef | Mapping[str, Any],
    *,
    default_catalog: str | None,
    default_schema: str | None,
) -> ObjectRef:
    """Normalize a complete ObjectRef, applying defaults only to omitted parts.

    An explicit catalog or schema always wins. A missing schema requires a
    driver-provided default; this function never guesses from global SQL text.
    """

    ref = ObjectRef.from_value(value)
    if isinstance(ref.datasource_id, bool) or not isinstance(ref.datasource_id, int) or ref.datasource_id <= 0:
        raise ValueError("ObjectRef datasourceId must be a positive integer")

    database = _required_text(ref.database, "database")
    kind = _required_text(ref.kind, "kind")
    name = _required_text(ref.name, "name")

    catalog = ref.catalog if ref.catalog is not None else default_catalog
    if catalog is not None:
        catalog = _required_text(catalog, "catalog")

    schema = ref.schema if ref.schema is not None else default_schema
    if schema is None or not isinstance(schema, str) or not schema.strip():
        raise ValueError("ObjectRef schema is required when the driver has no default schema")

    parent = ref.parent
    if parent is not None:
        parent = _required_text(parent, "parent")
    return ObjectRef(
        datasource_id=ref.datasource_id,
        database=database,
        catalog=catalog,
        schema=schema.strip(),
        kind=kind,
        name=name,
        parent=parent,
    )


def build_execution_context(
    *,
    datasource_id: int,
    dialect: str,
    object_ref: ObjectRef | Mapping[str, Any],
    default_catalog: str | None = None,
    default_schema: str | None,
) -> SqlExecutionContext:
    """Build an explicit context for an ObjectRef on the selected datasource."""

    if isinstance(datasource_id, bool) or not isinstance(datasource_id, int) or datasource_id <= 0:
        raise ValueError("datasource_id must be a positive integer")
    if not isinstance(dialect, str) or not dialect.strip():
        raise ValueError("dialect is required")

    ref = resolve_object_ref(
        object_ref,
        default_catalog=default_catalog,
        default_schema=default_schema,
    )
    if ref.datasource_id != datasource_id:
        raise ValueError("ObjectRef datasourceId does not match execution datasource")

    return SqlExecutionContext(
        datasource_id=datasource_id,
        dialect=dialect.strip().lower(),
        database=ref.database,
        catalog=ref.catalog,
        schema=ref.schema,
    )
