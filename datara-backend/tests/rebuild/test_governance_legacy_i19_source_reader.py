from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, create_engine, event
from sqlalchemy.exc import OperationalError

from rebuild.governance.legacy_source_reader import I19_SOURCE_COLUMNS, LegacyI19SourceReader


def _sqlite_i19_engine(*, omit_column: tuple[str, str] | None = None):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    integer_fields = {"id", "ds_id", "tag_id"}
    time_fields = {"create_time", "update_time"}
    for table_name, (identity_field, columns) in I19_SOURCE_COLUMNS.items():
        table_columns = []
        for name in columns:
            if omit_column == (table_name, name):
                continue
            if name in integer_fields:
                column_type = Integer
            elif name in time_fields:
                column_type = DateTime
            else:
                column_type = String(2048)
            table_columns.append(Column(name, column_type, primary_key=name == identity_field))
        Table(table_name, metadata, *table_columns)
    metadata.create_all(engine)
    return engine


def test_i19_reader_reads_fixed_columns_in_keyset_order_and_sqlite_is_read_only():
    engine = _sqlite_i19_engine()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO t_meta_table_ext "
            "(id, ds_id, db_name, table_name, biz_domain, security_level, owner, remark) "
            "VALUES (2, 7, 'dw', 'orders', '交易', '内部', 'data', 'note')"
        )
        connection.exec_driver_sql(
            "INSERT INTO t_meta_tag (id, name, cat, color, `desc`) "
            "VALUES (1, '核心', '业务', '#112233', '核心表')"
        )
        connection.exec_driver_sql(
            "INSERT INTO t_meta_tagging (id, tag_id, target_type, target_key, created_by) "
            "VALUES (1, 1, 'table', '7/dw/orders', 'operator')"
        )
        connection.exec_driver_sql(
            "INSERT INTO t_meta_tagging (id, tag_id, target_type, target_key, created_by) "
            "VALUES (2, 1, 'field', '7/dw/orders/order_id', 'operator')"
        )

    statements: list[str] = []

    def enforce_read_only(_connection, _cursor, statement, *_args):
        verb = statement.lstrip().split(None, 1)[0].upper()
        statements.append(verb)
        assert verb in {"SELECT", "PRAGMA"}

    event.listen(engine, "before_cursor_execute", enforce_read_only)
    snapshot = LegacyI19SourceReader(engine, sqlite_test_mode=True).read_snapshot(page_size=1)

    assert snapshot.schema == "datara_meta"
    assert snapshot.counts == {"t_meta_table_ext": 1, "t_meta_tag": 1, "t_meta_tagging": 2}
    assert snapshot.rows["t_meta_tagging"][0]["id"] == 1
    assert snapshot.rows["t_meta_tagging"][1]["id"] == 2
    assert snapshot.rows["t_meta_table_ext"][0]["ds_id"] == 7
    assert len(snapshot.digest) == 64
    assert statements and set(statements) == {"SELECT", "PRAGMA"}


def test_i19_snapshot_digest_is_content_stable_and_captured_at_is_separate():
    engine = _sqlite_i19_engine()
    reader = LegacyI19SourceReader(engine, sqlite_test_mode=True)
    first = reader.read_snapshot(captured_at=datetime(2026, 10, 15, 1, 0, tzinfo=ZoneInfo("Asia/Shanghai")))
    second = reader.read_snapshot(captured_at=datetime(2026, 10, 15, 2, 0, tzinfo=ZoneInfo("Asia/Shanghai")))

    assert first.captured_at != second.captured_at
    assert first.digest == second.digest


def test_i19_snapshot_digest_changes_with_source_content():
    engine = _sqlite_i19_engine()
    reader = LegacyI19SourceReader(engine, sqlite_test_mode=True)
    before = reader.read_snapshot()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO t_meta_tag (id, name, cat, color, `desc`) "
            "VALUES (1, '核心', '业务', '#112233', '核心表')"
        )
    after = reader.read_snapshot()

    assert before.digest != after.digest


def test_i19_reader_fails_closed_when_allowlisted_column_is_missing():
    engine = _sqlite_i19_engine(omit_column=("t_meta_tagging", "target_key"))

    with pytest.raises(OperationalError):
        LegacyI19SourceReader(engine, sqlite_test_mode=True).read_snapshot()


def test_i19_reader_refuses_total_row_truncation():
    engine = _sqlite_i19_engine()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO t_meta_tag (id, name, cat, color, `desc`) "
            "VALUES (1, '核心', '业务', '#112233', '核心表')"
        )
        connection.exec_driver_sql(
            "INSERT INTO t_meta_tag (id, name, cat, color, `desc`) "
            "VALUES (2, '关键', '业务', '#445566', '关键表')"
        )

    with pytest.raises(RuntimeError, match="legacy I19 snapshot exceeded configured total row safety limit"):
        LegacyI19SourceReader(engine, sqlite_test_mode=True).read_snapshot(max_total_rows=1)


def test_i19_reader_rejects_invalid_limits_and_naive_capture_time():
    engine = _sqlite_i19_engine()
    reader = LegacyI19SourceReader(engine, sqlite_test_mode=True)

    with pytest.raises(ValueError, match="page_size"):
        reader.read_snapshot(page_size=0)
    with pytest.raises(ValueError, match="max_total_rows"):
        reader.read_snapshot(max_total_rows=0)
    with pytest.raises(ValueError, match="timezone-aware"):
        reader.read_snapshot(captured_at=datetime(2026, 10, 15, 1, 0))


def test_i19_reader_accepts_only_explicit_sqlite_test_mode_and_legacy_schema():
    sqlite_engine = _sqlite_i19_engine()
    with pytest.raises(ValueError, match="SQLite is allowed only for tests"):
        LegacyI19SourceReader(sqlite_engine)

    target_engine = create_engine("mysql+pymysql://reader:unused@127.0.0.1/datara_rebuild_i0")
    with pytest.raises(ValueError, match="must point to datara_meta"):
        LegacyI19SourceReader(target_engine)
