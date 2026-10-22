"""Explicit versioned migration entry point for the runtime node registry."""

from rebuild.governance.migrations import GovernanceMigration, MigrationResult, MigrationRunner
from rebuild.runtime_node.revisions import v0001_runtime_node_registry

RUNTIME_NODE_MIGRATIONS = (
    GovernanceMigration(
        revision=v0001_runtime_node_registry.revision,
        checksum=v0001_runtime_node_registry.checksum,
        upgrade=v0001_runtime_node_registry.upgrade,
        tables=v0001_runtime_node_registry.RUNTIME_NODE_TABLES,
    ),
)


def apply_runtime_node_migrations(engine) -> MigrationResult:
    return MigrationRunner(engine, RUNTIME_NODE_MIGRATIONS).apply()
