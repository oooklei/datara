"""R8-A AI eight-tool unified bridge (P1-3 runtime wiring, steps 2-3).

Contract source (frozen v1): docs/increments/2026-10-17-R8-A八工具契约.md.
Gap list: docs/increments/evidence/R8/2026-10-17-Codex-P1-3-bridge-readiness.md.
Orders: supervisor #160 P1-3 unlock; Trae #164 five-step schedule.

Red lines honored here:
- Single unified call endpoint; envelope owns auth/audit/budget/error normalization;
  handlers cannot bypass it (§2.1).
- `generate_sql` is NOT a registry tool (supervisor #147): it stays internal to the
  adapter/orchestrator layer and is wired in a later step.
- No second execution engine: the bridge never touches
  ``DatasourceEngineRegistry`` or any SQL runner directly (readiness review);
  ``run_sql`` will only ever run through the injected R5-A execution port (step 4).
- Fail closed: ``build_ai_router`` refuses to mount without an injected audit
  writer; default ``create_app`` mounts no bridge at all, so no unaudited or
  ungoverned execution path can exist.
- Honest errors: unwired PoC tools stay listed in the registry but report
  ``enabled=False`` and refuse calls with ``TOOL_DISABLED`` — no fabricated
  results (R8A-02/O7); handler-raised errors normalize to the frozen 12-code
  space, never private codes.
- Audit threads tool_call_id/user_id/roles/project_id/refs (P1-6' evidence
  interface); ``started_at``/``finished_at`` remain storage-generated in the real
  DB-backed writer (§4); audit write failure never fakes SUCCESS.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Mapping

from fastapi import APIRouter, Body, Header
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from rebuild.identity.contracts import Permission, Role, authorize
from rebuild.identity.models import ProjectMemberRecord
from rebuild.project.models import ProjectRecord

Handler = Callable[[Mapping[str, Any], Mapping[str, Any] | None, Mapping[str, Any]], Mapping[str, Any]]

# §2.2 frozen tool list, frozen order. Not a registry entry: generate_sql
# (adapter-internal) must never appear here (supervisor #147).
R8A_TOOLS = (
    "search_schema",
    "validate_sql",
    "run_sql",
    "get_workflow",
    "validate_workflow",
    "inspect_workflow_run",
    "get_task_metrics",
    "get_lineage",
)

TOOL_VERSION = 1

# Pre-N-C roles fallback (§8): platform permission vocabulary until N-C freezes
# the dedicated permission-point words. run_sql executes SQL -> RUN_INSTANCE.
TOOL_PERMISSIONS: dict[str, Permission] = {
    "search_schema": Permission.VIEW_ALL,
    "validate_sql": Permission.EDIT_DEFINITION,
    "run_sql": Permission.RUN_INSTANCE,
    "get_workflow": Permission.VIEW_ALL,
    "validate_workflow": Permission.EDIT_DEFINITION,
    "inspect_workflow_run": Permission.VIEW_ALL,
    "get_task_metrics": Permission.VIEW_ALL,
    "get_lineage": Permission.VIEW_ALL,
}

IDEMPOTENT_RETRY = {"max_attempts": 2, "backoff_ms": 500}
NO_AUTO_RETRY = {"max_attempts": 1, "backoff_ms": 0}  # run_sql: non-idempotent (§6/§7.3)

TOOL_REGISTRY: tuple[dict[str, Any], ...] = (
    {
        "name": "search_schema",
        "version": TOOL_VERSION,
        "description": "检索项目元数据目录中的表/视图与列信息",
        "enabled": False,  # dynamic at discovery: enabled ⇔ handler wired (R8A-02 PoC)
        "required_permissions": [Permission.VIEW_ALL.value],
        "timeout_ms": 10000,
        "retry_policy": IDEMPOTENT_RETRY,
        "budget": {"max_limit": 100},
    },
    {
        "name": "validate_sql",
        "version": TOOL_VERSION,
        "description": "复用 R5-A lintSql 链路校验 SQL 并返回问题列表",
        "enabled": False,
        "required_permissions": [Permission.EDIT_DEFINITION.value],
        "timeout_ms": 10000,
        "retry_policy": IDEMPOTENT_RETRY,
        "budget": {"max_sql_bytes": 102400},
    },
    {
        "name": "run_sql",
        "version": TOOL_VERSION,
        "description": "经 R5-A 统一执行链路执行 SQL（非幂等，不自动重试）",
        "enabled": False,
        "required_permissions": [Permission.RUN_INSTANCE.value],
        "timeout_ms": 30000,
        "retry_policy": NO_AUTO_RETRY,
        "budget": {"max_row_limit": 1000, "max_timeout_ms": 30000},
    },
    {
        "name": "get_workflow",
        "version": TOOL_VERSION,
        "description": "读取工作流定义概要（含发布状态与最新运行）",
        "enabled": False,
        "required_permissions": [Permission.VIEW_ALL.value],
        "timeout_ms": 5000,
        "retry_policy": IDEMPOTENT_RETRY,
        "budget": {},
    },
    {
        "name": "validate_workflow",
        "version": TOOL_VERSION,
        "description": "复用统一 validate_graph 链路校验工作流定义",
        "enabled": False,
        "required_permissions": [Permission.EDIT_DEFINITION.value],
        "timeout_ms": 15000,
        "retry_policy": IDEMPOTENT_RETRY,
        "budget": {},
    },
    {
        "name": "inspect_workflow_run",
        "version": TOOL_VERSION,
        "description": "读取工作流运行记录与任务明细诊断",
        "enabled": False,
        "required_permissions": [Permission.VIEW_ALL.value],
        "timeout_ms": 5000,
        "retry_policy": IDEMPOTENT_RETRY,
        "budget": {"max_tasks": 1000},
    },
    {
        "name": "get_task_metrics",
        "version": TOOL_VERSION,
        "description": "读取统计四表的任务统计（不推导不补算）",
        "enabled": False,
        "required_permissions": [Permission.VIEW_ALL.value],
        "timeout_ms": 10000,
        "retry_policy": IDEMPOTENT_RETRY,
        "budget": {"max_time_window_days": 90},
    },
    {
        "name": "get_lineage",
        "version": TOOL_VERSION,
        "description": "读取血缘存储的上下游血缘（不推导）",
        "enabled": False,
        "required_permissions": [Permission.VIEW_ALL.value],
        "timeout_ms": 10000,
        "retry_policy": IDEMPOTENT_RETRY,
        "budget": {"max_depth": 5, "max_nodes": 500},
    },
)

REGISTRY_BY_NAME = {entry["name"]: entry for entry in TOOL_REGISTRY}

R8A_CONTEXT_TYPES = (
    "PROJECT",
    "WORKFLOW",
    "NODE",
    "SQL",
    "DATASOURCE",
    "VARIABLE",
    "RUN",
    "METRICS",
    "METADATA",
    "LINEAGE",
)

ERROR_MESSAGES: dict[str, str] = {
    "TOOL_NOT_FOUND": "工具不在注册表中",
    "TOOL_VERSION_MISMATCH": "tool_version 与注册表不符",
    "TOOL_DISABLED": "工具已被禁用",
    "INVALID_PARAMS": "参数校验失败",
    "PERMISSION_DENIED": "权限不足",
    "BUDGET_EXCEEDED": "预算策略越界",
    "NOT_FOUND": "目标实体不存在",
    "DEPENDENCY_UNAVAILABLE": "下游依赖不可达",
    "EXECUTION_TIMEOUT": "执行超时",
    "EXECUTION_FAILED": "执行失败",
    "EXECUTION_CANCELLED": "执行已取消",
    "INTERNAL_ERROR": "内部错误",
}


class ToolError(Exception):
    """Handler-raised typed error; the envelope normalizes it to §5 wire shape.

    Construction refuses codes outside the frozen 12-code space — handlers can
    never invent private error codes (§5: 禁止新增未登记错误码).
    """

    def __init__(self, code: str, *, retryable: bool = False, details: Mapping[str, Any] | None = None):
        super().__init__(code)
        if code not in ERROR_MESSAGES:
            raise ValueError(f"unregistered error code: {code}")
        self.code = code
        self.retryable = retryable
        self.details = details


@dataclass(frozen=True)
class AiBridgePorts:
    """Injected ports for the R8-A bridge (fail-closed composition seam).

    ``handlers``: per-tool handler mapping; absent handler -> honest
    DEPENDENCY_UNAVAILABLE. ``audit_writer``: required §4 sink; its absence
    refuses bridge construction entirely.
    """

    handlers: Mapping[str, Handler] = field(default_factory=dict)
    audit_writer: Any | None = None


def build_ai_router(
    session_factory: sessionmaker,
    token_service: Any,
    active_tokens: set[str],
    ports: AiBridgePorts,
) -> APIRouter:
    """Build the R8-A router; fail closed unless every required port is present."""
    if ports.audit_writer is None:
        raise ValueError("R8-A bridge requires an injected audit writer (fail-closed, §4/readiness)")
    unknown = sorted(set(ports.handlers) - set(R8A_TOOLS))
    if unknown:
        raise ValueError(f"handlers contain non-registry tools: {unknown}")

    router = APIRouter()

    def principal(token: str, authorization: str) -> dict[str, object]:
        raw = token or (authorization[7:] if authorization.startswith("Bearer ") else "")
        if not raw:
            raise ValueError("missing token")
        if raw not in active_tokens:
            raise ValueError("token revoked or unknown")
        return token_service.verify(raw)

    def unauthorized() -> JSONResponse:
        return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})

    def server_time_now() -> str:
        with session_factory() as session:
            value = session.scalar(select(func.now()))
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    def write_audit(record: Mapping[str, Any]) -> bool:
        """Single audit sink call; never bypassed, never swallowed silently."""
        try:
            ports.audit_writer.write(record)
            return True
        except Exception:
            return False

    def budget_consumption(result: Mapping[str, Any] | None) -> dict[str, Any]:
        """§4 actual consumption derived from the tool result, when present."""
        if not isinstance(result, Mapping):
            return {}
        budget: dict[str, Any] = {}
        if isinstance(result.get("row_count"), int):
            budget["rows_returned"] = result["row_count"]
        if "truncated" in result:
            budget["truncated"] = bool(result["truncated"])
        if isinstance(result.get("duration_ms"), int):
            budget["duration_ms"] = result["duration_ms"]
        return budget

    def audit_record(
        *,
        audit_id: str,
        tool_call_id: str,
        tool: str,
        tool_version: int,
        user: Mapping[str, object],
        project_id: int | None,
        request_payload: Mapping[str, Any],
        outcome: str,
        error_code: str | None,
        latency_ms: int,
        refs: Mapping[str, Any],
        started_at: str,
        result: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "audit_id": audit_id,
            "tool_call_id": tool_call_id,
            "tool": tool,
            "tool_version": tool_version,
            "user_id": user.get("user_id"),
            "roles": [user.get("role")] if user.get("role") else [],
            "project_id": project_id,
            "request_payload": request_payload,
            "outcome": outcome,
            "error_code": error_code,
            "started_at": started_at,
            "finished_at": server_time_now(),  # DB-generated timestamps (§4)
            "latency_ms": latency_ms,
            "budget": budget_consumption(result),
            "refs": dict(refs),
        }

    def envelope(
        *,
        tool_call_id: str,
        tool: str,
        tool_version: int,
        audit_id: str,
        server_time: str,
        status: str,
        result: Mapping[str, Any] | None,
        error: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "tool_call_id": tool_call_id,
            "tool": tool,
            "tool_version": tool_version,
            "status": status,
            "result": result,
            "error": error,
            "audit_id": audit_id,
            "server_time": server_time,
        }

    def error_payload(code: str, retryable: bool, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": code, "message": ERROR_MESSAGES[code], "retryable": retryable}
        if details is not None:
            payload["details"] = details
        return payload

    # per-tool params schema (required fields); budget-relevant fields type-checked below
    REQUIRED_PARAMS: dict[str, tuple[str, ...]] = {
        "search_schema": ("project_id",),
        "validate_sql": ("project_id", "datasource_id", "sql"),
        "run_sql": ("project_id", "datasource_id", "sql"),
        "get_workflow": ("project_id",),
        "validate_workflow": ("project_id",),
        "inspect_workflow_run": ("project_id", "run_id"),
        "get_task_metrics": ("project_id",),
        "get_lineage": ("project_id", "entity_type", "entity"),
    }

    def invalid_details(fields: Mapping[str, str]) -> dict[str, Any]:
        return {"fields": dict(fields)}

    def validate_params(tool: str, params: Mapping[str, Any]) -> dict[str, Any] | None:
        """Return INVALID_PARAMS details, or None when the schema holds."""
        missing = [name for name in REQUIRED_PARAMS[tool] if params.get(name) in (None, "")]
        problems = {name: "required" for name in missing}
        project_id = params.get("project_id")
        if "project_id" in params and not isinstance(project_id, int):
            problems["project_id"] = "must be an integer"
        if tool == "validate_workflow":
            if not params.get("definition") and not params.get("workflow_id"):
                problems["definition"] = "definition or workflow_id required"
        if tool == "get_task_metrics":
            if not params.get("run_id") and not params.get("time_window"):
                problems["time_window"] = "run_id or time_window required"
        if tool == "get_lineage" and params.get("entity_type") not in ("TABLE", "COLUMN"):
            problems["entity_type"] = "must be TABLE or COLUMN"
        if params.get("limit") is not None and not isinstance(params.get("limit"), int):
            problems["limit"] = "must be an integer"
        if params.get("row_limit") is not None and not isinstance(params.get("row_limit"), int):
            problems["row_limit"] = "must be an integer"
        if params.get("timeout_ms") is not None and not isinstance(params.get("timeout_ms"), int):
            problems["timeout_ms"] = "must be an integer"
        if params.get("depth") is not None and not isinstance(params.get("depth"), int):
            problems["depth"] = "must be an integer"
        return invalid_details(problems) if problems else None

    def budget_violation(tool: str, params: Mapping[str, Any]) -> bool:
        """Static pre-execution budget interception (§6)."""
        if tool == "search_schema" and isinstance(params.get("limit"), int) and params["limit"] > 100:
            return True
        if tool == "validate_sql":
            sql = params.get("sql")
            if isinstance(sql, str) and len(sql.encode("utf-8")) > 102400:
                return True
        if tool == "run_sql":
            if isinstance(params.get("row_limit"), int) and params["row_limit"] > 1000:
                return True
            if isinstance(params.get("timeout_ms"), int) and params["timeout_ms"] > 30000:
                return True
        if tool == "get_lineage" and isinstance(params.get("depth"), int) and params["depth"] > 5:
            return True
        if tool == "get_task_metrics":
            window = params.get("time_window")
            if isinstance(window, Mapping):
                try:
                    start = datetime.fromisoformat(str(window.get("from")).replace("Z", "+00:00"))
                    end = datetime.fromisoformat(str(window.get("to")).replace("Z", "+00:00"))
                except ValueError:
                    return False
                if (end - start).days > 90:
                    return True
        return False

    @router.get("/api/v1/rebuild/ai/tools")
    def discover_tools(token: str = Header(default=""), authorization: str = Header(default="")):
        try:
            principal(token, authorization)
        except ValueError:
            return unauthorized()
        # enabled ⇔ handler wired: PoC lists unwired tools but reports them disabled (R8A-02)
        return [{**entry, "enabled": entry["name"] in ports.handlers} for entry in TOOL_REGISTRY]

    @router.post("/api/v1/rebuild/ai/tool-calls")
    def invoke_tool(
        body: Mapping[str, Any] = Body(default={}),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        started = time.perf_counter()
        try:
            user = principal(token, authorization)
        except ValueError:
            return unauthorized()

        tool_call_id = body.get("tool_call_id")
        tool = body.get("tool")
        tool_version = body.get("tool_version")
        params = body.get("params") if isinstance(body.get("params"), Mapping) else None
        page_context = body.get("page_context")

        envelope_problems: dict[str, str] = {}
        if not isinstance(tool_call_id, str) or not tool_call_id:
            envelope_problems["tool_call_id"] = "required"
        if not isinstance(tool, str) or not tool:
            envelope_problems["tool"] = "required"
        if not isinstance(tool_version, int):
            envelope_problems["tool_version"] = "required integer"
        if params is None:
            envelope_problems["params"] = "required object"
        if page_context is not None:
            if not isinstance(page_context, Mapping) or page_context.get("context_type") not in R8A_CONTEXT_TYPES:
                envelope_problems["page_context"] = "context_type must be one of the ten frozen types"
            elif page_context.get("context_ref") is not None and not isinstance(
                page_context.get("context_ref"), Mapping
            ):
                envelope_problems["page_context"] = "context_ref must be an object or null"
        audit_id = str(uuid.uuid4())
        server_time = server_time_now()
        latency_ms = int((time.perf_counter() - started) * 1000)
        if envelope_problems:
            audit_ok = write_audit(
                audit_record(
                    audit_id=audit_id,
                    tool_call_id=tool_call_id if isinstance(tool_call_id, str) else "",
                    tool=tool if isinstance(tool, str) else "",
                    tool_version=tool_version if isinstance(tool_version, int) else 0,
                    user=user,
                    project_id=None,
                    request_payload={"params": params, "page_context": page_context},
                    outcome="ERROR",
                    error_code="INVALID_PARAMS",
                    latency_ms=latency_ms,
                    refs={},
                    started_at=server_time,
                )
            )
            invalid_error = error_payload("INVALID_PARAMS", False, invalid_details(envelope_problems))
            if not audit_ok:
                invalid_error["details"] = {**invalid_error.get("details", {}), "audit_write_failed": True}
            return envelope(
                tool_call_id=tool_call_id if isinstance(tool_call_id, str) else "",
                tool=tool if isinstance(tool, str) else "",
                tool_version=tool_version if isinstance(tool_version, int) else 0,
                audit_id=audit_id,
                server_time=server_time,
                status="ERROR",
                result=None,
                error=invalid_error,
            )

        def finish_error(code: str, retryable: bool, details: Mapping[str, Any] | None = None):
            audit_ok = write_audit(
                audit_record(
                    audit_id=audit_id,
                    tool_call_id=tool_call_id,
                    tool=tool,
                    tool_version=tool_version,
                    user=user,
                    project_id=params.get("project_id") if isinstance(params.get("project_id"), int) else None,
                    request_payload=dict(params),
                    outcome="ERROR",
                    error_code=code,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    refs={},
                    started_at=server_time,
                )
            )
            error = error_payload(code, retryable, details)
            if not audit_ok:
                # "失败可追踪" (acceptance §4): mark the sink outage on the wire
                error["details"] = {**(error.get("details") or {}), "audit_write_failed": True}
            return envelope(
                tool_call_id=tool_call_id,
                tool=tool,
                tool_version=tool_version,
                audit_id=audit_id,
                server_time=server_time,
                status="ERROR",
                result=None,
                error=error,
            )

        entry = REGISTRY_BY_NAME.get(tool)
        if entry is None:
            return finish_error("TOOL_NOT_FOUND", False)
        if tool_version != entry["version"]:
            return finish_error("TOOL_VERSION_MISMATCH", False)

        # R8A-05 order: trusted identity -> project authorization -> params/budget -> dispatch.
        # The body project_id is only the authorization target, never the identity itself.
        target_project_id = params.get("project_id")
        if not isinstance(target_project_id, int):
            return finish_error(
                "INVALID_PARAMS", False, invalid_details({"project_id": "required integer"})
            )
        role = str(user.get("role", ""))
        user_id = int(user.get("user_id", 0))
        permission = TOOL_PERMISSIONS[tool]
        if not authorize(role, permission):
            # §3: permission denial shares one canned message with ghost projects — no leak.
            return finish_error("PERMISSION_DENIED", False)
        with session_factory() as session:
            project = session.get(ProjectRecord, target_project_id)
            if project is None:
                return finish_error("PERMISSION_DENIED", False)
            if role != Role.ADMIN.value and project.owner_id != user_id:
                member = session.scalar(
                    select(ProjectMemberRecord).where(
                        ProjectMemberRecord.project_id == target_project_id,
                        ProjectMemberRecord.user_id == user_id,
                    )
                )
                if member is None or not authorize(member.role, permission):
                    return finish_error("PERMISSION_DENIED", False)

        param_problems = validate_params(tool, params)
        if param_problems:
            return finish_error("INVALID_PARAMS", False, param_problems)
        if budget_violation(tool, params):
            return finish_error("BUDGET_EXCEEDED", False)
        if tool not in ports.handlers:
            # Dispatch stage (R8A-05 order): PoC lists unwired tools but refuses
            # them honestly — no fake results (R8A-02).
            return finish_error("TOOL_DISABLED", False)

        handler = ports.handlers[tool]
        context: dict[str, Any] = {
            "tool_call_id": tool_call_id,
            "audit_id": audit_id,
            "user_id": user_id,
            "roles": [role],
            "project_id": target_project_id,
            "page_context": dict(page_context) if isinstance(page_context, Mapping) else None,
            "granted_permissions": [permission.value],
        }
        page_refs = (
            dict(page_context.get("context_ref"))
            if isinstance(page_context, Mapping) and isinstance(page_context.get("context_ref"), Mapping)
            else {}
        )
        tool_error: ToolError | None = None
        try:
            result = dict(handler(params, page_context, context))
            outcome, error_code = "SUCCESS", None
        except ToolError as exc:
            result, outcome, error_code, tool_error = None, "ERROR", exc.code, exc
        except Exception:
            result, outcome, error_code = None, "ERROR", "INTERNAL_ERROR"
        # Handler-threaded audit refs (§7.3 run_sql: execution_id/datasource_id):
        # merged into the audit record, stripped from the wire result.
        refs = dict(page_refs)
        if isinstance(result, Mapping):
            threaded = result.pop("refs", None)
            if isinstance(threaded, Mapping):
                refs.update(threaded)
        record = audit_record(
            audit_id=audit_id,
            tool_call_id=tool_call_id,
            tool=tool,
            tool_version=tool_version,
            user=user,
            project_id=target_project_id,
            request_payload=dict(params),
            outcome=outcome,
            error_code=error_code,
            latency_ms=int((time.perf_counter() - started) * 1000),
            refs=refs,
            started_at=server_time,
            result=result,
        )
        if not write_audit(record):
            # unaudited success is forbidden: discard the handler result, fail closed
            return envelope(
                tool_call_id=tool_call_id,
                tool=tool,
                tool_version=tool_version,
                audit_id=audit_id,
                server_time=server_time,
                status="ERROR",
                result=None,
                error=error_payload("INTERNAL_ERROR", False, {"audit_write_failed": True}),
            )
        if outcome == "SUCCESS":
            return envelope(
                tool_call_id=tool_call_id,
                tool=tool,
                tool_version=tool_version,
                audit_id=audit_id,
                server_time=server_time,
                status="SUCCESS",
                result=result,
                error=None,
            )
        if tool_error is not None:
            # typed handler error: frozen code + handler-chosen retryable/details
            return envelope(
                tool_call_id=tool_call_id,
                tool=tool,
                tool_version=tool_version,
                audit_id=audit_id,
                server_time=server_time,
                status="ERROR",
                result=None,
                error=error_payload(tool_error.code, tool_error.retryable, tool_error.details),
            )
        return envelope(
            tool_call_id=tool_call_id,
            tool=tool,
            tool_version=tool_version,
            audit_id=audit_id,
            server_time=server_time,
            status="ERROR",
            result=None,
            error=error_payload("INTERNAL_ERROR", False),
        )

    return router
