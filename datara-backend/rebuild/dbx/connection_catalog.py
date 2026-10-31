"""Short-lived, single-flight cache for the embedded DBX connection catalog.

The embedded DBX IDE renders its connection tree from a single upstream call
(`GET /api/connection/list`). On first open that call must reach DBX and can take
seconds; the DBX shell reports "bridge ready" long before the tree finishes, so
users can briefly see an empty list and believe their connections disappeared.

This cache keeps the last successful DBX catalog for a few seconds and serves
repeat reads from memory. It is deliberately small:

- TTL-bounded so a connection saved elsewhere is re-read promptly.
- single-flight: concurrent readers share one upstream call. Leader election is
  done under the condition lock, so a reader can never mistake a just-finished
  load for "nobody is loading" and start a duplicate upstream call.
- failure does not poison the cache: an errored load clears the in-flight guard
  and raises, so the next read retries.
- owned by the router builder (not module-level) so each app/test gets an
  independent cache.

Only raw DBX rows are cached. Owner filtering (`safe_connection_list`) always
runs per request, and every write path that changes the catalog must call
`invalidate()` so the next read re-fetches.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any


class ConnectionCatalogCache:
    def __init__(self, *, ttl_seconds: float = 5.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._cond = threading.Condition()
        self._rows: list[dict[str, Any]] | None = None
        self._expires_at = 0.0
        # Bumped on every invalidate(); a load that started before an
        # invalidation must not republish stale rows afterwards.
        self._generation = 0
        self._loading = False

    def invalidate(self) -> None:
        with self._cond:
            self._generation += 1
            self._rows = None
            self._expires_at = 0.0
            self._cond.notify_all()

    def _fresh_locked(self) -> list[dict[str, Any]] | None:
        if self._rows is not None and time.monotonic() < self._expires_at:
            return self._rows
        return None

    def get(self, loader: Callable[[], list[dict[str, Any]]]) -> list[dict[str, Any]]:
        with self._cond:
            cached = self._fresh_locked()
            if cached is not None:
                return cached
            # Followers wait for the in-flight leader; one of them becomes the
            # next leader if that load failed.
            while self._loading:
                self._cond.wait()
                cached = self._fresh_locked()
                if cached is not None:
                    return cached
            generation = self._generation
            self._loading = True
        try:
            rows = loader()
        except BaseException:
            with self._cond:
                self._loading = False
                self._cond.notify_all()
            raise
        with self._cond:
            if generation == self._generation:
                self._rows = rows
                self._expires_at = time.monotonic() + self.ttl_seconds
            self._loading = False
            self._cond.notify_all()
        return rows

    def warm(self, loader: Callable[[], list[dict[str, Any]]]) -> None:
        """Preload the cache off the request path; failures are swallowed."""
        with self._cond:
            if self._loading or self._fresh_locked() is not None:
                return
            self._loading = True
            generation = self._generation

        def run() -> None:
            try:
                rows = loader()
            except BaseException:
                with self._cond:
                    self._loading = False
                    self._cond.notify_all()
                return
            with self._cond:
                if generation == self._generation:
                    self._rows = rows
                    self._expires_at = time.monotonic() + self.ttl_seconds
                self._loading = False
                self._cond.notify_all()

        threading.Thread(target=run, daemon=True).start()
