"""Versioned workflow-domain migrations."""

from rebuild.governance.migrations import GovernanceMigration, MigrationResult, MigrationRunner
from rebuild.workflow.revisions import v0001_workflow_type


WORKFLOW_MIGRATIONS = (
    GovernanceMigration(
        revision=v0001_workflow_type.revision,
        checksum=v0001_workflow_type.checksum,
        upgrade=v0001_workflow_type.upgrade,
        tables=("workflow_definition",),
    ),
)


def apply_workflow_migrations(engine) -> MigrationResult:
    result = MigrationRunner(engine, WORKFLOW_MIGRATIONS).apply()
    v0001_workflow_type.validate_schema(engine)
    return result
