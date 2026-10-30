"""Owner checks for dbx IDE requests before they reach the single-user dbx API.

This module is deliberately independent of HTTP routing so the policy can be
tested before switching the iframe proxy to the datara gateway.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class DbxIdeForbidden(PermissionError):
    pass


_PUBLIC_CONNECTION_FIELDS = frozenset({
    "id", "name", "db_type", "host", "port", "database", "username",
    "color", "driver_label", "driver_profile", "jdbc_driver_class", "jdbc_driver_paths",
    "ssl", "sysdba", "idle_disconnect_secs", "save_password", "connect_timeout_secs",
    "idle_timeout_secs", "query_timeout_secs", "keepalive_interval_secs",
    "manual_transaction_timeout_secs",
})
_CONNECTION_ID_KEYS = frozenset({
    "connectionId", "connection_id", "sourceConnectionId", "targetConnectionId",
    "source_connection_id", "target_connection_id",
})
_CONNECTION_IDS_KEYS = frozenset({"connectionIds", "connection_ids", "removedIds", "removed_ids"})


def referenced_connection_ids(value: Any) -> set[str]:
    """Find explicit dbx connection IDs in nested JSON request frames."""
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in _CONNECTION_ID_KEYS and isinstance(item, str) and item:
                found.add(item)
            elif key in _CONNECTION_IDS_KEYS and isinstance(item, list):
                found.update(candidate for candidate in item if isinstance(candidate, str) and candidate)
            elif key == "config" and isinstance(item, Mapping):
                candidate = item.get("id")
                if isinstance(candidate, str) and candidate:
                    found.add(candidate)
            elif key == "configs" and isinstance(item, list):
                found.update(
                    candidate["id"] for candidate in item
                    if isinstance(candidate, Mapping) and isinstance(candidate.get("id"), str) and candidate["id"]
                )
            found.update(referenced_connection_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.update(referenced_connection_ids(item))
    return found


def require_visible(value: Any, visible_ids: set[str]) -> None:
    denied = referenced_connection_ids(value) - visible_ids
    if denied:
        raise DbxIdeForbidden("connection not visible")


def safe_connection_list(items: Sequence[dict[str, Any]], visible_ids: set[str]) -> list[dict[str, Any]]:
    """Return only owner-visible connection metadata, never stored credentials."""
    result: list[dict[str, Any]] = []
    for item in items:
        if str(item.get("id")) not in visible_ids:
            continue
        public = {
            key: value for key, value in item.items()
            if key in _PUBLIC_CONNECTION_FIELDS and (
                key != "ssl" or isinstance(value, bool)
            )
        }
        # dbx's current UI expects a password key even when credentials are
        # held server-side; its real value must never reach the iframe.
        public["password"] = ""
        result.append(public)
    return result


def merge_connection_save_payload(payload: dict[str, Any], stored: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    """Keep fields hidden by the IDE gateway when editing a saved connection.

    DBX treats each config in connection/save as a full replacement. The browser
    sees a redacted copy, so sending it unchanged would erase credentials and
    advanced settings already present in DBX.
    """
    configs = payload.get("configs", [])
    merged: list[dict[str, Any]] = []
    for config in configs:
        existing = stored.get(config["id"])
        if existing is None:
            merged.append(config)
            continue
        combined = {**existing, **config}
        if not config.get("password"):
            combined["password"] = existing.get("password", "")
        for key in existing.keys() - _PUBLIC_CONNECTION_FIELDS - {"password"}:
            if config.get(key) in (None, "", [], {}):
                combined[key] = existing[key]
        merged.append(combined)
    return {**payload, "configs": merged}


def scoped_history_search(payload: dict[str, Any], visible_ids: set[str]) -> dict[str, Any] | None:
    """Force dbx history filters to owner-visible connection IDs.

    dbx interprets empty connection and database filter arrays as *all* history,
    so return ``None`` when the caller has no eligible IDs. Name-only legacy
    filters cannot establish ownership and are deliberately excluded.
    """
    connections = payload.get("connections", [])
    databases = payload.get("databases", [])
    if not isinstance(connections, list) or not isinstance(databases, list):
        raise DbxIdeForbidden("invalid history filter")
    filters = connections + databases
    if any(not isinstance(item, Mapping) for item in filters):
        raise DbxIdeForbidden("invalid history filter")
    if any(item.get("connection_name") and not item.get("connection_id") for item in filters):
        return None
    requested = {
        item["connection_id"] for item in filters
        if isinstance(item.get("connection_id"), str) and item["connection_id"]
    }
    allowed = visible_ids & requested if filters else visible_ids
    if not allowed:
        return None
    safe_databases = [
        item for item in databases
        if item.get("connection_id") in allowed and isinstance(item.get("database"), str)
    ]
    return {
        **payload,
        "connections": [{"connection_id": connection_id} for connection_id in sorted(allowed)],
        "databases": safe_databases,
    }


def saved_sql_descendants(library: Mapping[str, Any], folder_id: str) -> set[tuple[str, str]]:
    """Enumerate the objects dbx deletes when a folder is removed recursively."""
    folders = library.get("folders", [])
    files = library.get("files", [])
    if not isinstance(folders, list) or not isinstance(files, list):
        raise DbxIdeForbidden("invalid SQL library")
    result: set[tuple[str, str]] = set()
    pending = [folder_id]
    while pending:
        current = pending.pop()
        if ("sql-folder", current) in result:
            continue
        result.add(("sql-folder", current))
        pending.extend(
            child["id"] for child in folders
            if isinstance(child, Mapping) and isinstance(child.get("id"), str)
            and child.get("parentFolderId") == current
        )
        result.update(
            ("sql-file", child["id"]) for child in files
            if isinstance(child, Mapping) and isinstance(child.get("id"), str)
            and child.get("folderId") == current
        )
    return result


def canonical_connect_payload(payload: dict[str, Any], stored: Mapping[str, dict[str, Any]], visible_ids: set[str]) -> dict[str, Any]:
    """Replace browser-supplied connection config with the dbx-owned copy."""
    config = payload.get("config")
    if not isinstance(config, Mapping) or not isinstance(config.get("id"), str):
        raise DbxIdeForbidden("saved connection required")
    connection_id = config["id"]
    if connection_id not in visible_ids or connection_id not in stored:
        raise DbxIdeForbidden("connection not visible")
    return {**payload, "config": stored[connection_id]}


def classify_save(payload: dict[str, Any], stored_ids: set[str], manageable_ids: set[str]) -> set[str]:
    """Validate a dbx save batch and return IDs newly created by this user."""
    configs = payload.get("configs", [])
    removed = payload.get("removedIds", [])
    if not isinstance(configs, list) or not isinstance(removed, list):
        raise DbxIdeForbidden("invalid save frame")
    new_ids: set[str] = set()
    for config in configs:
        if not isinstance(config, Mapping) or not isinstance(config.get("id"), str) or not config["id"]:
            raise DbxIdeForbidden("connection id required")
        connection_id = config["id"]
        if connection_id in stored_ids:
            if connection_id not in manageable_ids:
                raise DbxIdeForbidden("connection owner required")
        else:
            new_ids.add(connection_id)
    for connection_id in removed:
        if not isinstance(connection_id, str) or connection_id not in manageable_ids:
            raise DbxIdeForbidden("connection owner required")
    if new_ids.intersection(removed):
        raise DbxIdeForbidden("cannot create and remove the same connection")
    return new_ids
