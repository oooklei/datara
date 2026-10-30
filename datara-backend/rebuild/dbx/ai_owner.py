"""Owner-scoped view of dbx's single-user AI configuration store."""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from rebuild.dbx import DbxError
from rebuild.dbx.access import DbxObjectAccess
from rebuild.dbx.models import DbxAiUserStateRecord, DbxObjectOwnershipRecord


KIND = "ai-config"
SHARED_REF = "datara-shared-ai-config:"
_SECRET_FIELDS = {
    "apiKey", "customHeaders", "proxyUrl", "codexCliEnv", "claudeCodeCliEnv",
    "piAgentCliEnv", "opencodeCliEnv", "cursorCliEnv", "grokCliEnv",
    "codebuddyCliEnv", "qoderCliEnv",
}
_RUNTIME_FIELDS = {"model", "runtimeEffort", "maxOutputTokens", "enableThinking", "reasoningLevel"}


def valid_config_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value not in {".", ".."}
        and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value) is not None
    )


def config_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(
        not isinstance(row, dict) or not valid_config_id(row.get("id")) for row in value
    ):
        raise DbxError()
    return value


def visible_configs(
    session: Session, rows: list[dict[str, Any]], *, project_id: int, user_id: int, admin: bool,
) -> list[dict[str, Any]]:
    access = DbxObjectAccess(session)
    visible = access.visible_ids(kind=KIND, project_id=project_id, user_id=user_id, is_admin=admin)
    state = session.get(DbxAiUserStateRecord, (project_id, user_id))
    result = []
    for row in rows:
        owner = access.get(KIND, row["id"])
        if not admin and (row["id"] not in visible or owner is None or owner.project_id != project_id):
            continue
        item = dict(row)
        if owner is not None and owner.owner_id != user_id and not admin:
            item = redact_shared_config(item)
        item["isDefault"] = state is not None and state.default_config_id == row["id"]
        result.append(item)
    if result and not any(item["isDefault"] for item in result):
        result[0]["isDefault"] = True
    return result


def redact_shared_config(row: dict[str, Any]) -> dict[str, Any]:
    item = {key: value for key, value in row.items() if key not in _SECRET_FIELDS}
    item["apiKey"] = SHARED_REF + row["id"]
    item["customHeaders"] = {}
    item["proxyUrl"] = ""
    item["endpoint"] = "https://shared-config.invalid"
    for key in tuple(item):
        if key.endswith("CliPath") or key.endswith("CliEnv"):
            item.pop(key)
    return item


def user_state(session: Session, project_id: int, user_id: int) -> DbxAiUserStateRecord:
    state = session.get(DbxAiUserStateRecord, (project_id, user_id))
    if state is None:
        state = DbxAiUserStateRecord(project_id=project_id, user_id=user_id)
        session.add(state)
    return state


def visible_config_ids(
    session: Session, *, project_id: int, user_id: int, admin: bool, rows: list[dict[str, Any]],
) -> set[str]:
    if admin:
        return {row["id"] for row in rows}
    access = DbxObjectAccess(session)
    ids = access.visible_ids(kind=KIND, project_id=project_id, user_id=user_id, is_admin=False)
    return ids & {row["id"] for row in rows}


def resolve_config(
    session: Session, rows: list[dict[str, Any]], supplied: dict[str, Any], *,
    project_id: int, user_id: int, admin: bool,
) -> dict[str, Any] | None:
    """Resolve an authorized saved config, then apply only safe runtime choices."""
    visible = visible_config_ids(session, project_id=project_id, user_id=user_id, admin=admin, rows=rows)
    by_id = {row["id"]: row for row in rows if row["id"] in visible}
    marker = supplied.get("apiKey")
    config_id = (
        marker[len(SHARED_REF):]
        if isinstance(marker, str) and marker.startswith(SHARED_REF)
        else supplied.get("id")
    )
    if isinstance(config_id, str) and config_id in by_id:
        source = by_id[config_id]
    elif isinstance(marker, str) and marker.startswith(SHARED_REF):
        return None
    else:
        matches = [
            row for row in by_id.values()
            if row.get("apiKey", "") == supplied.get("apiKey", "")
            and row.get("endpoint") == supplied.get("endpoint")
            and row.get("provider") == supplied.get("provider")
        ]
        if len(matches) != 1:
            return None
        source = matches[0]
    resolved = {key: value for key, value in source.items() if key not in {"id", "name", "isDefault"}}
    for key in _RUNTIME_FIELDS:
        if key in supplied:
            resolved[key] = supplied[key]
    return resolved


def selection_from_state(session: Session, project_id: int, user_id: int) -> dict[str, Any] | None:
    state = session.get(DbxAiUserStateRecord, (project_id, user_id))
    if state is None or state.chat_selection_json is None:
        return None
    return json.loads(state.chat_selection_json)


def owned_config(session: Session, config_id: str, *, project_id: int, user_id: int, admin: bool) -> bool:
    owner: DbxObjectOwnershipRecord | None = DbxObjectAccess(session).get(KIND, config_id)
    return owner is not None and owner.project_id == project_id and (admin or owner.owner_id == user_id)
