"""Read-only I20 metric/version mapping preview with project-scoped target identities."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.governance.legacy_i20_mapping import MappedI20Snapshot, map_i20_snapshot
from rebuild.governance.legacy_mapping import LegacyMappingContext, MappingIssue
from rebuild.governance.legacy_source_reader import I20_SOURCE_COLUMNS
from rebuild.governance.models import (
    SemanticMetricProfileRecord,
    SemanticMetricRecord,
    SemanticMetricVersionRecord,
)


@dataclass(frozen=True)
class I20MappingPreview:
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
    mapping: MappedI20Snapshot


def build_i20_mapping_preview(
    session: Session,
    project_id: int,
    source_snapshot: object,
    *,
    captured_at: datetime | None = None,
) -> I20MappingPreview:
    """Compare fixed I20 source identities to target provenance; never mutate either database."""
    if project_id <= 0:
        raise ValueError("project_id must be positive")
    if getattr(source_snapshot, "schema", None) != "datara_meta":
        raise ValueError("source snapshot schema must be datara_meta")
    captured_at = captured_at or datetime.now(ZoneInfo("Asia/Shanghai"))
    if captured_at.tzinfo is None:
        raise ValueError("captured_at must be timezone-aware")

    metrics = session.scalars(select(SemanticMetricRecord).where(SemanticMetricRecord.project_id == project_id)).all()
    metric_ids: dict[tuple[str, str], int] = {}
    target_counts = {
        "t_indicator": len(metrics),
        "t_indicator_version": 0,
    }
    profiles = session.scalars(
        select(SemanticMetricProfileRecord)
        .join(SemanticMetricRecord, SemanticMetricRecord.id == SemanticMetricProfileRecord.metric_id)
        .where(SemanticMetricRecord.project_id == project_id)
    ).all()
    for record in profiles:
        if record.source_system == "datara_meta" and record.source_table == "t_indicator" and record.source_id:
            identity = ("t_indicator", record.source_id)
            if identity in metric_ids:
                raise ValueError("duplicate target source identity")
            metric_ids[identity] = record.metric_id

    version_records = session.scalars(
        select(SemanticMetricVersionRecord)
        .join(SemanticMetricRecord, SemanticMetricRecord.id == SemanticMetricVersionRecord.metric_id)
        .where(SemanticMetricRecord.project_id == project_id)
    ).all()
    target_counts["t_indicator_version"] = len(version_records)
    for record in version_records:
        if (
            record.source_system == "datara_meta"
            and record.source_table == "t_indicator_version"
            and record.source_id
        ):
            identity = ("t_indicator_version", record.source_id)
            if identity in metric_ids:
                raise ValueError("duplicate target source identity")
            metric_ids[identity] = record.id

    context = LegacyMappingContext(target_project_id=project_id, target_ids=metric_ids)
    mapping = map_i20_snapshot(source_snapshot, context)
    entries: list[dict[str, object]] = []
    dispositions = {"new_identity_candidate": 0, "target_identity_match": 0, "blocked": 0}
    all_issues: list[MappingIssue] = list(mapping.mapping_issues)
    for bundle in mapping.metrics:
        rows = (bundle.metric, *bundle.versions)
        for row in rows:
            row_issues = list(row.mapping_issues)
            if row is bundle.metric:
                row_issues.extend(bundle.mapping_issues)
            row_issues.extend(
                issue
                for issue in mapping.mapping_issues
                if issue.source_table == row.source_table and issue.source_id == row.source_id
            )
            disposition = (
                "blocked"
                if row_issues or (row is bundle.metric and any(v.mapping_issues for v in bundle.versions))
                else "target_identity_match"
                if row.target_id is not None
                else "new_identity_candidate"
            )
            dispositions[disposition] += 1
            entries.append(
                {
                    "source_table": row.source_table,
                    "source_id": row.source_id,
                    "disposition": disposition,
                    "target_table": row.target_table,
                    "target_id": row.target_id,
                    "issues": sorted({issue.code for issue in row_issues}),
                }
            )
    for issue in mapping.orphan_versions:
        dispositions["blocked"] += 1
        entries.append(
            {
                "source_table": issue.source_table,
                "source_id": issue.source_id,
                "disposition": "blocked",
                "target_table": "rebuild_governance_semantic_metric_version",
                "target_id": None,
                "issues": [issue.code],
            }
        )
    source_counts = dict(getattr(source_snapshot, "counts", {}))
    if set(source_counts) != set(I20_SOURCE_COLUMNS):
        raise ValueError("source snapshot counts must include both I20 tables")
    if any(source_counts[table] != len(source_snapshot.rows[table]) for table in I20_SOURCE_COLUMNS):
        raise ValueError("source snapshot counts do not match row payload")
    identity_payload = sorted(
        (table, identity, target_id) for (table, identity), target_id in metric_ids.items()
    )
    target_digest = hashlib.sha256(
        json.dumps(identity_payload, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return I20MappingPreview(
        project_id=project_id,
        captured_at=captured_at,
        source_schema=source_snapshot.schema,
        source_digest=source_snapshot.digest,
        target_digest=target_digest,
        source_counts=source_counts,
        target_counts=target_counts,
        dispositions=dispositions,
        entries=tuple(entries),
        issues=tuple(all_issues),
        mapping=mapping,
    )
