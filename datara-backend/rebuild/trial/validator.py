"""TrialValidator — static validation of a workflow draft for TRIAL runs (WF-13).

Design source: docs/increments/2026-10-14-datara-platform-rebuild-design.md §4.1.

Validation checks (each produces a structured error with code WF_TRIAL_INVALID):
- START/END presence: at least one START and one END node must exist.
- Orphan nodes: every non-START node must have at least one incoming edge;
  every non-END node must have at least one outgoing edge.
- Cycle detection: the graph must be a DAG (TRIAL runs use topological ordering).
- DEPENDENCY targets: DEPENDENCY nodes must reference an existing dependency config
  (checked via params.dependency_id against the dependency domain).
- Required params: each node type must have its required params present
  (SQL: sql or sql_file; PYTHON: script; SHELL: command).

Returns a list of TrialValidationError dicts; empty list = valid.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.dependency.models import DependencyConfigRecord
from rebuild.workflow.models import WorkflowEdgeRecord, WorkflowNodeRecord


# Node types that require specific params.
NODE_TYPE_REQUIRED_PARAMS: dict[str, tuple[str, ...]] = {
    "SQL": ("sql", "sql_file"),
    "PYTHON": ("script",),
    "SHELL": ("command",),
    "SYNC": ("sync_task_id",),
}


class TrialValidationError:
    """One structured validation failure."""

    def __init__(self, code: str, message: str, node_code: str | None = None) -> None:
        self.code = code
        self.message = message
        self.node_code = node_code

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.node_code is not None:
            result["node_code"] = self.node_code
        return result


class TrialValidator:
    """Static validator for TRIAL run readiness."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def validate(self, definition_id: int) -> list[TrialValidationError]:
        """Validate the current editing draft; return a list of errors (empty = valid)."""
        nodes = self._draft_nodes(definition_id)
        edges = self._draft_edges(definition_id)
        if not nodes:
            return [TrialValidationError("WF_TRIAL_INVALID", "draft has no nodes")]

        errors: list[TrialValidationError] = []
        node_codes = {n.node_code for n in nodes}
        node_map = {n.node_code: n for n in nodes}

        # 1. START/END presence.
        has_start = any(n.node_type == "START" for n in nodes)
        has_end = any(n.node_type == "END" for n in nodes)
        if not has_start:
            errors.append(TrialValidationError("WF_TRIAL_INVALID", "draft must contain at least one START node"))
        if not has_end:
            errors.append(TrialValidationError("WF_TRIAL_INVALID", "draft must contain at least one END node"))

        # 2. Edge endpoint integrity.
        for edge in edges:
            if edge.from_node not in node_codes:
                errors.append(
                    TrialValidationError(
                        "WF_TRIAL_INVALID",
                        f"edge source {edge.from_node!r} is not a draft node",
                    )
                )
            if edge.to_node not in node_codes:
                errors.append(
                    TrialValidationError(
                        "WF_TRIAL_INVALID",
                        f"edge target {edge.to_node!r} is not a draft node",
                    )
                )

        # 3. Orphan node detection.
        incoming = {code: 0 for code in node_codes}
        outgoing = {code: 0 for code in node_codes}
        for edge in edges:
            if edge.from_node in node_codes and edge.to_node in node_codes:
                outgoing[edge.from_node] += 1
                incoming[edge.to_node] += 1

        for node in nodes:
            if node.node_type != "START" and incoming[node.node_code] == 0:
                errors.append(
                    TrialValidationError(
                        "WF_TRIAL_INVALID",
                        f"node {node.node_code!r} has no incoming edge (orphan)",
                        node.node_code,
                    )
                )
            if node.node_type != "END" and outgoing[node.node_code] == 0:
                errors.append(
                    TrialValidationError(
                        "WF_TRIAL_INVALID",
                        f"node {node.node_code!r} has no outgoing edge (orphan)",
                        node.node_code,
                    )
                )

        # 4. Cycle detection (DFS).
        cycle = self._detect_cycle(nodes, edges)
        if cycle is not None:
            errors.append(
                TrialValidationError(
                    "WF_TRIAL_INVALID",
                    f"draft contains a cycle: {' -> '.join(cycle)}",
                )
            )

        # 5. DEPENDENCY target existence.
        self._validate_dependency_targets(errors, node_map)

        # 6. Required params.
        self._validate_required_params(errors, node_map)

        return errors

    def _detect_cycle(
        self, nodes: list[WorkflowNodeRecord], edges: list[WorkflowEdgeRecord]
    ) -> list[str] | None:
        """Return the cycle path if one exists, None otherwise."""
        adjacency: dict[str, list[str]] = {n.node_code: [] for n in nodes}
        for edge in edges:
            if edge.from_node in adjacency and edge.to_node in adjacency:
                adjacency[edge.from_node].append(edge.to_node)

        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {code: WHITE for code in adjacency}
        path: list[str] = []

        def dfs(node: str) -> list[str] | None:
            color[node] = GRAY
            path.append(node)
            for neighbor in adjacency[node]:
                if color[neighbor] == GRAY:
                    # Found cycle: extract it from path.
                    idx = path.index(neighbor)
                    return path[idx:] + [neighbor]
                if color[neighbor] == WHITE:
                    result = dfs(neighbor)
                    if result is not None:
                        return result
            path.pop()
            color[node] = BLACK
            return None

        for code in adjacency:
            if color[code] == WHITE:
                result = dfs(code)
                if result is not None:
                    return result
        return None

    def _validate_dependency_targets(
        self, errors: list[TrialValidationError], node_map: dict[str, WorkflowNodeRecord]
    ) -> None:
        """Check that DEPENDENCY nodes reference existing dependency configs."""
        import json

        for code, node in node_map.items():
            if node.node_type != "DEPENDENCY":
                continue
            params = json.loads(node.params_json) if node.params_json else {}
            dep_id = params.get("dependency_id")
            if dep_id is None:
                errors.append(
                    TrialValidationError(
                        "WF_TRIAL_INVALID",
                        f"DEPENDENCY node {code!r} is missing params.dependency_id",
                        code,
                    )
                )
                continue
            exists = self._session.scalar(
                select(DependencyConfigRecord.id).where(
                    DependencyConfigRecord.id == int(dep_id)
                )
            )
            if exists is None:
                errors.append(
                    TrialValidationError(
                        "WF_TRIAL_INVALID",
                        f"DEPENDENCY node {code!r} references missing dependency {dep_id}",
                        code,
                    )
                )

    def _validate_required_params(
        self, errors: list[TrialValidationError], node_map: dict[str, WorkflowNodeRecord]
    ) -> None:
        """Check that each node has its type-specific required params."""
        import json

        for code, node in node_map.items():
            required = NODE_TYPE_REQUIRED_PARAMS.get(node.node_type)
            if not required:
                continue
            params = json.loads(node.params_json) if node.params_json else {}
            if not any(params.get(key) for key in required):
                errors.append(
                    TrialValidationError(
                        "WF_TRIAL_INVALID",
                        f"{node.node_type} node {code!r} is missing required param (one of {list(required)})",
                        code,
                    )
                )

    def _draft_nodes(self, definition_id: int) -> list[WorkflowNodeRecord]:
        return self._session.scalars(
            select(WorkflowNodeRecord)
            .where(
                WorkflowNodeRecord.definition_id == definition_id,
                WorkflowNodeRecord.version_id.is_(None),
            )
            .order_by(WorkflowNodeRecord.id)
        ).all()

    def _draft_edges(self, definition_id: int) -> list[WorkflowEdgeRecord]:
        return self._session.scalars(
            select(WorkflowEdgeRecord)
            .where(
                WorkflowEdgeRecord.definition_id == definition_id,
                WorkflowEdgeRecord.version_id.is_(None),
            )
            .order_by(WorkflowEdgeRecord.id)
        ).all()
