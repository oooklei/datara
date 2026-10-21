"""Migration registration for the security (access audit) domain.

Reuses the governance migration machinery (``MigrationRunner`` /
``GovernanceMigration``) so that all rebuild domains share one
``rebuild_schema_migration`` tracking table and one runner implementation.
"""

from __future__ import annotations

from rebuild.governance.migrations import GovernanceMigration, MigrationRunner
from rebuild.sec.models import SEC_TABLES
from rebuild.sec.revisions import v0001_sec_access_log

__all__ = ["GovernanceMigration", "MigrationRunner", "S1_SEC_MIGRATIONS"]


S1_SEC_MIGRATIONS = (
    GovernanceMigration(
        revision=v0001_sec_access_log.revision,
        checksum=v0001_sec_access_log.checksum,
        upgrade=v0001_sec_access_log.upgrade,
        tables=SEC_TABLES,
    ),
)
