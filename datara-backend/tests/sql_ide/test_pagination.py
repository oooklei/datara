from __future__ import annotations

import base64
import json

import pytest

from rebuild.sql_ide.pagination import PaginationError, paginate_result


class MemoryPageStore:
    """Minimal ResultPageStore contract fake with an immutable snapshot."""

    def __init__(self):
        self.rows = [["a"], ["b"], ["c"]]
        self.calls = []
        self.expose_snapshot_id = True

    def get_snapshot_meta(self, *, history_id, stmt_index):
        meta = {
            "columns": ["value"],
            "totalRows": len(self.rows),
            "truncated": False,
        }
        if self.expose_snapshot_id:
            meta["resultSetId"] = "snapshot-1"
        return meta

    def fetch_page(self, *, history_id, stmt_index, offset, limit):
        self.calls.append((history_id, stmt_index, offset, limit))
        rows = self.rows[offset : offset + limit]
        return {
            "resultSetId": "snapshot-1",
            "columns": ["value"],
            "rows": rows,
            "page": {"offset": offset, "limit": limit, "hasMore": offset + len(rows) < len(self.rows)},
            "totalRows": len(self.rows),
        }


def test_offset_pagination_reads_only_the_persisted_snapshot():
    store = MemoryPageStore()

    result = paginate_result(store, history_id="history-1", stmt_index=0, offset=1, limit=1)

    assert result["rows"] == [["b"]]
    assert result["page"]["offset"] == 1
    assert result["page"]["hasMore"] is True
    assert result["nextCursor"]
    assert store.calls == [("history-1", 0, 1, 1)]


def test_cursor_continues_same_snapshot_without_reexecuting_sql():
    store = MemoryPageStore()
    first = paginate_result(store, history_id="history-1", stmt_index=0, offset=0, limit=2)

    second = paginate_result(
        store,
        history_id="history-1",
        stmt_index=0,
        cursor=first["nextCursor"],
        limit=2,
    )

    assert second["rows"] == [["c"]]
    assert second["page"]["offset"] == 2
    assert second["nextCursor"] is None
    assert [call[2] for call in store.calls] == [0, 2]


def test_cursor_is_bound_to_history_and_statement():
    store = MemoryPageStore()
    first = paginate_result(store, history_id="history-1", stmt_index=0, offset=0, limit=1)

    with pytest.raises(PaginationError, match="cursor.*request") as exc_info:
        paginate_result(
            store,
            history_id="other-history",
            stmt_index=0,
            cursor=first["nextCursor"],
            limit=1,
        )
    assert exc_info.value.error_code == "CURSOR_INVALID"


def test_cursor_from_a_different_snapshot_is_rejected():
    store = MemoryPageStore()
    first = paginate_result(store, history_id="history-1", stmt_index=0, offset=0, limit=1)
    original_meta = store.get_snapshot_meta
    store.get_snapshot_meta = lambda **kwargs: {**original_meta(**kwargs), "resultSetId": "snapshot-2"}

    with pytest.raises(ValueError, match="snapshot"):
        paginate_result(
            store,
            history_id="history-1",
            stmt_index=0,
            cursor=first["nextCursor"],
            limit=1,
        )


def test_offset_and_cursor_cannot_be_combined():
    store = MemoryPageStore()
    token = base64.urlsafe_b64encode(
        json.dumps({"v": 1, "h": "history-1", "s": 0, "o": 1, "r": "snapshot-1"}).encode()
    ).decode().rstrip("=")

    with pytest.raises(ValueError, match="either.*offset.*cursor"):
        paginate_result(store, history_id="history-1", stmt_index=0, offset=0, cursor=token)


def test_continuation_cursor_is_not_issued_without_snapshot_identity():
    store = MemoryPageStore()
    store.expose_snapshot_id = False

    with pytest.raises(ValueError, match="snapshot identity.*issue"):
        paginate_result(store, history_id="history-1", stmt_index=0, offset=0, limit=1)


def test_page_limit_allows_500_rows():
    store = MemoryPageStore()

    result = paginate_result(store, history_id="history-1", stmt_index=0, limit=500)

    assert result["page"]["limit"] == 500


def test_page_limit_rejects_501_rows():
    store = MemoryPageStore()

    with pytest.raises(ValueError, match="1 and 500"):
        paginate_result(store, history_id="history-1", stmt_index=0, limit=501)


def test_cursor_is_rejected_when_current_snapshot_identity_is_missing():
    store = MemoryPageStore()
    first = paginate_result(store, history_id="history-1", stmt_index=0, offset=0, limit=1)
    store.expose_snapshot_id = False

    with pytest.raises(PaginationError, match="snapshot identity.*accept") as exc_info:
        paginate_result(
            store,
            history_id="history-1",
            stmt_index=0,
            cursor=first["nextCursor"],
            limit=1,
        )
    assert exc_info.value.error_code == "CURSOR_INVALID"


def test_malformed_cursor_uses_stable_domain_error_code():
    store = MemoryPageStore()

    with pytest.raises(PaginationError, match="cursor is invalid") as exc_info:
        paginate_result(store, history_id="history-1", stmt_index=0, cursor="not-a-cursor")

    assert exc_info.value.error_code == "CURSOR_INVALID"


def test_numeric_argument_validation_remains_plain_value_error():
    store = MemoryPageStore()

    with pytest.raises(ValueError, match="limit must") as exc_info:
        paginate_result(store, history_id="history-1", stmt_index=0, limit=0)

    assert not isinstance(exc_info.value, PaginationError)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"stmt_index": True},
        {"offset": 0.5},
        {"limit": True},
    ],
)
def test_pagination_rejects_non_integer_numeric_arguments(kwargs):
    store = MemoryPageStore()
    arguments = {"history_id": "history-1", "stmt_index": 0, **kwargs}

    with pytest.raises(ValueError):
        paginate_result(store, **arguments)

