"""Explicit, versioned DDL entry point for the stream domain.

Apply manually from ``datara-backend`` with::

    REBUILD_DB_URL=... python -m rebuild.stream.migrations --apply

Importing this module and starting the application never applies migrations.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from sqlalchemy import create_engine

from rebuild.governance.migrations import GovernanceMigration, MigrationResult, MigrationRunner
from rebuild.stream.revisions import v0001_legacy_job_mapping, v0002_stream_job_attempt


# Full stream schema owned by the versioned registry (v0001 five tables +
# v0002 stream_job_attempt; DEP-05 user ruling 方案 A).
STREAM_TABLES = v0001_legacy_job_mapping.STREAM_TABLES + v0002_stream_job_attempt.STREAM_TABLES


STREAM_MIGRATIONS = (
    GovernanceMigration(
        revision=v0001_legacy_job_mapping.revision,
        checksum=v0001_legacy_job_mapping.checksum,
        upgrade=v0001_legacy_job_mapping.upgrade,
        tables=v0001_legacy_job_mapping.STREAM_TABLES,
    ),
    GovernanceMigration(
        revision=v0002_stream_job_attempt.revision,
        checksum=v0002_stream_job_attempt.checksum,
        upgrade=v0002_stream_job_attempt.upgrade,
        tables=v0002_stream_job_attempt.STREAM_TABLES,
    ),
)


def apply_stream_migrations(engine) -> MigrationResult:
    """Apply registered stream schema revisions through the shared runner."""
    return MigrationRunner(engine, STREAM_MIGRATIONS).apply()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply explicitly requested stream schema migrations.")
    parser.add_argument("--apply", action="store_true", required=True, help="apply registered stream migrations")
    args = parser.parse_args(argv)
    if not args.apply:
        parser.error("--apply is required")

    database_url = os.environ.get("REBUILD_DB_URL")
    if not database_url:
        print("STREAM_MIGRATION_ERROR: REBUILD_DB_URL is not configured", file=sys.stderr)
        return 2

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        result = apply_stream_migrations(engine)
        print(json.dumps({"applied": result.applied, "skipped": result.skipped}, ensure_ascii=False))
        return 0
    except Exception as error:
        print(f"STREAM_MIGRATION_ERROR: {type(error).__name__}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
