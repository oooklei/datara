"""Project-scoped, read-only preview for legacy I21 quality governance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.governance.legacy_i21_mapping import MappedI21Snapshot, map_i21_snapshot
from rebuild.governance.legacy_mapping import LegacyMappingContext, MappingIssue
from rebuild.governance.legacy_source_reader import I21_SOURCE_COLUMNS
from rebuild.governance.models import (
    QualityAlarmPolicyRecord,
    QualityExceptionRecord,
    QualityReportRecord,
    QualityRunLegacyDetailsRecord,
    QualityRunRecord,
    QualityRuleDefinitionRecord,
    QualityTaskRecord,
    QualityTaskRuleRecord,
)


_TARGET_MODELS = {
    "t_qc_rule": QualityRuleDefinitionRecord,
    "t_qc_task": QualityTaskRecord,
    "t_qc_exception": QualityExceptionRecord,
    "t_qc_report": QualityReportRecord,
    "t_qc_alarm_policy": QualityAlarmPolicyRecord,
}


@dataclass(frozen=True)
class I21MappingPreview:
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
    mapping: MappedI21Snapshot


def build_i21_mapping_preview(
    session: Session,
    project_id: int,
    source_snapshot: object,
    *,
    captured_at: datetime | None = None,
) -> I21MappingPreview:
    """Compare I21 source identities to target provenance without returning payloads or writing."""
    if project_id <= 0:
        raise ValueError("project_id must be positive")
    if getattr(source_snapshot, "schema", None) != "datara_meta":
        raise ValueError("source snapshot schema must be datara_meta")
    captured_at = captured_at or datetime.now(ZoneInfo("Asia/Shanghai"))
    if captured_at.tzinfo is None:
        raise ValueError("captured_at must be timezone-aware")

    source_counts = dict(getattr(source_snapshot, "counts", {}))
    if set(source_counts) != set(I21_SOURCE_COLUMNS):
        raise ValueError("source snapshot counts must include all six I21 tables")
    if any(source_counts[table] != len(source_snapshot.rows[table]) for table in I21_SOURCE_COLUMNS):
        raise ValueError("source snapshot counts do not match row payload")

    source_ids: dict[str, set[str]] = {}
    for table in I21_SOURCE_COLUMNS:
        source_ids[table] = {
            str(row.get("id"))
            for row in source_snapshot.rows[table]
            if isinstance(row, Mapping) and isinstance(row.get("id"), int) and not isinstance(row.get("id"), bool)
        }

    target_ids: dict[tuple[str, str], int] = {}
    target_counts: dict[str, int] = {}
    cross_project: set[tuple[str, str]] = set()
    ambiguous: set[tuple[str, str]] = set()

    for source_table, model in _TARGET_MODELS.items():
        records = session.scalars(
            select(model).where(
                model.source_system == "datara_meta",
                model.source_table == source_table,
            )
        ).all()
        target_counts[source_table] = sum(record.project_id == project_id for record in records)
        candidates: dict[str, list[int]] = {}
        for record in records:
            if not record.source_id:
                continue
            identity = (source_table, record.source_id)
            if record.project_id != project_id:
                if record.source_id in source_ids[source_table]:
                    cross_project.add(identity)
                continue
            if record.source_id in source_ids[source_table]:
                candidates.setdefault(record.source_id, []).append(record.id)
        for source_id, record_ids in candidates.items():
            identity = (source_table, source_id)
            if len(record_ids) > 1:
                ambiguous.add(identity)
            elif identity not in cross_project:
                target_ids[identity] = record_ids[0]

    task_rule_rows = session.execute(
        select(QualityTaskRuleRecord, QualityTaskRecord.project_id)
        .join(QualityTaskRecord, QualityTaskRecord.id == QualityTaskRuleRecord.task_id)
        .where(QualityTaskRecord.project_id == project_id)
    ).all()
    target_counts["task_rule_links"] = len(task_rule_rows)
    target_task_links: dict[int, list[tuple[int, int]]] = {}
    for task_rule, linked_project_id in task_rule_rows:
        if linked_project_id == project_id:
            target_task_links.setdefault(task_rule.task_id, []).append(
                (task_rule.ordinal_position, task_rule.rule_definition_id)
            )

    run_query = (
        select(QualityRunLegacyDetailsRecord, QualityRunRecord.project_id)
        .outerjoin(QualityRunRecord, QualityRunRecord.id == QualityRunLegacyDetailsRecord.quality_run_id)
        .where(
            QualityRunLegacyDetailsRecord.source_system == "datara_meta",
            QualityRunLegacyDetailsRecord.source_table == "t_qc_run",
        )
    )
    run_rows = session.execute(run_query).all()
    target_counts["t_qc_run"] = sum(target_project_id == project_id for _details, target_project_id in run_rows)
    run_candidates: dict[str, list[int]] = {}
    for details, target_project_id in run_rows:
        if not details.source_id or details.source_id not in source_ids["t_qc_run"]:
            continue
        identity = ("t_qc_run", details.source_id)
        if target_project_id != project_id:
            cross_project.add(identity)
        else:
            run_candidates.setdefault(details.source_id, []).append(details.id)
    for source_id, record_ids in run_candidates.items():
        identity = ("t_qc_run", source_id)
        if len(record_ids) > 1:
            ambiguous.add(identity)
        elif identity not in cross_project:
            target_ids[identity] = record_ids[0]

    pending = frozenset(
        (table, str(row.get("id")))
        for table, table_rows in source_snapshot.rows.items()
        for row in table_rows
        if isinstance(row, Mapping) and row.get("id") is not None
    )
    mapping = map_i21_snapshot(
        source_snapshot,
        LegacyMappingContext(target_project_id=project_id, target_ids=target_ids, pending_identities=pending),
    )
    issues_by_identity: dict[tuple[str, str], set[str]] = {}
    for issue in mapping.mapping_issues:
        if issue.source_table and issue.source_id:
            issues_by_identity.setdefault((issue.source_table, issue.source_id), set()).add(issue.code)
    for task_bundle in mapping.tasks:
        task_id = task_bundle.task.target_id
        if task_id is None:
            continue
        expected_links = []
        unresolved_link = False
        for link in task_bundle.rule_links:
            if not isinstance(link.rule_definition_id, int):
                unresolved_link = True
                break
            expected_links.append((link.ordinal_position, link.rule_definition_id))
        identity = ("t_qc_task", task_bundle.task.source_id)
        actual_links = sorted(target_task_links.get(task_id, []))
        if unresolved_link:
            issues_by_identity.setdefault(identity, set()).add("target_task_rule_identity_unresolved")
        elif sorted(expected_links) != actual_links:
            issues_by_identity.setdefault(identity, set()).add("target_task_rule_links_mismatch")
    for identity in cross_project:
        issues_by_identity.setdefault(identity, set()).add("cross_project_target_identity")
    for identity in ambiguous:
        issues_by_identity.setdefault(identity, set()).add("ambiguous_target_identity")

    mapped_rows = [*mapping.rules, *(task.task for task in mapping.tasks), *mapping.runs,
                   *mapping.exceptions, *mapping.reports, *mapping.alarm_policies]
    row_by_identity = {(row.source_table, row.source_id): row for row in mapped_rows}
    entries: list[dict[str, object]] = []
    dispositions = {"new_identity_candidate": 0, "target_identity_match": 0, "blocked": 0}
    all_identities = {
        (table, source_id)
        for table, ids in source_ids.items()
        for source_id in ids
    }
    for identity in sorted(all_identities):
        row = row_by_identity.get(identity)
        issue_codes = issues_by_identity.get(identity, set())
        if identity in cross_project or identity in ambiguous:
            disposition = "blocked"
        elif issue_codes:
            disposition = "blocked"
        elif row is not None and row.target_id is not None:
            disposition = "target_identity_match"
        else:
            disposition = "new_identity_candidate"
        dispositions[disposition] += 1
        entries.append(
            {
                "source_table": identity[0],
                "source_id": identity[1],
                "disposition": disposition,
                "target_table": row.target_table if row is not None else _target_table(identity[0]),
                "target_id": row.target_id if row is not None and disposition == "target_identity_match" else None,
                "issues": sorted(issue_codes),
            }
        )
    for issue in mapping.mapping_issues:
        if not issue.source_table or not issue.source_id or (issue.source_table, issue.source_id) in all_identities:
            continue
        identity = (issue.source_table, issue.source_id)
        dispositions["blocked"] += 1
        entries.append(
            {
                "source_table": issue.source_table,
                "source_id": issue.source_id,
                "disposition": "blocked",
                "target_table": _target_table(issue.source_table),
                "target_id": None,
                "issues": sorted(issues_by_identity.get(identity, {issue.code})),
            }
        )

    target_payload = sorted((table, source_id, target_id) for (table, source_id), target_id in target_ids.items())
    target_digest = hashlib.sha256(
        json.dumps(target_payload, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    safe_issues = tuple(
        MappingIssue(issue.code, issue.source_table, issue.source_id, "") for issue in mapping.mapping_issues
    )
    safe_issues += tuple(
        MappingIssue("cross_project_target_identity", table, source_id, "")
        for table, source_id in sorted(cross_project)
    )
    safe_issues += tuple(
        MappingIssue("ambiguous_target_identity", table, source_id, "")
        for table, source_id in sorted(ambiguous)
    )
    return I21MappingPreview(
        project_id=project_id,
        captured_at=captured_at,
        source_schema=source_snapshot.schema,
        source_digest=source_snapshot.digest,
        target_digest=target_digest,
        source_counts=source_counts,
        target_counts=target_counts,
        dispositions=dispositions,
        entries=tuple(entries),
        issues=safe_issues,
        mapping=mapping,
    )


def _target_table(source_table: str) -> str:
    return {
        "t_qc_rule": "rebuild_governance_quality_rule_definition",
        "t_qc_task": "rebuild_governance_quality_task",
        "t_qc_run": "rebuild_governance_quality_run_legacy_details",
        "t_qc_exception": "rebuild_governance_quality_exception",
        "t_qc_report": "rebuild_governance_quality_report",
        "t_qc_alarm_policy": "rebuild_governance_quality_alarm_policy",
    }.get(source_table, "")
