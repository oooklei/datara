"""Read-only planning orchestration for the legacy I18 carry-forward."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from rebuild.governance.legacy_dry_run import I18DryRunPlan, I18TargetSnapshot, build_i18_dry_run_plan
from rebuild.governance.legacy_mapping import LegacyMappingContext, map_legacy_row
from rebuild.governance.legacy_source_reader import (
    I18_SOURCE_COLUMNS,
    LEGACY_SCHEMA,
    LegacyI18SourceSnapshot,
)


# User-approved exact identity alias for the observed I18 source data. This is
# deliberately not fuzzy matching and must not be generalized to other values.
I18_APPROVED_REFERENCE_ALIASES = {
    ("t_biz_domain", "交易"): ("t_biz_domain", "交易域"),
}
I18_APPROVED_RELATION_FIELD_ALIASES = {
    ("1", "source", "order_id"): "order_no",
    ("2", "target", "dt"): "order_date",
}
I18_APPROVED_SKIP_REASON = "approved_missing_model_reference"


@dataclass(frozen=True)
class I18LegacyDryRunResult:
    source_digest: str
    source_captured_at: datetime
    target_digest: str
    target_captured_at: datetime
    plan: I18DryRunPlan


def build_i18_legacy_dry_run(
    project_id: int,
    source_snapshot: LegacyI18SourceSnapshot,
    target_snapshot: I18TargetSnapshot,
) -> I18LegacyDryRunResult:
    """Map a complete source snapshot and classify it against a read-only target snapshot."""

    if project_id <= 0:
        raise ValueError("project_id must be positive")
    if source_snapshot.schema != LEGACY_SCHEMA:
        raise ValueError(f"source snapshot schema must be {LEGACY_SCHEMA}")
    if source_snapshot.captured_at.tzinfo is None:
        raise ValueError("source snapshot captured_at must be timezone-aware")
    if not _is_sha256(source_snapshot.digest):
        raise ValueError("source snapshot digest must be a SHA-256 hex string")
    if set(source_snapshot.rows) != set(I18_SOURCE_COLUMNS):
        raise ValueError("source snapshot must include all seven allowlisted I18 tables")
    if set(source_snapshot.counts) != set(I18_SOURCE_COLUMNS) or any(
        source_snapshot.counts[table] != len(source_snapshot.rows[table]) for table in I18_SOURCE_COLUMNS
    ):
        raise ValueError("source snapshot counts do not match the complete row payload")

    pending_identities: set[tuple[str, str]] = set()
    for table_name, (identity_field, _columns) in I18_SOURCE_COLUMNS.items():
        for source_row in source_snapshot.rows[table_name]:
            source_id = source_row.get(identity_field)
            if source_id is None:
                raise ValueError(f"source row in {table_name} is missing its identity")
            pending_identities.add((table_name, str(source_id)))
            if table_name == "t_biz_domain" and source_row.get("name"):
                # The old model schema explicitly stores t_biz_model.biz_domain -> t_biz_domain.name.
                pending_identities.add((table_name, str(source_row["name"])))

    context = LegacyMappingContext(
        target_project_id=project_id,
        target_ids=target_snapshot.target_ids,
        pending_identities=frozenset(pending_identities),
        approved_reference_aliases=I18_APPROVED_REFERENCE_ALIASES,
        approved_relation_field_aliases=I18_APPROVED_RELATION_FIELD_ALIASES,
    )
    mapped_rows = [
        map_legacy_row(table_name, source_row, context)
        for table_name in I18_SOURCE_COLUMNS
        for source_row in source_snapshot.rows[table_name]
    ]
    version_rows = [
        row for row in source_snapshot.rows["t_dw_model_version"] if str(row.get("id")) == "1"
    ]
    if version_rows:
        model_one_exists = any(str(row.get("id")) == "1" for row in source_snapshot.rows["t_dw_model"])
        if len(version_rows) != 1 or str(version_rows[0].get("model_id")) != "1" or model_one_exists:
            raise ValueError("approved skip precondition changed for t_dw_model_version#1")
    approved_skips = (
        {("t_dw_model_version", "1"): I18_APPROVED_SKIP_REASON} if version_rows else {}
    )
    plan = build_i18_dry_run_plan(
        mapped_rows,
        project_id=project_id,
        snapshot=target_snapshot,
        approved_skips=approved_skips,
    )
    return I18LegacyDryRunResult(
        source_digest=source_snapshot.digest,
        source_captured_at=source_snapshot.captured_at,
        target_digest=target_snapshot.digest,
        target_captured_at=target_snapshot.captured_at,
        plan=plan,
    )


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value.lower())
