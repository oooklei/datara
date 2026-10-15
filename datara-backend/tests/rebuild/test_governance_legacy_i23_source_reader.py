from datetime import datetime, timezone

import pytest
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, event
from sqlalchemy.exc import OperationalError

from rebuild.governance.legacy_source_reader import I23_SOURCE_COLUMNS, LegacyI23SourceReader


def _sqlite_i23_engine(*, omit_column: str | None = None):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    columns = []
    for name in I23_SOURCE_COLUMNS["t_user"][1]:
        if name == omit_column:
            continue
        column_type = Integer if name == "id" else DateTime if name.endswith("_time") else String(128)
        columns.append(Column(name, column_type, primary_key=name == "id"))
    Table("t_user", metadata, *columns)
    metadata.create_all(engine)
    return engine


def test_i23_reader_reads_identity_metadata_only_and_is_read_only():
    engine = _sqlite_i23_engine()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO t_user (id, user_name, user_role, state, create_time, update_time) "
            "VALUES (1, 'analyst-a', 'analyst', 'enabled', '2026-10-01 00:00:00', '2026-10-02 00:00:00')"
        )

    statements: list[str] = []

    def enforce_read_only(_connection, _cursor, statement, *_args):
        verb = statement.lstrip().split(None, 1)[0].upper()
        statements.append(statement.upper())
        assert verb in {"SELECT", "PRAGMA"}

    event.listen(engine, "before_cursor_execute", enforce_read_only)
    snapshot = LegacyI23SourceReader(engine, sqlite_test_mode=True).read_snapshot(page_size=1)

    assert snapshot.schema == "datara_meta"
    assert snapshot.counts == {"t_user": 1}
    assert snapshot.rows["t_user"][0]["user_name"] == "analyst-a"
    assert snapshot.rows["t_user"][0]["user_role"] == "analyst"
    assert set(snapshot.rows["t_user"][0]) == set(I23_SOURCE_COLUMNS["t_user"][1])
    assert all("USER_PWD" not in statement for statement in statements)
    assert statements and {statement.split(None, 1)[0] for statement in statements} <= {"SELECT", "PRAGMA"}


def test_i23_reader_empty_digest_ignores_capture_time_and_tracks_source_content():
    engine = _sqlite_i23_engine()
    reader = LegacyI23SourceReader(engine, sqlite_test_mode=True)
    first = reader.read_snapshot(captured_at=datetime(2026, 10, 15, 1, tzinfo=timezone.utc))
    second = reader.read_snapshot(captured_at=datetime(2026, 10, 15, 2, tzinfo=timezone.utc))
    assert first.counts == {"t_user": 0}
    assert first.digest == second.digest

    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO t_user (id, user_name, user_role, state) VALUES (2, 'dev-a', 'dev', 'enabled')"
        )
    assert reader.read_snapshot().digest != first.digest


def test_i23_reader_fails_closed_on_missing_columns_and_row_limit():
    with pytest.raises(OperationalError):
        LegacyI23SourceReader(_sqlite_i23_engine(omit_column="user_role"), sqlite_test_mode=True).read_snapshot()

    engine = _sqlite_i23_engine()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO t_user (id, user_name, user_role, state) VALUES (1, 'a', 'viewer', 'enabled'), "
            "(2, 'b', 'viewer', 'enabled')"
        )
    with pytest.raises(RuntimeError, match="legacy I23 snapshot exceeded configured total row safety limit"):
        LegacyI23SourceReader(engine, sqlite_test_mode=True).read_snapshot(max_total_rows=1)


def test_i23_reader_validates_limits_timestamp_and_database_scope():
    reader = LegacyI23SourceReader(_sqlite_i23_engine(), sqlite_test_mode=True)
    with pytest.raises(ValueError, match="page_size"):
        reader.read_snapshot(page_size=0)
    with pytest.raises(ValueError, match="max_total_rows"):
        reader.read_snapshot(max_total_rows=0)
    with pytest.raises(ValueError, match="timezone-aware"):
        reader.read_snapshot(captured_at=datetime(2026, 10, 15))

    with pytest.raises(ValueError, match="SQLite is allowed only for tests"):
        LegacyI23SourceReader(_sqlite_i23_engine())
    target_engine = create_engine("mysql+pymysql://reader:unused@127.0.0.1/datara_rebuild_i0")
    with pytest.raises(ValueError, match="must point to datara_meta"):
        LegacyI23SourceReader(target_engine)
