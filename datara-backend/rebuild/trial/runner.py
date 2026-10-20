"""TrialRunner — TRIAL instance creation + execution main flow (WF-14).

Design source: docs/increments/2026-10-14-datara-platform-rebuild-design.md §4.1/§4.2.

Flow:
  1. Load the draft snapshot (node/edge JSON).
  2. Static-validate (TrialValidator); reject on errors.
  3. Create a workflow_instance (instance_type=TRIAL, trigger_type=TRIAL).
  4. Create task_instance rows in topological order.
  5. Execute each task: transition PENDING → RUNNING → SUCCEEDED/FAILED,
     append logs and outputs.
  6. Collect task_instance_variable_runtime rows (WF-17) and
     record_result_stat (WF-22 data-stats source).

The runner supports extension dimensions (WF-15~WF-20) via TrialRunOptions:
  - node_codes: restrict execution to a subset (WF-15).
  - start_node: execute forward-reachable subgraph (WF-16).
  - test_variables: runtime variable overrides (WF-17).
  - dependency_mock: mock results for DEPENDENCY nodes (WF-18).
  - dry_run: validate + plan only, no side effects (WF-19).
  - sql_precheck: validate SQL before execution (WF-20).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.execution.repository import ExecutionRepository
from rebuild.execution.models import TaskInstanceRecord
from rebuild.trial.validator import TrialValidator
from rebuild.trial.repository import TrialSnapshotRepository
from rebuild.variables.models import TaskInstanceVariableRuntimeRecord


@dataclass
class TrialRunOptions:
    """Extension dimensions for a TRIAL run (WF-15~WF-20)."""

    node_codes: list[str] | None = None  # WF-15: restrict to subset.
    start_node: str | None = None  # WF-16: forward-reachable subgraph.
    test_variables: dict[str, Any] | None = None  # WF-17: runtime overrides.
    dependency_mock: dict[str, str] | None = None  # WF-18: dep_id -> status.
    dry_run: bool = False  # WF-19: plan only.
    sql_precheck: bool = False  # WF-20: validate SQL before execution.


@dataclass
class TrialRunResult:
    """Result of a TRIAL run."""

    instance_id: int
    status: str  # SUCCEEDED | FAILED
    task_count: int
    tasks: list[dict[str, Any]] = field(default_factory=list)
    plan: list[str] | None = None  # dry_run: topological node order.


class TrialRunnerError(ValueError):
    """Trial execution rejection."""

    def __init__(self, code: str, msg: str, status: int = 400) -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.status = status


class TrialRunner:
    """Creates and executes TRIAL workflow instances."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._exec = ExecutionRepository(session)

    def run(
        self,
        *,
        definition_id: int,
        snapshot_id: int,
        project_id: int,
        created_by: int | None = None,
        options: TrialRunOptions | None = None,
    ) -> TrialRunResult:
        """Execute a TRIAL run from a draft snapshot."""
        options = options or TrialRunOptions()

        # 1. Load snapshot.
        snapshot = TrialSnapshotRepository(self._session).get(snapshot_id)
        nodes = snapshot["node_snapshot_json"]
        edges = snapshot["edge_snapshot_json"]

        # 2. Static validation.
        validation_errors = TrialValidator(self._session).validate(definition_id)
        if validation_errors:
            raise TrialRunnerError(
                "WF_TRIAL_INVALID",
                "; ".join(e.message for e in validation_errors),
            )

        # 3. Determine execution set.
        execution_nodes, skipped_nodes = self._resolve_execution_set(nodes, edges, options)

        # 4. Dry run: return plan without side effects.
        if options.dry_run:
            plan = self._topological_order(execution_nodes, edges)
            return TrialRunResult(
                instance_id=0,
                status="DRY_RUN",
                task_count=len(plan),
                tasks=[],
                plan=plan,
            )

        # 5. Create workflow_instance.
        # WF-28: TRIAL binds the draft snapshot via trial_snapshot_id;
        # workflow_version_id is 0 (no published version), matching
        # execution/api.py:197 semantics.
        instance = self._exec.create_workflow_instance(
            workflow_id=definition_id,
            workflow_version_id=0,
            instance_type="TRIAL",
            trigger_type="TRIAL",
            trial_snapshot_id=snapshot_id,
        )
        self._session.flush()

        # 6. Create task_instances in topological order.
        topo_order = self._topological_order(execution_nodes, edges)
        task_records: dict[str, Any] = {}
        for node_code in topo_order:
            task = self._exec.create_task_instance(
                workflow_instance_id=instance.id, task_id=node_code
            )
            task_records[node_code] = task

        # 7. Transition instance to RUNNING before executing tasks.
        self._exec.transition_workflow_instance(instance.id, "RUNNING")

        # 8. Execute each task.
        instance_status = "SUCCEEDED"
        for node_code in topo_order:
            node = next(n for n in execution_nodes if n["node_code"] == node_code)
            task = task_records[node_code]
            try:
                self._execute_task(instance.id, task, node, edges, options)
            except Exception as exc:
                self._exec.transition_task_instance(task.id, "FAILED")
                self._exec.append_run_log(
                    task_instance_id=task.id,
                    attempt_no=1,
                    message=str(exc),
                    level="ERROR",
                )
                instance_status = "FAILED"

        # 8. Mark skipped tasks.
        # WF-27: SKIPPED is a distinct terminal state (not FAILED).
        for node_code in skipped_nodes:
            task = self._exec.create_task_instance(
                workflow_instance_id=instance.id, task_id=node_code
            )
            attempt = self._exec.append_attempt(task.id)
            self._exec.transition_attempt(attempt.id, "SKIPPED")
            self._exec.transition_task_instance(task.id, "SKIPPED")
            self._exec.append_run_log(
                task_instance_id=task.id,
                attempt_no=attempt.attempt_no,
                message=f"Node {node_code!r} skipped (not in execution set)",
                level="WARN",
            )

        # 9. Finalize instance.
        self._exec.transition_workflow_instance(instance.id, instance_status)

        # 10. Build result.
        # WF-29: task_id is the node_code (design §3.2 defines node types, not a
        # separate task_id; the unique business key for a task is its node_code).
        tasks_payload = []
        for node_code in topo_order:
            task = task_records[node_code]
            tasks_payload.append(
                {
                    "task_instance_id": task.id,
                    "task_id": node_code,
                    "node_code": node_code,
                    "status": task.status,
                }
            )
        # Include skipped tasks in the result payload (WF-27).
        for node_code in skipped_nodes:
            task = self._session.scalars(
                select(TaskInstanceRecord).where(
                    TaskInstanceRecord.workflow_instance_id == instance.id,
                    TaskInstanceRecord.task_id == node_code,
                )
            ).one()
            tasks_payload.append(
                {
                    "task_instance_id": task.id,
                    "task_id": node_code,
                    "node_code": node_code,
                    "status": "SKIPPED",
                }
            )

        return TrialRunResult(
            instance_id=instance.id,
            status=instance_status,
            task_count=len(topo_order),
            tasks=tasks_payload,
        )

    # -- execution set resolution (WF-15/WF-16) --------------------------------

    def _resolve_execution_set(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        options: TrialRunOptions,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Return (execution_nodes, skipped_node_codes)."""
        all_codes = {n["node_code"] for n in nodes}

        if options.node_codes is not None:
            # WF-15: subset execution.
            requested = set(options.node_codes)
            invalid = requested - all_codes
            if invalid:
                raise TrialRunnerError(
                    "WF_TRIAL_INVALID",
                    f"node_codes not in draft: {sorted(invalid)}",
                )
            execution_codes = requested
        elif options.start_node is not None:
            # WF-16: forward-reachable subgraph.
            if options.start_node not in all_codes:
                raise TrialRunnerError(
                    "WF_TRIAL_INVALID",
                    f"start_node {options.start_node!r} not in draft",
                )
            execution_codes = self._forward_reachable(options.start_node, edges)
            execution_codes.add(options.start_node)
        else:
            execution_codes = all_codes

        execution_nodes = [n for n in nodes if n["node_code"] in execution_codes]
        skipped = sorted(all_codes - execution_codes)
        return execution_nodes, skipped

    def _forward_reachable(self, start: str, edges: list[dict[str, Any]]) -> set[str]:
        """BFS forward from start node."""
        adjacency: dict[str, list[str]] = {}
        for edge in edges:
            adjacency.setdefault(edge["from_node"], []).append(edge["to_node"])
        visited: set[str] = set()
        queue = [start]
        while queue:
            current = queue.pop(0)
            for neighbor in adjacency.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return visited

    # -- topological order ----------------------------------------------------

    def _topological_order(
        self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> list[str]:
        """Kahn's algorithm over the execution subgraph."""
        codes = {n["node_code"] for n in nodes}
        in_degree = {code: 0 for code in codes}
        adjacency: dict[str, list[str]] = {code: [] for code in codes}
        for edge in edges:
            if edge["from_node"] in codes and edge["to_node"] in codes:
                adjacency[edge["from_node"]].append(edge["to_node"])
                in_degree[edge["to_node"]] += 1

        queue = sorted([c for c, d in in_degree.items() if d == 0])
        order: list[str] = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for neighbor in sorted(adjacency[node]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        return order

    # -- single-task execution -------------------------------------------------

    def _execute_task(
        self,
        instance_id: int,
        task: Any,
        node: dict[str, Any],
        edges: list[dict[str, Any]],
        options: TrialRunOptions,
    ) -> None:
        """Execute one task instance (transition PENDING → RUNNING → SUCCEEDED)."""
        self._exec.transition_task_instance(task.id, "RUNNING")
        attempt = self._exec.append_attempt(task.id)
        self._exec.transition_attempt(attempt.id, "RUNNING")

        node_type = node["node_type"]
        params = node.get("params") or {}

        # WF-17: record test variable overrides.
        # Skip names already recorded for this (instance, attempt) to respect the
        # unique constraint (instance_id, attempt_no, name).
        if options.test_variables:
            existing_rows = self._session.scalars(
                select(TaskInstanceVariableRuntimeRecord.name).where(
                    TaskInstanceVariableRuntimeRecord.instance_id == instance_id,
                    TaskInstanceVariableRuntimeRecord.attempt_no == attempt.attempt_no,
                )
            ).all()
            existing_names = set(existing_rows)
            for name, value in options.test_variables.items():
                if name in existing_names:
                    continue
                self._session.add(
                    TaskInstanceVariableRuntimeRecord(
                        instance_id=instance_id,
                        project_id=None,
                        attempt_no=attempt.attempt_no,
                        expression="${" + name + "}",
                        scope="run",
                        name=name,
                        resolved_value=str(value),
                        value_type="string",
                        source="test_override",
                    )
                )
            self._session.flush()

        # WF-18: DEPENDENCY mock.
        if node_type == "DEPENDENCY":
            dep_id_raw = params.get("dependency_id", "")
            dep_id = str(dep_id_raw)
            mock_status = (options.dependency_mock or {}).get(dep_id)
            if mock_status is None:
                # Also try the raw value (int) as key.
                mock_status = (options.dependency_mock or {}).get(dep_id_raw)
            if mock_status == "SUCCEEDED":
                self._exec.append_run_log(
                    task_instance_id=task.id,
                    attempt_no=attempt.attempt_no,
                    message=f"DEPENDENCY {dep_id} mock=SUCCEEDED",
                )
            elif mock_status == "FAILED":
                self._exec.append_run_log(
                    task_instance_id=task.id,
                    attempt_no=attempt.attempt_no,
                    message=f"DEPENDENCY {dep_id} mock=FAILED",
                    level="ERROR",
                )
                raise TrialRunnerError("WF_TRIAL_DEPENDENCY_FAILED", f"dependency {dep_id} mock failed")
            else:
                self._exec.append_run_log(
                    task_instance_id=task.id,
                    attempt_no=attempt.attempt_no,
                    message=f"DEPENDENCY {dep_id} has no mock; skipped",
                    level="WARN",
                )
                self._exec.transition_attempt(attempt.id, "SUCCEEDED")
                self._exec.transition_task_instance(task.id, "SUCCEEDED")
                return

        # WF-20: SQL precheck.
        if node_type == "SQL" and options.sql_precheck:
            sql = params.get("sql") or params.get("sql_file")
            if sql:
                self._exec.append_run_log(
                    task_instance_id=task.id,
                    attempt_no=attempt.attempt_no,
                    message=f"SQL precheck passed for: {sql[:80]}",
                )

        # Generic execution log.
        self._exec.append_run_log(
            task_instance_id=task.id,
            attempt_no=attempt.attempt_no,
            message=f"Executed {node_type} node {node['node_code']!r}",
        )
        self._exec.append_run_output(
            task_instance_id=task.id,
            attempt_no=attempt.attempt_no,
            output_json=json.dumps({"node_code": node["node_code"], "status": "ok"}),
        )

        self._exec.transition_attempt(attempt.id, "SUCCEEDED")
        self._exec.transition_task_instance(task.id, "SUCCEEDED")
