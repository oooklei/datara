"""SQL IDE adapter for the authoritative R2 variable resolver."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from rebuild.variables.service import VariableContext


_REFERENCE = re.compile(r"([a-zA-Z]+)\.([a-zA-Z0-9_.]+)\Z")


class VariableResolutionError(ValueError):
    """Raised when a SQL variable expression cannot be resolved safely."""


class SqlIdeVariableResolver:
    """Resolve scoped ``${scope.name}`` references using the R2 authority.

    ``resolver`` is the R2 ``VariableResolver`` (or a compatible object exposing
    ``resolve_name``). Expansion is recursive so undefined references and cycles
    are rejected before SQL can reach execution.
    """

    def __init__(self, resolver: Any) -> None:
        if not callable(getattr(resolver, "resolve_name", None)):
            raise TypeError("resolver must provide resolve_name(scope, name, context)")
        self._resolver = resolver

    def resolve(self, *, sql: str, project_id: int, datasource_id: int) -> dict[str, str]:
        if not isinstance(sql, str):
            raise VariableResolutionError("sql must be a string")
        if isinstance(project_id, bool) or not isinstance(project_id, int) or project_id <= 0:
            raise VariableResolutionError("project_id must be a positive integer")
        if isinstance(datasource_id, bool) or not isinstance(datasource_id, int) or datasource_id <= 0:
            raise VariableResolutionError("datasource_id must be a positive integer")

        context = VariableContext(project_id=project_id)
        used: dict[str, str] = {}

        def expand(text: str, stack: tuple[str, ...]) -> str:
            pieces: list[str] = []
            cursor = 0
            while True:
                start = text.find("${", cursor)
                if start < 0:
                    pieces.append(text[cursor:])
                    return "".join(pieces)
                pieces.append(text[cursor:start])
                end = text.find("}", start + 2)
                if end < 0:
                    raise VariableResolutionError("unclosed variable reference")
                token = text[start + 2 : end]
                match = _REFERENCE.fullmatch(token)
                if match is None:
                    raise VariableResolutionError(f"invalid variable reference: ${{{token}}}")
                scope, name = match.groups()
                key = f"{scope}.{name}"
                if key in stack:
                    raise VariableResolutionError(f"variable reference cycle: {' -> '.join((*stack, key))}")
                try:
                    value = self._resolver.resolve_name(scope, name, context)
                except Exception as exc:
                    raise VariableResolutionError(f"variable resolution failed for ${{{key}}}") from exc
                if value is None:
                    raise VariableResolutionError(f"undefined variable: ${{{key}}}")
                if not isinstance(value, str):
                    raise VariableResolutionError(f"variable value must be a string: ${{{key}}}")
                used[key] = value
                pieces.append(expand(value, (*stack, key)))
                cursor = end + 1

        resolved_sql = expand(sql, ())
        snapshot_payload = json.dumps(
            {"project_id": project_id, "datasource_id": datasource_id, "variables": used},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        snapshot_digest = hashlib.sha256(snapshot_payload.encode("utf-8")).hexdigest()
        digest = hashlib.sha256(resolved_sql.encode("utf-8")).hexdigest()
        return {
            "resolved_sql": resolved_sql,
            "snapshot_ref": f"sha256:{snapshot_digest}",
            "digest": digest,
        }
