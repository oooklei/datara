"""Execution bridge for resolving variable references at attempt start."""

from __future__ import annotations

from typing import Any

from rebuild.variables.repository import VariableRepository
from rebuild.variables.service import VariableContext, VariableResolver


def resolve_execution_parameters(
    session: Any,
    *,
    instance_id: int,
    attempt_no: int,
    context: VariableContext,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Resolve runtime parameters and persist only a redacted audit snapshot.

    The returned mapping is in-memory executor input. Snapshot rows are written
    through the variable repository, which masks sensitive values before flush.
    """
    resolver = VariableResolver(lambda owner: VariableRepository(session).list_owner(owner))
    resolved, snapshot = resolver.resolve_parameters(parameters, context)
    rows = [
        {
            **item,
            "instance_id": instance_id,
            "attempt_no": attempt_no,
            "project_id": context.project_id,
        }
        for item in snapshot
    ]
    if rows:
        VariableRepository(session).write_snapshot_rows(rows)
    return resolved
