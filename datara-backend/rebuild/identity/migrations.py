"""Identity-owned startup migrations.

The token digest hardening revision lives in the historical R3 revision
package, but it is required by the current identity ORM and login path.  Keep
it independently runnable so API startup does not need to apply the unrelated
governance catalogue migrations.
"""

from rebuild.governance.migrations import GovernanceMigration, MigrationResult, MigrationRunner
from rebuild.governance.revisions import v0004_token_digest_hardening


IDENTITY_MIGRATIONS = (
    GovernanceMigration(
        revision=v0004_token_digest_hardening.revision,
        checksum=v0004_token_digest_hardening.checksum,
        upgrade=v0004_token_digest_hardening.upgrade,
        postflight=v0004_token_digest_hardening.postflight,
    ),
)


def apply_identity_migrations(engine) -> MigrationResult:
    return MigrationRunner(engine, IDENTITY_MIGRATIONS).apply()
