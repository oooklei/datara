"""Versioned migration registry for the component specification domain."""

from __future__ import annotations

from rebuild.component_spec.revisions import v0001_component_spec_tables
from rebuild.component_spec.revisions import v0002_component_catalog_upload
from rebuild.governance.migrations import (
    GovernanceMigration,
    MigrationApplyError,
    MigrationResult,
    MigrationRunner,
)


COMPONENT_SPEC_MIGRATIONS = (
    GovernanceMigration(
        revision=v0001_component_spec_tables.revision,
        checksum=v0001_component_spec_tables.checksum,
        upgrade=v0001_component_spec_tables.upgrade,
        tables=v0001_component_spec_tables.COMPONENT_TABLES,
    ),
    GovernanceMigration(
        revision=v0002_component_catalog_upload.revision,
        checksum=v0002_component_catalog_upload.checksum,
        upgrade=v0002_component_catalog_upload.upgrade,
        tables=("t_component_version",),
    ),
)


def apply_component_spec_migrations(engine) -> MigrationResult:
    """Apply component catalog DDL/data and reject drift after recorded success."""
    result = MigrationRunner(engine, COMPONENT_SPEC_MIGRATIONS).apply()
    try:
        v0001_component_spec_tables.validate_schema(engine)
        v0002_component_catalog_upload.validate_schema(engine)
    except Exception as error:
        raise MigrationApplyError(
            f"component catalog schema validation failed ({type(error).__name__})"
        ) from None
    return result
