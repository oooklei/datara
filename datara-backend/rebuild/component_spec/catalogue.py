"""Frozen design-time component catalogue and declaration gates.

The catalogue is deliberately small: it is the product surface approved for
the three workflow kinds, not a mirror of every executor registered in the
legacy runtime.
"""

from __future__ import annotations

from typing import Any


WORKFLOW_COMPONENT_TYPES: dict[str, tuple[str, ...]] = {
    "NORMAL": ("sql", "python", "shell", "dependent"),
    "SYNC": (
        "src_base_orch",
        "tgt_base_orch",
        "file_sync_orch",
        "endpoint_select",
        "field_map",
        "field_map_union",
        "condition_set",
    ),
    "STREAM": ("stream_input", "stream_fuse", "stream_output", "page_board"),
}
DESIGN_COMPONENT_TYPES = frozenset(t for values in WORKFLOW_COMPONENT_TYPES.values() for t in values)
RUNTIME_ONLY_TYPES = frozenset({"sync", "file_sync"})
FORM_SECTIONS = ("inputs", "outputs", "params", "conditions", "constraints", "exclusions", "refs", "exports")
PICK_FIELDS = frozenset({"table", "column", "cron", "sshHost"})
BEHAVIOR_ACTIONS = frozenset({"set", "clear", "copy", "refresh", "validate"})
HIDDEN_INPUTS = frozenset({"runId", "nodeId", "workflowId", "tenantId"})
REMOTE_ENDPOINTS = frozenset({"datasource.tree", "datasource.topics", "runtime.nodes"})


def workflow_kind(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized if normalized in WORKFLOW_COMPONENT_TYPES else None


def empty_form() -> dict[str, list[Any]]:
    return {section: [] for section in FORM_SECTIONS}


def _walk(value: Any, path: str = "spec"):
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def validate_declaration(spec: dict[str, Any]) -> list[str]:
    """Validate the JSON declaration dialect consumed by the rebuilt UI."""
    errors: list[str] = []
    form = spec.get("form")
    if form is not None:
        if not isinstance(form, dict):
            errors.append("form must be an object")
        else:
            missing = [name for name in FORM_SECTIONS if name not in form]
            extra = [name for name in form if name not in FORM_SECTIONS]
            if missing:
                errors.append(f"form missing sections: {missing}")
            if extra:
                errors.append(f"form has unsupported sections: {extra}")
            for name in FORM_SECTIONS:
                if name in form and not isinstance(form[name], list):
                    errors.append(f"form.{name} must be an array")

    for path, value in _walk(spec):
        key = path.rsplit(".", 1)[-1]
        if key in {"showIf", "onChange", "text"} and isinstance(value, str):
            lowered = value.lower()
            if "=>" in value or "function" in lowered:
                errors.append(f"{path} must be declarative data, not a function")
        if key == "pick" and isinstance(value, dict):
            unsupported = [name for name in value if name not in PICK_FIELDS]
            if unsupported:
                errors.append(f"{path} has unsupported keys: {unsupported}")
        if key == "behaviors":
            if value is not None and not isinstance(value, list):
                errors.append("behaviors must be an array")
            elif isinstance(value, list):
                for index, behavior in enumerate(value):
                    action = behavior.get("action") if isinstance(behavior, dict) else None
                    if action not in BEHAVIOR_ACTIONS:
                        errors.append(f"behaviors[{index}].action is not allowed")
        if key == "hiddenInputs":
            if not isinstance(value, list) or any(item not in HIDDEN_INPUTS for item in value):
                errors.append("extensions.hiddenInputs contains an unsupported input")
        if key == "remote":
            if not isinstance(value, str) or value not in REMOTE_ENDPOINTS:
                errors.append(f"{path} is not an approved remote endpoint")
    return errors
