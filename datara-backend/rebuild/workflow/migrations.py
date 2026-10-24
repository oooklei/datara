"""Versioned workflow-domain migrations."""

from rebuild.governance.migrations import GovernanceMigration, MigrationResult, MigrationRunner
from rebuild.workflow.revisions import v0001_workflow_type
from rebuild.workflow.revisions import v0002_workflow_categories


WORKFLOW_MIGRATIONS = (
    GovernanceMigration(
        revision=v0001_workflow_type.revision,
        checksum=v0001_workflow_type.checksum,
        upgrade=v0001_workflow_type.upgrade,
        tables=("workflow_definition",),
    ),
    GovernanceMigration(
        revision=v0002_workflow_categories.revision,
        checksum=v0002_workflow_categories.checksum,
        upgrade=v0002_workflow_categories.upgrade,
        tables=("workflow_definition", "workflow_category"),
    ),
)


def apply_workflow_migrations(engine) -> MigrationResult:
    result = MigrationRunner(engine, WORKFLOW_MIGRATIONS).apply()
    v0001_workflow_type.validate_schema(engine)
    v0002_workflow_categories.validate_schema(engine)
    return result
