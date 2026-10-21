"""R8-A AI tool handler builders for the seven non-run_sql tools.

Contract (frozen v1): docs/increments/2026-10-17-R8-A八工具契约.md §7.
Each builder returns a ``Handler`` callable composed over injected ports.
The bridge envelope owns auth/audit/budget/error normalization; handlers
only implement tool-specific logic and raise ``ToolError`` for failures.
"""

from __future__ import annotations

import hashlib
from collections import deque
from typing import Any, Mapping

from sqlalchemy import func, select

from rebuild.ai_bridge import Handler, ToolError
from rebuild.execution.models import TaskInstanceRecord, WorkflowInstanceRecord
from rebuild.sql_ide.linter import lint_sql
from rebuild.workflow.models import (
    WorkflowDefinitionRecord,
    WorkflowEdgeRecord,
    WorkflowNodeRecord,
    WorkflowVersionRecord,
)
from rebuild.datasource.contracts import DataSourceDraft
from rebuild.workflow.repository import VALID_NODE_TYPES


def _datasource_draft(record: Any) -> DataSourceDraft:
    return DataSourceDraft(
        name=record.name,
        kind=record.kind,
        host=record.host,
        port=record.port,
        database=record.database_name,
        username=record.username,
        password=record.password,
    )


# ---------------------------------------------------------------------------
# search_schema — metadata catalog search (§7.1)
# ---------------------------------------------------------------------------


def build_search_schema_handler(session_factory: Any, connector_factory: Any) -> Handler:
    """Compose the search_schema handler over the metadata catalog."""

    def handler(
        params: Mapping[str, Any],
        page_context: Mapping[str, Any] | None,
        ctx: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        project_id = ctx["project_id"]
        keyword = params.get("keyword", "")
        schema_name = params.get("schema_name")
        table_name = params.get("table_name")
        include_columns = params.get("include_columns", False)
        limit = params.get("limit", 20)
        cursor = params.get("cursor")

        with session_factory() as session:
            # Find the project's primary datasource for metadata browsing
            from rebuild.datasource.models import ProjectDatasourceRecord

            datasource = session.scalar(
                select(ProjectDatasourceRecord).where(
                    ProjectDatasourceRecord.project_id == project_id
                )
            )
            if datasource is None:
                raise ToolError("NOT_FOUND")

            from rebuild.datasource.metadata import metadata_catalog_for

            try:
                catalog = metadata_catalog_for(
                    _datasource_draft(datasource),
                    connector=connector_factory(project_id, datasource.id),
                )
                objects = catalog.objects(
                    schema_name or datasource.database_name,
                    after=str(cursor) if cursor else None,
                    limit=limit,
                )
            except Exception as exc:
                raise ToolError(
                    "DEPENDENCY_UNAVAILABLE", retryable=True,
                    details={"dependency": type(exc).__name__},
                ) from exc
            entries: list[dict[str, Any]] = []

            has_more = len(objects) > limit
            for obj in objects[:limit]:
                obj_name = obj.get("name", "")
                obj_kind = obj.get("type", "table")
                obj_schema = obj.get("schema", schema_name or datasource.database_name)

                # Apply filters
                if keyword and keyword.lower() not in obj_name.lower():
                    continue
                if table_name and obj_name != table_name:
                    continue

                entry: dict[str, Any] = {
                    "kind": obj_kind.upper() if obj_kind else "TABLE",
                    "schema_name": obj_schema,
                    "table_name": obj_name,
                    "table_comment": obj.get("comment"),
                    "digest": hashlib.sha256(
                        f"{obj_schema}.{obj_name}".encode()
                    ).hexdigest()[:16],
                }

                if include_columns:
                    try:
                        columns = catalog.columns(obj_schema, obj_name)
                        entry["columns"] = [
                            {
                                "name": col.get("name", ""),
                                "type": col.get("data_type", ""),
                                "nullable": col.get("nullable", True),
                                "comment": col.get("comment"),
                            }
                            for col in columns
                        ]
                    except Exception as exc:
                        raise ToolError(
                            "DEPENDENCY_UNAVAILABLE", retryable=True,
                            details={"dependency": type(exc).__name__},
                        ) from exc

                entries.append(entry)
                if len(entries) >= limit:
                    break

            next_cursor = entries[-1]["table_name"] if has_more and entries else None

            return {
                "entries": entries,
                "next_cursor": next_cursor,
                "row_count": len(entries),
                "truncated": has_more,
            }

    return handler


# ---------------------------------------------------------------------------
# validate_sql — SQL lint (§7.2)
# ---------------------------------------------------------------------------


def build_validate_sql_handler(session_factory: Any) -> Handler:
    """Compose the validate_sql handler over the sqlglot linter."""

    def handler(
        params: Mapping[str, Any],
        page_context: Mapping[str, Any] | None,
        ctx: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        sql = params["sql"]
        # datasource_id is mandatory even when the caller supplies a dialect:
        # it is the project-isolation anchor and must never be bypassed by an
        # optional request field.
        from rebuild.datasource.models import ProjectDatasourceRecord

        with session_factory() as session:
            datasource = session.get(ProjectDatasourceRecord, params["datasource_id"])
            if datasource is None or datasource.project_id != ctx["project_id"]:
                raise ToolError("NOT_FOUND")
            dialect = params.get("dialect") or datasource.kind

        result = lint_sql(sql, dialect=dialect)
        diagnostics = result.get("diagnostics", [])

        issues = [
            {
                "severity": diag.get("severity", "ERROR").upper(),
                "line": diag.get("line"),
                "column": diag.get("column"),
                "message": diag.get("message", ""),
                "code": diag.get("code", "LINT"),
            }
            for diag in diagnostics
        ]

        lint_ref = hashlib.sha256(sql.encode()).hexdigest()[:16]

        return {
            "valid": result.get("valid", len(issues) == 0),
            "issues": issues,
            "lint_ref": lint_ref,
        }

    return handler


# ---------------------------------------------------------------------------
# get_workflow — workflow definition read (§7.4)
# ---------------------------------------------------------------------------


def build_get_workflow_handler(session_factory: Any) -> Handler:
    """Compose the get_workflow handler over WorkflowRepository."""

    def handler(
        params: Mapping[str, Any],
        page_context: Mapping[str, Any] | None,
        ctx: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        project_id = ctx["project_id"]
        workflow_id = params.get("workflow_id")
        name = params.get("name")
        version = params.get("version")

        with session_factory() as session:
            if workflow_id is not None:
                definition = session.get(WorkflowDefinitionRecord, workflow_id)
            elif name:
                definition = session.scalar(
                    select(WorkflowDefinitionRecord).where(
                        WorkflowDefinitionRecord.project_id == project_id,
                        WorkflowDefinitionRecord.name == name,
                    )
                )
            else:
                raise ToolError(
                    "INVALID_PARAMS",
                    details={"fields": {"workflow_id": "workflow_id or name required"}},
                )

            if definition is None or definition.project_id != project_id:
                raise ToolError("NOT_FOUND")

            # Get the requested or current version
            if version is not None:
                version_record = session.scalar(
                    select(WorkflowVersionRecord).where(
                        WorkflowVersionRecord.definition_id == definition.id,
                        WorkflowVersionRecord.version == version,
                    )
                )
                if version_record is None:
                    raise ToolError("NOT_FOUND")
            else:
                version_record = session.scalar(
                    select(WorkflowVersionRecord)
                    .where(WorkflowVersionRecord.definition_id == definition.id)
                    .order_by(WorkflowVersionRecord.version.desc())
                    .limit(1)
                )

            # Count nodes/edges
            node_count = (
                session.scalar(
                    select(func.count())
                    .select_from(WorkflowNodeRecord)
                    .where(WorkflowNodeRecord.version_id == version_record.id)
                )
                if version_record
                else 0
            ) or 0
            edge_count = (
                session.scalar(
                    select(func.count())
                    .select_from(WorkflowEdgeRecord)
                    .where(WorkflowEdgeRecord.version_id == version_record.id)
                )
                if version_record
                else 0
            ) or 0

            # Latest run
            latest_run = None
            if version_record:
                run = session.scalar(
                    select(WorkflowInstanceRecord)
                    .where(WorkflowInstanceRecord.workflow_version_id == version_record.id)
                    .order_by(WorkflowInstanceRecord.started_at.desc())
                    .limit(1)
                )
                if run:
                    latest_run = {
                        "run_id": run.id,
                        "status": run.status,
                        "started_at": run.started_at.isoformat() if run.started_at else None,
                    }

            return {
                "workflow_id": definition.id,
                "name": definition.name,
                "version": version_record.version if version_record else definition.current_version,
                "publish_status": version_record.status if version_record else "DRAFT",
                "node_count": node_count,
                "edge_count": edge_count,
                "updated_at": definition.updated_at.isoformat() if hasattr(definition, "updated_at") and definition.updated_at else None,
                "latest_run": latest_run,
                "refs": {"workflow_id": definition.id},
            }

    return handler


# ---------------------------------------------------------------------------
# validate_workflow — workflow definition validation (§7.5)
# ---------------------------------------------------------------------------


def build_validate_workflow_handler(session_factory: Any) -> Handler:
    """Compose the validate_workflow handler."""

    def handler(
        params: Mapping[str, Any],
        page_context: Mapping[str, Any] | None,
        ctx: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        project_id = ctx["project_id"]
        definition = params.get("definition")
        workflow_id = params.get("workflow_id")
        version = params.get("version")

        issues: list[dict[str, Any]] = []

        if definition is not None:
            # Inline definition validation
            issues = _validate_graph(definition)
        elif workflow_id is not None:
            # Load from repository and validate
            with session_factory() as session:
                wf_def = session.get(WorkflowDefinitionRecord, workflow_id)
                if wf_def is None or wf_def.project_id != project_id:
                    raise ToolError("NOT_FOUND")
                if version is not None:
                    ver = session.scalar(
                        select(WorkflowVersionRecord).where(
                            WorkflowVersionRecord.definition_id == workflow_id,
                            WorkflowVersionRecord.version == version,
                        )
                    )
                else:
                    ver = session.scalar(
                        select(WorkflowVersionRecord)
                        .where(WorkflowVersionRecord.definition_id == workflow_id)
                        .order_by(WorkflowVersionRecord.version.desc())
                        .limit(1)
                    )
                if ver is None:
                    raise ToolError("NOT_FOUND")
                # Validate the version's nodes/edges
                nodes = session.scalars(
                    select(WorkflowNodeRecord).where(WorkflowNodeRecord.version_id == ver.id)
                ).all()
                edges = session.scalars(
                    select(WorkflowEdgeRecord).where(WorkflowEdgeRecord.version_id == ver.id)
                ).all()
                graph = {
                    "nodes": [
                        {"id": n.id, "node_code": n.node_code, "node_type": n.node_type}
                        for n in nodes
                    ],
                    "edges": [
                        {"id": e.id, "from_node": e.from_node, "to_node": e.to_node}
                        for e in edges
                    ],
                }
                issues = _validate_graph(graph)
        else:
            raise ToolError(
                "INVALID_PARAMS",
                details={"fields": {"definition": "definition or workflow_id required"}},
            )

        return {"valid": len(issues) == 0, "issues": issues}

    return handler


def _validate_graph(graph: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Validate a workflow graph structure."""
    issues: list[dict[str, Any]] = []
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    node_codes: set[str] = set()
    for node in nodes:
        code = node.get("node_code") or node.get("id")
        if not code:
            issues.append(
                {
                    "severity": "ERROR",
                    "code": "NODE_MISSING_CODE",
                    "message": "Node missing node_code/id",
                }
            )
            continue
        if code in node_codes:
            issues.append(
                {
                    "severity": "ERROR",
                    "code": "DUPLICATE_NODE_CODE",
                    "message": f"Duplicate node_code: {code}",
                    "node_id": code,
                }
            )
        node_codes.add(code)

        node_type = node.get("node_type")
        if node_type and node_type not in VALID_NODE_TYPES:
            issues.append(
                {
                    "severity": "ERROR",
                    "code": "INVALID_NODE_TYPE",
                    "message": f"Invalid node_type: {node_type}",
                    "node_id": code,
                }
            )

    for edge in edges:
        from_node = edge.get("from_node")
        to_node = edge.get("to_node")
        if from_node and from_node not in node_codes:
            issues.append(
                {
                    "severity": "ERROR",
                    "code": "EDGE_UNKNOWN_FROM",
                    "message": f"Edge from_node not in graph: {from_node}",
                }
            )
        if to_node and to_node not in node_codes:
            issues.append(
                {
                    "severity": "ERROR",
                    "code": "EDGE_UNKNOWN_TO",
                    "message": f"Edge to_node not in graph: {to_node}",
                }
            )

    if not nodes:
        issues.append(
            {
                "severity": "WARN",
                "code": "EMPTY_GRAPH",
                "message": "Workflow has no nodes",
            }
        )

    return issues


# ---------------------------------------------------------------------------
# inspect_workflow_run — run record diagnosis (§7.6)
# ---------------------------------------------------------------------------


def build_inspect_workflow_run_handler(session_factory: Any) -> Handler:
    """Compose the inspect_workflow_run handler."""

    def handler(
        params: Mapping[str, Any],
        page_context: Mapping[str, Any] | None,
        ctx: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        project_id = ctx["project_id"]
        run_id = params["run_id"]
        attempt = params.get("attempt")
        include_tasks = params.get("include_tasks", False)

        with session_factory() as session:
            run = session.get(WorkflowInstanceRecord, run_id)
            if run is None:
                raise ToolError("NOT_FOUND")

            # Verify project access via workflow definition
            wf_ver = session.get(WorkflowVersionRecord, run.workflow_version_id)
            if wf_ver is None:
                raise ToolError("NOT_FOUND")
            wf_def = session.get(WorkflowDefinitionRecord, wf_ver.definition_id)
            if wf_def is None or wf_def.project_id != project_id:
                raise ToolError("NOT_FOUND")

            tasks = None
            if include_tasks:
                task_records = session.scalars(
                    select(TaskInstanceRecord).where(
                        TaskInstanceRecord.workflow_instance_id == run_id
                    )
                ).all()
                if attempt is not None and attempt != run.current_attempt_no:
                    raise ToolError("NOT_FOUND")
                truncated = len(task_records) > 1000
                tasks = [
                    {
                        "task_id": t.id,
                        "node_id": t.task_id,
                        "type": t.task_id.split(":")[0] if ":" in t.task_id else t.task_id,
                        "status": t.status,
                        "rows_ok": None,
                        "rows_failed": None,
                        "rows_skipped": None,
                        "started_at": t.started_at.isoformat() if t.started_at else None,
                        "finished_at": t.finished_at.isoformat() if t.finished_at else None,
                    }
                    for t in task_records[:1000]
                ]
            else:
                truncated = False

            return {
                "run_id": run.id,
                "status": run.status,
                "cancel_requested": getattr(run, "cancel_requested", None),
                "attempt_id": run.current_attempt_no,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "tasks": tasks,
                "truncated": truncated,
                "refs": {"run_id": run.id},
            }

    return handler


# ---------------------------------------------------------------------------
# get_task_metrics — task statistics (§7.7)
# ---------------------------------------------------------------------------


def build_get_task_metrics_handler(session_factory: Any) -> Handler:
    """Compose the get_task_metrics handler."""

    def handler(
        params: Mapping[str, Any],
        page_context: Mapping[str, Any] | None,
        ctx: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        project_id = ctx["project_id"]
        run_id = params.get("run_id")
        time_window = params.get("time_window")
        group_by = params.get("group_by")

        with session_factory() as session:
            if run_id is not None:
                run = session.get(WorkflowInstanceRecord, run_id)
                if run is None:
                    raise ToolError("NOT_FOUND")
                # No persisted per-run status buckets exist yet. R7 forbids
                # inventing them from task counters.
                raise ToolError("DEPENDENCY_UNAVAILABLE", retryable=True)
            elif time_window is not None:
                # The persisted R7 rows do not contain the frozen bucket
                # contract's total/cancelled fields.  Adding counts or filling
                # cancelled=0 would be forbidden derivation, so stay honest
                # until a compatible collector/storage projection exists.
                raise ToolError("DEPENDENCY_UNAVAILABLE", retryable=True)
            else:
                raise ToolError(
                    "INVALID_PARAMS",
                    details={"fields": {"run_id": "run_id or time_window required"}},
                )

            return {
                "buckets": buckets,
                "p95_duration_ms": None,  # Not derived (§7.7 red line)
                "refs": {"run_id": run_id} if run_id else {"time_window": time_window},
            }

    return handler


# ---------------------------------------------------------------------------
# get_lineage — lineage analysis (§7.8)
# ---------------------------------------------------------------------------


def build_get_lineage_handler(session_factory: Any) -> Handler:
    """Compose the get_lineage handler."""

    def handler(
        params: Mapping[str, Any],
        page_context: Mapping[str, Any] | None,
        ctx: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        project_id = ctx["project_id"]
        entity_type = params["entity_type"]
        entity = params["entity"]
        direction = params.get("direction", "BOTH")
        depth = params.get("depth", 3)

        # Parse entity: schema.table or schema.table.column
        parts = entity.split(".")
        if len(parts) < 2:
            raise ToolError(
                "INVALID_PARAMS",
                details={"fields": {"entity": "must be schema.table or schema.table.column"}},
            )

        with session_factory() as session:
            from rebuild.metrics.models import LineageWritebackRecord

            lineage_records = session.scalars(
                select(LineageWritebackRecord).where(
                    LineageWritebackRecord.project_id == project_id
                )
            ).all()

            raw_edges = [(r.source_entity, r.target_entity, r.run_kind) for r in lineage_records]
            if not any(entity in (source, target) for source, target, _ in raw_edges):
                raise ToolError("NOT_FOUND")
            node_ids = {entity}
            edges: list[dict[str, Any]] = []
            seen_edges: set[tuple[str, str, str]] = set()
            queue = deque([(entity, 0)])
            truncated = False
            while queue:
                current, level = queue.popleft()
                if level >= depth:
                    continue
                for source, target, kind in raw_edges:
                    follows = (
                        direction in ("DOWNSTREAM", "BOTH") and source == current
                    ) or (
                        direction in ("UPSTREAM", "BOTH") and target == current
                    )
                    if not follows:
                        continue
                    edge_key = (source, target, kind)
                    if edge_key not in seen_edges:
                        edges.append({"source": source, "target": target, "kind": kind})
                        seen_edges.add(edge_key)
                    neighbour = target if source == current else source
                    if neighbour not in node_ids:
                        if len(node_ids) >= 500:
                            truncated = True
                            continue
                        node_ids.add(neighbour)
                        queue.append((neighbour, level + 1))
            nodes = [
                {"id": item, "type": entity_type, "label": item}
                for item in sorted(node_ids)
            ]

            return {
                "root": entity,
                "nodes": nodes,
                "edges": edges,
                "truncated": truncated,
                "refs": {"entity": entity, "direction": direction, "depth": depth},
            }

    return handler


# ---------------------------------------------------------------------------
# Assembly: build all handlers from app.state
# ---------------------------------------------------------------------------


def build_all_handlers(session_factory: Any, connector_factory: Any) -> dict[str, Handler]:
    """Build all eight tool handlers from the given session_factory.

    Returns a mapping of tool name to handler callable. The run_sql handler
    is composed separately (it needs the execution port, not session_factory).
    """
    return {
        "search_schema": build_search_schema_handler(session_factory, connector_factory),
        "validate_sql": build_validate_sql_handler(session_factory),
        "get_workflow": build_get_workflow_handler(session_factory),
        "validate_workflow": build_validate_workflow_handler(session_factory),
        "inspect_workflow_run": build_inspect_workflow_run_handler(session_factory),
        "get_task_metrics": build_get_task_metrics_handler(session_factory),
        "get_lineage": build_get_lineage_handler(session_factory),
    }
