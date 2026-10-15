"""Read-only metadata browser for registered MySQL project data sources."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pymysql

from rebuild.datasource.contracts import DataSourceDraft, validate_datasource

MAX_PAGE_SIZE = 200
MAX_COLUMN_COUNT = 500
SYSTEM_SCHEMAS = ("information_schema", "mysql", "performance_schema", "sys")


def _connect(draft: DataSourceDraft):
    return pymysql.connect(
        host=draft.host,
        port=draft.port,
        user=draft.username,
        password=draft.password,
        database=draft.database,
        connect_timeout=3,
        read_timeout=5,
        write_timeout=3,
        autocommit=False,
    )


class MySQLMetadataCatalog:
    """Queries visible catalog objects through a bounded read-only transaction."""

    def __init__(self, draft: DataSourceDraft, *, connector: Callable[[DataSourceDraft], Any] = _connect):
        self._draft = draft
        self._connector = connector

    def schemas(self, *, after: str | None = None, limit: int = 100) -> list[str]:
        self._ensure_mysql()
        bounded_limit = _page_size(limit)
        query = """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT IN (%s, %s, %s, %s)
        """
        parameters: tuple[Any, ...] = SYSTEM_SCHEMAS
        if after is not None:
            query += " AND schema_name > %s"
            parameters += (after,)
        query += " ORDER BY schema_name LIMIT %s"
        parameters += (bounded_limit + 1,)
        return [str(row[0]) for row in self._query(query, parameters)]

    def objects(self, schema: str, *, after: str | None = None, limit: int = 100) -> list[dict[str, str]]:
        self._ensure_mysql()
        bounded_limit = _page_size(limit)
        query = """
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = %s AND table_type IN ('BASE TABLE', 'VIEW')
        """
        parameters: tuple[Any, ...] = (schema,)
        if after is not None:
            query += " AND table_name > %s"
            parameters += (after,)
        query += " ORDER BY table_name LIMIT %s"
        parameters += (bounded_limit + 1,)
        return [
            {"schema": schema, "name": str(name), "type": "view" if kind == "VIEW" else "table"}
            for name, kind in self._query(query, parameters)
        ]

    def columns(self, schema: str, object_name: str, *, limit: int = MAX_COLUMN_COUNT) -> list[dict[str, Any]]:
        self._ensure_mysql()
        bounded_limit = min(max(int(limit), 1), MAX_COLUMN_COUNT)
        query = """
            SELECT column_name, data_type, column_type, is_nullable, column_key, column_comment
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position LIMIT %s
        """
        rows = self._query(query, (schema, object_name, bounded_limit + 1))
        return [
            {
                "schema": schema,
                "object": object_name,
                "name": str(name),
                "data_type": str(data_type),
                "database_type": str(database_type),
                "nullable": is_nullable == "YES",
                "primary_key": column_key == "PRI",
                "comment": str(comment or ""),
            }
            for name, data_type, database_type, is_nullable, column_key, comment in rows
        ]

    def _ensure_mysql(self) -> None:
        validate_datasource(self._draft)
        if self._draft.kind.lower() != "mysql":
            raise ValueError("metadata browsing currently supports mysql only")

    def _query(self, statement: str, parameters: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        connection = self._connector(self._draft)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                connection.begin()
                cursor.execute(statement, parameters)
                return list(cursor.fetchall())
        finally:
            try:
                connection.rollback()
            finally:
                connection.close()


class PostgreSQLMetadataCatalog:
    """Queries PostgreSQL's visible catalog through parameterized read-only statements."""

    def __init__(self, draft: DataSourceDraft, *, connector: Callable[[DataSourceDraft], Any]):
        self._draft = draft
        self._connector = connector

    def schemas(self, *, after: str | None = None, limit: int = 100) -> list[str]:
        self._ensure_postgresql()
        query = """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT IN ('information_schema', 'pg_catalog')
              AND schema_name NOT LIKE 'pg_toast%%'
              AND schema_name NOT LIKE 'pg_temp_%%'
        """
        parameters: tuple[Any, ...] = ()
        if after is not None:
            query += " AND schema_name > %s"
            parameters += (after,)
        query += " ORDER BY schema_name LIMIT %s"
        parameters += (_page_size(limit) + 1,)
        return [str(row[0]) for row in self._query(query, parameters)]

    def objects(self, schema: str, *, after: str | None = None, limit: int = 100) -> list[dict[str, str]]:
        self._ensure_postgresql()
        query = """
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = %s AND table_type IN ('BASE TABLE', 'VIEW')
        """
        parameters: tuple[Any, ...] = (schema,)
        if after is not None:
            query += " AND table_name > %s"
            parameters += (after,)
        query += " ORDER BY table_name LIMIT %s"
        parameters += (_page_size(limit) + 1,)
        return [
            {"schema": schema, "name": str(name), "type": "view" if kind == "VIEW" else "table"}
            for name, kind in self._query(query, parameters)
        ]

    def columns(self, schema: str, object_name: str, *, limit: int = MAX_COLUMN_COUNT) -> list[dict[str, Any]]:
        self._ensure_postgresql()
        bounded_limit = min(max(int(limit), 1), MAX_COLUMN_COUNT)
        query = """
            SELECT c.column_name, c.data_type, c.udt_name, c.is_nullable,
                EXISTS (
                    SELECT 1
                    FROM information_schema.table_constraints tc
                    JOIN information_schema.key_column_usage kcu
                      USING (constraint_catalog, constraint_schema, constraint_name)
                    WHERE tc.constraint_type = 'PRIMARY KEY'
                      AND tc.table_schema = c.table_schema
                      AND tc.table_name = c.table_name
                      AND kcu.column_name = c.column_name
                ) AS is_primary_key,
                pg_catalog.col_description(
                    pg_catalog.to_regclass(
                        pg_catalog.quote_ident(c.table_schema) || '.' || pg_catalog.quote_ident(c.table_name)
                    )::oid,
                    c.ordinal_position
                ) AS column_comment
            FROM information_schema.columns c
            WHERE c.table_schema = %s AND c.table_name = %s
            ORDER BY c.ordinal_position LIMIT %s
        """
        rows = self._query(query, (schema, object_name, bounded_limit + 1))
        return [
            {
                "schema": schema,
                "object": object_name,
                "name": str(name),
                "data_type": str(data_type),
                "database_type": str(database_type),
                "nullable": nullable == "YES",
                "primary_key": bool(primary_key),
                "comment": comment or "",
            }
            for name, data_type, database_type, nullable, primary_key, comment in rows
        ]

    def _ensure_postgresql(self) -> None:
        validate_datasource(self._draft)
        if self._draft.kind.lower() != "postgresql":
            raise ValueError("PostgreSQL metadata browsing requires a postgresql datasource")

    def _query(self, statement: str, parameters: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        connection = self._connector(self._draft)
        try:
            with connection.cursor() as cursor:
                cursor.execute("BEGIN READ ONLY")
                cursor.execute(statement, parameters)
                return list(cursor.fetchall())
        finally:
            try:
                connection.rollback()
            finally:
                connection.close()


def metadata_catalog_for(
    draft: DataSourceDraft, *, connector: Callable[[DataSourceDraft], Any]
) -> MySQLMetadataCatalog | PostgreSQLMetadataCatalog:
    """Select the dialect catalog without changing the shared API contract."""
    kind = draft.kind.lower()
    if kind == "mysql":
        return MySQLMetadataCatalog(draft, connector=connector)
    if kind == "postgresql":
        return PostgreSQLMetadataCatalog(draft, connector=connector)
    raise ValueError(f"metadata browsing does not support datasource kind: {draft.kind}")


def _page_size(value: int) -> int:
    return min(max(int(value), 1), MAX_PAGE_SIZE)
