"""Page through one local calendar day of dbx SQL history.

The collector is read-only and makes no assumptions about project ownership.
The caller must apply a verified connection-to-project mapping before exposing
or persisting results for a datara project.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from rebuild.dbx import DbxClient

from .analyzer import analyze_history_entry


_SHANGHAI = ZoneInfo("Asia/Shanghai")


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_SHANGHAI)
    return parsed.astimezone(_SHANGHAI)


def collect_daily_history(day: date, client: DbxClient, *, page_limit: int = 200, max_pages: int = 1000, connection_ids: set[str] | None = None) -> list[dict[str, Any]]:
    if page_limit < 1 or max_pages < 1:
        raise ValueError("page_limit and max_pages must be positive")
    start = datetime.combine(day, time.min, _SHANGHAI)
    end = start + timedelta(days=1)
    cursor: dict[str, str] | None = None
    seen_cursors: set[tuple[str, str]] = set()
    seen_ids: set[str] = set()
    entries: list[dict[str, Any]] = []
    for _ in range(max_pages):
        page = client.search_history(started_at=start.isoformat(), ended_at=end.isoformat(), cursor=cursor, limit=page_limit, connection_ids=connection_ids)
        rows = page.get("entries")
        if not isinstance(rows, list):
            raise ValueError("dbx history response has no entries list")
        for entry in rows:
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                continue
            try:
                executed_at = _timestamp(str(entry.get("executed_at", "")))
            except ValueError:
                continue
            if start <= executed_at < end and entry["id"] not in seen_ids:
                entries.append(entry)
                seen_ids.add(entry["id"])
        next_cursor = page.get("next_cursor")
        if not next_cursor:
            return entries
        if not isinstance(next_cursor, dict):
            raise ValueError("dbx history returned an invalid cursor")
        marker = (str(next_cursor.get("executed_at", "")), str(next_cursor.get("id", "")))
        if not all(marker) or marker in seen_cursors:
            raise ValueError("dbx history cursor did not advance")
        seen_cursors.add(marker)
        cursor = {"executed_at": marker[0], "id": marker[1]}
    raise ValueError("dbx history exceeded max_pages")


def analyze_daily_history(
    entries: list[dict[str, Any]],
    *,
    allowed_connection_ids: set[str],
    dialect_by_connection: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Analyze only connections already authorized for the target project."""
    dialects = dialect_by_connection or {}
    return [
        analyze_history_entry(entry, dialect=dialects.get(str(entry.get("connection_id", ""))))
        for entry in entries
        if str(entry.get("connection_id", "")) in allowed_connection_ids
    ]
