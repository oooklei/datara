"""run_sql tool composition: injected R5-A execution-port seam + PoC read-only gate.

Contract (frozen v1): docs/increments/2026-10-17-R8-A八工具契约.md §7.3/§6/§11.
Acceptance: run_sql executes ONLY through the injected R5-A ``executeSql`` port
— the bridge never touches ``DatasourceEngineRegistry``, never builds an engine,
never opens a SQLAlchemy connection (readiness red lines). No production port
exists yet (registered gap): default ``create_app`` keeps run_sql disabled and
the production factory assembly lands with R5-A.

PoC read-only gate: mutating SQL is rejected BEFORE the port is called, reusing
the sql_ide conservative lexical scanner (one tokenizer, never a SQL parser).
run_sql is non-idempotent (§6): no auto retry — every execution-error mapping
reports retryable=False, overriding §5 idempotent-tool defaults.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

DEFAULT_ROW_LIMIT = 200  # §7.3 default
DEFAULT_TIMEOUT_MS = 30000  # §7.3 default
MAX_TIMEOUT_MS = 30000  # §6: converge only, never widen

_READONLY_LEADING_TOKENS = frozenset({"SELECT"})


class SqlExecutionError(Exception):
    """Port-side failure carrying engine-side details (§5 details contract)."""

    def __init__(self, message: str, *, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.details = details


class SqlExecutionTimeout(SqlExecutionError):
    pass


class SqlExecutionCancelled(SqlExecutionError):
    pass


class SqlDependencyUnavailable(SqlExecutionError):
    pass


class SqlExecutionFailed(SqlExecutionError):
    pass


@runtime_checkable
class SqlExecutionPort(Protocol):
    """R5-A ``executeSql`` seam (§7.3 red line: unified execution chain)."""

    def execute(
        self,
        *,
        project_id: int,
        datasource_id: int,
        sql: str,
        row_limit: int,
        timeout_ms: int,
        dialect: str | None = None,
    ) -> Mapping[str, Any]:
        ...


def evaluate_readonly_sql(sql: str) -> tuple[bool, list[dict[str, str]]]:
    """Conservative PoC read-only verdict; never opens a connection, never executes."""
    raise NotImplementedError("P1-3 step-4 GREEN lands in the next commit")


def build_run_sql_handler(port: SqlExecutionPort):
    """Compose the run_sql handler over the injected execution port."""
    raise NotImplementedError("P1-3 step-4 GREEN lands in the next commit")
