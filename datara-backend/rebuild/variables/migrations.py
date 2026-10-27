"""Versioned migrations for the variables-owned schema."""

from rebuild.common.migrations import GovernanceMigration, MigrationResult, MigrationRunner
from rebuild.variables.revisions import (
    v0001_runtime_timestamp,
    v0002_environment_group_scope,
    v0003_runtime_source_width,
    v0004_runtime_scope_name_key,
)

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
    GovernanceMigration(
        revision=v0003_runtime_source_width.revision,
        checksum=v0003_runtime_source_width.checksum,
        upgrade=v0003_runtime_source_width.upgrade,
        postflight=v0003_runtime_source_width.postflight,
    ),
    GovernanceMigration(
        revision=v0004_runtime_scope_name_key.revision,
        checksum=v0004_runtime_scope_name_key.checksum,
        upgrade=v0004_runtime_scope_name_key.upgrade,
        postflight=v0004_runtime_scope_name_key.postflight,
    ),
)


def apply_variable_migrations(engine) -> MigrationResult:
    return MigrationRunner(engine, VARIABLE_MIGRATIONS).apply()
