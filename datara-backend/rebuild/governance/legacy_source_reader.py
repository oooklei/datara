"""Allowlisted, read-only readers for the legacy I18-I20 source tables."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Mapping
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

LEGACY_SCHEMA = "datara_meta"
TARGET_SCHEMA = "datara_rebuild_i0"
LEGACY_SOURCE_URL_ENV = "REBUILD_LEGACY_META_URL"

# (primary key, selected columns). Keep this list aligned with the reviewed I18 source mapping.
I18_SOURCE_COLUMNS: dict[str, tuple[str, tuple[str, ...]]] = {
    "t_biz_domain": (
        "id",
        ("id", "name", "remark", "create_time", "update_time"),
    ),
    "t_dw_layer": (
        "code",
        ("code", "name", "rule", "color", "seq", "create_time", "update_time"),
    ),
    "t_engine_type": (
        "name",
        ("name", "ddl", "xc", "create_time", "update_time"),
    ),
    "t_dw_model": (
        "id",
        (
            "id",
            "code",
            "name",
            "layer",
            "type",
            "biz_domain",
            "engine",
            "ds_id",
            "db_name",
            "security_level",
            "status",
            "version",
            "er_pos",
            "last_ddl",
            "built_at",
            "built_by",
            "owner",
            "remark",
            "create_time",
            "update_time",
        ),
    ),
    "t_dw_model_field": (
        "id",
        (
            "id",
            "model_id",
            "seq",
            "name",
            "data_type",
            "length",
            "precision",
            "nullable",
            "default_value",
            "comment",
            "is_pk",
            "is_partition",
            "dict_ref",
            "create_time",
            "update_time",
        ),
    ),
    "t_dw_model_relation": (
        "id",
        (
            "id",
            "src_model_id",
            "tgt_model_id",
            "rel_type",
            "src_fields",
            "tgt_fields",
            "join_desc",
            "created_by",
            "create_time",
            "update_time",
        ),
    ),
    "t_dw_model_version": (
        "id",
        (
            "id",
            "model_id",
            "version",
            "snapshot_json",
            "change_note",
            "created_by",
            "create_time",
            "update_time",
        ),
    ),
}

# (primary key, selected columns). These I19 columns are derived from the
# retained legacy ORM declarations and still require live schema preflight.
I19_SOURCE_COLUMNS: dict[str, tuple[str, tuple[str, ...]]] = {
    "t_meta_table_ext": (
        "id",
        (
            "id",
            "ds_id",
            "db_name",
            "table_name",
            "biz_domain",
            "security_level",
            "owner",
            "remark",
            "create_time",
            "update_time",
        ),
    ),
    "t_meta_tag": (
        "id",
        ("id", "name", "cat", "color", "desc", "create_time", "update_time"),
    ),
    "t_meta_tagging": (
        "id",
        ("id", "tag_id", "target_type", "target_key", "created_by", "create_time"),
    ),
}

# Field contract from the retained legacy Indicator ORM; live schema still
# requires a version-bound read-only preflight before any source read/import.
I20_SOURCE_COLUMNS: dict[str, tuple[str, tuple[str, ...]]] = {
    "t_indicator": (
        "id",
        (
            "id",
            "code",
            "name",
            "type",
            "biz_domain",
            "biz_def",
            "tech_def",
            "src_kind",
            "src_ref",
            "src_field",
            "out_table",
            "out_task",
            "period",
            "dims",
            "unit",
            "status",
            "version",
            "owner",
            "base_metric_id",
            "agg_fn",
            "num_field",
            "time_field",
            "dim_field",
            "filter_cond",
            "create_time",
            "update_time",
        ),
    ),
    "t_indicator_version": (
        "id",
        ("id", "indicator_id", "version", "snapshot_json", "change_note", "created_by", "create_time"),
    ),
}


@dataclass(frozen=True)
class LegacyI18SourceSnapshot:
    schema: str
    captured_at: datetime
    digest: str
    counts: Mapping[str, int]
    rows: Mapping[str, tuple[Mapping[str, object], ...]]


class LegacyI18SourceReader:
    def __init__(self, engine: Engine, *, sqlite_test_mode: bool = False) -> None:
        self.engine = engine
        self.sqlite_test_mode = sqlite_test_mode
        backend = engine.dialect.name
        if backend == "mysql":
            database = engine.url.database
            if database != LEGACY_SCHEMA or database == TARGET_SCHEMA:
                raise ValueError(f"legacy source URL must point to {LEGACY_SCHEMA}")
        elif backend == "sqlite" and sqlite_test_mode:
            pass
        elif backend == "sqlite":
            raise ValueError("SQLite is allowed only for tests")
        else:
            raise ValueError("legacy I18 source reader supports MySQL only")

    @classmethod
    def from_runtime_env(cls) -> LegacyI18SourceReader:
        database_url = os.getenv(LEGACY_SOURCE_URL_ENV, "")
        if not database_url:
            raise RuntimeError(f"{LEGACY_SOURCE_URL_ENV} is not configured")
        parsed = make_url(database_url)
        if parsed.get_backend_name() != "mysql" or parsed.database != LEGACY_SCHEMA:
            raise ValueError(f"{LEGACY_SOURCE_URL_ENV} must point to MySQL schema {LEGACY_SCHEMA}")
        engine = create_engine(database_url, pool_pre_ping=True, hide_parameters=True)
        return cls(engine)

    def read_snapshot(
        self,
        *,
        page_size: int = 500,
        max_total_rows: int = 100_000,
        captured_at: datetime | None = None,
    ) -> LegacyI18SourceSnapshot:
        if not 1 <= page_size <= 10_000:
            raise ValueError("page_size must be between 1 and 10000")
        if max_total_rows < 1:
            raise ValueError("max_total_rows must be positive")
        captured_at = captured_at or datetime.now(ZoneInfo("Asia/Shanghai"))
        if captured_at.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware")

        all_rows: dict[str, tuple[Mapping[str, object], ...]] = {}
        total_read = 0
        connection = self.engine.connect()
        transaction = connection.begin()
        sqlite_query_only = self.engine.dialect.name == "sqlite"
        try:
            if sqlite_query_only:
                connection.exec_driver_sql("PRAGMA query_only = ON")
            else:
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            for table_name, (identity_column, columns) in I18_SOURCE_COLUMNS.items():
                table_rows = self._read_table(
                    connection,
                    table_name,
                    identity_column,
                    columns,
                    page_size,
                    max_total_rows - total_read,
                )
                total_read += len(table_rows)
                if total_read > max_total_rows:
                    raise RuntimeError(f"legacy I18 snapshot exceeded row safety limit {max_total_rows}")
                all_rows[table_name] = tuple(table_rows)
            transaction.rollback()
        except Exception:
            if transaction.is_active:
                transaction.rollback()
            raise
        finally:
            if sqlite_query_only and not connection.closed:
                connection.exec_driver_sql("PRAGMA query_only = OFF")
                connection.rollback()
            connection.close()

        payload = {
            "schema": LEGACY_SCHEMA,
            "captured_at": captured_at.isoformat(),
            "rows": {
                table: [_json_safe(row) for row in rows]
                for table, rows in all_rows.items()
            },
        }
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return LegacyI18SourceSnapshot(
            schema=LEGACY_SCHEMA,
            captured_at=captured_at,
            digest=digest,
            counts={table: len(rows) for table, rows in all_rows.items()},
            rows=all_rows,
        )

    def _read_table(
        self,
        connection,
        table_name,
        identity_column,
        columns,
        page_size,
        remaining_rows,
        source_label="I18",
    ):
        preparer = connection.dialect.identifier_preparer
        quoted_columns = ", ".join(preparer.quote(column) for column in columns)
        if self.engine.dialect.name == "mysql":
            table_ref = f"{preparer.quote_schema(LEGACY_SCHEMA)}.{preparer.quote(table_name)}"
        else:
            table_ref = preparer.quote(table_name)
        quoted_identity = preparer.quote(identity_column)
        rows: list[Mapping[str, object]] = []
        last_identity: object | None = None
        while True:
            where_clause = f" WHERE {quoted_identity} > :last_identity" if last_identity is not None else ""
            statement = text(
                f"SELECT {quoted_columns} FROM {table_ref}{where_clause} "
                f"ORDER BY {quoted_identity} LIMIT :page_size"
            )
            parameters = {"page_size": page_size}
            if last_identity is not None:
                parameters["last_identity"] = last_identity
            page = connection.execute(statement, parameters).mappings().all()
            if not page:
                break
            if len(rows) + len(page) > remaining_rows:
                raise RuntimeError(
                    f"legacy {source_label} snapshot exceeded configured total row safety limit"
                )
            rows.extend(dict(row) for row in page)
            last_identity = page[-1][identity_column]
            if len(page) < page_size:
                break
        return rows


@dataclass(frozen=True)
class LegacyI19SourceSnapshot:
    schema: str
    captured_at: datetime
    digest: str
    counts: Mapping[str, int]
    rows: Mapping[str, tuple[Mapping[str, object], ...]]


class LegacyI19SourceReader(LegacyI18SourceReader):
    """Read the fixed I19 metadata/tagging tables without opening a write path."""

    def read_snapshot(
        self,
        *,
        page_size: int = 500,
        max_total_rows: int = 100_000,
        captured_at: datetime | None = None,
    ) -> LegacyI19SourceSnapshot:
        if not 1 <= page_size <= 10_000:
            raise ValueError("page_size must be between 1 and 10000")
        if max_total_rows < 1:
            raise ValueError("max_total_rows must be positive")
        captured_at = captured_at or datetime.now(ZoneInfo("Asia/Shanghai"))
        if captured_at.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware")

        all_rows: dict[str, tuple[Mapping[str, object], ...]] = {}
        total_read = 0
        connection = self.engine.connect()
        transaction = connection.begin()
        sqlite_query_only = self.engine.dialect.name == "sqlite"
        try:
            if sqlite_query_only:
                connection.exec_driver_sql("PRAGMA query_only = ON")
            else:
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            for table_name, (identity_column, columns) in I19_SOURCE_COLUMNS.items():
                table_rows = self._read_table(
                    connection,
                    table_name,
                    identity_column,
                    columns,
                    page_size,
                    max_total_rows - total_read,
                    "I19",
                )
                total_read += len(table_rows)
                if total_read > max_total_rows:
                    raise RuntimeError(f"legacy I19 snapshot exceeded row safety limit {max_total_rows}")
                all_rows[table_name] = tuple(table_rows)
            transaction.rollback()
        except Exception:
            if transaction.is_active:
                transaction.rollback()
            raise
        finally:
            if sqlite_query_only and not connection.closed:
                connection.exec_driver_sql("PRAGMA query_only = OFF")
                connection.rollback()
            connection.close()

        payload = {
            "schema": LEGACY_SCHEMA,
            "rows": {
                table: [_json_safe(row) for row in rows]
                for table, rows in all_rows.items()
            },
        }
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return LegacyI19SourceSnapshot(
            schema=LEGACY_SCHEMA,
            captured_at=captured_at,
            digest=digest,
            counts={table: len(rows) for table, rows in all_rows.items()},
            rows=all_rows,
        )


@dataclass(frozen=True)
class LegacyI20SourceSnapshot:
    schema: str
    captured_at: datetime
    digest: str
    counts: Mapping[str, int]
    rows: Mapping[str, tuple[Mapping[str, object], ...]]


class LegacyI20SourceReader(LegacyI18SourceReader):
    """Read fixed I20 metric definition/version columns without interpretation."""

    def read_snapshot(
        self,
        *,
        page_size: int = 500,
        max_total_rows: int = 100_000,
        captured_at: datetime | None = None,
    ) -> LegacyI20SourceSnapshot:
        if not 1 <= page_size <= 10_000:
            raise ValueError("page_size must be between 1 and 10000")
        if max_total_rows < 1:
            raise ValueError("max_total_rows must be positive")
        captured_at = captured_at or datetime.now(ZoneInfo("Asia/Shanghai"))
        if captured_at.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware")

        all_rows: dict[str, tuple[Mapping[str, object], ...]] = {}
        total_read = 0
        connection = self.engine.connect()
        transaction = connection.begin()
        sqlite_query_only = self.engine.dialect.name == "sqlite"
        try:
            if sqlite_query_only:
                connection.exec_driver_sql("PRAGMA query_only = ON")
            else:
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            for table_name, (identity_column, columns) in I20_SOURCE_COLUMNS.items():
                table_rows = self._read_table(
                    connection,
                    table_name,
                    identity_column,
                    columns,
                    page_size,
                    max_total_rows - total_read,
                    "I20",
                )
                total_read += len(table_rows)
                if total_read > max_total_rows:
                    raise RuntimeError(f"legacy I20 snapshot exceeded row safety limit {max_total_rows}")
                all_rows[table_name] = tuple(table_rows)
            transaction.rollback()
        except Exception:
            if transaction.is_active:
                transaction.rollback()
            raise
        finally:
            if sqlite_query_only and not connection.closed:
                connection.exec_driver_sql("PRAGMA query_only = OFF")
                connection.rollback()
            connection.close()

        payload = {
            "schema": LEGACY_SCHEMA,
            "rows": {
                table: [_json_safe(row) for row in rows]
                for table, rows in all_rows.items()
            },
        }
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return LegacyI20SourceSnapshot(
            schema=LEGACY_SCHEMA,
            captured_at=captured_at,
            digest=digest,
            counts={table: len(rows) for table, rows in all_rows.items()},
            rows=all_rows,
        )


def _json_safe(value: object) -> object:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    return value
