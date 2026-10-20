"""Versioned execution DDL migration registry.

The governance migration runner supplies revision/checksum persistence,
MySQL GET_LOCK serialization, running/completed/failed states and retry rules.
This module registers only execution-owned tables and leaves app lifespan
assembly to the host application.
"""

from rebuild.execution.revisions import v0001_execution_tables
from rebuild.execution.models import EXECUTION_TABLES
from rebuild.governance.migrations import GovernanceMigration, MigrationResult, MigrationRunner


EXECUTION_MIGRATIONS = (
    GovernanceMigration(
        revision=v0001_execution_tables.revision,
        checksum=v0001_execution_tables.checksum,
        upgrade=v0001_execution_tables.upgrade,
        tables=EXECUTION_TABLES,
    ),
)


def apply_execution_migrations(engine) -> MigrationResult:
    """Apply execution DDL exactly once using the shared versioned runner."""
    return MigrationRunner(engine, EXECUTION_MIGRATIONS).apply()
