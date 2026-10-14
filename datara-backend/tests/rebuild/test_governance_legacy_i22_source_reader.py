from datetime import datetime, timezone

import pytest
from sqlalchemy import Column, DateTime, Integer, JSON, MetaData, String, Table, create_engine, event
from sqlalchemy.exc import OperationalError

from rebuild.governance.legacy_source_reader import I22_SOURCE_COLUMNS, LegacyI22SourceReader


def _sqlite_i22_engine(*, omit_column: tuple[str, str] | None = None):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    integer_fields = {"id", "biz_id", "version", "std_code_id", "seq", "length", "element_id", "code_id"}
    json_fields = {"payload_json", "summary_json", "issues_json"}
    for table_name, (identity_field, columns) in I22_SOURCE_COLUMNS.items():
        table_columns = []
        for name in columns:
            if omit_column == (table_name, name):
                continue
            if name in integer_fields:
                column_type = Integer
            elif name in json_fields:
                column_type = JSON
            elif name in {"create_time", "update_time"}:
                column_type = DateTime
            else:
                column_type = String(4096)
            table_columns.append(Column(name, column_type, primary_key=name == identity_field))
        Table(table_name, metadata, *table_columns)
    metadata.create_all(engine)
    return engine


def test_i22_reader_reads_all_seven_allowlisted_tables_read_only_and_preserves_values():
    engine = _sqlite_i22_engine()
    with engine.begin() as connection:
        for table_name in I22_SOURCE_COLUMNS:
            connection.exec_driver_sql(f"INSERT INTO {table_name} (id) VALUES (1)")
        connection.exec_driver_sql(
            "UPDATE t_std_approval SET payload_json = '{\"source\":\"unchanged\"}', opinion = 'keep' WHERE id = 1"
        )
        connection.exec_driver_sql("UPDATE t_std_code_value SET std_code_id = 1, c = 'A', n = 'Alpha' WHERE id = 1")

    statements: list[str] = []

    def enforce_read_only(_connection, _cursor, statement, *_args):
        verb = statement.lstrip().split(None, 1)[0].upper()
        statements.append(verb)
        assert verb in {"SELECT", "PRAGMA"}

    event.listen(engine, "before_cursor_execute", enforce_read_only)
    snapshot = LegacyI22SourceReader(engine, sqlite_test_mode=True).read_snapshot(page_size=1)

    assert snapshot.schema == "datara_meta"
    assert set(snapshot.rows) == set(I22_SOURCE_COLUMNS)
    assert all(snapshot.counts[table_name] == 1 for table_name in I22_SOURCE_COLUMNS)
    assert snapshot.rows["t_std_approval"][0]["payload_json"] == '{"source":"unchanged"}'
    assert snapshot.rows["t_std_code_value"][0]["c"] == "A"
    assert len(snapshot.digest) == 64
    assert statements and set(statements) == {"SELECT", "PRAGMA"}


def test_i22_reader_empty_snapshot_digest_ignores_capture_time():
    reader = LegacyI22SourceReader(_sqlite_i22_engine(), sqlite_test_mode=True)
    first = reader.read_snapshot(captured_at=datetime(2026, 10, 15, 1, tzinfo=timezone.utc))
    second = reader.read_snapshot(captured_at=datetime(2026, 10, 15, 2, tzinfo=timezone.utc))

    assert all(count == 0 for count in first.counts.values())
    assert first.captured_at != second.captured_at
    assert first.digest == second.digest


def test_i22_reader_digest_changes_with_source_content():
    engine = _sqlite_i22_engine()
    reader = LegacyI22SourceReader(engine, sqlite_test_mode=True)
    before = reader.read_snapshot()
    with engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO t_std_code (id, code) VALUES (1, 'status')")
    after = reader.read_snapshot()

    assert before.digest != after.digest


def test_i22_reader_fails_closed_when_an_allowlisted_column_is_missing():
    engine = _sqlite_i22_engine(omit_column=("t_std_mapping", "code_id"))

    with pytest.raises(OperationalError):
        LegacyI22SourceReader(engine, sqlite_test_mode=True).read_snapshot()


def test_i22_reader_refuses_total_row_truncation():
    engine = _sqlite_i22_engine()
    with engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO t_std_code (id) VALUES (1), (2)")

    with pytest.raises(RuntimeError, match="legacy I22 snapshot exceeded configured total row safety limit"):
        LegacyI22SourceReader(engine, sqlite_test_mode=True).read_snapshot(max_total_rows=1)


def test_i22_reader_rejects_invalid_limits_and_naive_timestamp():
    reader = LegacyI22SourceReader(_sqlite_i22_engine(), sqlite_test_mode=True)

    with pytest.raises(ValueError, match="page_size"):
        reader.read_snapshot(page_size=0)
    with pytest.raises(ValueError, match="max_total_rows"):
        reader.read_snapshot(max_total_rows=0)
    with pytest.raises(ValueError, match="timezone-aware"):
        reader.read_snapshot(captured_at=datetime(2026, 10, 15, 1))


def test_i22_reader_requires_explicit_sqlite_test_mode_and_rejects_target_schema():
    sqlite_engine = _sqlite_i22_engine()
    with pytest.raises(ValueError, match="SQLite is allowed only for tests"):
        LegacyI22SourceReader(sqlite_engine)

    target_engine = create_engine("mysql+pymysql://reader:unused@127.0.0.1/datara_rebuild_i0")
    with pytest.raises(ValueError, match="must point to datara_meta"):
        LegacyI22SourceReader(target_engine)
