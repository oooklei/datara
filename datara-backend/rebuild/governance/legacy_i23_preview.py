"""Read-only identity mapping preview for explicitly authorized legacy I23 reads."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Mapping
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from rebuild.governance.legacy_i23_mapping import (
    I23IdentityTarget,
    LegacyI23MappingContext,
    map_i23_snapshot,
)
from rebuild.governance.legacy_mapping import MappingIssue
from rebuild.governance.legacy_source_reader import I23_SOURCE_COLUMNS
from rebuild.governance.models import LegacyIdentityMappingRecord
from rebuild.identity.models import UserRecord


MAX_I23_PREVIEW_ROWS = 1_000
MAX_I23_TARGET_ROWS = 2_001


def build_i23_identity_preview(
    session: Session,
    source_snapshot: object,
    selections: Mapping[str, int],
    *,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    """Build a non-persistent preview from the approved six-column source snapshot."""
    rows = getattr(source_snapshot, "rows", None)
    counts = getattr(source_snapshot, "counts", None)
    if (
        getattr(source_snapshot, "schema", None) != "datara_meta"
        or not isinstance(rows, Mapping)
        or set(rows) != {"t_user"}
        or not isinstance(rows["t_user"], (tuple, list))
        or not isinstance(counts, Mapping)
        or counts.get("t_user") != len(rows["t_user"])
        or len(rows["t_user"]) > MAX_I23_PREVIEW_ROWS
    ):
        raise ValueError("invalid or oversized I23 source snapshot")

    source_rows = rows["t_user"]
    expected_columns = set(I23_SOURCE_COLUMNS["t_user"][1])
    if any(not isinstance(row, Mapping) or set(row) != expected_columns for row in source_rows):
        raise ValueError("I23 source row columns differ from the fixed allowlist")
    source_ids = [str(row.get("id")) for row in source_rows if isinstance(row, Mapping)]
    if len(source_ids) != len(source_rows) or len(set(source_ids)) != len(source_ids):
        raise ValueError("invalid or duplicate I23 source identity")
    if any(not source_id.isdecimal() or int(source_id) <= 0 for source_id in source_ids):
        raise ValueError("invalid I23 source identity")
    source_captured_at = getattr(source_snapshot, "captured_at", None)
    if not isinstance(source_captured_at, datetime) or source_captured_at.tzinfo is None:
        raise ValueError("I23 source snapshot timestamp must be timezone-aware")
    if set(selections) - set(source_ids):
        raise ValueError("selection references an identity outside the current source snapshot")
    if any(not source_id.isdecimal() or int(source_id) <= 0 for source_id in selections):
        raise ValueError("invalid I23 source selection key")
    if any(
        isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0 for user_id in selections.values()
    ):
        raise ValueError("invalid I23 target user selection")

    source_names = {
        row.get("user_name")
        for row in source_rows
        if isinstance(row, Mapping) and isinstance(row.get("user_name"), str)
    }
    source_id_set = set(source_ids)
    identity_rows = (
        session.execute(
            select(
                LegacyIdentityMappingRecord.id,
                LegacyIdentityMappingRecord.user_id,
                LegacyIdentityMappingRecord.source_id,
                LegacyIdentityMappingRecord.source_username,
                LegacyIdentityMappingRecord.source_role,
                LegacyIdentityMappingRecord.mapped_role,
                LegacyIdentityMappingRecord.mapping_status,
            ).where(
                LegacyIdentityMappingRecord.source_system == "datara_meta",
                LegacyIdentityMappingRecord.source_table == "t_user",
                LegacyIdentityMappingRecord.source_id.in_(source_id_set),
            )
        ).all()
        if source_id_set
        else []
    )

    identity_by_source: dict[str, object] = {}
    for record in identity_rows:
        source_id = str(record.source_id)
        if source_id in identity_by_source:
            raise ValueError("duplicate target I23 source identity")
        identity_by_source[source_id] = record

    requested_user_ids = set(selections.values())
    existing_user_ids = {record.user_id for record in identity_rows}
    user_filters = []
    if source_names:
        user_filters.append(UserRecord.username.in_(source_names))
    user_ids = requested_user_ids | existing_user_ids
    if user_ids:
        user_filters.append(UserRecord.id.in_(user_ids))
    if user_filters:
        target_rows = session.execute(
            select(UserRecord.id, UserRecord.username, UserRecord.role, UserRecord.status)
            .where(or_(*user_filters))
            .order_by(UserRecord.id)
            .limit(MAX_I23_TARGET_ROWS)
        ).all()
    else:
        target_rows = []
    if len(target_rows) >= MAX_I23_TARGET_ROWS:
        raise ValueError("I23 target candidate set exceeds the configured safety limit")
    users_by_id = {
        row.id: I23IdentityTarget(user_id=row.id, username=row.username, role=row.role, status=row.status)
        for row in target_rows
    }

    target_users: dict[str, I23IdentityTarget] = {}
    mapping_record_ids: dict[str, int] = {}
    for source_id in source_ids:
        existing = identity_by_source.get(source_id)
        selected_id = selections.get(source_id)
        if selected_id is None and existing is not None:
            selected_id = existing.user_id
        if selected_id is not None and selected_id in users_by_id:
            target_users[source_id] = users_by_id[selected_id]
        if existing is not None:
            mapping_record_ids[source_id] = existing.id

    mapped = map_i23_snapshot(
        source_snapshot,
        LegacyI23MappingContext(target_users=target_users, mapping_record_ids=mapping_record_ids),
    )
    mapped_by_source = {row.source_id: row for row in mapped.rows}
    source_by_id = {str(row["id"]): row for row in source_rows}
    entries: list[dict[str, object]] = []
    issue_items: list[dict[str, object]] = []
    dispositions = {
        "identity_candidate": 0,
        "target_identity_match": 0,
        "unresolved": 0,
        "blocked": 0,
    }

    for source_id in source_ids:
        source = source_by_id[source_id]
        mapped_row = mapped_by_source.get(source_id)
        local_issues = list(mapped_row.mapping_issues if mapped_row else ())
        existing = identity_by_source.get(source_id)
        selected_id = selections.get(source_id)
        if selected_id is None and existing is not None:
            selected_id = existing.user_id
        selected_target = users_by_id.get(selected_id) if selected_id is not None else None
        if selected_id is not None and selected_target is None:
            local_issues.append(MappingIssue("selected_target_user_not_found", "t_user", source_id, str(selected_id)))
        if existing is not None:
            if existing.source_username != source.get("user_name"):
                local_issues.append(
                    MappingIssue(
                        "existing_identity_source_name_mismatch", "t_user", source_id, "stored mapping username differs"
                    )
                )
            if existing.source_role != source.get("user_role"):
                local_issues.append(
                    MappingIssue(
                        "existing_identity_source_role_mismatch", "t_user", source_id, "stored mapping role differs"
                    )
                )
            if existing.mapping_status != "mapped":
                local_issues.append(
                    MappingIssue(
                        "existing_identity_mapping_not_mapped", "t_user", source_id, "stored mapping is not active"
                    )
                )
            if source_id in selections and selections[source_id] != existing.user_id:
                local_issues.append(
                    MappingIssue(
                        "selection_conflicts_with_existing_mapping",
                        "t_user",
                        source_id,
                        "preview cannot change an existing identity mapping",
                    )
                )
            if selected_target is not None and existing.mapped_role != selected_target.role:
                local_issues.append(
                    MappingIssue(
                        "existing_identity_target_role_mismatch", "t_user", source_id, "stored target role differs"
                    )
                )

        if local_issues:
            disposition = "blocked"
        elif selected_target is None:
            disposition = "unresolved"
        elif existing is not None:
            disposition = "target_identity_match"
        else:
            disposition = "identity_candidate"
        dispositions[disposition] += 1
        existing_user_id = existing.user_id if existing is not None else None
        candidates = [
            {
                "user": user,
                "candidate_type": "same_name" if user.username == source.get("user_name") else "existing_mapping",
            }
            for user in users_by_id.values()
            if user.username == source.get("user_name") or user.user_id == existing_user_id
        ]
        entries.append(
            {
                "source_id": source_id,
                "source_username": source.get("user_name"),
                "source_role": source.get("user_role"),
                "source_status": source.get("state"),
                "source_created_at": _iso(source.get("create_time")),
                "source_updated_at": _iso(source.get("update_time")),
                "target_candidates": [
                    {
                        "user_id": candidate["user"].user_id,
                        "username": candidate["user"].username,
                        "role": candidate["user"].role,
                        "status": candidate["user"].status,
                        "candidate_type": candidate["candidate_type"],
                    }
                    for candidate in candidates
                ],
                "selected_target_user_id": selected_id,
                "existing_mapping_id": existing.id if existing is not None else None,
                "disposition": disposition,
                "issues": [
                    {"code": issue.code, "source_id": issue.source_id, "detail": issue.detail} for issue in local_issues
                ],
            }
        )
        issue_items.extend(
            {"code": issue.code, "source_id": issue.source_id, "detail": issue.detail} for issue in local_issues
        )

    target_identity = {
        "users": sorted((user_id, user.username, user.role, user.status) for user_id, user in users_by_id.items()),
        "source_mappings": sorted(
            (
                str(record.source_id),
                record.id,
                record.user_id,
                record.source_username,
                record.source_role,
                record.mapped_role,
                record.mapping_status,
            )
            for record in identity_rows
        ),
    }
    target_digest = hashlib.sha256(
        json.dumps(target_identity, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    captured_at = captured_at or datetime.now(ZoneInfo("Asia/Shanghai"))
    if captured_at.tzinfo is None:
        raise ValueError("captured_at must be timezone-aware")
    return {
        "source": {
            "schema": "datara_meta",
            "captured_at": _iso(source_captured_at),
            "digest": getattr(source_snapshot, "digest", ""),
            "counts": {"t_user": len(source_rows)},
        },
        "target": {
            "captured_at": captured_at.isoformat(),
            "identity_digest": target_digest,
            "candidate_users": len(users_by_id),
            "existing_identity_mappings": len(identity_rows),
        },
        "preview": {
            "counts": dispositions,
            "entries": entries,
            "issues": issue_items,
            "parity_verified": False,
            "import_enabled": False,
        },
    }


def _iso(value: object) -> str | None:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value if isinstance(value, str) else None
