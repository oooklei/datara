"""Pure, fail-closed I23 identity-link mapping without credential migration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import re
from typing import Mapping

from rebuild.governance.legacy_mapping import MappedLegacyRow, MappingIssue
from rebuild.governance.legacy_source_reader import I23_SOURCE_COLUMNS
from rebuild.identity.contracts import Role


_COLUMNS = set(I23_SOURCE_COLUMNS["t_user"][1])
_STATUSES = {"enabled", "disabled"}


@dataclass(frozen=True)
class I23IdentityTarget:
    """Explicit existing new-backend user selected for one legacy identity."""

    user_id: int
    username: str
    role: str
    status: str


@dataclass(frozen=True)
class LegacyI23MappingContext:
    target_users: Mapping[str, I23IdentityTarget] = field(default_factory=dict)
    mapping_record_ids: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class MappedI23Snapshot:
    rows: tuple[MappedLegacyRow, ...]
    mapping_issues: tuple[MappingIssue, ...]

    @property
    def ready_to_import(self) -> bool:
        return not self.mapping_issues and all(row.ready_to_import for row in self.rows)


def map_i23_snapshot(snapshot: object, context: LegacyI23MappingContext) -> MappedI23Snapshot:
    """Map legacy source identities to explicitly existing target users.

    The input contract excludes `user_pwd`; this function never accepts or
    emits credential material and never creates a target user or project link.
    """

    source_rows = getattr(snapshot, "rows", None)
    if (
        getattr(snapshot, "schema", None) != "datara_meta"
        or not isinstance(source_rows, Mapping)
        or set(source_rows) != {"t_user"}
        or not isinstance(source_rows["t_user"], (tuple, list))
    ):
        return _empty(MappingIssue("invalid_i23_snapshot_shape", "t_user", "", "expected complete t_user snapshot"))

    issues = _validate_context(context)
    if issues:
        return _empty(*issues)

    output: list[MappedLegacyRow] = []
    source_ids: set[str] = set()
    source_usernames: set[str] = set()
    target_user_bindings: set[int] = set()
    for source in source_rows["t_user"]:
        if not isinstance(source, Mapping):
            issues.append(MappingIssue("invalid_source_row", "t_user", "", "row must be a mapping"))
            continue
        source_id = _identity(source.get("id"))
        if source_id is None:
            issues.append(MappingIssue("invalid_source_identity", "t_user", "", "id must be a positive integer"))
            continue
        if source_id in source_ids:
            issues.append(MappingIssue("duplicate_source_identity", "t_user", source_id, "duplicate source id"))
            continue
        source_ids.add(source_id)
        if set(source) != _COLUMNS:
            issues.append(MappingIssue("incomplete_source_row", "t_user", source_id, "column set differs from reader"))
            continue

        local: list[MappingIssue] = []
        username = _text(source.get("user_name"), 64, source_id, "user_name", local)
        source_role = _enum(source.get("user_role"), {role.value for role in Role}, source_id, "role", local)
        state = _enum(source.get("state"), _STATUSES, source_id, "state", local)
        source_created_at = _datetime(source.get("create_time"), source_id, "create_time", local)
        source_updated_at = _datetime(source.get("update_time"), source_id, "update_time", local)

        if username:
            if username in source_usernames:
                local.append(MappingIssue("duplicate_source_username", "t_user", source_id, username))
            source_usernames.add(username)

        target = context.target_users.get(source_id)
        if target is None:
            local.append(
                MappingIssue("unresolved_target_user", "t_user", source_id, "explicit target user id required")
            )
        else:
            if not _positive_int(target.user_id):
                local.append(MappingIssue("invalid_target_user_id", "t_user", source_id, str(target.user_id)))
            if target.user_id in target_user_bindings:
                local.append(MappingIssue("duplicate_target_user_binding", "t_user", source_id, str(target.user_id)))
            target_user_bindings.add(target.user_id)
            if username != target.username:
                local.append(MappingIssue("target_username_mismatch", "t_user", source_id, str(target.user_id)))
            if source_role != target.role:
                local.append(MappingIssue("target_role_mismatch", "t_user", source_id, str(target.user_id)))
            if state != target.status:
                local.append(MappingIssue("target_status_mismatch", "t_user", source_id, str(target.user_id)))

        target_id = context.mapping_record_ids.get(source_id)
        if target_id is not None and not _positive_int(target_id):
            local.append(MappingIssue("invalid_mapping_record_id", "t_user", source_id, str(target_id)))
        row = MappedLegacyRow(
            source_system="datara_meta",
            source_table="t_user",
            source_id=source_id,
            target_table="rebuild_governance_legacy_identity_mapping",
            target_id=target_id,
            values={
                "user_id": target.user_id if target is not None else None,
                "source_username": username or "",
                "source_role": source_role or "",
                "mapped_role": source_role or "",
                "mapping_status": "mapped",
                "source_created_at": source_created_at,
                "source_updated_at": source_updated_at,
            },
            mapping_issues=tuple(local),
        )
        issues.extend(local)
        output.append(row)

    return MappedI23Snapshot(tuple(output), tuple(dict.fromkeys(issues)))


def _validate_context(context: LegacyI23MappingContext) -> list[MappingIssue]:
    issues: list[MappingIssue] = []
    for source_id, target in context.target_users.items():
        if _identity_key(source_id) is None or not isinstance(target, I23IdentityTarget):
            issues.append(
                MappingIssue("invalid_target_user_mapping", "t_user", str(source_id), "invalid source key/value")
            )
            continue
        if not _positive_int(target.user_id):
            issues.append(MappingIssue("invalid_target_user_id", "t_user", source_id, str(target.user_id)))
        _text(target.username, 64, source_id, "target.username", issues)
        if target.role not in {role.value for role in Role}:
            issues.append(MappingIssue("unsupported_target_role", "t_user", source_id, str(target.role)))
        if target.status not in _STATUSES:
            issues.append(MappingIssue("unsupported_target_status", "t_user", source_id, str(target.status)))
    for source_id, target_id in context.mapping_record_ids.items():
        if _identity_key(source_id) is None or not _positive_int(target_id):
            issues.append(MappingIssue("invalid_mapping_record_id", "t_user", str(source_id), str(target_id)))
    return issues


def _identity(value: object) -> str | None:
    if not _positive_int(value):
        return None
    return str(value)


def _identity_key(value: object) -> str | None:
    if isinstance(value, str) and value.isdecimal() and int(value) > 0:
        return value
    return _identity(value)


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _text(value: object, limit: int, source_id: str, name: str, issues: list[MappingIssue]) -> str | None:
    if not isinstance(value, str):
        issues.append(MappingIssue("invalid_source_value", "t_user", source_id, f"{name} must be text"))
        return None
    if not value or len(value) > limit:
        issues.append(MappingIssue("invalid_source_value", "t_user", source_id, f"{name} is empty or too long"))
        return None
    return value


def _enum(value: object, allowed: set[str], source_id: str, name: str, issues: list[MappingIssue]) -> str | None:
    if not isinstance(value, str) or value not in allowed:
        issues.append(MappingIssue(f"unsupported_legacy_{name}", "t_user", source_id, str(value)))
        return None
    return value


def _datetime(value: object, source_id: str, name: str, issues: list[MappingIssue]) -> datetime | None:
    if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", value) is None:
        issues.append(MappingIssue("invalid_source_value", "t_user", source_id, f"{name} is not a datetime"))
        return None
    try:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            parsed = datetime.fromisoformat(value)
        else:
            parsed = None
    except ValueError:
        parsed = None
    if parsed is None:
        issues.append(MappingIssue("invalid_source_value", "t_user", source_id, f"{name} is not a datetime"))
        return None
    if parsed.tzinfo is not None:
        issues.append(MappingIssue("timezone_aware_source_datetime", "t_user", source_id, name))
        return None
    return parsed


def _empty(*issues: MappingIssue) -> MappedI23Snapshot:
    return MappedI23Snapshot((), tuple(issues))
