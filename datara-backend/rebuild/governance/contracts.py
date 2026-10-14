from __future__ import annotations

from enum import StrEnum
import re

from rebuild.identity.contracts import Permission, Role, authorize


class MigrationStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


_MIGRATION_TRANSITIONS: dict[MigrationStatus, frozenset[MigrationStatus]] = {
    MigrationStatus.PLANNED: frozenset({MigrationStatus.RUNNING, MigrationStatus.FAILED}),
    MigrationStatus.RUNNING: frozenset(
        {MigrationStatus.COMPLETED, MigrationStatus.FAILED, MigrationStatus.ROLLED_BACK}
    ),
    MigrationStatus.FAILED: frozenset({MigrationStatus.ROLLED_BACK}),
    MigrationStatus.COMPLETED: frozenset(),
    MigrationStatus.ROLLED_BACK: frozenset(),
}


def is_sha256_digest(value: str) -> bool:
    return re.fullmatch(r"[0-9a-f]{64}", value) is not None


def migration_replay_decision(existing_payload_sha256: str | None, incoming_payload_sha256: str) -> str:
    if not is_sha256_digest(incoming_payload_sha256):
        raise ValueError("payload_sha256 must be a lowercase SHA-256 digest")
    if existing_payload_sha256 is None:
        return "new"
    if not is_sha256_digest(existing_payload_sha256):
        raise ValueError("stored payload_sha256 is invalid")
    return "replay" if existing_payload_sha256 == incoming_payload_sha256 else "conflict"


def migration_transition_allowed(current: MigrationStatus | str, target: MigrationStatus | str) -> bool:
    try:
        current_status = MigrationStatus(current)
        target_status = MigrationStatus(target)
    except ValueError:
        return False
    return target_status in _MIGRATION_TRANSITIONS[current_status]


def authorize_project_access(
    *,
    actor_id: int,
    owner_id: int,
    global_role: Role | str,
    member_role: Role | str | None,
    permission: Permission | str,
) -> bool:
    try:
        resolved_global_role = Role(global_role)
        resolved_permission = Permission(permission)
    except ValueError:
        return False
    if resolved_global_role is Role.ADMIN:
        return True
    if actor_id != owner_id and member_role is None:
        return False
    effective_role = resolved_global_role if actor_id == owner_id else member_role
    return authorize(effective_role, resolved_permission)
