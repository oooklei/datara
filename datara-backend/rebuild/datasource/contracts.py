"""I1 数据源草稿校验和能力矩阵。"""

from dataclasses import dataclass
from typing import Any

import pymysql


@dataclass(frozen=True)
class DataSourceDraft:
    name: str
    kind: str
    host: str
    port: int
    database: str
    username: str
    password: str = ""


@dataclass(frozen=True)
class ValidatedDataSource:
    draft: DataSourceDraft
    capabilities: set[str]


def validate_datasource(draft: DataSourceDraft) -> ValidatedDataSource:
    for field in ("name", "kind", "host", "database", "username"):
        if not getattr(draft, field).strip():
            raise ValueError(f"{field} is required")
    if not 1 <= draft.port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    capability_map = {
        "mysql": {"query", "metadata", "cross_schema"},
        "postgresql": {"query", "metadata", "cross_schema"},
    }
    capabilities = capability_map.get(draft.kind.lower())
    if capabilities is None:
        raise ValueError(f"unsupported datasource kind: {draft.kind}")
    return ValidatedDataSource(draft=draft, capabilities=set(capabilities))


def probe_datasource(draft: DataSourceDraft) -> dict[str, Any]:
    """Open a short-lived MySQL connection and return a small runtime probe."""
    validated = validate_datasource(draft)
    if draft.kind.lower() != "mysql":
        raise ValueError("runtime probe currently supports mysql only")
    connection = pymysql.connect(
        host=draft.host,
        port=draft.port,
        user=draft.username,
        password=draft.password,
        database=draft.database,
        connect_timeout=3,
        read_timeout=3,
        write_timeout=3,
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE(), VERSION()")
            database, version = cursor.fetchone()
        return {
            "connected": True,
            "database": database,
            "server_version": version,
            "capabilities": sorted(validated.capabilities),
        }
    finally:
        connection.close()

