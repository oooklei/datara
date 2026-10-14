"""Deterministic, database-independent planning for I18 carry-forward batches."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping

from rebuild.governance.legacy_mapping import (
    MappedLegacyRow,
    MappingIssue,
    TargetIdentityReference,
    validate_i18_mapping_graph,
)

SourceIdentity = tuple[str, str]

_IMPORT_ORDER = {
    "t_biz_domain": 10,
    "t_dw_layer": 20,
    "t_engine_type": 30,
    "t_dw_model": 40,
    "t_dw_model_field": 50,
    "t_dw_model_relation": 60,
    "t_dw_model_version": 70,
}


@dataclass(frozen=True)
class DryRunEntry:
    source_table: str
    source_id: str
    disposition: str
    fingerprint: str
    issues: tuple[MappingIssue, ...] = ()


@dataclass(frozen=True)
class I18DryRunPlan:
    project_id: int
    source_count: int
    counts: Mapping[str, int]
    entries: tuple[DryRunEntry, ...]
    import_order: tuple[SourceIdentity, ...]
    blocking_issues: tuple[MappingIssue, ...]
    snapshot_digest: str
    snapshot_captured_at: datetime

    @property
    def ready_to_import(self) -> bool:
        return self.counts["blocked"] == 0 and self.counts["conflict"] == 0


@dataclass(frozen=True)
class I18TargetSnapshot:
    project_id: int
    captured_at: datetime
    digest: str
    row_fingerprints: Mapping[SourceIdentity, str]
    target_ids: Mapping[SourceIdentity, int]
    model_fields: Mapping[int, frozenset[str]]
    unique_key_owners: Mapping[tuple[object, ...], SourceIdentity]


def semantic_fingerprint(row: MappedLegacyRow) -> str:
    """Hash mapped business semantics independent of dict ordering and target IDs."""

    canonical = {
        "target_table": row.target_table,
        "values": _canonicalize(row.values),
        "child_rows": _canonicalize(row.child_rows),
    }
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_i18_dry_run_plan(
    rows: list[MappedLegacyRow],
    *,
    project_id: int,
    snapshot: I18TargetSnapshot,
) -> I18DryRunPlan:
    """Classify rows only against a project-bound, caller-supplied read-only snapshot."""

    if snapshot.captured_at.tzinfo is None:
        raise ValueError("target snapshot captured_at must be timezone-aware")
    if len(snapshot.digest) != 64 or any(char not in "0123456789abcdef" for char in snapshot.digest.lower()):
        raise ValueError("target snapshot digest must be a SHA-256 hex string")
    if set(snapshot.row_fingerprints) - set(snapshot.target_ids):
        raise ValueError("every existing source identity in snapshot must include its target ID")
    issues = list(validate_i18_mapping_graph(rows, snapshot.model_fields))
    issue_index: dict[SourceIdentity, list[MappingIssue]] = {}
    for issue in issues:
        issue_index.setdefault((issue.source_table, issue.source_id), []).append(issue)

    entries: list[DryRunEntry] = []
    for row in rows:
        identity = (row.source_table, row.source_id)
        row_issues = list(issue_index.get(identity, ()))
        for value in row.values.values():
            if isinstance(value, TargetIdentityReference) and (
                value.source_table,
                value.source_id,
            ) in snapshot.target_ids:
                reference_issue = MappingIssue(
                    "existing_identity_must_resolve_to_target_id",
                    row.source_table,
                    row.source_id,
                    f"{value.source_table}:{value.source_id}",
                )
                row_issues.append(reference_issue)
                issues.append(reference_issue)
        if snapshot.project_id != project_id:
            snapshot_issue = MappingIssue(
                "target_snapshot_project_mismatch",
                row.source_table,
                row.source_id,
                f"snapshot={snapshot.project_id}, requested={project_id}",
            )
            row_issues.append(snapshot_issue)
            issues.append(snapshot_issue)
        mapped_project_id = row.values.get("project_id")
        if mapped_project_id is not None and mapped_project_id != project_id:
            scope_issue = MappingIssue(
                "project_scope_mismatch",
                row.source_table,
                row.source_id,
                f"mapped={mapped_project_id}, requested={project_id}",
            )
            row_issues.append(scope_issue)
            issues.append(scope_issue)
        fingerprint = semantic_fingerprint(row)
        unique_key = _unique_key(row)
        key_owner = snapshot.unique_key_owners.get(unique_key) if unique_key is not None else None
        key_issue = None
        if key_owner is not None and key_owner != identity:
            key_issue = MappingIssue(
                "target_business_key_collision",
                row.source_table,
                row.source_id,
                f"occupied by {key_owner[0]}:{key_owner[1]}",
            )
            issues.append(key_issue)
        if row_issues:
            disposition = "blocked"
        elif key_issue is not None:
            disposition = "conflict"
        elif identity not in snapshot.row_fingerprints:
            disposition = "create"
        elif snapshot.row_fingerprints[identity] == fingerprint:
            disposition = "unchanged"
        else:
            disposition = "conflict"
        entries.append(
            DryRunEntry(
                row.source_table,
                row.source_id,
                disposition,
                fingerprint,
                tuple(row_issues + ([key_issue] if key_issue is not None else [])),
            )
        )

    dispositions = {
        (entry.source_table, entry.source_id): entry.disposition
        for entry in entries
    }
    source_rows = {(row.source_table, row.source_id): row for row in rows}
    for index, entry in enumerate(entries):
        if entry.disposition != "create":
            continue
        source_row = source_rows[(entry.source_table, entry.source_id)]
        dependency_issues = []
        for value in source_row.values.values():
            if not isinstance(value, TargetIdentityReference):
                continue
            parent_identity = (value.source_table, value.source_id)
            parent_disposition = dispositions.get(parent_identity)
            if parent_disposition in {"blocked", "conflict"}:
                dependency_issues.append(
                    MappingIssue(
                        "dependency_not_importable",
                        entry.source_table,
                        entry.source_id,
                        f"{parent_identity[0]}:{parent_identity[1]} ({parent_disposition})",
                    )
                )
        if dependency_issues:
            issues.extend(dependency_issues)
            entries[index] = DryRunEntry(
                entry.source_table,
                entry.source_id,
                "blocked",
                entry.fingerprint,
                entry.issues + tuple(dependency_issues),
            )

    counts = {
        disposition: sum(entry.disposition == disposition for entry in entries)
        for disposition in ("create", "unchanged", "conflict", "blocked")
    }
    import_order = tuple(
        (entry.source_table, entry.source_id)
        for entry in sorted(
            (entry for entry in entries if entry.disposition == "create"),
            key=lambda entry: (_IMPORT_ORDER.get(entry.source_table, 999), entry.source_id),
        )
    )
    return I18DryRunPlan(
        project_id=project_id,
        source_count=len(rows),
        counts=counts,
        entries=tuple(entries),
        import_order=import_order,
        blocking_issues=tuple(issues),
        snapshot_digest=snapshot.digest,
        snapshot_captured_at=snapshot.captured_at,
    )


def _canonicalize(value: object) -> object:
    if isinstance(value, TargetIdentityReference):
        return {"source_table": value.source_table, "source_id": value.source_id}
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonicalize(item) for item in value]
    return value


def _unique_key(row: MappedLegacyRow) -> tuple[object, ...] | None:
    values = row.values
    project_id = values.get("project_id")
    if row.source_table == "t_biz_domain":
        return ("domain", project_id, values.get("name"))
    if row.source_table == "t_dw_layer":
        return ("layer", project_id, values.get("code"))
    if row.source_table == "t_engine_type":
        return ("engine", project_id, values.get("name"))
    if row.source_table == "t_dw_model":
        return ("model", project_id, values.get("code"))
    if row.source_table == "t_dw_model_field" and isinstance(values.get("model_id"), int):
        return ("model_field", values["model_id"], values.get("field_name"))
    if row.source_table == "t_dw_model_version" and isinstance(values.get("model_id"), int):
        return ("model_version", values["model_id"], values.get("version"))
    return None
