"""Versioned migration registry for the component specification domain."""

from __future__ import annotations

from rebuild.component_spec.revisions import v0001_component_spec_tables
from rebuild.component_spec.revisions import v0002_component_catalog_upload
from rebuild.component_spec.revisions import v0003_stream_component_catalog
from rebuild.common.migrations import (
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
    # Versioned data migration: structurally guarantee the upload declaration
    # for sql/python/shell instead of relying on the seed script (D-09).
    GovernanceMigration(
        revision=v0002_component_catalog_upload.revision,
        checksum=v0002_component_catalog_upload.checksum,
        upgrade=v0002_component_catalog_upload.upgrade,
    ),
    GovernanceMigration(
        revision=v0003_stream_component_catalog.revision,
        checksum=v0003_stream_component_catalog.checksum,
        upgrade=v0003_stream_component_catalog.upgrade,
    ),
)


def apply_component_spec_migrations(engine) -> MigrationResult:
    """Apply component catalog DDL and reject drift after recorded success."""
    result = MigrationRunner(engine, COMPONENT_SPEC_MIGRATIONS).apply()
    try:
        v0001_component_spec_tables.validate_schema(engine)
        v0002_component_catalog_upload.validate_schema(engine)
        v0003_stream_component_catalog.validate_schema(engine)
    except Exception as error:
        raise MigrationApplyError(
            f"component catalog schema validation failed ({type(error).__name__})"
        ) from None
    return result
