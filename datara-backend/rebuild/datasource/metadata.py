"""Read-only metadata browser for registered MySQL project data sources."""

from __future__ import annotations

from collections.abc import Callable
import re
from typing import Any

import pymysql

from rebuild.datasource.contracts import DataSourceDraft, validate_datasource

MAX_PAGE_SIZE = 200
MAX_COLUMN_COUNT = 500
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
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

    def objects(
        self, schema: str, *, kind: str | None = None, after: str | None = None, limit: int = 100
    ) -> list[dict[str, str]]:
        self._ensure_mysql()
        bounded_limit = _page_size(limit)
        query = """
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = %s AND table_type IN ('BASE TABLE', 'VIEW')
        """
        parameters: tuple[Any, ...] = (schema,)
        if kind == "table":
            query += " AND table_type = 'BASE TABLE'"
        elif kind == "view":
            query += " AND table_type = 'VIEW'"
        if after is not None:
            query += " AND table_name > %s"
            parameters += (after,)
        query += " ORDER BY table_name LIMIT %s"
        parameters += (bounded_limit + 1,)
        return [
            {"schema": schema, "name": str(name), "type": "view" if table_type == "VIEW" else "table"}
            for name, table_type in self._query(query, parameters)
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

    def indexes(self, schema: str, object_name: str, *, limit: int = 200) -> list[dict[str, Any]]:
        self._ensure_mysql()
        rows = self._query(
            "SELECT index_name, column_name, non_unique, seq_in_index "
            "FROM information_schema.statistics WHERE table_schema=%s AND table_name=%s "
            "ORDER BY index_name, seq_in_index LIMIT %s",
            (schema, object_name, _page_size(limit)),
        )
        return [{"schema": schema, "object": object_name, "name": str(name), "column": str(column),
                 "unique": not bool(non_unique), "position": int(position)}
                for name, column, non_unique, position in rows]

    def routines(
        self, schema: str, *, kind: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        self._ensure_mysql()
        if kind == "trigger":
            return self.triggers(schema, limit=limit)
        if kind == "event":
            return self.events(schema, limit=limit)
        query = (
            "SELECT routine_name, routine_type, data_type FROM information_schema.routines "
            "WHERE routine_schema=%s"
        )
        parameters: tuple[Any, ...] = (schema,)
        if kind == "function":
            query += " AND routine_type = 'FUNCTION'"
        elif kind == "procedure":
            query += " AND routine_type = 'PROCEDURE'"
        query += " ORDER BY routine_name LIMIT %s"
        parameters += (_page_size(limit),)
        rows = self._query(query, parameters)
        return [{"schema": schema, "name": str(name), "type": str(kind).lower(), "returnType": str(data_type or "")}
                for name, kind, data_type in rows]

    def triggers(self, schema: str, *, limit: int = 200) -> list[dict[str, Any]]:
        self._ensure_mysql()
        rows = self._query(
            "SELECT trigger_name, event_manipulation, event_object_table FROM information_schema.triggers "
            "WHERE trigger_schema=%s ORDER BY trigger_name LIMIT %s", (schema, _page_size(limit))
        )
        return [{"schema": schema, "name": str(name), "type": "trigger",
                 "event": str(event or ""), "table": str(table or "")}
                for name, event, table in rows]

    def events(self, schema: str, *, limit: int = 200) -> list[dict[str, Any]]:
        self._ensure_mysql()
        rows = self._query(
            "SELECT event_name FROM information_schema.events "
            "WHERE event_schema=%s ORDER BY event_name LIMIT %s", (schema, _page_size(limit))
        )
        return [{"schema": schema, "name": str(name), "type": "event"} for (name,) in rows]

    _SHOW_CREATE = {
        "table": "TABLE", "view": "VIEW", "function": "FUNCTION",
        "procedure": "PROCEDURE", "trigger": "TRIGGER", "event": "EVENT",
    }

    def definition(self, schema: str, object_name: str, *, kind: str | None = None) -> str:
        self._ensure_mysql()
        _validate_identifier(schema); _validate_identifier(object_name)
        target = self._SHOW_CREATE.get(str(kind or "table").lower(), "TABLE")
        rows = self._query(f"SHOW CREATE {target} `{schema}`.`{object_name}`", ())
        if not rows:
            raise ValueError("object definition not found")
        for value in rows[0]:
            text = str(value or "")
            if text.lstrip().upper().startswith("CREATE "):
                return text
        raise ValueError("object definition not found")

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

    def objects(
        self, schema: str, *, kind: str | None = None, after: str | None = None, limit: int = 100
    ) -> list[dict[str, str]]:
        self._ensure_postgresql()
        query = """
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = %s AND table_type IN ('BASE TABLE', 'VIEW')
        """
        parameters: tuple[Any, ...] = (schema,)
        if kind == "table":
            query += " AND table_type = 'BASE TABLE'"
        elif kind == "view":
            query += " AND table_type = 'VIEW'"
        if after is not None:
            query += " AND table_name > %s"
            parameters += (after,)
        query += " ORDER BY table_name LIMIT %s"
        parameters += (_page_size(limit) + 1,)
        return [
            {"schema": schema, "name": str(name), "type": "view" if table_type == "VIEW" else "table"}
            for name, table_type in self._query(query, parameters)
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

    def indexes(self, schema: str, object_name: str, *, limit: int = 200) -> list[dict[str, Any]]:
        self._ensure_postgresql()
        rows = self._query(
            "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname=%s AND tablename=%s "
            "ORDER BY indexname LIMIT %s", (schema, object_name, _page_size(limit))
        )
        return [{"schema": schema, "object": object_name, "name": str(name), "definition": str(definition)}
                for name, definition in rows]

    def routines(
        self, schema: str, *, kind: str | None = None, limit: int = 200
    ) -> list[dict[str, Any]]:
        self._ensure_postgresql()
        if kind == "trigger":
            return self.triggers(schema, limit=limit)
        if kind == "event":
            return []
        query = (
            "SELECT routine_name, routine_type, data_type FROM information_schema.routines "
            "WHERE routine_schema=%s"
        )
        parameters: tuple[Any, ...] = (schema,)
        if kind == "function":
            query += " AND routine_type = 'FUNCTION'"
        elif kind == "procedure":
            query += " AND routine_type = 'PROCEDURE'"
        query += " ORDER BY routine_name LIMIT %s"
        parameters += (_page_size(limit),)
        rows = self._query(query, parameters)
        return [{"schema": schema, "name": str(name), "type": str(kind).lower(), "returnType": str(data_type or "")}
                for name, kind, data_type in rows]

    def triggers(self, schema: str, *, limit: int = 200) -> list[dict[str, Any]]:
        self._ensure_postgresql()
        rows = self._query(
            "SELECT trigger_name, event_manipulation, event_object_table FROM information_schema.triggers "
            "WHERE trigger_schema=%s ORDER BY trigger_name LIMIT %s", (schema, _page_size(limit))
        )
        return [{"schema": schema, "name": str(name), "type": "trigger",
                 "event": str(event or ""), "table": str(table or "")}
                for name, event, table in rows]

    def definition(self, schema: str, object_name: str, *, kind: str | None = None) -> str:
        self._ensure_postgresql()
        _validate_identifier(schema); _validate_identifier(object_name)
        normalized = str(kind or "").lower()
        if normalized in {"function", "procedure"}:
            rows = self._query(
                "SELECT pg_get_functiondef(p.oid) FROM pg_proc p "
                "JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = %s AND p.proname = %s LIMIT 1",
                (schema, object_name),
            )
            if rows and rows[0][0]:
                return str(rows[0][0])
            raise ValueError("object definition not found")
        if normalized == "trigger":
            rows = self._query(
                "SELECT pg_get_triggerdef(t.oid) FROM pg_trigger t "
                "JOIN pg_class c ON c.oid = t.tgrelid "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = %s AND t.tgname = %s LIMIT 1",
                (schema, object_name),
            )
            if rows and rows[0][0]:
                return str(rows[0][0])
            raise ValueError("object definition not found")
        rows = self._query(
            "SELECT pg_get_viewdef(to_regclass(format('%I.%I', %s, %s)), true)",
            (schema, object_name),
        )
        if rows and rows[0][0]:
            return str(rows[0][0])
        columns = self.columns(schema, object_name)
        if not columns:
            raise ValueError("object definition not found")
        return "CREATE TABLE %s.%s (%s);" % (
            schema, object_name,
            ", ".join(f"{c['name']} {c['database_type']}" for c in columns),
        )

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


def _validate_identifier(value: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError("metadata identifier is invalid")
