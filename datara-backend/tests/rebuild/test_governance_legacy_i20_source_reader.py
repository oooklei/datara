from datetime import datetime, timezone

import pytest
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, event
from sqlalchemy.exc import OperationalError

from rebuild.governance.legacy_source_reader import I20_SOURCE_COLUMNS, LegacyI20SourceReader


def _sqlite_i20_engine(*, omit_column: tuple[str, str] | None = None):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    integer_fields = {"id", "version", "base_metric_id", "indicator_id"}
    time_fields = {"create_time", "update_time"}
    for table_name, (identity_field, columns) in I20_SOURCE_COLUMNS.items():
        table_columns = []
        for name in columns:
            if omit_column == (table_name, name):
                continue
            column_type = Integer if name in integer_fields else DateTime if name in time_fields else String(4096)
            table_columns.append(Column(name, column_type, primary_key=name == identity_field))
        Table(table_name, metadata, *table_columns)
    metadata.create_all(engine)
    return engine


def test_i20_reader_selects_fixed_columns_preserves_raw_payload_and_reads_pages_read_only():
    engine = _sqlite_i20_engine()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO t_indicator (id, code, name, type, biz_def, dims) "
            "VALUES (2, 'M2', '订单数', '原子', '订单计数', 'region,channel')"
        )
        connection.exec_driver_sql(
            "INSERT INTO t_indicator (id, code, name, type, biz_def, dims) "
            "VALUES (1, 'M1', '用户数', '原子', '用户计数', '[region, channel]')"
        )
        connection.exec_driver_sql(
            "INSERT INTO t_indicator_version "
            "(id, indicator_id, version, snapshot_json, change_note) "
            "VALUES (11, 1, 1, '{\"dims\":\"[region, channel]\"}', 'initial')"
        )

    statements: list[str] = []

    def enforce_read_only(_connection, _cursor, statement, *_args):
        verb = statement.lstrip().split(None, 1)[0].upper()
        statements.append(verb)
        assert verb in {"SELECT", "PRAGMA"}

    event.listen(engine, "before_cursor_execute", enforce_read_only)
    snapshot = LegacyI20SourceReader(engine, sqlite_test_mode=True).read_snapshot(page_size=1)

    assert snapshot.schema == "datara_meta"
    assert snapshot.counts == {"t_indicator": 2, "t_indicator_version": 1}
    assert [row["id"] for row in snapshot.rows["t_indicator"]] == [1, 2]
    assert snapshot.rows["t_indicator"][0]["dims"] == "[region, channel]"
    assert snapshot.rows["t_indicator_version"][0]["snapshot_json"] == '{"dims":"[region, channel]"}'
    assert len(snapshot.digest) == 64
    assert statements and set(statements) == {"SELECT", "PRAGMA"}


def test_i20_reader_empty_snapshot_digest_is_independent_of_capture_time():
    reader = LegacyI20SourceReader(_sqlite_i20_engine(), sqlite_test_mode=True)
    first = reader.read_snapshot(captured_at=datetime(2026, 10, 15, 1, tzinfo=timezone.utc))
    second = reader.read_snapshot(captured_at=datetime(2026, 10, 15, 2, tzinfo=timezone.utc))

    assert first.counts == {"t_indicator": 0, "t_indicator_version": 0}
    assert first.captured_at != second.captured_at
    assert first.digest == second.digest


def test_i20_reader_content_changes_change_snapshot_digest():
    engine = _sqlite_i20_engine()
    reader = LegacyI20SourceReader(engine, sqlite_test_mode=True)
    before = reader.read_snapshot()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO t_indicator (id, code, name, type, biz_def) "
            "VALUES (1, 'M1', '用户数', '原子', '用户计数')"
        )
    after = reader.read_snapshot()

    assert before.digest != after.digest


def test_i20_reader_fails_closed_when_an_allowlisted_column_is_missing():
    engine = _sqlite_i20_engine(omit_column=("t_indicator", "dims"))

    with pytest.raises(OperationalError):
        LegacyI20SourceReader(engine, sqlite_test_mode=True).read_snapshot()


def test_i20_reader_refuses_total_row_truncation():
    engine = _sqlite_i20_engine()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO t_indicator (id, code, name, type, biz_def) VALUES (1, 'M1', '用户数', '原子', 'x')"
        )
        connection.exec_driver_sql(
            "INSERT INTO t_indicator (id, code, name, type, biz_def) VALUES (2, 'M2', '订单数', '原子', 'y')"
        )

    with pytest.raises(RuntimeError, match="legacy I20 snapshot exceeded configured total row safety limit"):
        LegacyI20SourceReader(engine, sqlite_test_mode=True).read_snapshot(max_total_rows=1)


def test_i20_reader_rejects_invalid_limits_and_naive_capture_time():
    reader = LegacyI20SourceReader(_sqlite_i20_engine(), sqlite_test_mode=True)

    with pytest.raises(ValueError, match="page_size"):
        reader.read_snapshot(page_size=0)
    with pytest.raises(ValueError, match="max_total_rows"):
        reader.read_snapshot(max_total_rows=0)
    with pytest.raises(ValueError, match="timezone-aware"):
        reader.read_snapshot(captured_at=datetime(2026, 10, 15, 1))


def test_i20_reader_rejects_implicit_sqlite_and_nonlegacy_schema():
    sqlite_engine = _sqlite_i20_engine()
    with pytest.raises(ValueError, match="SQLite is allowed only for tests"):
        LegacyI20SourceReader(sqlite_engine)

    target_engine = create_engine("mysql+pymysql://reader:unused@127.0.0.1/datara_rebuild_i0")
    with pytest.raises(ValueError, match="must point to datara_meta"):
        LegacyI20SourceReader(target_engine)
