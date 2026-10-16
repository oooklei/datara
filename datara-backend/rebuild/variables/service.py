"""Deterministic variable resolution for the R2 unified variable domain.

Design source: docs/increments/2026-10-14-datara-platform-rebuild-design.md §5 —
unified reference syntax ``${scope.name}`` / ``$[time-expression]``, the
seven-level precedence chain ``run > task > workflow > project > global > env >
builtin`` plus the transient ``tmp`` scope, and the five diagnostic codes
(SYNTAX / UNDEFINED / TYPE_MISMATCH / SCOPE_INVISIBLE / CYCLE).

Values are plain strings on the wire (FE contract: ``value: string``); the
declared ``value_type`` (string/number/boolean/json) constrains how the string
must parse. Sensitive values are returned in plaintext (declaration §5 Q11).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
import re
from typing import Any

# Seven-level precedence chain (design §5, difference note 6: this chain is the
# design source of truth; narrowing requires user approval).
PRECEDENCE: tuple[str, ...] = ("run", "task", "workflow", "project", "global", "env", "builtin")

# All referenceable scope prefixes (seven-level chain + tmp transient scope).
REFERENCE_SCOPES: frozenset[str] = frozenset((*PRECEDENCE, "tmp"))

# Scopes whose definitions can be persisted through the API. workflow/task
# values belong to execution contexts and run/env/builtin are transient or
# system-owned, so saving into those scopes is rejected.
PERSISTABLE_SCOPES: frozenset[str] = frozenset(("global", "project", "tmp"))

VALUE_TYPES: tuple[str, ...] = ("string", "number", "boolean", "json")

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")

# ${scope.name} where scope is a known prefix; anything else shaped like ${...}
# that cannot be parsed this way is a SYNTAX error.
_REF_PATTERN = re.compile(r"\$\{([a-zA-Z]+)\.([a-zA-Z0-9_.]+)\}")
_ANY_BRACED = re.compile(r"\$\{([^}]*)\}")
_TIME_PATTERN = re.compile(r"\$\[([^\]]*)\]")

# Built-in read-only variables (builtin scope).
BUILTIN_VARIABLES: dict[str, str] = {
    "version": "0.1.0",
}

_DIAGNOSTIC_CODES = ("SYNTAX", "UNDEFINED", "TYPE_MISMATCH", "SCOPE_INVISIBLE", "CYCLE")


class VariableDomainError(ValueError):
    """Domain-level rejection carrying the envelope error code."""

    def __init__(self, code: int, msg: str) -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg


@dataclass(frozen=True, slots=True)
class ResolvedVariable:
    """A concrete variable value visible in a context."""

    name: str
    scope: str
    value: str
    value_type: str
    sensitive: bool = False
    description: str = ""


@dataclass(frozen=True, slots=True)
class VariableContext:
    """Where references are checked/completed from (FE VariableContext)."""

    project_id: int
    workflow_id: int | None = None
    workflow_version: int | None = None
    task_id: str | None = None
    attempt_no: int | None = None


def parse_context(payload: dict[str, Any]) -> VariableContext:
    """Build a context from a snake_case request payload; project_id required."""
    project_id = payload.get("project_id")
    if isinstance(project_id, bool) or not isinstance(project_id, int) or project_id <= 0:
        raise VariableDomainError(4001, "context.project_id must be a positive integer")
    return VariableContext(
        project_id=project_id,
        workflow_id=_optional_positive_int(payload.get("workflow_id")),
        workflow_version=_optional_positive_int(payload.get("workflow_version")),
        task_id=_optional_text(payload.get("task_id")),
        attempt_no=_optional_positive_int(payload.get("attempt_no")),
    )


def _optional_positive_int(raw: Any) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise VariableDomainError(4001, "context ids must be positive integers")
    return raw


def _optional_text(raw: Any) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip()


def validate_definition(scope: str, name: str, value_type: str, value: str) -> None:
    """Validate a definition about to be persisted; raise VariableDomainError."""
    if scope not in PERSISTABLE_SCOPES:
        raise VariableDomainError(
            4001,
            f"scope {scope!r} is not persistable; storeable scopes are {sorted(PERSISTABLE_SCOPES)}",
        )
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise VariableDomainError(4001, f"invalid variable name: {name!r}")
    if value_type not in VALUE_TYPES:
        raise VariableDomainError(4001, f"value_type must be one of {list(VALUE_TYPES)}")
    if not isinstance(value, str):
        raise VariableDomainError(4001, "value must be a string")
    type_error = type_mismatch(value_type, value)
    if type_error is not None:
        raise VariableDomainError(4002, f"TYPE_MISMATCH: {type_error}")


def type_mismatch(value_type: str, value: str) -> str | None:
    """Return a reason string when value does not parse as value_type, else None."""
    if value_type == "number":
        try:
            float(value)
        except ValueError:
            return f"value {value!r} is not a number"
    elif value_type == "boolean":
        if value.lower() not in ("true", "false"):
            return f"value {value!r} is not a boolean"
    elif value_type == "json":
        try:
            json.loads(value)
        except json.JSONDecodeError:
            return "value is not valid JSON"
    return None


def references_in(text: str) -> tuple[list[dict[str, str]], list[str], list[str]]:
    """Split text into (valid refs, time expressions, syntax error fragments)."""
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    consumed: list[tuple[int, int]] = []
    for match in _REF_PATTERN.finditer(text):
        scope, name = match.group(1), match.group(2)
        key = (scope, name)
        if key not in seen:
            seen.add(key)
            refs.append({"scope": scope, "name": name})
        consumed.append((match.start(), match.end()))
    time_expressions = [match.group(1) for match in _TIME_PATTERN.finditer(text)]
    syntax_errors: list[str] = []
    for match in _ANY_BRACED.finditer(text):
        span = (match.start(), match.end())
        if not any(start <= span[0] < span[1] or span[0] <= start < span[1] for start, end in consumed):
            syntax_errors.append(match.group(0))
    return refs, time_expressions, syntax_errors


class VariableResolver:
    """Resolves variables for a context using the seven-level precedence chain."""

    def __init__(self, definitions_by_owner_key: Any) -> None:
        """``definitions_by_owner_key(owner_key) -> list[ResolvedVariable]``."""
        self._definitions_by_owner_key = definitions_by_owner_key

    # -- catalog -----------------------------------------------------------

    def visible_scopes(self, context: VariableContext) -> tuple[str, ...]:
        """Scopes whose values are visible in this context (chain order)."""
        visible: list[str] = ["run", "task", "workflow", "project", "global", "env", "builtin"]
        if context.workflow_id is None:
            visible.remove("workflow")
        if context.task_id is None:
            visible.remove("task")
        return tuple(visible)

    def catalog(self, context: VariableContext) -> list[ResolvedVariable]:
        """All variables visible in the context, chain order first-wins deduped."""
        owners: list[tuple[str, str]] = [("global", "global")]
        if context.project_id:
            owners.insert(0, ("project", f"project:{context.project_id}"))
            owners.append(("tmp", f"tmp:{context.project_id}"))
        if context.workflow_id is not None:
            owners.append(("workflow", f"workflow:{context.project_id}:{context.workflow_id}"))
        if context.task_id is not None:
            owners.append(("task", f"task:{context.project_id}:{context.task_id}"))
        catalog: dict[str, ResolvedVariable] = {}
        for scope, owner_key in owners:
            for item in self._definitions_by_owner_key(owner_key):
                catalog.setdefault(item.name, item)
        for name, value in BUILTIN_VARIABLES.items():
            catalog.setdefault(name, ResolvedVariable(name=name, scope="builtin", value=value, value_type="string"))
        return list(catalog.values())

    def resolve_name(self, scope: str, name: str, context: VariableContext) -> str | None:
        """Resolve a single (scope, name); None when absent."""
        if scope == "env":
            return os.environ.get(name)
        if scope == "builtin":
            return BUILTIN_VARIABLES.get(name)
        owner_key = self._owner_key_for(scope, context)
        if owner_key is None:
            return None
        for item in self._definitions_by_owner_key(owner_key):
            if item.name == name:
                return item.value
        return None

    def _owner_key_for(self, scope: str, context: VariableContext) -> str | None:
        if scope == "global":
            return "global"
        if scope in ("project", "tmp"):
            return f"{scope}:{context.project_id}"
        if scope == "workflow" and context.workflow_id is not None:
            return f"workflow:{context.project_id}:{context.workflow_id}"
        if scope == "task" and context.task_id is not None:
            return f"task:{context.project_id}:{context.task_id}"
        return None

    # -- diagnostics -------------------------------------------------------

    def check_reference(self, expression: str, context: VariableContext) -> dict[str, Any]:
        """Full reference check producing the five diagnostic codes."""
        diagnostics: list[dict[str, str]] = []
        refs, _time_expressions, syntax_errors = references_in(expression)
        for fragment in syntax_errors:
            diagnostics.append({"code": "SYNTAX", "message": f"unparsable reference fragment: {fragment}"})
        visible = set(self.visible_scopes(context))
        for ref in refs:
            scope, name = ref["scope"], ref["name"]
            if scope not in REFERENCE_SCOPES or scope not in visible:
                diagnostics.append(
                    {"code": "SCOPE_INVISIBLE", "message": f"scope {scope!r} is not visible in this context"}
                )
                continue
            value = self.resolve_name(scope, name, context)
            if value is None:
                diagnostics.append({"code": "UNDEFINED", "message": f"variable {scope}.{name} is not defined"})
                continue
            item = self._definition_of(scope, name, context)
            if item is not None:
                mismatch = type_mismatch(item.value_type, item.value)
                if mismatch is not None:
                    diagnostics.append({"code": "TYPE_MISMATCH", "message": f"{scope}.{name}: {mismatch}"})
            cycle = self._cycle_via(scope, name, context, origin=(scope, name), visited=set())
            if cycle is not None:
                chain = " -> ".join([f"{scope}.{name}", *cycle])
                diagnostics.append({"code": "CYCLE", "message": f"cyclic reference: {chain}"})
        return {
            "expression": expression,
            "valid": not diagnostics,
            "diagnostics": diagnostics,
        }

    def _definition_of(self, scope: str, name: str, context: VariableContext) -> ResolvedVariable | None:
        owner_key = self._owner_key_for(scope, context)
        if owner_key is None:
            return None
        for item in self._definitions_by_owner_key(owner_key):
            if item.name == name:
                return item
        return None

    def _cycle_via(
        self,
        scope: str,
        name: str,
        context: VariableContext,
        *,
        origin: tuple[str, str],
        visited: set[tuple[str, str]],
    ) -> list[str] | None:
        """Follow value-embedded references; return the cycle tail or None."""
        key = (scope, name)
        if key == origin and key in visited:
            return [f"{scope}.{name}"]
        if key in visited:
            return None
        visited.add(key)
        item = self._definition_of(scope, name, context)
        if item is None:
            return None
        refs, _times, _errors = references_in(item.value)
        for ref in refs:
            tail = self._cycle_via(ref["scope"], ref["name"], context, origin=origin, visited=visited)
            if tail is not None:
                return [f"{scope}.{name}", *tail]
        return None

    # -- preview / completion ----------------------------------------------

    def preview_resolution(self, expression: str, context: VariableContext) -> dict[str, Any]:
        """Resolve the first reference in the expression for current-value preview."""
        result = self.check_reference(expression, context)
        diagnostics = result["diagnostics"]
        refs, _times, _errors = references_in(expression)
        resolved_value: str | None = None
        source: dict[str, str] | None = None
        if refs and not any(d["code"] in ("SYNTAX", "SCOPE_INVISIBLE", "UNDEFINED", "CYCLE") for d in diagnostics):
            ref = refs[0]
            value = self.resolve_name(ref["scope"], ref["name"], context)
            if value is not None:
                resolved_value = value
                source = {"scope": ref["scope"], "name": ref["name"]}
        return {
            "expression": expression,
            "resolved_value": resolved_value,
            "source": source,
            "diagnostics": diagnostics,
        }

    def complete(self, prefix: str, context: VariableContext) -> list[dict[str, Any]]:
        """Completion items for visible variables whose qualified name matches prefix."""
        normalized = prefix.strip().removeprefix("${").removesuffix("}").lower()
        scope_filter: str | None = None
        name_prefix = normalized
        if "." in normalized:
            scope_part, _, rest = normalized.partition(".")
            scope_filter, name_prefix = scope_part, rest
        items: list[dict[str, Any]] = []
        for item in self.catalog(context):
            if scope_filter is not None and item.scope != scope_filter:
                continue
            if not item.name.lower().startswith(name_prefix):
                continue
            items.append(
                {
                    "scope": item.scope,
                    "name": item.name,
                    "value_type": item.value_type,
                    "current_value": item.value,
                    "sensitive": item.sensitive,
                    "description": item.description,
                }
            )
        # env scope is not catalogued; surface matching environment variables.
        if scope_filter in (None, "env"):
            for env_name in sorted(os.environ):
                if env_name.startswith(name_prefix):
                    items.append(
                        {
                            "scope": "env",
                            "name": env_name,
                            "value_type": "string",
                            "current_value": os.environ[env_name],
                            "sensitive": False,
                            "description": "process environment variable",
                        }
                    )
        return items
