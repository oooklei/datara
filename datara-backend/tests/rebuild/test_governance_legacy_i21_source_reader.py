from datetime import datetime, timezone

import pytest
from sqlalchemy import Column, DateTime, Float, Integer, MetaData, String, Table, create_engine, event
from sqlalchemy.exc import OperationalError

from rebuild.governance.legacy_source_reader import I21_SOURCE_COLUMNS, LegacyI21SourceReader


def _sqlite_i21_engine(*, omit_column: tuple[str, str] | None = None):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    integer_fields = {"id", "task_id", "run_id", "rule_id", "hit_count"}
    float_fields = {"threshold", "score"}
    bool_fields = {"enabled"}
    time_fields = {
        "create_time",
        "update_time",
        "started_at",
        "finished_at",
        "handled_at",
        "last_run_at",
        "last_fired_at",
    }
    for table_name, (identity_field, columns) in I21_SOURCE_COLUMNS.items():
        table_columns = []
        for name in columns:
            if omit_column == (table_name, name):
                continue
            if name in integer_fields:
                column_type = Integer
            elif name in float_fields:
                column_type = Float
            elif name in bool_fields:
                column_type = Integer
            elif name in time_fields:
                column_type = DateTime
            else:
                column_type = String(4096)
            table_columns.append(Column(name, column_type, primary_key=name == identity_field))
        Table(table_name, metadata, *table_columns)
    metadata.create_all(engine)
    return engine


def test_i21_reader_reads_all_six_allowlisted_tables_read_only_and_preserves_json_payloads():
    engine = _sqlite_i21_engine()
    with engine.begin() as connection:
        for table_name in I21_SOURCE_COLUMNS:
            connection.exec_driver_sql(f"INSERT INTO {table_name} (id) VALUES (1)")
        connection.exec_driver_sql(
            "UPDATE t_qc_rule SET params_json = '{\"min\":1}' WHERE id = 1"
        )
        connection.exec_driver_sql(
            "UPDATE t_qc_run SET stats_json = '{\"rows\":4}' WHERE id = 1"
        )
        connection.exec_driver_sql(
            "UPDATE t_qc_report SET content_json = '{\"summary\":\"raw\"}' WHERE id = 1"
        )

    statements: list[str] = []

    def enforce_read_only(_connection, _cursor, statement, *_args):
        verb = statement.lstrip().split(None, 1)[0].upper()
        statements.append(verb)
        assert verb in {"SELECT", "PRAGMA"}

    event.listen(engine, "before_cursor_execute", enforce_read_only)
    snapshot = LegacyI21SourceReader(engine, sqlite_test_mode=True).read_snapshot(page_size=1)

    assert snapshot.schema == "datara_meta"
    assert set(snapshot.rows) == set(I21_SOURCE_COLUMNS)
    assert all(snapshot.counts[table_name] == 1 for table_name in I21_SOURCE_COLUMNS)
    assert snapshot.rows["t_qc_rule"][0]["params_json"] == '{"min":1}'
    assert snapshot.rows["t_qc_run"][0]["stats_json"] == '{"rows":4}'
    assert snapshot.rows["t_qc_report"][0]["content_json"] == '{"summary":"raw"}'
    assert len(snapshot.digest) == 64
    assert statements and set(statements) == {"SELECT", "PRAGMA"}


def test_i21_reader_empty_snapshot_digest_ignores_capture_time():
    reader = LegacyI21SourceReader(_sqlite_i21_engine(), sqlite_test_mode=True)
    first = reader.read_snapshot(captured_at=datetime(2026, 10, 15, 1, tzinfo=timezone.utc))
    second = reader.read_snapshot(captured_at=datetime(2026, 10, 15, 2, tzinfo=timezone.utc))

    assert all(count == 0 for count in first.counts.values())
    assert first.captured_at != second.captured_at
    assert first.digest == second.digest


def test_i21_reader_digest_changes_with_source_content():
    engine = _sqlite_i21_engine()
    reader = LegacyI21SourceReader(engine, sqlite_test_mode=True)
    before = reader.read_snapshot()
    with engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO t_qc_rule (id, name) VALUES (1, 'not-null')")
    after = reader.read_snapshot()

    assert before.digest != after.digest


def test_i21_reader_fails_closed_when_an_allowlisted_column_is_missing():
    engine = _sqlite_i21_engine(omit_column=("t_qc_task", "rule_ids"))

    with pytest.raises(OperationalError):
        LegacyI21SourceReader(engine, sqlite_test_mode=True).read_snapshot()


def test_i21_reader_refuses_total_row_truncation():
    engine = _sqlite_i21_engine()
    with engine.begin() as connection:
        connection.exec_driver_sql("INSERT INTO t_qc_rule (id) VALUES (1), (2)")

    with pytest.raises(RuntimeError, match="legacy I21 snapshot exceeded configured total row safety limit"):
        LegacyI21SourceReader(engine, sqlite_test_mode=True).read_snapshot(max_total_rows=1)


def test_i21_reader_rejects_invalid_limits_and_naive_timestamp():
    reader = LegacyI21SourceReader(_sqlite_i21_engine(), sqlite_test_mode=True)

    with pytest.raises(ValueError, match="page_size"):
        reader.read_snapshot(page_size=0)
    with pytest.raises(ValueError, match="max_total_rows"):
        reader.read_snapshot(max_total_rows=0)
    with pytest.raises(ValueError, match="timezone-aware"):
        reader.read_snapshot(captured_at=datetime(2026, 10, 15, 1))


def test_i21_reader_requires_explicit_sqlite_test_mode_and_rejects_target_schema():
    sqlite_engine = _sqlite_i21_engine()
    with pytest.raises(ValueError, match="SQLite is allowed only for tests"):
        LegacyI21SourceReader(sqlite_engine)

    target_engine = create_engine("mysql+pymysql://reader:unused@127.0.0.1/datara_rebuild_i0")
    with pytest.raises(ValueError, match="must point to datara_meta"):
        LegacyI21SourceReader(target_engine)
