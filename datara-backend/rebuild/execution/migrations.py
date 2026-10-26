"""Versioned execution DDL migration registry.

The governance migration runner supplies revision/checksum persistence,
MySQL GET_LOCK serialization, running/completed/failed states and retry rules.
This module registers only execution-owned tables and leaves app lifespan
assembly to the host application.
"""

from rebuild.execution.revisions import (
    v0001_execution_tables,
    v0002_run_statistics,
    v0003_run_snapshot_contract,
)
from rebuild.common.migrations import GovernanceMigration, MigrationResult, MigrationRunner


EXECUTION_MIGRATIONS = (
    GovernanceMigration(
        revision=v0001_execution_tables.revision,
        checksum=v0001_execution_tables.checksum,
        upgrade=v0001_execution_tables.upgrade,
        tables=v0001_execution_tables.TABLES,
    ),
    GovernanceMigration(
        revision=v0002_run_statistics.revision,
        checksum=v0002_run_statistics.checksum,
        upgrade=v0002_run_statistics.upgrade,
        tables=v0002_run_statistics.TABLES,
    ),
    GovernanceMigration(
        revision=v0003_run_snapshot_contract.revision,
        checksum=v0003_run_snapshot_contract.checksum,
        upgrade=v0003_run_snapshot_contract.upgrade,
        postflight=v0003_run_snapshot_contract.postflight,
    ),
)


def apply_execution_migrations(engine) -> MigrationResult:
    """Apply execution DDL exactly once using the shared versioned runner."""
    return MigrationRunner(engine, EXECUTION_MIGRATIONS).apply()
