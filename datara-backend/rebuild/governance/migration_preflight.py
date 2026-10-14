"""Read-only schema comparison for the R3 governance migration gate."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import json
import os
import sys

from sqlalchemy import Boolean, Engine, create_engine, inspect, text

from rebuild.governance.migrations import R3_GOVERNANCE_MIGRATIONS
from rebuild.governance.models import GOVERNANCE_TABLES, SchemaMigrationRecord

import_module("rebuild.project.models")  # Register the referenced core table in Base.metadata.


@dataclass(frozen=True)
class SchemaPreflightReport:
    revision: str
    checksum: str
    existing_tables: tuple[str, ...]
    missing_tables: tuple[str, ...]
    conflicts: tuple[str, ...]
    revision_table_present: bool
    revision_status: str

    @property
    def ready(self) -> bool:
        return not self.conflicts


def inspect_governance_schema(engine: Engine) -> SchemaPreflightReport:
    """Compare existing objects with the one registered R3 DDL, without DDL/DML writes."""
    if len(R3_GOVERNANCE_MIGRATIONS) != 1:
        raise ValueError("R3 preflight requires an explicitly selected single revision")
    migration = R3_GOVERNANCE_MIGRATIONS[0]
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    expected_names = {table.name for table in GOVERNANCE_TABLES}
    missing = expected_names - existing
    conflicts: list[str] = []

    for table in GOVERNANCE_TABLES:
        if table.name not in existing:
            continue
        conflicts.extend(_compare_table(inspector, table))

    revision_present = SchemaMigrationRecord.__tablename__ in existing
    revision_status = "absent"
    if revision_present:
        revision_columns = {column["name"] for column in inspector.get_columns(SchemaMigrationRecord.__tablename__)}
        required_columns = {column.name for column in SchemaMigrationRecord.__table__.columns}
        if not required_columns <= revision_columns:
            conflicts.append("migration revision table has an incompatible column set")
        else:
            with engine.connect() as connection:
                row = connection.execute(
                    text(
                        "SELECT checksum, status FROM rebuild_schema_migration "
                        "WHERE revision = :revision"
                    ),
                    {"revision": migration.revision},
                ).mappings().first()
            if row is not None:
                revision_status = str(row["status"])
                if row["checksum"] != migration.checksum:
                    conflicts.append("migration revision checksum differs from the registered code")
                if revision_status == "completed" and missing:
                    conflicts.append("completed revision is missing one or more governance tables")
                if revision_status not in {"running", "failed", "completed"}:
                    conflicts.append("migration revision has an unsupported status")

    return SchemaPreflightReport(
        revision=migration.revision,
        checksum=migration.checksum,
        existing_tables=tuple(sorted(expected_names & existing)),
        missing_tables=tuple(sorted(missing)),
        conflicts=tuple(conflicts),
        revision_table_present=revision_present,
        revision_status=revision_status,
    )


def _compare_table(inspector, expected_table) -> list[str]:
    conflicts: list[str] = []
    actual_columns = {column["name"]: column for column in inspector.get_columns(expected_table.name)}
    for expected in expected_table.columns:
        actual = actual_columns.get(expected.name)
        if actual is None:
            conflicts.append(f"{expected_table.name}: missing column {expected.name}")
            continue
        if not _types_compatible(actual["type"], expected.type):
            conflicts.append(f"{expected_table.name}.{expected.name}: incompatible type")
        if bool(actual["nullable"]) != bool(expected.nullable):
            conflicts.append(f"{expected_table.name}.{expected.name}: incompatible nullability")
        if expected.server_default is not None and actual.get("default") is None:
            conflicts.append(f"{expected_table.name}.{expected.name}: missing server default")

    actual_pk = set(inspector.get_pk_constraint(expected_table.name).get("constrained_columns") or ())
    expected_pk = {column.name for column in expected_table.primary_key.columns}
    if actual_pk != expected_pk:
        conflicts.append(f"{expected_table.name}: incompatible primary key")

    actual_indexes = {
        item["name"]: tuple(item["column_names"] or ()) for item in inspector.get_indexes(expected_table.name)
    }
    for index in expected_table.indexes:
        expected_columns = tuple(column.name for column in index.columns)
        if actual_indexes.get(index.name) != expected_columns:
            conflicts.append(f"{expected_table.name}: missing or incompatible index {index.name}")

    actual_unique = {
        item.get("name"): tuple(item.get("column_names") or ())
        for item in inspector.get_unique_constraints(expected_table.name)
    }
    for constraint in expected_table.constraints:
        if constraint.__class__.__name__ != "UniqueConstraint":
            continue
        expected_columns = tuple(column.name for column in constraint.columns)
        if actual_unique.get(constraint.name) != expected_columns:
            conflicts.append(f"{expected_table.name}: missing or incompatible unique constraint {constraint.name}")

    actual_fks = {
        (
            tuple(item.get("constrained_columns") or ()),
            item.get("referred_table"),
            tuple(item.get("referred_columns") or ()),
        )
        for item in inspector.get_foreign_keys(expected_table.name)
    }
    for constraint in expected_table.foreign_key_constraints:
        expected_fk = (
            tuple(element.parent.name for element in constraint.elements),
            constraint.elements[0].column.table.name,
            tuple(element.column.name for element in constraint.elements),
        )
        if expected_fk not in actual_fks:
            conflicts.append(
                f"{expected_table.name}: missing or incompatible foreign key {constraint.name or expected_fk[0]}"
            )
    return conflicts


def _types_compatible(actual_type, expected_type) -> bool:
    actual_affinity = getattr(actual_type, "_type_affinity", type(actual_type))
    expected_affinity = getattr(expected_type, "_type_affinity", type(expected_type))
    if actual_affinity is expected_affinity:
        return True
    # MySQL stores SQLAlchemy Boolean columns as TINYINT(1); larger TINYINTs
    # remain integers and must not be accepted as booleans.
    return (
        isinstance(expected_type, Boolean)
        and actual_type.__class__.__name__.upper() == "TINYINT"
        and getattr(actual_type, "display_width", None) == 1
    )


def main() -> int:
    database_url = os.environ.get("REBUILD_DB_URL")
    if not database_url:
        print("R3_PREFLIGHT_ERROR: REBUILD_DB_URL is not configured", file=sys.stderr)
        return 2
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        report = inspect_governance_schema(engine)
        payload = {
            "revision": report.revision,
            "checksum": report.checksum,
            "existing_tables": report.existing_tables,
            "missing_tables": report.missing_tables,
            "conflicts": report.conflicts,
            "revision_table_present": report.revision_table_present,
            "revision_status": report.revision_status,
            "ready": report.ready,
            "read_only": True,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0 if report.ready else 3
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
