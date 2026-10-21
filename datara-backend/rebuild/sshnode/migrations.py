"""Explicit versioned migration entry point for the SSH node registry."""

from rebuild.governance.migrations import GovernanceMigration, MigrationResult, MigrationRunner
from rebuild.sshnode.revisions import v0001_ssh_node_registry

SSH_NODE_MIGRATIONS = (
    GovernanceMigration(
        revision=v0001_ssh_node_registry.revision,
        checksum=v0001_ssh_node_registry.checksum,
        upgrade=v0001_ssh_node_registry.upgrade,
        tables=v0001_ssh_node_registry.SSH_NODE_TABLES,
    ),
)


def apply_ssh_node_migrations(engine) -> MigrationResult:
    return MigrationRunner(engine, SSH_NODE_MIGRATIONS).apply()
