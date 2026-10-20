from __future__ import annotations

from datetime import datetime, timedelta, timezone
from importlib.util import find_spec

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from rebuild.common.db import Base


def test_persistent_result_snapshot_store_is_available():
    assert find_spec("rebuild.sql_ide.result_store") is not None


def _store_type():
    if find_spec("rebuild.sql_ide.result_store") is None:
        pytest.skip("persistent result snapshot store is not implemented yet")
    from rebuild.sql_ide.result_store import PersistentResultPageStore

    return PersistentResultPageStore


@pytest.fixture
def result_store():
    store_type = _store_type()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield store_type(session_factory=factory)
    engine.dispose()


def test_snapshot_pages_are_immutable_and_scoped_to_project_user(result_store):
    result_set_id = result_store.save_snapshot(
        project_id=7,
        user_id=11,
        history_id="history-1",
        stmt_index=0,
        columns=["id"],
        rows=[[1], [2], [3]],
    )

    page = result_store.fetch_page(
        project_id=7,
        user_id=11,
        history_id="history-1",
        stmt_index=0,
        offset=1,
        limit=1,
    )

    assert page == {
        "resultSetId": result_set_id,
        "columns": ["id"],
        "rows": [[2]],
        "page": {"offset": 1, "limit": 1, "hasMore": True},
        "totalRows": 3,
        "expiresAt": page["expiresAt"],
    }
    with pytest.raises(LookupError, match="not available"):
        result_store.fetch_page(
            project_id=8,
            user_id=11,
            history_id="history-1",
            stmt_index=0,
            offset=0,
            limit=1,
        )
    result_store.save_snapshot(
        project_id=7,
        user_id=11,
        history_id="history-1",
        stmt_index=0,
        columns=["changed"],
        rows=[[99]],
    )
    assert result_store.fetch_page(
        project_id=7,
        user_id=11,
        history_id="history-1",
        result_set_id=result_set_id,
        offset=0,
        limit=10,
    )["rows"] == [[1], [2], [3]]


def test_snapshot_expires_after_contract_ttl_and_can_be_cleaned(result_store):
    now = datetime.now(timezone.utc)
    result_store.save_snapshot(
        project_id=7,
        user_id=11,
        history_id="history-expired",
        stmt_index=0,
        columns=["id"],
        rows=[[1]],
        now=now - timedelta(hours=25),
    )

    with pytest.raises(LookupError, match="expired"):
        result_store.fetch_page(
            project_id=7,
            user_id=11,
            history_id="history-expired",
            stmt_index=0,
            offset=0,
            limit=10,
            now=now,
        )

    assert result_store.cleanup_expired(now=now) == 1


def test_page_bounds_are_enforced(result_store):
    """A5 contract §2.2/§3#12: limit must be 1..200 (aligned with pagination layer).

    DEP-03: user ruling S109 unified the page limit at 200 across the whole chain
    (result_store / pagination / history / status + A5 contract doc).
    """
    result_store.save_snapshot(
        project_id=7,
        user_id=11,
        history_id="history-bounds",
        stmt_index=0,
        columns=["id"],
        rows=[[1]],
    )

    # limit=200 is valid (DEP-03 unified upper bound)
    page = result_store.fetch_page(
        project_id=7,
        user_id=11,
        history_id="history-bounds",
        stmt_index=0,
        offset=0,
        limit=200,
    )
    assert page["page"]["limit"] == 200

    # limit=201 exceeds the unified upper bound
    with pytest.raises(ValueError, match="limit"):
        result_store.fetch_page(
            project_id=7,
            user_id=11,
            history_id="history-bounds",
            stmt_index=0,
            offset=0,
            limit=201,
        )


def test_statement_can_hold_multiple_results_addressed_by_result_set_id(result_store):
    first_id = result_store.save_snapshot(
        project_id=7,
        user_id=11,
        history_id="history-multiple",
        stmt_index=0,
        columns=["id"],
        rows=[[1]],
    )
    second_id = result_store.save_snapshot(
        project_id=7,
        user_id=11,
        history_id="history-multiple",
        stmt_index=0,
        columns=["id"],
        rows=[[2]],
    )

    first_page = result_store.fetch_page(
        project_id=7,
        user_id=11,
        history_id="history-multiple",
        result_set_id=first_id,
        offset=0,
        limit=1,
    )
    second_page = result_store.fetch_page(
        project_id=7,
        user_id=11,
        history_id="history-multiple",
        result_set_id=second_id,
        offset=0,
        limit=1,
    )

    assert first_page["rows"] == [[1]]
    assert second_page["rows"] == [[2]]
