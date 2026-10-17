"""Validation, window resolution, verdict engine and persistence for R4-DEPENDENCY.

Contract source (frozen, A2 v2.1): R4-DEP-RES-API-contract-pending.md §2/§3.1/§4/§7.1-§7.9
+ B2 §2 + R4-SYNC契约差异对齐清单 (cross-domain rulings do not apply here unless cited).

Narrow-scope disclosures (recorded in evidence, mirrored in handoff):
- main has no workflow registry / run-history domain yet, so
  DEP_OBJECT_NOT_FOUND / DEP_UPSTREAM_NOT_PUBLISHED / DEP_VERSION_IMMUTABLE
  publication checks are not enforceable here (candidate/task listing returns
  an honest empty list); they land with the registry domain.
- Condition verdicts consume the R7 metric tables as the upstream history
  source (workflow_result_stat / task_instance_data_stat / task_data_error_sample):
  workflow-level conditions use per-run_date success/failure counts; task-level
  conditions use a data-flow + error-sample proxy. These are real tables and real
  queries, documented as the v1 history source until the execution domain lands.
- date_value week/month multi-interval DS semantics collapse to envelope
  intervals pending the R4 freeze follow-up (§7.4 lists DS behavior as reference).
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.dependency.models import DependencyConfigRecord
from rebuild.metrics.models import (
    TaskDataErrorSampleRecord,
    TaskInstanceDataStatRecord,
    WorkflowResultStatRecord,
)


class DependencyDomainError(ValueError):
    """Domain rejection carrying a stable machine code (contract §2)."""

    def __init__(self, code: str, msg: str, diagnostics: list[dict[str, str]] | None = None) -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.diagnostics = diagnostics or []

    def payload(self) -> dict[str, Any]:
        return {"code": self.code, "msg": self.msg, "data": {"diagnostics": self.diagnostics} if self.diagnostics else None}


def _diag(field: str, code: str, message: str) -> dict[str, str]:
    return {"field": field, "code": code, "message": message}


VALID_KINDS = ("workflow", "task", "file", "table_state", "external_task")
VALID_PERIODS = ("hour", "day", "week", "month")
VALID_JOINS = ("AND", "OR")
VALID_FAILURE_POLICIES = ("fail", "waiting")
VALID_TIMEOUT_STRATEGIES = ("warn", "failed")
VALID_DEPEND_RESULTS = ("success", "failed")

# §7.4 frozen dateValue value-domain per cycle (DS form reference).
VALID_DATE_VALUES: dict[str, tuple[str, ...]] = {
    "hour": ("currentHour", "last1Hour", "last2Hours", "last3Hours", "last24Hours"),
    "day": ("today", "last1Days", "last2Days", "last3Days", "last7Days"),
    "week": (
        "thisWeek",
        "lastWeek",
        "lastMonday",
        "lastTuesday",
        "lastWednesday",
        "lastThursday",
        "lastFriday",
        "lastSaturday",
        "lastSunday",
    ),
    "month": ("thisMonth", "thisMonthBegin", "lastMonth", "lastMonthBegin", "lastMonthEnd"),
}

# §7.1 selector sentinel mapping (DS Constants: DEPENDENT_WORKFLOW_CODE=0,
# DEPENDENT_ALL_TASK_CODE=-1, positive = task code).
SENTINEL_SELECTOR: dict[int, str] = {0: "workflow", -1: "all_tasks"}


def _as_int(value: Any, field: str, diagnostics: list[dict[str, str]], minimum: int | None = None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        diagnostics.append(_diag(field, "INVALID", f"{field} must be an integer"))
        return None
    if minimum is not None and value < minimum:
        diagnostics.append(_diag(field, "INVALID", f"{field} must be >= {minimum}"))
        return None
    return value


def _validate_window(condition: dict[str, Any], index_path: str, diagnostics: list[dict[str, str]]) -> None:
    """§3.1 dual-input mutex: exactly one of (cycle+date_value) XOR (date_range)."""
    has_cycle = "cycle" in condition or "date_value" in condition
    has_range = "date_range" in condition
    if has_cycle and has_range:
        diagnostics.append(
            _diag(f"{index_path}.window", "DEP_INVALID_WINDOW", "cycle+date_value and date_range are mutually exclusive; submit exactly one")
        )
        return
    if not has_cycle and not has_range:
        diagnostics.append(
            _diag(f"{index_path}.window", "DEP_INVALID_WINDOW", "one time input is required: cycle+date_value or date_range")
        )
        return
    if has_range:
        date_range = condition.get("date_range")
        if not isinstance(date_range, dict):
            diagnostics.append(_diag(f"{index_path}.date_range", "DEP_INVALID_WINDOW", "date_range must be an object"))
            return
        period = date_range.get("period_type")
        if period not in VALID_PERIODS:
            diagnostics.append(_diag(f"{index_path}.date_range.period_type", "DEP_INVALID_WINDOW", f"period_type must be one of {VALID_PERIODS}"))
        begin = date_range.get("begin_offset")
        end = date_range.get("end_offset")
        begin_ok = isinstance(begin, int) and not isinstance(begin, bool)
        end_ok = isinstance(end, int) and not isinstance(end, bool)
        if not begin_ok or not end_ok:
            diagnostics.append(_diag(f"{index_path}.date_range", "DEP_INVALID_WINDOW", "begin_offset/end_offset must be integers"))
        elif end < begin:
            diagnostics.append(_diag(f"{index_path}.date_range", "DEP_INVALID_WINDOW", "end_offset must not be before begin_offset"))
        return
    cycle = condition.get("cycle")
    date_value = condition.get("date_value")
    if cycle not in VALID_PERIODS:
        diagnostics.append(_diag(f"{index_path}.cycle", "DEP_INVALID_WINDOW", f"cycle must be one of {VALID_PERIODS}"))
    if not isinstance(date_value, str) or (cycle in VALID_DATE_VALUES and date_value not in VALID_DATE_VALUES[cycle]):
        allowed = VALID_DATE_VALUES.get(cycle, ()) if isinstance(cycle, str) else ()
        diagnostics.append(_diag(f"{index_path}.date_value", "DEP_INVALID_WINDOW", f"date_value must be one of {allowed} for cycle={cycle}"))


def validate_condition(condition: Any, group_index: int, cond_index: int) -> dict[str, Any]:
    """Normalize one condition per §7.1/§7.2/§7.4/§7.6; raise on hard errors."""
    index_path = f"groups[{group_index}].conditions[{cond_index}]"
    if not isinstance(condition, dict):
        raise DependencyDomainError(
            "DEP_INVALID_WINDOW", "condition must be an object", [_diag(index_path, "INVALID", "condition must be an object")]
        )
    diagnostics: list[dict[str, str]] = []

    kind = condition.get("kind")
    if kind is not None and kind not in VALID_KINDS:
        diagnostics.append(_diag(f"{index_path}.kind", "INVALID", f"kind must be one of {VALID_KINDS}"))
    if kind in ("file", "table_state", "external_task"):
        # §7.1: extension kinds are frozen as enum values only; per-kind parameter
        # structure lands with the BE implementation design follow-up ("再确认").
        raise DependencyDomainError(
            "DEP_INVALID_WINDOW",
            f"condition kind={kind} parameter structure is not frozen yet",
            [_diag(f"{index_path}.kind", "NOT_FROZEN", f"kind={kind} detailed fields land with the R4 follow-up freeze")],
        )

    upstream_workflow_id = _as_int(condition.get("upstream_workflow_id"), f"{index_path}.upstream_workflow_id", diagnostics, minimum=1)
    if upstream_workflow_id is None:
        raise DependencyDomainError(
            "DEP_INVALID_WINDOW", "upstream_workflow_id is required", diagnostics or [_diag(f"{index_path}.upstream_workflow_id", "REQUIRED", "upstream_workflow_id is required")]
        )

    upstream_version = _as_int(condition.get("upstream_workflow_version"), f"{index_path}.upstream_workflow_version", diagnostics, minimum=1)

    task_code = condition.get("upstream_task_code")
    selector = condition.get("selector")
    code_present = task_code is not None
    if code_present and (isinstance(task_code, bool) or not isinstance(task_code, int)):
        diagnostics.append(_diag(f"{index_path}.upstream_task_code", "INVALID", "upstream_task_code sentinel must be an integer (0 / -1 / positive task code)"))
        task_code = None
        code_present = False

    if selector is not None and selector not in ("workflow", "all_tasks", "task"):
        diagnostics.append(_diag(f"{index_path}.selector", "INVALID", "selector must be one of workflow|all_tasks|task"))
        selector = None

    if kind is None and not code_present and selector is None:
        # Legacy v1 compatibility: absent kind AND absent sentinel → workflow/0.
        # The v1 default never maps to -1 (§7.1).
        eff_kind, eff_selector, eff_code = "workflow", "workflow", 0
    elif code_present:
        if task_code == 0:
            eff_selector = "workflow"
        elif task_code == -1:
            eff_selector = "all_tasks"
        else:
            eff_selector = "task"
        if selector is not None and selector != eff_selector:
            diagnostics.append(
                _diag(f"{index_path}.selector", "MISMATCH", f"selector={selector} does not match sentinel upstream_task_code={task_code}")
            )
        eff_selector = eff_selector if selector is None else selector
        eff_code = int(task_code)  # type ignore: guarded above
        eff_kind = kind if kind is not None else ("workflow" if eff_selector == "workflow" else "task")
        if eff_selector == "workflow" and task_code != 0:
            diagnostics.append(_diag(f"{index_path}.upstream_task_code", "MISMATCH", "selector=workflow requires sentinel 0"))
        if eff_selector == "all_tasks" and task_code != -1:
            diagnostics.append(_diag(f"{index_path}.upstream_task_code", "MISMATCH", "selector=all_tasks requires sentinel -1"))
        if eff_selector == "task" and task_code <= 0:
            diagnostics.append(_diag(f"{index_path}.upstream_task_code", "MISMATCH", "selector=task requires a positive task code"))
    else:
        # selector explicit (or kind explicit) without sentinel → reject (§7.1).
        diagnostics.append(
            _diag(f"{index_path}.upstream_task_code", "REQUIRED", "explicit selector requires the matching upstream_task_code sentinel (workflow=0, all_tasks=-1, task=positive)")
        )
        eff_kind, eff_selector, eff_code = "workflow", "workflow", 0

    # §7.1 kind/selector cross constraints.
    if eff_kind == "workflow" and eff_selector != "workflow":
        diagnostics.append(_diag(f"{index_path}.kind", "MISMATCH", "kind=workflow only allows selector=workflow"))
    if eff_kind == "task" and eff_selector == "workflow":
        diagnostics.append(_diag(f"{index_path}.kind", "MISMATCH", "kind=task requires selector=all_tasks or task"))

    depend_result = condition.get("depend_result", "success")
    if depend_result not in VALID_DEPEND_RESULTS:
        diagnostics.append(_diag(f"{index_path}.depend_result", "INVALID", f"depend_result must be one of {VALID_DEPEND_RESULTS}"))

    parameter_passing = condition.get("parameter_passing", False)
    if not isinstance(parameter_passing, bool):
        diagnostics.append(_diag(f"{index_path}.parameter_passing", "INVALID", "parameter_passing must be a boolean"))

    _validate_window(condition, index_path, diagnostics)

    if diagnostics:
        raise DependencyDomainError("DEP_INVALID_WINDOW", "condition validation failed", diagnostics)

    return {
        "kind": eff_kind,
        "selector": eff_selector,
        "upstream_task_code": eff_code if eff_kind in ("workflow", "task") else 0,
        "upstream_workflow_id": upstream_workflow_id,
        "upstream_workflow_version": upstream_version,
        "cycle": condition.get("cycle"),
        "date_value": condition.get("date_value"),
        "date_range": condition.get("date_range") if isinstance(condition.get("date_range"), dict) else None,
        "depend_result": depend_result,
        "parameter_passing": bool(parameter_passing),
    }


def validate_policy(payload: dict[str, Any], diagnostics: list[dict[str, str]]) -> dict[str, Any]:
    """§7.3/§7.9 config-level policy validation."""
    policy: dict[str, Any] = {}

    check_interval = payload.get("check_interval_seconds")
    if check_interval is not None:
        value = _as_int(check_interval, "check_interval_seconds", diagnostics)
        if value is not None and value <= 0:
            diagnostics.append(_diag("check_interval_seconds", "INVALID", "check_interval_seconds must be a positive integer when provided"))
        else:
            policy["check_interval_seconds"] = value

    failure_policy = payload.get("failure_policy", "fail")
    if failure_policy not in VALID_FAILURE_POLICIES:
        diagnostics.append(_diag("failure_policy", "INVALID", f"failure_policy must be one of {VALID_FAILURE_POLICIES}"))
        failure_policy = "fail"
    policy["failure_policy"] = failure_policy

    failure_waiting = payload.get("failure_waiting_seconds")
    failure_waiting_reported = any(d["field"] == "failure_waiting_seconds" for d in diagnostics)
    if failure_waiting is not None:
        value = _as_int(failure_waiting, "failure_waiting_seconds", diagnostics)
        if value is not None and value <= 0:
            diagnostics.append(_diag("failure_waiting_seconds", "INVALID", "failure_waiting_seconds must be a positive integer (seconds; source minutes ×60 conversion happens at the FE/storage boundary)"))
            failure_waiting_reported = True
        else:
            policy["failure_waiting_seconds"] = value
    if failure_policy == "waiting" and policy.get("failure_waiting_seconds") is None and not failure_waiting_reported:
        diagnostics.append(_diag("failure_waiting_seconds", "REQUIRED", "failure_waiting_seconds is required when failure_policy=waiting"))

    timeout_seconds = payload.get("timeout_seconds")
    if timeout_seconds is not None:
        value = _as_int(timeout_seconds, "timeout_seconds", diagnostics)
        if value is not None and value <= 0:
            diagnostics.append(_diag("timeout_seconds", "INVALID", "timeout_seconds must be a positive integer"))
        else:
            policy["timeout_seconds"] = value

    wait_enabled = payload.get("dependent_wait_timeout_enabled", False)
    if not isinstance(wait_enabled, bool):
        diagnostics.append(_diag("dependent_wait_timeout_enabled", "INVALID", "dependent_wait_timeout_enabled must be a boolean"))
        wait_enabled = False
    policy["dependent_wait_timeout_enabled"] = wait_enabled

    wait_seconds = payload.get("dependent_wait_timeout_seconds")
    if wait_seconds is not None:
        value = _as_int(wait_seconds, "dependent_wait_timeout_seconds", diagnostics)
        if value is not None and value <= 0:
            diagnostics.append(_diag("dependent_wait_timeout_seconds", "INVALID", "dependent_wait_timeout_seconds must be a positive integer"))
        else:
            policy["dependent_wait_timeout_seconds"] = value

    strategies = payload.get("dependent_wait_timeout_strategies")
    if strategies is None:
        strategies = ["warn"] if wait_enabled else None
    if strategies is not None:
        if not isinstance(strategies, list) or not strategies or any(s not in VALID_TIMEOUT_STRATEGIES for s in strategies):
            diagnostics.append(
                _diag("dependent_wait_timeout_strategies", "INVALID", f"dependent_wait_timeout_strategies must be a non-empty subset of {VALID_TIMEOUT_STRATEGIES}")
            )
        else:
            policy["dependent_wait_timeout_strategies"] = strategies
    if wait_enabled:
        if policy.get("dependent_wait_timeout_seconds") is None:
            diagnostics.append(_diag("dependent_wait_timeout_seconds", "REQUIRED", "dependent_wait_timeout_seconds is required when dependent_wait_timeout_enabled=true"))
        if policy.get("dependent_wait_timeout_strategies") is None and not diagnostics:
            policy["dependent_wait_timeout_strategies"] = ["warn"]

    # §7.9: ①failure-waiting and ②dependent-wait-timeout are mutually exclusive.
    if failure_policy == "waiting" and wait_enabled:
        diagnostics.append(_diag("failure_policy", "DEP_INVALID_TIMEOUT_POLICY", "failure_policy=waiting and dependent_wait_timeout_enabled=true are mutually exclusive"))

    return policy


def parse_groups(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    """Validate groups + group_relation + policy; return (conditions, group_relation, policy)."""
    groups = payload.get("groups")
    diagnostics: list[dict[str, str]] = []
    if not isinstance(groups, list) or not groups:
        raise DependencyDomainError(
            "DEP_INVALID_WINDOW", "groups must be a non-empty list", [_diag("groups", "REQUIRED", "groups must be a non-empty list")]
        )
    group_relation = payload.get("group_relation", "AND")
    if group_relation not in VALID_JOINS:
        raise DependencyDomainError(
            "DEP_INVALID_WINDOW", "group_relation must be AND or OR", [_diag("group_relation", "INVALID", "group_relation must be AND or OR")]
        )
    conditions: list[dict[str, Any]] = []
    for group_index, group in enumerate(groups):
        if not isinstance(group, dict):
            raise DependencyDomainError("DEP_INVALID_WINDOW", "group must be an object", [_diag(f"groups[{group_index}]", "INVALID", "group must be an object")])
        join = group.get("join", "AND")
        if join not in VALID_JOINS:
            raise DependencyDomainError(
                "DEP_INVALID_WINDOW", "group join must be AND or OR", [_diag(f"groups[{group_index}].join", "INVALID", "join must be AND or OR")]
            )
        raw_conditions = group.get("conditions")
        if not isinstance(raw_conditions, list) or not raw_conditions:
            raise DependencyDomainError(
                "DEP_INVALID_WINDOW", "each group requires at least one condition", [_diag(f"groups[{group_index}].conditions", "REQUIRED", "conditions must be a non-empty list")]
            )
        for cond_index, condition in enumerate(raw_conditions):
            normalized = validate_condition(condition, group_index, cond_index)
            normalized["group_index"] = group_index
            normalized["group_join"] = join
            conditions.append(normalized)
    policy = validate_policy(payload, diagnostics)
    if diagnostics:
        raise DependencyDomainError("DEP_INVALID_TIMEOUT_POLICY" if any(d["code"] == "DEP_INVALID_TIMEOUT_POLICY" for d in diagnostics) else "DEP_INVALID_WINDOW", "policy validation failed", diagnostics)
    return conditions, group_relation, policy


# ---------------------------------------------------------------------------
# Window resolution (deterministic UTC math; half-open [start, end) per §7.4).
# ---------------------------------------------------------------------------


def _month_start(dt: datetime, offset: int) -> datetime:
    total = dt.year * 12 + (dt.month - 1) + offset
    year, month = divmod(total, 12)
    return datetime(year, month + 1, 1, tzinfo=dt.tzinfo)


def _resolve_date_range(date_range: dict[str, Any], as_of: datetime) -> tuple[datetime, datetime]:
    period = date_range["period_type"]
    begin = int(date_range["begin_offset"])
    end = int(date_range["end_offset"])
    if period == "hour":
        base = as_of.replace(minute=0, second=0, microsecond=0)
        step = timedelta(hours=1)
    elif period == "day":
        base = as_of.replace(hour=0, minute=0, second=0, microsecond=0)
        step = timedelta(days=1)
    elif period == "week":
        base = (as_of.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=as_of.weekday()))
        step = timedelta(days=7)
    else:
        base = _month_start(as_of.replace(hour=0, minute=0, second=0, microsecond=0), 0)
        step = None
    if step is not None:
        start = base + begin * step
        end = base + (end + 1) * step
    else:
        start = _month_start(base, begin)
        end = _month_start(base, end + 1)
    return start, end


def _resolve_date_value(cycle: str, date_value: str, as_of: datetime) -> tuple[datetime, datetime]:
    """§7.4 dateValue mapping. Envelope-interval simplification is disclosed."""
    day0 = as_of.replace(hour=0, minute=0, second=0, microsecond=0)
    if cycle == "hour":
        hour0 = as_of.replace(minute=0, second=0, microsecond=0)
        mapping = {
            "currentHour": (hour0, hour0 + timedelta(hours=1)),
            "last1Hour": (hour0 - timedelta(hours=1), hour0),
            "last2Hours": (hour0 - timedelta(hours=2), hour0),
            "last3Hours": (hour0 - timedelta(hours=3), hour0),
            "last24Hours": (hour0 - timedelta(hours=24), hour0),
        }
    elif cycle == "day":
        mapping = {
            "today": (day0, day0 + timedelta(days=1)),
            "last1Days": (day0 - timedelta(days=1), day0),
            "last2Days": (day0 - timedelta(days=2), day0),
            "last3Days": (day0 - timedelta(days=3), day0),
            "last7Days": (day0 - timedelta(days=7), day0),
        }
    elif cycle == "week":
        monday = day0 - timedelta(days=as_of.weekday())
        mapping = {"thisWeek": (monday, monday + timedelta(days=7)), "lastWeek": (monday - timedelta(days=7), monday)}
        for index, name in enumerate(("lastMonday", "lastTuesday", "lastWednesday", "lastThursday", "lastFriday", "lastSaturday", "lastSunday")):
            day = monday - timedelta(days=7) + timedelta(days=index)
            mapping[name] = (day, day + timedelta(days=1))
    else:
        month0 = _month_start(day0, 0)
        prev = _month_start(day0, -1)
        nxt = _month_start(day0, 1)
        mapping = {
            "thisMonth": (month0, nxt),
            "thisMonthBegin": (month0, nxt),
            "lastMonth": (prev, month0),
            "lastMonthBegin": (prev, month0),
            "lastMonthEnd": (prev, month0),
        }
    return mapping[date_value]


def resolve_condition_window(condition: dict[str, Any], as_of: datetime) -> tuple[str, str]:
    """Resolve one condition's evaluation window; ISO-8601 UTC strings."""
    if condition.get("date_range") is not None:
        start, end = _resolve_date_range(condition["date_range"], as_of)
    else:
        start, end = _resolve_date_value(str(condition["cycle"]), str(condition["date_value"]), as_of)
    return start.isoformat().replace("+00:00", "Z"), end.isoformat().replace("+00:00", "Z")


def compose_expression(conditions: list[dict[str, Any]], group_relation: str) -> str:
    """Server-side final dependency expression (what you preview is what is judged)."""
    groups: dict[int, list[str]] = {}
    joins: dict[int, str] = {}
    for condition in conditions:
        task_part = ""
        if condition["selector"] == "task":
            task_part = f" task({condition['upstream_task_code']})"
        elif condition["selector"] == "all_tasks":
            task_part = " task(ALL)"
        polarity = "" if condition["depend_result"] == "success" else "! "
        if condition.get("date_range") is not None:
            date_range = condition["date_range"]
            window = f"{date_range['period_type']}[{date_range['begin_offset']}..{date_range['end_offset']}]"
        else:
            window = f"{condition['cycle']}:{condition['date_value']}"
        groups.setdefault(int(condition["group_index"]), []).append(
            f"{polarity}wf({condition['upstream_workflow_id']}){task_part} {window}"
        )
        joins[int(condition["group_index"])] = condition["group_join"]
    rendered = [
        (parts[0] if len(parts) == 1 else "(" + f" {joins[index]} ".join(parts) + ")")
        for index, parts in sorted(groups.items())
    ]
    return f" {group_relation} ".join(rendered)


# ---------------------------------------------------------------------------
# Verdict engine (§7.5 two-level three-state machine + Datara timeout).
# ---------------------------------------------------------------------------


HistoryLookup = Callable[[dict[str, Any], str, str], str]
"""condition + window_start + window_end → condition verdict (satisfied|pending|failed|timeout)."""


def evaluate_condition_static(
    condition: dict[str, Any], window_start: str, window_end: str, as_of: datetime, timeout_seconds: int | None, lookup: HistoryLookup
) -> str:
    """One condition's verdict: history lookup first, then open-window/timeout rules."""
    verdict = lookup(condition, window_start, window_end)
    if verdict != "no_record":
        return verdict
    as_of_iso = as_of.isoformat().replace("+00:00", "Z")
    if as_of_iso < window_end:
        return "pending"
    if timeout_seconds is not None:
        threshold = (datetime.fromisoformat(window_end.replace("Z", "+00:00")) + timedelta(seconds=timeout_seconds)).isoformat().replace("+00:00", "Z")
        if as_of_iso >= threshold:
            return "timeout"
    return "pending"


def combine_verdicts(verdicts: list[str], relation: str) -> str:
    """§7.5 three-state machine applied at both levels; four-enum outcome.

    Precedence (narrow-scope decision, disclosed): AND = failed > pending >
    timeout > satisfied; OR = satisfied > pending > timeout > failed.
    """
    if not verdicts:
        return "satisfied" if relation == "AND" else "failed"
    if relation == "AND":
        for state in ("failed", "pending", "timeout"):
            if state in verdicts:
                return state
        return "satisfied"
    for state in ("satisfied", "pending", "timeout"):
        if state in verdicts:
            return state
    return "failed"


def evaluate_expression(
    conditions: list[dict[str, Any]], group_relation: str, as_of: datetime, timeout_seconds: int | None, lookup: HistoryLookup
) -> tuple[str, list[dict[str, Any]]]:
    """Two-level composition: per-group join, then group_relation (§7.5/§7.8)."""
    resolved: list[dict[str, Any]] = []
    group_results: dict[int, list[str]] = {}
    for condition in conditions:
        window_start, window_end = resolve_condition_window(condition, as_of)
        verdict = evaluate_condition_static(condition, window_start, window_end, as_of, timeout_seconds, lookup)
        group_results.setdefault(int(condition["group_index"]), []).append(verdict)
        entry: dict[str, Any] = {
            "upstream_workflow_id": condition["upstream_workflow_id"],
            "window_start": window_start,
            "window_end": window_end,
            "verdict": verdict,
        }
        if condition["selector"] == "task":
            entry["upstream_task_code"] = str(condition["upstream_task_code"])
        resolved.append(entry)
    overall = combine_verdicts(
        [combine_verdicts(group_results[index], conditions_group_join(conditions, index)) for index in sorted(group_results)],
        group_relation,
    )
    return overall, resolved


def conditions_group_join(conditions: list[dict[str, Any]], group_index: int) -> str:
    for condition in conditions:
        if int(condition["group_index"]) == group_index:
            return str(condition["group_join"])
    return "AND"


def metrics_history_lookup(session: Session) -> HistoryLookup:
    """Live history source over the R7 metric tables (narrow-scope, disclosed).

    - selector=workflow: workflow_result_stat rows for the upstream workflow in
      the window. depend_result=success → satisfied when success rows exist and
      failed when only failure rows exist; depend_result=failed inverts.
    - selector=task/all_tasks: task_instance_data_stat rows for the task in the
      window; error samples in the window mark failure (execution-domain proxy).
    """
    def lookup(condition: dict[str, Any], window_start: str, window_end: str) -> str:
        # Bind real date/datetime objects: SQLite stores Date/DateTime as
        # space-separated text, so raw string comparison against ISO "T"-joined
        # window strings would never match. Half-open [start, end) per §7.4.
        start_date = date.fromisoformat(window_start[:10])
        end_date = date.fromisoformat(window_end[:10])
        start_dt = datetime.fromisoformat(window_start.replace("Z", "+00:00")).replace(tzinfo=None)
        end_dt = datetime.fromisoformat(window_end.replace("Z", "+00:00")).replace(tzinfo=None)
        if condition["selector"] == "workflow":
            # Day-granularity history proxy (disclosed): an hour-cycle window on
            # a single day cannot match a date column and falls through to
            # pending/timeout rules until the execution domain lands.
            rows = session.scalars(
                select(WorkflowResultStatRecord).where(
                    WorkflowResultStatRecord.workflow_id == int(condition["upstream_workflow_id"]),
                    WorkflowResultStatRecord.run_date >= start_date,
                    WorkflowResultStatRecord.run_date < end_date,
                )
            ).all()
            if not rows:
                return "no_record"
            has_success = any(row.success_count > 0 for row in rows)
            has_failure = any(row.failure_count > 0 for row in rows)
            if condition["depend_result"] == "success":
                if has_success:
                    return "satisfied"
                if has_failure:
                    return "failed"
            else:
                if has_failure:
                    return "satisfied"
                if has_success:
                    return "failed"
            return "no_record"
        # all_tasks proxy (disclosed): task rows in window are not workflow-scoped
        # on main (no execution-domain link yet), so the filter is window-only.
        rows = session.scalars(
            select(TaskInstanceDataStatRecord).where(
                TaskInstanceDataStatRecord.created_at >= start_dt,
                TaskInstanceDataStatRecord.created_at < end_dt,
                *(  # task selector narrows to the sentinel task code.
                    [TaskInstanceDataStatRecord.task_id == str(condition["upstream_task_code"])]
                    if condition["selector"] == "task"
                    else []
                ),
            )
        ).all()
        if not rows:
            return "no_record"
        if condition["selector"] == "task":
            samples = session.scalars(
                select(TaskDataErrorSampleRecord).where(
                    TaskDataErrorSampleRecord.task_id == str(condition["upstream_task_code"]),
                    TaskDataErrorSampleRecord.captured_at >= start_dt,
                    TaskDataErrorSampleRecord.captured_at < end_dt,
                )
            ).all()
            has_errors = bool(samples)
        else:
            has_errors = False
        if condition["depend_result"] == "success":
            return "failed" if has_errors else "satisfied"
        return "satisfied" if has_errors else "failed"

    return lookup


# ---------------------------------------------------------------------------
# Persistence (save = replace draft configuration for the slot).
# ---------------------------------------------------------------------------


class DependencyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_config(self, project_id: int, workflow_id: int, workflow_version: int, task_id: str, conditions: list[dict[str, Any]], group_relation: str, policy: dict[str, Any]) -> int:
        existing = self._session.scalar(
            select(DependencyConfigRecord).where(
                DependencyConfigRecord.project_id == project_id,
                DependencyConfigRecord.workflow_id == workflow_id,
                DependencyConfigRecord.workflow_version == workflow_version,
                DependencyConfigRecord.task_id == task_id,
            )
        )
        groups_payload: list[dict[str, Any]] = []
        for condition in conditions:
            entry = {key: value for key, value in condition.items() if key not in ("group_index", "group_join")}
            groups_payload.append({"join": condition["group_join"], "conditions": [entry]})
        if existing is None:
            record = DependencyConfigRecord(
                project_id=project_id,
                workflow_id=workflow_id,
                workflow_version=workflow_version,
                task_id=task_id,
                groups_json=json.dumps(groups_payload),
                group_relation=group_relation,
                check_interval_seconds=policy.get("check_interval_seconds"),
                failure_policy=policy.get("failure_policy", "fail"),
                failure_waiting_seconds=policy.get("failure_waiting_seconds"),
                timeout_seconds=policy.get("timeout_seconds"),
                dependent_wait_timeout_enabled=bool(policy.get("dependent_wait_timeout_enabled", False)),
                dependent_wait_timeout_seconds=policy.get("dependent_wait_timeout_seconds"),
                dependent_wait_timeout_strategies_json=json.dumps(policy["dependent_wait_timeout_strategies"]) if policy.get("dependent_wait_timeout_strategies") is not None else None,
            )
            self._session.add(record)
            self._session.flush()
            return record.id
        existing.groups_json = json.dumps(groups_payload)
        existing.group_relation = group_relation
        existing.check_interval_seconds = policy.get("check_interval_seconds")
        existing.failure_policy = policy.get("failure_policy", "fail")
        existing.failure_waiting_seconds = policy.get("failure_waiting_seconds")
        existing.timeout_seconds = policy.get("timeout_seconds")
        existing.dependent_wait_timeout_enabled = bool(policy.get("dependent_wait_timeout_enabled", False))
        existing.dependent_wait_timeout_seconds = policy.get("dependent_wait_timeout_seconds")
        existing.dependent_wait_timeout_strategies_json = (
            json.dumps(policy["dependent_wait_timeout_strategies"]) if policy.get("dependent_wait_timeout_strategies") is not None else None
        )
        return existing.id
