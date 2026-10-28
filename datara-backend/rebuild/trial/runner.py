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
  - sql_execute: execute explicitly opted-in SQL in an isolated SQLite runtime.
"""

from __future__ import annotations

import json
import hashlib
import os
import sqlite3
import subprocess
import sys
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.execution.repository import ExecutionRepository
from rebuild.execution.models import TaskInstanceRecord, WorkflowInstanceRecord
from rebuild.execution.sync_executor import execute_sync_attempt
from rebuild.sync.executor import SyncRuntimeAdapter
from rebuild.execution.run_stats import RunStatisticsService
from rebuild.dependency.models import DependencyConfigRecord
from rebuild.dependency.repository import (
    DependencyDomainError,
    evaluate_expression,
    metrics_history_lookup,
    parse_groups,
)
from rebuild.resources.models import ResourceBindingRecord, ResourceRecord, ResourceVersionRecord
from rebuild.resources.repository import storage_dir
from rebuild.trial.validator import TrialValidator
from rebuild.trial.repository import TrialSnapshotRepository
from rebuild.variables.models import TaskInstanceVariableRuntimeRecord
from rebuild.variables.repository import VariableRepository
from rebuild.variables.service import VariableContext, VariableDomainError, VariableResolver


@dataclass
class TrialRunOptions:
    """Extension dimensions for a TRIAL run (WF-15~WF-20)."""

    node_codes: list[str] | None = None  # WF-15: restrict to subset.
    start_node: str | None = None  # WF-16: forward-reachable subgraph.
    test_variables: dict[str, Any] | None = None  # WF-17: runtime overrides.
    environment_group_id: int | None = None  # Selected environment layer.
    dependency_mock: dict[str, str] | None = None  # WF-18: dep_id -> status.
    dry_run: bool = False  # WF-19: plan only.
    sql_precheck: bool = False  # WF-20: validate SQL before execution.
    sql_execute: bool = False  # Execute SQL in an isolated SQLite runtime.


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

    def __init__(
        self,
        session: Session,
        sync_driver_factory: Callable[..., SyncRuntimeAdapter] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._exec = ExecutionRepository(session)
        self._sync_driver_factory = sync_driver_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))

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
        environment_group_id = options.environment_group_id
        if (
            environment_group_id is not None
            and (
                isinstance(environment_group_id, bool)
                or not isinstance(environment_group_id, int)
                or environment_group_id <= 0
            )
        ):
            raise TrialRunnerError(
                "WF_TRIAL_VARIABLE_INVALID",
                "environment_group_id must be a positive integer",
            )

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

        nodes, edges = self._materialize_sync_runtime(nodes, edges)

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
                self._execute_task(
                    instance.id,
                    task,
                    node,
                    edges,
                    options,
                    project_id=project_id,
                    definition_id=definition_id,
                )
            except Exception as exc:
                if task.status == "PENDING":
                    failed_attempt = self._exec.append_attempt(task.id)
                    self._exec.transition_attempt(failed_attempt.id, "RUNNING")
                    self._exec.transition_attempt(failed_attempt.id, "FAILED")
                if task.status in {"PENDING", "RUNNING"}:
                    self._exec.transition_task_instance(task.id, "FAILED")
                self._exec.append_run_log(
                    task_instance_id=task.id,
                    attempt_no=1,
                    message=(
                        f"{exc.code}: {exc.msg}"
                        if isinstance(exc, TrialRunnerError)
                        else str(exc)
                    ),
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

        # Persist one authoritative workflow-level result receipt and the
        # log-independent monitoring snapshot.  A trial is a real execution:
        # its component outcomes must therefore be visible in the same run
        # statistics table as scheduled/formal runs.
        terminal_tasks = self._session.scalars(
            select(TaskInstanceRecord).where(
                TaskInstanceRecord.workflow_instance_id == instance.id
            )
        ).all()
        success_count = sum(task.status == "SUCCEEDED" for task in terminal_tasks)
        failure_count = sum(task.status == "FAILED" for task in terminal_tasks)
        skipped_count = sum(task.status == "SKIPPED" for task in terminal_tasks)
        self._exec.record_result_stat(
            workflow_instance_id=instance.id,
            task_instance_id=None,
            attempt_no=0,
            success_count=success_count,
            failed_count=failure_count,
            skipped_count=skipped_count,
        )
        RunStatisticsService(self._session).finalize(instance.id)

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

    @staticmethod
    def _materialize_sync_runtime(
        nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Insert one deterministic runtime SYNC task before the graph END.

        The saved draft remains declarative. Runtime-only ``sync`` nodes are
        derived from the single endpoint selector and its mapping/condition
        companions for every trial, so retries bind the same task id.
        """
        materialized_nodes = deepcopy(nodes)
        materialized_edges = deepcopy(edges)
        if any(node.get("node_type") == "sync" for node in materialized_nodes):
            return materialized_nodes, materialized_edges
        endpoints = [node for node in materialized_nodes if node.get("node_type") == "endpoint_select"]
        if not endpoints:
            return materialized_nodes, materialized_edges
        if len(endpoints) != 1:
            raise TrialRunnerError("WF_TRIAL_SYNC_INVALID", "SYNC trial requires exactly one endpoint_select")
        endpoint = endpoints[0]
        params = deepcopy(endpoint.get("params") or {})
        base_mode = params.get("baseMode") or params.get("base_mode")
        if base_mode not in {"src_base", "tgt_base", "file_sync"}:
            raise TrialRunnerError("WF_TRIAL_SYNC_INVALID", "SYNC endpoint baseMode is unsupported")
        companions = [
            node
            for node in materialized_nodes
            if node.get("node_type") in {"field_map", "field_map_union", "condition_set"}
        ]
        for companion in companions:
            companion_params = companion.get("params") or {}
            for key in ("source", "target", "mappings", "transform_config", "target_properties", "fieldMap"):
                if key not in params and key in companion_params:
                    params[key] = deepcopy(companion_params[key])
            if companion.get("node_type") == "condition_set" and "filterExpr" in companion_params:
                transform_config = params.setdefault("transform_config", {})
                transform_config.setdefault("filter_condition", companion_params["filterExpr"])
        # B6 验收修复（2026-10-28 用户裁决）：src_base_orch/tgt_base_orch 携带的 schema 是
        # SYNC 运行时引用（schema.object 库表限定名）的必要来源；endpoint_select spec 契约
        # 不含 schema 键，物化时并入 srcSchema/tgtSchema 供 sync_runtime 合成 source/target
        for orch in materialized_nodes:
            orch_type = orch.get("node_type")
            if orch_type not in {"src_base_orch", "tgt_base_orch"}:
                continue
            orch_params = orch.get("params") or {}
            schema_value = orch_params.get("schema")
            binding_key = "srcSchema" if orch_type == "src_base_orch" else "tgtSchema"
            if binding_key not in params and isinstance(schema_value, str) and schema_value.strip():
                params[binding_key] = schema_value.strip()
        if "mappings" not in params and isinstance(params.get("fieldMap"), list):
            params["mappings"] = [
                {
                    "source_column": item.get("from", item.get("key")),
                    "target_column": item.get("to", item.get("value")),
                    "source_type": item.get("source_type", "string"),
                    "target_type": item.get("target_type", "string"),
                    "transform_expression": item.get("transform_expression", ""),
                    "mapping_status": item.get("mapping_status", "AUTO"),
                    "nullable": item.get("nullable", True),
                    "default_value": item.get("default_value"),
                }
                for item in params["fieldMap"]
                if isinstance(item, dict)
            ]
        params["_materialized_endpoint"] = endpoint["node_code"]
        runtime_code = f"sys_exec_{endpoint['node_code']}"
        design_codes = {endpoint["node_code"], *(node["node_code"] for node in companions)}
        predecessors = {
            edge["from_node"]
            for edge in materialized_edges
            if edge.get("to_node") in design_codes and edge.get("from_node") not in design_codes
        }
        successors = {
            edge["to_node"]
            for edge in materialized_edges
            if edge.get("from_node") in design_codes and edge.get("to_node") not in design_codes
        }
        materialized_nodes = [node for node in materialized_nodes if node["node_code"] not in design_codes]
        materialized_nodes.append(
            {
                "node_code": runtime_code,
                "node_type": "file_sync" if base_mode == "file_sync" else "sync",
                "name": "SYNC runtime",
                "params": params,
                "runtime_only": True,
                "source_node_code": endpoint["node_code"],
                "position_x": endpoint.get("position_x"),
                "position_y": endpoint.get("position_y"),
            }
        )
        materialized_edges = [
            edge
            for edge in materialized_edges
            if edge.get("from_node") not in design_codes and edge.get("to_node") not in design_codes
        ]
        materialized_edges.extend(
            {"from_node": predecessor, "to_node": runtime_code}
            for predecessor in sorted(predecessors)
        )
        materialized_edges.extend(
            {"from_node": runtime_code, "to_node": successor}
            for successor in sorted(successors)
        )
        return materialized_nodes, materialized_edges

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
        *,
        project_id: int,
        definition_id: int,
    ) -> None:
        """Execute one task instance (transition PENDING → RUNNING → SUCCEEDED)."""
        node_type = str(node["node_type"])
        if node_type.lower() in {"sync", "file_sync"}:
            if self._sync_driver_factory is None:
                raise TrialRunnerError(
                    "WF_TRIAL_SYNC_DRIVER_MISSING",
                    "SYNC trial requires a runtime driver",
                )
            instance = self._session.get(WorkflowInstanceRecord, instance_id)
            workflow_version = int(instance.trial_snapshot_id or instance.workflow_version_id or 0)
            sync_snapshot = {
                **deepcopy(node.get("params") or {}),
                "project_id": project_id,
                "workflow_id": definition_id,
                "workflow_version": workflow_version,
                "task_id": str(node["node_code"]),
            }
            driver = self._sync_driver_factory(sync_snapshot)
            if driver is None:
                raise TrialRunnerError(
                    "WF_TRIAL_SYNC_DRIVER_MISSING",
                    "SYNC runtime driver factory returned no driver",
                )
            # file_sync 变体：factory 会向 sync_snapshot 合成 file source/target 引用
            # （dict 可变副作用是此边界的契约），prepare 校验放宽 file_path 源。
            execute_sync_attempt(
                self._session,
                sync_snapshot,
                workflow_instance_id=instance_id,
                task_instance_id=task.id,
                driver=driver,
                allow_file_source=node_type.lower() == "file_sync",
            )
            return

        self._exec.transition_task_instance(task.id, "RUNNING")
        attempt = self._exec.append_attempt(task.id)
        self._exec.transition_attempt(attempt.id, "RUNNING")

        params = node.get("params") or {}
        variable_repository = VariableRepository(self._session)
        variable_resolver = VariableResolver(
            lambda owner_key: variable_repository.list_owner(owner_key),
            run_values={name: str(value) for name, value in (options.test_variables or {}).items()},
        )
        try:
            params, variable_snapshot = variable_resolver.resolve_parameters(
                params,
                VariableContext(
                    project_id=project_id,
                    workflow_id=definition_id,
                    task_id=str(node["node_code"]),
                    environment_group_id=options.environment_group_id,
                    attempt_no=attempt.attempt_no,
                ),
            )
        except VariableDomainError as exc:
            raise TrialRunnerError("WF_TRIAL_VARIABLE_INVALID", exc.msg) from exc
        resource_source = self._resolve_resource_source(
            project_id=project_id,
            definition_id=definition_id,
            task_id=str(node["node_code"]),
            node_type=str(node_type),
            params=params,
        )

        # WF-17: record test variable overrides.
        # Dedupe on (scope, name): a run-scope override and a persisted
        # project/workflow definition of the same name are distinct references
        # and both belong in the immutable snapshot (design §3.4).
        if options.test_variables:
            existing_rows = self._session.execute(
                select(
                    TaskInstanceVariableRuntimeRecord.scope,
                    TaskInstanceVariableRuntimeRecord.name,
                ).where(
                    TaskInstanceVariableRuntimeRecord.instance_id == instance_id,
                    TaskInstanceVariableRuntimeRecord.attempt_no == attempt.attempt_no,
                )
            ).all()
            existing_keys = {(scope, name) for scope, name in existing_rows}
            for name, value in options.test_variables.items():
                if ("run", name) in existing_keys:
                    continue
                existing_keys.add(("run", name))
                self._session.add(
                    TaskInstanceVariableRuntimeRecord(
                        instance_id=instance_id,
                        # The override row belongs to the instance's project so
                        # GET /run-snapshot can return it; cross-project reads
                        # stay filtered (P0-7 fail-closed).
                        project_id=project_id,
                        attempt_no=attempt.attempt_no,
                        expression="${run." + name + "}",
                        scope="run",
                        name=name,
                        resolved_value=str(value),
                        value_type="string",
                        source="test_override",
                    )
                )
            self._session.flush()

        # Persist the variables that were actually consumed by this task.
        # The runtime table is (instance, attempt, scope, name) unique, so
        # downstream tasks reusing the same reference must not duplicate it.
        existing_snapshot_keys = {
            (scope, name)
            for scope, name in self._session.execute(
                select(
                    TaskInstanceVariableRuntimeRecord.scope,
                    TaskInstanceVariableRuntimeRecord.name,
                ).where(
                    TaskInstanceVariableRuntimeRecord.instance_id == instance_id,
                    TaskInstanceVariableRuntimeRecord.attempt_no == attempt.attempt_no,
                )
            ).all()
        }
        snapshot_rows = []
        for item in variable_snapshot:
            key = (item["scope"], item["name"])
            if key in existing_snapshot_keys:
                continue
            existing_snapshot_keys.add(key)
            snapshot_rows.append(
                {
                    **item,
                    "instance_id": instance_id,
                    "project_id": project_id,
                    "attempt_no": attempt.attempt_no,
                }
            )
        if snapshot_rows:
            variable_repository.write_snapshot_rows(snapshot_rows)

        # WF-18: DEPENDENCY mock.  Palette component refs use the immutable
        # lower-case ``dependent`` type, while legacy drafts use
        # ``DEPENDENCY``.  Both must execute through the same dependency gate;
        # otherwise a rebuilt component graph would silently skip dependency
        # semantics and be reported as a generic successful task.
        if str(node_type).upper() in {"DEPENDENCY", "DEPENDENT"}:
            dep_id_raw = params.get("dependency_id", "")
            dep_id = str(dep_id_raw)
            def fail_dependency(code: str, message: str) -> None:
                self._exec.transition_attempt(attempt.id, "FAILED")
                self._exec.transition_task_instance(task.id, "FAILED")
                raise TrialRunnerError(code, message)

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
                fail_dependency("WF_TRIAL_DEPENDENCY_FAILED", f"dependency {dep_id} mock failed")
            else:
                try:
                    dependency_id = int(dep_id_raw)
                except (TypeError, ValueError):
                    fail_dependency(
                        "WF_TRIAL_DEPENDENCY_CONFIG_INVALID",
                        f"dependency {dep_id!r} is not a valid dependency config id",
                    )
                dependency = self._session.get(DependencyConfigRecord, dependency_id)
                if (
                    dependency is None
                    or dependency.project_id != project_id
                    or dependency.workflow_id != definition_id
                    or dependency.workflow_version != 0
                    or dependency.task_id != str(node["node_code"])
                ):
                    fail_dependency(
                        "WF_TRIAL_DEPENDENCY_CONFIG_INVALID",
                        f"dependency {dependency_id} is not bound to this workflow task",
                    )
                try:
                    dependency_payload = {
                        "groups": json.loads(dependency.groups_json),
                        "group_relation": dependency.group_relation,
                        "check_interval_seconds": dependency.check_interval_seconds,
                        "failure_policy": dependency.failure_policy,
                        "failure_waiting_seconds": dependency.failure_waiting_seconds,
                        "timeout_seconds": dependency.timeout_seconds,
                        "dependent_wait_timeout_enabled": dependency.dependent_wait_timeout_enabled,
                        "dependent_wait_timeout_seconds": dependency.dependent_wait_timeout_seconds,
                        "dependent_wait_timeout_strategies": (
                            json.loads(dependency.dependent_wait_timeout_strategies_json)
                            if dependency.dependent_wait_timeout_strategies_json is not None
                            else None
                        ),
                    }
                    conditions, group_relation, policy = parse_groups(dependency_payload)
                    verdict, _resolved = evaluate_expression(
                        conditions,
                        group_relation,
                        self._clock(),
                        policy.get("timeout_seconds"),
                        metrics_history_lookup(self._session, project_id),
                    )
                except (DependencyDomainError, json.JSONDecodeError, TypeError, ValueError) as exc:
                    fail_dependency(
                        "WF_TRIAL_DEPENDENCY_CONFIG_INVALID",
                        f"dependency {dependency_id} configuration is invalid: {exc}",
                    )
                self._exec.append_run_log(
                    task_instance_id=task.id,
                    attempt_no=attempt.attempt_no,
                    message=f"DEPENDENCY {dependency_id} verdict={verdict}",
                    level="INFO" if verdict == "satisfied" else "ERROR",
                )
                if verdict != "satisfied":
                    code = {
                        "failed": "WF_TRIAL_DEPENDENCY_FAILED",
                        "pending": "WF_TRIAL_DEPENDENCY_PENDING",
                        "timeout": "WF_TRIAL_DEPENDENCY_TIMEOUT",
                    }.get(verdict, "WF_TRIAL_DEPENDENCY_UNSATISFIED")
                    fail_dependency(
                        code,
                        f"dependency {dependency_id} verdict is {verdict}",
                    )

        # WF-20: SQL precheck.
        if node_type == "SQL" and options.sql_precheck:
            sql = params.get("sql") or params.get("sql_file")
            if sql:
                self._exec.append_run_log(
                    task_instance_id=task.id,
                    attempt_no=attempt.attempt_no,
                    message=f"SQL precheck passed for: {sql[:80]}",
                )

        # NORMAL execution components: when a draft explicitly supplies code,
        # execute it through a bounded subprocess and persist its output.  Nodes
        # without executable content retain the deterministic trial behaviour.
        execution_output: dict[str, Any] = {"node_code": node["node_code"], "status": "ok"}
        # Explicit SQL execution is opt-in.  The isolated SQLite runtime
        # provides a real result set without granting trial code host or
        # datasource access; datasource-backed execution remains in SQL IDE.
        if str(node_type).upper() == "SQL" and (options.sql_execute or params.get("execute") is True):
            sql = resource_source or params.get("sql") or params.get("query")
            if not sql:
                raise TrialRunnerError("WF_TRIAL_SQL_EMPTY", "SQL node requires sql/query when execution is enabled")
            try:
                with sqlite3.connect(":memory:") as conn:
                    cursor = conn.execute(str(sql))
                    rows = cursor.fetchall() if cursor.description else []
                    columns = [column[0] for column in (cursor.description or ())]
                execution_output.update({"sql": str(sql), "columns": columns, "rows": rows, "row_count": len(rows)})
            except sqlite3.Error as exc:
                raise TrialRunnerError("WF_TRIAL_SQL_FAILED", f"SQL execution failed: {exc}") from exc

        if node_type in {"PYTHON", "python", "SHELL", "shell"}:
            source = resource_source or params.get("script") or params.get("code") or params.get("command")
            if source:
                command = [sys.executable, "-c", str(source)] if node_type.lower() == "python" else (
                    ["cmd", "/c", str(source)] if os.name == "nt" else ["sh", "-c", str(source)]
                )
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=min(int(params.get("timeout_seconds", 30)), 120),
                    env={**os.environ, **{str(k): str(v) for k, v in (params.get("env") or {}).items()}},
                    check=False,
                )
                execution_output.update({
                    "exit_code": completed.returncode,
                    "stdout": completed.stdout[-20000:],
                    "stderr": completed.stderr[-20000:],
                })
                if completed.returncode != 0:
                    raise TrialRunnerError(
                        "WF_TRIAL_SCRIPT_FAILED",
                        f"{node_type} node exited with {completed.returncode}",
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
            output_json=json.dumps(execution_output),
        )

        self._exec.transition_attempt(attempt.id, "SUCCEEDED")
        self._exec.transition_task_instance(task.id, "SUCCEEDED")

    def _resolve_resource_source(
        self,
        *,
        project_id: int,
        definition_id: int,
        task_id: str,
        node_type: str,
        params: dict[str, Any],
    ) -> str | None:
        """Resolve one explicitly pinned script resource and verify its immutable content."""
        if params.get("sourceMode", "inline") != "resource":
            return None
        ref = params.get("resourceRef")
        if not isinstance(ref, dict):
            raise TrialRunnerError("WF_TRIAL_RESOURCE_REF", "resourceRef is required in resource mode")
        resource_id = ref.get("resourceId")
        version = ref.get("version")
        if not isinstance(resource_id, int) or resource_id <= 0 or not isinstance(version, int) or version <= 0:
            raise TrialRunnerError("WF_TRIAL_RESOURCE_REF", "resourceRef requires positive resourceId and version")
        resource = self._session.get(ResourceRecord, resource_id)
        expected_kind = node_type.lower()
        if resource is None or resource.project_id != project_id or resource.kind != expected_kind:
            raise TrialRunnerError("WF_TRIAL_RESOURCE_REF", "resourceRef does not match the project and component kind")
        binding = self._session.scalar(
            select(ResourceBindingRecord).where(
                ResourceBindingRecord.project_id == project_id,
                ResourceBindingRecord.workflow_id == definition_id,
                ResourceBindingRecord.workflow_version == 1,
                ResourceBindingRecord.task_id == task_id,
                ResourceBindingRecord.resource_id == resource_id,
                ResourceBindingRecord.resource_version == version,
            )
        )
        if binding is None:
            raise TrialRunnerError("WF_TRIAL_RESOURCE_BINDING", "resourceRef is not bound to this workflow task")
        version_row = self._session.scalar(
            select(ResourceVersionRecord).where(
                ResourceVersionRecord.resource_id == resource_id,
                ResourceVersionRecord.version == version,
            )
        )
        if version_row is None:
            raise TrialRunnerError("WF_TRIAL_RESOURCE_REF", "resource version does not exist")
        path = os.path.join(storage_dir(), version_row.storage_path)
        try:
            with open(path, "rb") as handle:
                content = handle.read()
        except OSError as exc:
            raise TrialRunnerError("WF_TRIAL_RESOURCE_STORAGE", "resource content is unavailable") from exc
        if len(content) != version_row.size_bytes or hashlib.sha256(content).hexdigest() != version_row.digest:
            raise TrialRunnerError("WF_TRIAL_RESOURCE_INTEGRITY", "resource content failed integrity verification")
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TrialRunnerError("WF_TRIAL_RESOURCE_ENCODING", "script resource must be UTF-8") from exc
