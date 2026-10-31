from __future__ import annotations

from rebuild.common.migrations import (
    GovernanceMigration,
    MigrationApplyError,
    MigrationChecksumConflict,
    MigrationResult,
    MigrationRunner,
)
from rebuild.governance.models import (
    GOVERNANCE_I19_I20_TABLES,
    GOVERNANCE_TABLES,
    LEGACY_CARRY_FORWARD_TABLES,
)
from rebuild.governance.revisions import (
    v0001_governance_catalog,
    v0002_legacy_governance_carryforward,
    v0003_metadata_metric_carry_forward,
    v0004_token_digest_hardening,
    v0005_governance_project_fk_cascade,
)


R3_GOVERNANCE_MIGRATIONS = (
    GovernanceMigration(
        revision=v0001_governance_catalog.revision,
        checksum=v0001_governance_catalog.checksum,
        upgrade=v0001_governance_catalog.upgrade,
        tables=GOVERNANCE_TABLES,
    ),
    GovernanceMigration(
        revision=v0002_legacy_governance_carryforward.revision,
        checksum=v0002_legacy_governance_carryforward.checksum,
        upgrade=v0002_legacy_governance_carryforward.upgrade,
        tables=LEGACY_CARRY_FORWARD_TABLES,
    ),
    GovernanceMigration(
        revision=v0003_metadata_metric_carry_forward.revision,
        checksum=v0003_metadata_metric_carry_forward.checksum,
        upgrade=v0003_metadata_metric_carry_forward.upgrade,
        tables=GOVERNANCE_I19_I20_TABLES,
    ),
    GovernanceMigration(
        revision=v0004_token_digest_hardening.revision,
        checksum=v0004_token_digest_hardening.checksum,
        upgrade=v0004_token_digest_hardening.upgrade,
        postflight=v0004_token_digest_hardening.postflight,
    ),
    GovernanceMigration(
        revision=v0005_governance_project_fk_cascade.revision,
        checksum=v0005_governance_project_fk_cascade.checksum,
        upgrade=v0005_governance_project_fk_cascade.upgrade,
    ),
)
