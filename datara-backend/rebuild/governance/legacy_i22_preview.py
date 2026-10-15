"""Read-only I22 mapping preview; deliberately does not claim semantic parity."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.governance.legacy_i22_mapping import MappedI22Snapshot, map_i22_snapshot
from rebuild.governance.legacy_mapping import LegacyMappingContext, MappingIssue
from rebuild.governance.legacy_source_reader import I22_SOURCE_COLUMNS
from rebuild.governance.models import (
    StandardApprovalRecord,
    StandardCheckReportRecord,
    StandardCodeSetRecord,
    StandardCodeValueRecord,
    StandardElementRecord,
    StandardMappingRecord,
    StandardNamingRuleRecord,
)


_TARGET_MODELS = {
    "t_std_element": StandardElementRecord,
    "t_std_code": StandardCodeSetRecord,
    "t_std_naming_rule": StandardNamingRuleRecord,
    "t_std_mapping": StandardMappingRecord,
    "t_std_approval": StandardApprovalRecord,
    "t_std_check_report": StandardCheckReportRecord,
}
_MAPPED_ROWS = {
    "t_std_element": "elements",
    "t_std_code": "code_sets",
    "t_std_code_value": "code_values",
    "t_std_naming_rule": "naming_rules",
    "t_std_mapping": "mappings",
    "t_std_approval": "approvals",
    "t_std_check_report": "check_reports",
}


@dataclass(frozen=True)
class I22MappingPreview:
    project_id: int
    captured_at: datetime
    source_schema: str
    source_digest: str
    target_digest: str
    source_counts: Mapping[str, int]
    target_counts: Mapping[str, int]
    dispositions: Mapping[str, int]
    entries: tuple[Mapping[str, object], ...]
    issues: tuple[MappingIssue, ...]
    mapping: MappedI22Snapshot


def build_i22_mapping_preview(
    session: Session,
    project_id: int,
    source_snapshot: object,
    *,
    captured_at: datetime | None = None,
) -> I22MappingPreview:
    """Compare source mapping identities to project-scoped target provenance only.

    A target identity match is not called unchanged: this preview intentionally
    does not claim field-level semantic equality or authorize an import.
    """
    if project_id <= 0:
        raise ValueError("project_id must be positive")
    if getattr(source_snapshot, "schema", None) != "datara_meta":
        raise ValueError("source snapshot schema must be datara_meta")
    captured_at = captured_at or datetime.now(ZoneInfo("Asia/Shanghai"))
    if captured_at.tzinfo is None:
        raise ValueError("captured_at must be timezone-aware")

    target_ids: dict[tuple[str, str], int] = {}
    target_counts: dict[str, int] = {}
    for source_table, model in _TARGET_MODELS.items():
        records = session.scalars(select(model).where(model.project_id == project_id)).all()
        target_counts[source_table] = len(records)
        for record in records:
            if record.source_system != "datara_meta" or not record.source_table or not record.source_id:
                continue
            identity = (record.source_table, record.source_id)
            if identity in target_ids:
                raise ValueError(f"duplicate target source identity: {identity[0]}:{identity[1]}")
            target_ids[identity] = record.id

    code_values = session.scalars(
        select(StandardCodeValueRecord)
        .join(StandardCodeSetRecord, StandardCodeSetRecord.id == StandardCodeValueRecord.code_set_id)
        .where(StandardCodeSetRecord.project_id == project_id)
    ).all()
    target_counts["t_std_code_value"] = len(code_values)
    for record in code_values:
        if record.source_system != "datara_meta" or not record.source_table or not record.source_id:
            continue
        identity = (record.source_table, record.source_id)
        if identity in target_ids:
            raise ValueError(f"duplicate target source identity: {identity[0]}:{identity[1]}")
        target_ids[identity] = record.id

    context = LegacyMappingContext(target_project_id=project_id, target_ids=target_ids)
    mapped = map_i22_snapshot(source_snapshot, context)
    entries: list[dict[str, object]] = []
    issues: list[MappingIssue] = list(mapped.mapping_issues)
    counts = {"new_identity_candidate": 0, "target_identity_match": 0, "blocked": 0}
    for source_table, attr in _MAPPED_ROWS.items():
        for row in getattr(mapped, attr):
            row_issues = list(row.mapping_issues)
            row_issues.extend(
                MappingIssue("unresolved_reference", row.source_table, row.source_id, f"{table}:{identity}")
                for table, identity in row.unresolved_references
            )
            disposition = (
                "blocked"
                if row_issues
                else "target_identity_match"
                if row.target_id is not None
                else "new_identity_candidate"
            )
            counts[disposition] += 1
            entries.append(
                {
                    "source_table": source_table,
                    "source_id": row.source_id,
                    "disposition": disposition,
                    "target_table": row.target_table,
                    "target_id": row.target_id,
                    "issues": [
                        {"code": issue.code, "source_table": issue.source_table, "source_id": issue.source_id}
                        for issue in row_issues
                    ],
                }
            )
    source_counts = dict(getattr(source_snapshot, "counts", {}))
    if set(source_counts) != set(I22_SOURCE_COLUMNS):
        raise ValueError("source snapshot counts must include all seven I22 tables")
    if any(source_counts[table] != len(source_snapshot.rows[table]) for table in I22_SOURCE_COLUMNS):
        raise ValueError("source snapshot counts do not match row payload")
    identity_bytes = json.dumps(
        sorted((table, identity, target_id) for (table, identity), target_id in target_ids.items()),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    target_digest = hashlib.sha256(identity_bytes).hexdigest()
    return I22MappingPreview(
        project_id=project_id,
        captured_at=captured_at,
        source_schema=source_snapshot.schema,
        source_digest=source_snapshot.digest,
        target_digest=target_digest,
        source_counts=source_counts,
        target_counts=target_counts,
        dispositions=counts,
        entries=tuple(entries),
        issues=tuple(issues),
        mapping=mapped,
    )
