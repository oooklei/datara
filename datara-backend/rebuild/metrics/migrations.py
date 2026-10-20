"""Versioned migrations for the metrics-owned schema."""

from rebuild.governance.migrations import GovernanceMigration, MigrationResult, MigrationRunner
from rebuild.metrics.revisions import v0001_runtime_timestamps

METRICS_MIGRATIONS = (
    GovernanceMigration(
        revision=v0001_runtime_timestamps.revision,
        checksum=v0001_runtime_timestamps.checksum,
        upgrade=v0001_runtime_timestamps.upgrade,
    ),
)


def apply_metrics_migrations(engine) -> MigrationResult:
    return MigrationRunner(engine, METRICS_MIGRATIONS).apply()
