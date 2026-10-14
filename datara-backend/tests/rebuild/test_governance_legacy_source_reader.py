from datetime import datetime, timezone

import pytest
from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table, create_engine, event

from rebuild.governance.legacy_source_reader import I18_SOURCE_COLUMNS, LegacyI18SourceReader


def _sqlite_source_engine():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    integer_fields = {"id", "model_id", "seq", "version", "ds_id"}
    boolean_fields = {"nullable", "is_pk", "is_partition", "xc"}
    time_fields = {"create_time", "update_time", "built_at"}
    for table_name, (identity_field, columns) in I18_SOURCE_COLUMNS.items():
        table_columns = []
        for name in columns:
            if name in integer_fields:
                column_type = Integer
            elif name in boolean_fields:
                column_type = Boolean
            elif name in time_fields:
                column_type = DateTime
            else:
                column_type = String(2048)
            table_columns.append(Column(name, column_type, primary_key=name == identity_field))
        Table(table_name, metadata, *table_columns)
    metadata.create_all(engine)
    return engine


def test_source_reader_reads_only_fixed_i18_columns_and_pages_without_truncating():
    engine = _sqlite_source_engine()
    captured_at = datetime(2026, 10, 12, 22, 25, 28, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO t_dw_model (id, code, name, layer, type, biz_domain, engine) "
            "VALUES (17, 'orders', '订单', 'DWD', '明细表', '交易', 'Doris')"
        )
        connection.exec_driver_sql(
            "INSERT INTO t_dw_model (id, code, name, layer, type, biz_domain, engine) "
            "VALUES (18, 'users', '用户', 'DWD', '维度表', '交易', 'Doris')"
        )
        connection.exec_driver_sql(
            "INSERT INTO t_dw_model_field (id, model_id, seq, name) VALUES (29, 17, 1, 'order_id')"
        )

    statements = []

    def record_read_only_sql(_connection, _cursor, statement, *_args):
        verb = statement.lstrip().split(None, 1)[0].upper()
        statements.append(verb)
        assert verb in {"SELECT", "PRAGMA"}

    event.listen(engine, "before_cursor_execute", record_read_only_sql)
    snapshot = LegacyI18SourceReader(engine, sqlite_test_mode=True).read_snapshot(
        page_size=1,
        max_total_rows=20,
        captured_at=captured_at,
    )

    assert snapshot.schema == "datara_meta"
    assert snapshot.counts["t_dw_model"] == 2
    assert snapshot.counts["t_dw_model_field"] == 1
    assert snapshot.rows["t_dw_model"][0]["id"] == 17
    assert snapshot.rows["t_dw_model"][1]["id"] == 18
    assert snapshot.captured_at == captured_at
    assert len(snapshot.digest) == 64
    assert statements and set(statements) == {"SELECT", "PRAGMA"}


def test_source_reader_rejects_non_legacy_schema_and_requires_explicit_sqlite_test_mode():
    target_engine = create_engine("mysql+pymysql://reader:unused@127.0.0.1/datara_rebuild_i0")
    with pytest.raises(ValueError, match="must point to datara_meta"):
        LegacyI18SourceReader(target_engine)

    sqlite_engine = _sqlite_source_engine()
    with pytest.raises(ValueError, match="SQLite is allowed only for tests"):
        LegacyI18SourceReader(sqlite_engine)


def test_runtime_reader_requires_dedicated_legacy_meta_url(monkeypatch):
    monkeypatch.delenv("REBUILD_LEGACY_META_URL", raising=False)
    with pytest.raises(RuntimeError, match="REBUILD_LEGACY_META_URL is not configured"):
        LegacyI18SourceReader.from_runtime_env()

    monkeypatch.setenv("REBUILD_LEGACY_META_URL", "mysql+pymysql://reader:unused@127.0.0.1/ec_retail")
    with pytest.raises(ValueError, match="must point to MySQL schema datara_meta"):
        LegacyI18SourceReader.from_runtime_env()


def test_source_reader_refuses_silent_row_truncation():
    engine = _sqlite_source_engine()
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO t_dw_model (id, code, name, layer, type, biz_domain, engine) "
            "VALUES (17, 'orders', '订单', 'DWD', '明细表', '交易', 'Doris')"
        )
        connection.exec_driver_sql(
            "INSERT INTO t_dw_model (id, code, name, layer, type, biz_domain, engine) "
            "VALUES (18, 'users', '用户', 'DWD', '维度表', '交易', 'Doris')"
        )

    with pytest.raises(RuntimeError, match="legacy I18 snapshot exceeded configured total row safety limit"):
        LegacyI18SourceReader(engine, sqlite_test_mode=True).read_snapshot(
            page_size=1,
            max_total_rows=1,
        )
