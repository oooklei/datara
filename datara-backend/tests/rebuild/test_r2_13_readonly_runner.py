from __future__ import annotations

import pytest

from tools.verify_r2_13_readonly import (
    R3_GOVERNANCE_MIGRATIONS,
    assert_read_only_responses,
    assert_timestamp_snapshot,
)


def test_read_only_response_policy_allows_token_bootstrap_and_gets() -> None:
    assert_read_only_responses(
        [
            {"method": "POST", "path": "/api/v1/rebuild/validation-token", "status": 200},
            {"method": "GET", "path": "/api/v1/rebuild/projects", "status": 200},
            {"method": "GET", "path": "/api/v1/rebuild/governance/projects/8/assets", "status": 200},
        ]
    )


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_read_only_response_policy_rejects_non_bootstrap_mutations(method: str) -> None:
    with pytest.raises(AssertionError, match="unexpected non-read request"):
        assert_read_only_responses(
            [{"method": method, "path": "/api/v1/rebuild/governance/projects/8/assets", "status": 200}]
        )


def test_timestamp_snapshot_requires_server_defaults_and_completed_migrations() -> None:
    snapshot = {
        "tables": ["rebuild_governance_asset", "rebuild_schema_migration"],
        "timestamp_column_metadata": [
            f"{table}\t{column}\tNO\tCURRENT_TIMESTAMP"
            for table in ("rebuild_governance_asset", "rebuild_schema_migration")
            for column in ("created_at", "updated_at", "generated_at")
        ],
        "row_and_null_timestamp_counts": [
            {"table": table, "null_timestamp_counts": {"created_at": 0, "updated_at": 0}}
            for table in ("rebuild_governance_asset", "rebuild_schema_migration")
        ],
        "migration_records": [
            f"{migration.revision}\t{migration.checksum}\tcompleted\t1\t"
            "2026-10-15 01:00:00\t2026-10-15 01:00:01"
            for migration in R3_GOVERNANCE_MIGRATIONS
        ],
    }

    assert_timestamp_snapshot(snapshot)


def test_timestamp_snapshot_rejects_missing_database_default() -> None:
    snapshot = {
        "tables": ["rebuild_governance_asset"],
        "timestamp_column_metadata": [
            "rebuild_governance_asset\tcreated_at\tYES\t<NULL>",
            "rebuild_governance_asset\tupdated_at\tNO\tCURRENT_TIMESTAMP",
        ],
        "row_and_null_timestamp_counts": [
            {"table": "rebuild_governance_asset", "null_timestamp_counts": {"updated_at": 0}}
        ],
        "migration_records": [],
    }

    with pytest.raises(AssertionError, match="created_at lacks"):
        assert_timestamp_snapshot(snapshot)
