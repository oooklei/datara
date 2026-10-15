"""Read-only schema comparison for the R3 governance migration gate."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
import json
import os
import re
import sys

from sqlalchemy import Boolean, Engine, create_engine, inspect, text

from rebuild.governance.migrations import R3_GOVERNANCE_MIGRATIONS
from rebuild.governance.models import SchemaMigrationRecord

import_module("rebuild.project.models")  # Register the referenced core table in Base.metadata.
import_module("rebuild.identity.models")  # Register the user table referenced by carry-forward mappings.


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
    """Compare existing objects with every registered additive R3 revision, read-only."""
    if not R3_GOVERNANCE_MIGRATIONS:
        raise ValueError("R3 preflight requires at least one registered revision")
    migration = R3_GOVERNANCE_MIGRATIONS[-1]
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    expected_tables = tuple(table for revision in R3_GOVERNANCE_MIGRATIONS for table in revision.tables)
    expected_names = {table.name for table in expected_tables}
    missing = expected_names - existing
    conflicts: list[str] = []

    for table in expected_tables:
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
                for registered in R3_GOVERNANCE_MIGRATIONS:
                    row = connection.execute(
                        text(
                            "SELECT checksum, status FROM rebuild_schema_migration "
                            "WHERE revision = :revision"
                        ),
                        {"revision": registered.revision},
                    ).mappings().first()
                    if row is None:
                        if registered.revision == migration.revision:
                            revision_status = "absent"
                        continue
                    status = str(row["status"])
                    if registered.revision == migration.revision:
                        revision_status = status
                    if row["checksum"] != registered.checksum:
                        conflicts.append(f"migration checksum differs for {registered.revision}")
                    revision_tables = {table.name for table in registered.tables}
                    if status == "completed" and revision_tables & missing:
                        conflicts.append(f"completed revision {registered.revision} is missing one or more tables")
                    if status not in {"running", "failed", "completed"}:
                        conflicts.append(f"migration {registered.revision} has an unsupported status")

    return SchemaPreflightReport(
        revision=migration.revision,
        checksum=migration.checksum,
        existing_tables=tuple(sorted(expected_names & existing)),
        missing_tables=tuple(sorted(missing)),
        conflicts=tuple(conflicts),
        revision_table_present=revision_present,
        revision_status=revision_status,
    )



def _unique_index_is_full_column_index(index: dict) -> bool:
    """Return whether an inspected unique index enforces uniqueness for full columns."""
    columns = index.get("column_names")
    if not columns or any(not isinstance(column, str) or not column for column in columns):
        return False
    if index.get("expressions"):
        return False

    semantic_option_names = ("where", "predicate", "collation", "opclass", "operator_class", "length", "prefix")
    for key, value in index.items():
        if any(name in str(key).lower() for name in semantic_option_names) and value not in (None, "", [], {}):
            return False

    dialect_options = index.get("dialect_options") or {}
    if not isinstance(dialect_options, dict):
        return False
    for key, value in dialect_options.items():
        if any(name in str(key).lower() for name in semantic_option_names) and value not in (None, "", [], {}):
            return False
        if isinstance(value, dict):
            for option, option_value in value.items():
                if (
                    any(name in str(option).lower() for name in semantic_option_names)
                    and option_value not in (None, "", [], {})
                ):
                    return False
    return True


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

    actual_indexes = tuple(inspector.get_indexes(expected_table.name))
    for index in expected_table.indexes:
        expected_columns = tuple(column.name for column in index.columns)
        # MySQL limits index identifiers to 64 characters and SQLAlchemy's
        # generated names are shortened with a deterministic suffix. Names
        # are not part of the physical index contract; ordered columns and
        # uniqueness are. Compare those properties so a valid MySQL schema
        # does not fail preflight solely because its identifier was shortened.
        if not any(
            tuple(item.get("column_names") or ()) == expected_columns
            and bool(item.get("unique")) == bool(index.unique)
            and (not index.unique or _unique_index_is_full_column_index(item))
            for item in actual_indexes
        ):
            conflicts.append(f"{expected_table.name}: missing or incompatible index {index.name}")

    actual_unique = tuple(inspector.get_unique_constraints(expected_table.name))
    # Unique constraints from the dialect inspector describe full-key constraints.
    # Indexes are equivalent only when they use full columns and have no predicate,
    # expression, collation, or prefix-length semantics that weaken/change the key.
    actual_unique_columns = {
        tuple(item.get("column_names") or ())
        for item in actual_unique
        if _unique_index_is_full_column_index(item)
    }
    actual_unique_columns.update(
        tuple(item.get("column_names") or ())
        for item in actual_indexes
        if item.get("unique") and _unique_index_is_full_column_index(item)
    )
    all_unique_columns = {
        tuple(item.get("column_names") or ())
        for item in actual_unique
    }
    all_unique_columns.update(
        tuple(item.get("column_names") or ())
        for item in actual_indexes
        if item.get("unique")
    )
    expected_unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in expected_table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    expected_unique_columns.update(
        tuple(column.name for column in index.columns)
        for index in expected_table.indexes
        if index.unique
    )
    for constraint in expected_table.constraints:
        if constraint.__class__.__name__ != "UniqueConstraint":
            continue
        expected_columns = tuple(column.name for column in constraint.columns)
        if expected_columns not in actual_unique_columns:
            conflicts.append(f"{expected_table.name}: missing or incompatible unique constraint {constraint.name}")

    for unexpected_columns in sorted(all_unique_columns - expected_unique_columns):
        conflicts.append(f"{expected_table.name}: unexpected unique constraint or index {unexpected_columns}")

    actual_fks = {
        (
            tuple(item.get("constrained_columns") or ()),
            item.get("referred_table"),
            tuple(item.get("referred_columns") or ()),
            _normalize_referential_action((item.get("options") or {}).get("ondelete")),
        )
        for item in inspector.get_foreign_keys(expected_table.name)
    }
    for constraint in expected_table.foreign_key_constraints:
        expected_fk = (
            tuple(element.parent.name for element in constraint.elements),
            constraint.elements[0].column.table.name,
            tuple(element.column.name for element in constraint.elements),
            _normalize_referential_action(constraint.ondelete),
        )
        if expected_fk not in actual_fks:
            conflicts.append(
                f"{expected_table.name}: missing or incompatible foreign key {constraint.name or expected_fk[0]}"
            )
    actual_checks = {
        _normalize_check_expression(item.get("sqltext", ""))
        for item in inspector.get_check_constraints(expected_table.name)
    }
    for constraint in expected_table.constraints:
        if constraint.__class__.__name__ != "CheckConstraint":
            continue
        expected_check = _normalize_check_expression(str(constraint.sqltext))
        if expected_check not in actual_checks:
            conflicts.append(
                f"{expected_table.name}: missing or incompatible check constraint {constraint.name or expected_check}"
            )
    return conflicts


def _normalize_referential_action(action: str | None) -> str:
    normalized = (action or "NO ACTION").strip().upper().replace("_", " ")
    if normalized in {"RESTRICT", "NO ACTION"}:
        return "RESTRICT"
    return normalized


def _normalize_check_expression(expression: str) -> str:
    return re.sub(r"[\s`\"\[\]]+", "", expression).lower()


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
