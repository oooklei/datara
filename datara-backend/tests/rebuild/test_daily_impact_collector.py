from datetime import date

import pytest

from rebuild.impact import analyze_daily_history, collect_daily_history


def test_daily_history_pages_deduplicate_and_use_shanghai_day():
    requests = []

    class Client:
        def search_history(self, **request):
            requests.append(request)
            if len(requests) == 1:
                return {
                    "entries": [
                        {"id": "a", "executed_at": "2026-10-29T00:30:00+08:00"},
                        {"id": "old", "executed_at": "2026-10-28T15:59:59Z"},
                    ],
                    "next_cursor": {"executed_at": "2026-10-29T00:30:00+08:00", "id": "a"},
                }
            return {
                "entries": [
                    {"id": "a", "executed_at": "2026-10-29T00:30:00+08:00"},
                    {"id": "b", "executed_at": "2026-10-29T12:00:00+08:00"},
                ],
                "next_cursor": None,
            }

    rows = collect_daily_history(date(2026, 10, 29), Client())
    assert [row["id"] for row in rows] == ["a", "b"]
    assert requests[0]["started_at"] == "2026-10-29T00:00:00+08:00"
    assert requests[0]["ended_at"] == "2026-10-30T00:00:00+08:00"
    assert requests[1]["cursor"]["id"] == "a"


def test_repeated_cursor_fails_instead_of_looping_forever():
    class Client:
        def search_history(self, **request):
            return {"entries": [], "next_cursor": {"executed_at": "2026-10-29T00:00:00", "id": "same"}}

    with pytest.raises(ValueError, match="cursor did not advance"):
        collect_daily_history(date(2026, 10, 29), Client())


def test_daily_analysis_requires_explicit_project_connection_scope():
    rows = [
        {"id": "ours", "connection_id": "owned", "database": "sales", "sql": "DELETE FROM orders", "success": True},
        {"id": "theirs", "connection_id": "other", "database": "hr", "sql": "DELETE FROM people", "success": True},
    ]
    result = analyze_daily_history(rows, allowed_connection_ids={"owned"})
    assert [row["history_id"] for row in result] == ["ours"]
    assert analyze_daily_history(rows, allowed_connection_ids=set()) == []
