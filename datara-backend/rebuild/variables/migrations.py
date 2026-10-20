"""Versioned migrations for the variables-owned schema."""

from rebuild.governance.migrations import GovernanceMigration, MigrationResult, MigrationRunner
from rebuild.variables.revisions import v0001_runtime_timestamp

VARIABLE_MIGRATIONS = (
    GovernanceMigration(
        revision=v0001_runtime_timestamp.revision,
        checksum=v0001_runtime_timestamp.checksum,
        upgrade=v0001_runtime_timestamp.upgrade,
    ),
)


def apply_variable_migrations(engine) -> MigrationResult:
    return MigrationRunner(engine, VARIABLE_MIGRATIONS).apply()
