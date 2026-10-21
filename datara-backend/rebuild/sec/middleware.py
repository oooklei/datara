"""Collection channels for the access audit.

Two capture channels are provided as self-contained domain components:

1. ``SecAuditMiddleware`` — HTTP-level capture via a Starlette middleware.
   It records one access-log row per audited request (method-derived action,
   path as target, status-derived result). Mounting on the application is a
   pending integration step owned by the single-writer window; this module
   only ships the testable component.
2. ``install_sql_access_hook`` + ``SecSqlAccessRecorder`` — SQL-statement
   capture via a SQLAlchemy engine event hook. Statements are buffered by
   the recorder and persisted on an explicit ``flush()`` so that writing
   audit rows never re-enters the hook.

Mount point for channel 1 (pending single-writer window): the application
factory registers ``SecAuditMiddleware`` after authentication so that
``request.state`` already carries the resolved user name.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from rebuild.sec.models import RESULT_ALLOW, RESULT_DENY
from rebuild.sec.service import SecService

DEFAULT_EXCLUDED_PREFIXES = ("/api/v1/rebuild/sec",)
_METHOD_ACTIONS = {"GET": "query", "POST": "create", "PUT": "update", "DELETE": "delete", "PATCH": "update"}


def default_user_extractor(request: Request) -> str:
    """Resolve the audited user from request.state set by authentication."""
    return str(getattr(request.state, "rebuild_user_name", "") or "anonymous")


class SecAuditMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        session_factory: sessionmaker[Session],
        user_extractor: Callable[[Request], str] = default_user_extractor,
        excluded_prefixes: Iterable[str] = DEFAULT_EXCLUDED_PREFIXES,
        audited_methods: Iterable[str] = ("GET", "POST", "PUT", "DELETE", "PATCH"),
    ) -> None:
        super().__init__(app)
        self.session_factory = session_factory
        self.user_extractor = user_extractor
        self.excluded_prefixes = tuple(excluded_prefixes)
        self.audited_methods = frozenset(m.upper() for m in audited_methods)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if request.method.upper() in self.audited_methods and not request.url.path.startswith(
            self.excluded_prefixes
        ):
            status = response.status_code
            allowed = status < 400
            try:
                with self.session_factory() as session:
                    SecService(session).record_access(
                        user_name=self.user_extractor(request),
                        action=_METHOD_ACTIONS.get(request.method.upper(), request.method.lower()),
                        target=request.url.path,
                        rows_seen=0,
                        allowed=allowed,
                        reason=f"http_status_{status}",
                    )
                    session.commit()
            except Exception:  # auditing must never break the audited request
                pass
        return response


class SecSqlAccessRecorder:
    """Buffers SQL statement digests captured by the engine hook.

    ``flush()`` persists buffered entries in one transaction. Entries whose
    statement touches an ignored fragment (by default the audit table
    itself) are dropped to keep the capture loop from re-entering.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        user_name: str = "system",
        action: str = "execute_sql",
        max_statement_len: int = 512,
        ignored_fragments: Iterable[str] = ("rebuild_sec_access_log",),
    ) -> None:
        self.session_factory = session_factory
        self.user_name = user_name
        self.action = action
        self.max_statement_len = max_statement_len
        self.ignored_fragments = tuple(ignored_fragments)
        self._pending: list[dict[str, str]] = []
        self._lock = threading.Lock()

    def __call__(self, statement: str) -> None:
        if any(fragment in statement for fragment in self.ignored_fragments):
            return
        digest = " ".join(statement.split())[: self.max_statement_len]
        with self._lock:
            self._pending.append({"statement": digest})

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def flush(self) -> int:
        with self._lock:
            batch = self._pending
            self._pending = []
        if not batch:
            return 0
        with self.session_factory() as session:
            service = SecService(session)
            for entry in batch:
                service.record_access(
                    user_name=self.user_name,
                    action=self.action,
                    target=entry["statement"],
                    rows_seen=0,
                    allowed=True,
                    reason="sql_execution_hook",
                )
            session.commit()
        return len(batch)


def install_sql_access_hook(engine: Engine, recorder: Callable[[str], None]) -> None:
    """Register the before_cursor_execute capture hook on an engine."""

    @event.listens_for(engine, "before_cursor_execute")
    def _capture(conn, cursor, statement, parameters, context, executemany):  # pragma: no cover - trivial
        recorder(statement)
