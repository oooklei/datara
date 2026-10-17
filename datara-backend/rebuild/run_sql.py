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

from rebuild.ai_bridge import Handler, ToolError
from rebuild.sql_ide.ddl_policy import sql_tokens_and_statement_count

DEFAULT_ROW_LIMIT = 200  # §7.3 default
DEFAULT_TIMEOUT_MS = 30000  # §7.3 default
MAX_TIMEOUT_MS = 30000  # §6: converge only, never widen

_READONLY_LEADING_TOKENS = frozenset({"SELECT"})

_LEXICAL_MESSAGES = {
    "unterminated_quoted_value": "SQL 包含未闭合的引号值",
    "unterminated_block_comment": "SQL 包含未闭合的块注释",
    "backslash_escape_unclassified": "引号内反斜杠转义方言相关，无法本地安全分类",
    "executable_comment_unclassified": "MySQL 可执行注释超出只读 PoC 支持范围",
}


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
    tokens, statement_count, lexical_errors = sql_tokens_and_statement_count(sql)
    violations: list[dict[str, str]] = []
    for error in lexical_errors:
        violations.append(
            {"code": error, "message": _LEXICAL_MESSAGES.get(error, "SQL 含无法安全分类的词法构造")}
        )
    if statement_count != 1:
        violations.append({"code": "statement_count_invalid", "message": "只读 PoC 仅接受单条语句"})
    if not tokens or tokens[0] not in _READONLY_LEADING_TOKENS:
        violations.append(
            {
                "code": "not_readonly_select",
                "message": "只读 PoC 仅接受单条 SELECT，其余语句（含 WITH/EXPLAIN）一律拒绝",
            }
        )
    return (not violations), violations


def build_run_sql_handler(port: SqlExecutionPort) -> Handler:
    """Compose the run_sql handler over the injected execution port."""
    if not callable(getattr(port, "execute", None)):
        raise ValueError("run_sql requires an injected SqlExecutionPort exposing execute()")

    def handler(
        params: Mapping[str, Any],
        page_context: Mapping[str, Any] | None,
        ctx: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        sql = params["sql"]
        allowed, violations = evaluate_readonly_sql(sql)
        if not allowed:
            # PoC read-only policy violation is a params-schema rejection (§5);
            # code choice flagged to Codex/supervisor for confirmation (#174).
            raise ToolError("INVALID_PARAMS", details={"readonly_policy": violations})
        row_limit = params.get("row_limit", DEFAULT_ROW_LIMIT)
        if row_limit < 1:
            raise ToolError(
                "INVALID_PARAMS", details={"fields": {"row_limit": "must be a positive integer"}}
            )
        timeout_ms = params.get("timeout_ms", DEFAULT_TIMEOUT_MS)
        if timeout_ms < 1:
            raise ToolError(
                "INVALID_PARAMS", details={"fields": {"timeout_ms": "must be a positive integer"}}
            )
        timeout_ms = min(timeout_ms, MAX_TIMEOUT_MS)  # §6: converge only, never widen
        try:
            result = dict(
                port.execute(
                    project_id=ctx["project_id"],
                    datasource_id=params["datasource_id"],
                    sql=sql,
                    row_limit=row_limit,
                    timeout_ms=timeout_ms,
                    dialect=params.get("dialect"),
                )
            )
        except SqlExecutionTimeout as exc:
            raise ToolError("EXECUTION_TIMEOUT", retryable=False, details=exc.details) from exc
        except SqlExecutionCancelled as exc:
            raise ToolError("EXECUTION_CANCELLED", retryable=False, details=exc.details) from exc
        except SqlDependencyUnavailable as exc:
            raise ToolError("DEPENDENCY_UNAVAILABLE", retryable=False, details=exc.details) from exc
        except SqlExecutionFailed as exc:
            raise ToolError("EXECUTION_FAILED", retryable=False, details=exc.details) from exc
        # §7.3 audit refs (execution_id/datasource_id): the envelope merges the
        # refs key into the audit record and strips it from the wire result.
        result["refs"] = {
            "execution_id": result.get("execution_id"),
            "datasource_id": params["datasource_id"],
        }
        return result

    return handler
