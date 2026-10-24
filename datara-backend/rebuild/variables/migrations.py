"""Versioned migrations for the variables-owned schema."""

from rebuild.governance.migrations import GovernanceMigration, MigrationResult, MigrationRunner
from rebuild.variables.revisions import v0001_runtime_timestamp, v0002_environment_group_scope

VARIABLE_MIGRATIONS = (
    GovernanceMigration(
        revision=v0001_runtime_timestamp.revision,
        checksum=v0001_runtime_timestamp.checksum,
        upgrade=v0001_runtime_timestamp.upgrade,
    ),
    GovernanceMigration(
        revision=v0002_environment_group_scope.revision,
        checksum=v0002_environment_group_scope.checksum,
        upgrade=v0002_environment_group_scope.upgrade,
        postflight=v0002_environment_group_scope.postflight,
    ),
)


def apply_variable_migrations(engine) -> MigrationResult:
    return MigrationRunner(engine, VARIABLE_MIGRATIONS).apply()
