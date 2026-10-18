"""Offset and opaque-cursor pagination over persisted SQL result snapshots.

This module deliberately depends only on ``ResultPageStore``. It has no SQL
execution port, so continuing a page can only read the existing snapshot.
"""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any, Mapping

from rebuild.sql_ide.contracts import ResultPageStore

DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 500


class PaginationError(ValueError):
    """Stable domain error for malformed or out-of-scope page cursors."""

    error_code = "CURSOR_INVALID"


def paginate_result(
    store: ResultPageStore,
    *,
    history_id: str,
    stmt_index: int,
    offset: int | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_LIMIT,
) -> dict[str, Any]:
    """Read one page from a persisted result snapshot.

    A cursor is an opaque, versioned continuation token bound to the history,
    statement, and (when exposed by the store) result-set identity. It never
    contains SQL and this function never invokes SQL execution.
    """
    if (
        not history_id
        or not isinstance(stmt_index, int)
        or isinstance(stmt_index, bool)
        or stmt_index < 0
    ):
        raise ValueError("history_id and non-negative stmt_index are required")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_PAGE_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_LIMIT}")
    if cursor is not None and offset is not None:
        raise ValueError("provide either offset or cursor, not both")

    meta = store.get_snapshot_meta(history_id=history_id, stmt_index=stmt_index)
    snapshot_id = _snapshot_id(meta)
    if cursor is None:
        page_offset = 0 if offset is None else offset
        if not isinstance(page_offset, int) or isinstance(page_offset, bool) or page_offset < 0:
            raise ValueError("offset must be non-negative")
    else:
        token = _decode_cursor(cursor)
        if token["h"] != history_id or token["s"] != stmt_index:
            raise PaginationError("cursor does not match this request")
        if snapshot_id is None:
            raise PaginationError("snapshot identity is required to accept a cursor")
        if token["r"] != snapshot_id:
            raise PaginationError("cursor snapshot identity does not match current snapshot")
        page_offset = token["o"]

    page = dict(
        store.fetch_page(
            history_id=history_id,
            stmt_index=stmt_index,
            offset=page_offset,
            limit=limit,
        )
    )
    page_snapshot_id = _snapshot_id(page)
    if snapshot_id is not None and page_snapshot_id != snapshot_id:
        if cursor is not None:
            raise PaginationError("cursor page snapshot identity does not match current snapshot")
        raise ValueError("page snapshot identity does not match current snapshot")

    rows = page.get("rows")
    if not isinstance(rows, list):
        raise ValueError("result page rows must be a list")
    page_info = page.get("page")
    if not isinstance(page_info, Mapping):
        page_info = {}
    has_more = page_info.get("hasMore")
    if has_more is None:
        total_rows = page.get("totalRows", meta.get("totalRows"))
        if not isinstance(total_rows, int) or total_rows < 0:
            raise ValueError("snapshot totalRows is required to determine continuation")
        has_more = page_offset + len(rows) < total_rows
    if not isinstance(has_more, bool):
        raise ValueError("result page hasMore must be boolean")
    if has_more and snapshot_id is None:
        raise ValueError("snapshot identity is required to issue a continuation cursor")

    next_cursor = (
        _encode_cursor(
            history_id=history_id,
            stmt_index=stmt_index,
            offset=page_offset + len(rows),
            snapshot_id=snapshot_id,
        )
        if has_more
        else None
    )
    result = dict(page)
    result["page"] = {
        **dict(page_info),
        "offset": page_offset,
        "limit": limit,
        "hasMore": has_more,
    }
    result["nextCursor"] = next_cursor
    if "columns" not in result and "columns" in meta:
        result["columns"] = list(meta["columns"])
    if "totalRows" not in result and "totalRows" in meta:
        result["totalRows"] = meta["totalRows"]
    if "truncated" not in result and "truncated" in meta:
        result["truncated"] = meta["truncated"]
    return result


def _snapshot_id(value: Mapping[str, Any]) -> str | None:
    result = value.get("resultSetId", value.get("result_set_id"))
    if result is None:
        return None
    if not isinstance(result, str) or not result:
        raise ValueError("snapshot identity must be a non-empty string")
    return result


def _encode_cursor(*, history_id: str, stmt_index: int, offset: int, snapshot_id: str | None) -> str:
    payload = json.dumps(
        {"v": 1, "h": history_id, "s": stmt_index, "o": offset, "r": snapshot_id},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> dict[str, Any]:
    if not isinstance(cursor, str) or not cursor or len(cursor) > 4096:
        raise PaginationError("cursor is invalid")
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        payload = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise PaginationError("cursor is invalid") from exc
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise PaginationError("cursor version is unsupported")
    if (
        not isinstance(payload.get("h"), str)
        or not payload["h"]
        or not isinstance(payload.get("s"), int)
        or isinstance(payload["s"], bool)
        or payload["s"] < 0
        or not isinstance(payload.get("o"), int)
        or isinstance(payload["o"], bool)
        or payload["o"] < 0
        or (payload.get("r") is not None and (not isinstance(payload["r"], str) or not payload["r"]))
    ):
        raise PaginationError("cursor payload is invalid")
    return payload
