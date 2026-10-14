"""Explicitly gated CLI for the additive R3 governance migration."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from rebuild.governance.migration_preflight import inspect_governance_schema
from rebuild.governance.migrations import MigrationRunner, R3_GOVERNANCE_MIGRATIONS


TARGET_DATABASE = "datara_rebuild_i0"


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only preflight or apply the isolated R3 governance revision")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="inspect expected schema without writing")
    mode.add_argument("--apply", action="store_true", help="apply only the registered additive R3 revision")
    args = parser.parse_args()

    database_url = os.environ.get("REBUILD_DB_URL")
    if not database_url:
        print("R3_MIGRATION_ERROR: REBUILD_DB_URL is not configured", file=sys.stderr)
        return 2
    parsed = make_url(database_url)
    if parsed.get_backend_name() != "mysql" or parsed.database != TARGET_DATABASE:
        print("R3_MIGRATION_REFUSED: configured target is not the isolated R3 schema", file=sys.stderr)
        return 4

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        before = inspect_governance_schema(engine)
        if not before.ready:
            print(json.dumps(_report(before), ensure_ascii=False, sort_keys=True))
            return 3
        if args.dry_run:
            plan = {**_report(before), "plan": "create_missing_registered_governance_objects"}
            print(json.dumps(plan, ensure_ascii=False, sort_keys=True))
            return 0

        applied = MigrationRunner(engine, R3_GOVERNANCE_MIGRATIONS).apply()
        after = inspect_governance_schema(engine)
        if not after.ready or after.missing_tables:
            failure = {"postflight": _report(after), "migration_applied": applied.applied}
            print(json.dumps(failure, ensure_ascii=False, sort_keys=True))
            return 5
        result = {
            "target_database": TARGET_DATABASE,
            "preflight": _report(before),
            "applied": applied.applied,
            "skipped": applied.skipped,
            "postflight": _report(after),
            "read_only": False,
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    finally:
        engine.dispose()


def _report(report) -> dict[str, object]:
    return {**asdict(report), "ready": report.ready}


if __name__ == "__main__":
    raise SystemExit(main())
