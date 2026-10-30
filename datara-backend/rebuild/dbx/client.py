"""Server-side dbx API adapter.

The adapter only sends connection IDs. Database credentials must remain in dbx.
All calls use an internal token; a missing token fails closed before any HTTP
request. The dbx Web server must implement the matching internal trust channel
before this adapter can be used in deployment.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any


Transport = Callable[[str, str, bytes | None, dict[str, str], float], Any]


class DbxError(RuntimeError):
    """A dbx request failed without exposing connection or token secrets."""

    def __init__(self, status: int | None = None):
        super().__init__(f"dbx request failed ({status if status is not None else 'network'})")
        self.status = status


def _default_transport(method: str, url: str, body: bytes | None, headers: dict[str, str], timeout: float) -> Any:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


class DbxClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        internal_token: str | None = None,
        transport: Transport | None = None,
        timeout: float = 15.0,
        retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = (base_url or os.getenv("DBX_BASE_URL", "http://192.168.1.9:4224/ide")).rstrip("/")
        self.internal_token = internal_token if internal_token is not None else os.getenv("DBX_INTERNAL_TOKEN", "")
        self.transport = transport or _default_transport
        self.timeout = timeout
        self.retries = retries
        self.sleep = sleep

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None, payload: dict[str, Any] | None = None, prefix: str = "api") -> Any:
        if not self.internal_token:
            raise DbxError(503)
        query = urllib.parse.urlencode({key: value for key, value in (params or {}).items() if value is not None})
        url = f"{self.base_url}/{prefix}/{path.lstrip('/')}" + (f"?{query}" if query else "")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json", "X-Datara-Internal-Token": self.internal_token}
        if body is not None:
            headers["Content-Type"] = "application/json"
        # A timed-out POST can already have changed data upstream; replaying it
        # could run a SQL statement or save a connection twice.
        attempts = self.retries + 1 if method == "GET" else 1
        for attempt in range(attempts):
            try:
                return self.transport(method, url, body, headers, self.timeout)
            except urllib.error.HTTPError as exc:
                if attempt == attempts - 1 or exc.code not in (429, 502, 503, 504):
                    raise DbxError(exc.code) from None
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt == attempts - 1:
                    raise DbxError() from None
            self.sleep(0.2 * (2**attempt))
        raise DbxError()

    def open_stream(self, path: str, payload: dict[str, Any]) -> Any:
        """Open one authenticated DBX SSE response without replaying a POST."""
        if not self.internal_token:
            raise DbxError(503)
        if path not in {"ai/stream", "ai/agent-stream"}:
            raise ValueError("unsupported DBX stream")
        request = urllib.request.Request(
            f"{self.base_url}/api/{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Accept": "text/event-stream",
                "Content-Type": "application/json",
                "X-Datara-Internal-Token": self.internal_token,
            },
            method="POST",
        )
        try:
            return urllib.request.urlopen(request, timeout=300)
        except urllib.error.HTTPError as exc:
            raise DbxError(exc.code) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise DbxError() from None

    def list_connections(self) -> list[dict[str, Any]]:
        result = self._request("GET", "connection/list")
        if not isinstance(result, list):
            raise DbxError()
        return [item for item in result if isinstance(item, dict)]

    def internal_connection(self, connection_id: str) -> dict[str, Any]:
        """Read resolved credentials through DBX's token-guarded internal endpoint."""
        if not connection_id:
            raise ValueError("connection_id is required")
        encoded_id = urllib.parse.quote(connection_id, safe="")
        result = self._request("GET", f"connection/{encoded_id}/params", prefix="internal")
        if not isinstance(result, dict):
            raise DbxError()
        return result

    def save_connection(self, config: dict[str, Any]) -> Any:
        return self._request("POST", "connection/save", payload={"configs": [config], "removedIds": []})

    def remove_connection(self, connection_id: str) -> Any:
        return self._request("POST", "connection/save", payload={"configs": [], "removedIds": [connection_id]})

    def test_connection(self, config: dict[str, Any]) -> Any:
        return self._request("POST", "connection/test", payload={"config": config})

    def list_databases(self, connection_id: str) -> list[dict[str, Any]]:
        return self._request("GET", "schema/databases", params={"connection_id": connection_id})

    def list_schemas(self, connection_id: str, database: str) -> list[str]:
        return self._request("GET", "schema/schemas", params={"connection_id": connection_id, "database": database})

    def list_objects(self, connection_id: str, database: str, schema: str) -> list[dict[str, Any]]:
        return self._request("GET", "schema/objects", params={"connection_id": connection_id, "database": database, "schema": schema})

    def list_columns(self, connection_id: str, database: str, schema: str, table: str) -> list[dict[str, Any]]:
        return self._request("GET", "schema/columns", params={"connection_id": connection_id, "database": database, "schema": schema, "table": table})

    def search_history(self, *, started_at: str, ended_at: str, cursor: dict[str, str] | None = None, limit: int = 200, connection_ids: set[str] | None = None) -> dict[str, Any]:
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        return self._request("POST", "history/search", payload={
            "search_text": "", "connections": [{"connection_id": connection_id} for connection_id in sorted(connection_ids)] if connection_ids is not None else [], "databases": [],
            "started_at": started_at, "ended_at": ended_at,
            "cursor": cursor, "limit": limit,
        })

    def execute_sql(self, *, connection_id: str, database: str, sql: str, schema: str | None = None, max_rows: int | None = None) -> dict[str, Any]:
        if not connection_id or not database or not sql.strip():
            raise ValueError("connection_id, database and sql are required")
        payload: dict[str, Any] = {"connectionId": connection_id, "database": database, "sql": sql}
        if schema is not None:
            payload["schema"] = schema
        if max_rows is not None:
            payload["maxRows"] = max_rows
        return self._request("POST", "query/execute", payload=payload)
