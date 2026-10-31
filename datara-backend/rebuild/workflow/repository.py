"""Definition CRUD, draft editing, publish snapshot and version queries for the
new-Backend workflow domain (大盘缺口 #2/#12).

Design source (frozen): docs/increments/2026-10-14-datara-platform-rebuild-design.md
§3.1 (项目/工作流领域模型) + §4 (试运行/正式运行).

- Draft = definition-scoped node/edge rows with version_id NULL; upserts
  replace by node_code / (from_node, to_node) so re-saving is idempotent and
  draft edits can never touch published snapshot copies (version_id NOT NULL).
- publish() snapshots the current draft into a new monotonic workflow_version
  (status PUBLISHED) + version-scoped node/edge copies + one
  workflow_publish_record, bumps workflow_definition.current_version, and binds
  a snapshot_digest (sha256 over the canonical copied-row JSON). 正式运行必须
  绑定 workflow_version_id (§4.2), so published rows are frozen.
- Immutability: update_version_content() mutates only while the version row is
  status DRAFT (the §4.1 结果转正式版本 slot); anything else →
  WF_VERSION_IMMUTABLE (409). No repository path rewrites published copies,
  and get_version() re-verifies the stored digest against the copied rows
  (tamper evidence).
- Deletion guard: definitions with a published version cannot be deleted
  (WF_DEFINITION_HAS_PUBLISHED) so formal-run version bindings stay resolvable.
- Narrow scope: workflow_schedule is modeled only; firing and latest-published
  version resolution belong to the scheduler domain (T33). workflow_variable
  (§3.1) is owned by the existing variables domain; workflow_draft_snapshot
  (§4.1) lands with the trial-run domain.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from common.models import Component, ComponentVersion
from rebuild.workflow.models import (
    WorkflowDefinitionRecord,
    WorkflowCategoryRecord,
    WorkflowEdgeRecord,
    WorkflowNodeRecord,
    WorkflowPublishRecord,
    WorkflowVersionRecord,
)
from rebuild.component_spec.catalogue import (
    DESIGN_COMPONENT_TYPES,
    HIDDEN_INPUTS,
    RUNTIME_ONLY_TYPES,
    WORKFLOW_COMPONENT_TYPES,
)

# Design §3.2 first-phase Palette: task types + flow components.
VALID_NODE_TYPES = (
    "FLOW",
    "SYNC",
    "SQL",
    "PYTHON",
    "SHELL",
    "DEPENDENCY",
    "START",
    "END",
    "CONDITION",
    "FORK",
    "JOIN",
    "WAIT",
    "SUB_WORKFLOW",
)
LEGACY_NODE_TYPES = frozenset(VALID_NODE_TYPES)
WORKFLOW_TYPES = frozenset(WORKFLOW_COMPONENT_TYPES)


def _component_ref(node_type: str, node: dict[str, Any]) -> dict[str, Any] | None:
    ref = node.get("component_ref")
    if not isinstance(ref, dict):
        return None
    if ref.get("type") != node_type:
        return None
    version = ref.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        return None
    return {"type": node_type, "version": version}


def _kind_for_component(node_type: str) -> str | None:
    return next((kind for kind, values in WORKFLOW_COMPONENT_TYPES.items() if node_type in values), None)


def _forbidden_hidden_paths(value: Any, path: str = "params") -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in HIDDEN_INPUTS or key == "_componentRef":
                violations.append(child_path)
            violations.extend(_forbidden_hidden_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_forbidden_hidden_paths(child, f"{path}[{index}]"))
    return violations


def _validate_sync_form_params(node_type: str, params: dict[str, Any]) -> None:
    """Validate the serializable form contract for sync passthrough nodes.

    These nodes are declarative, but malformed values otherwise survive draft
    save and fail much later during materialization.  Keep the gate limited to
    explicit values (empty forms remain valid for legacy drafts).
    """
    if node_type == "endpoint_select":
        mode = params.get("baseMode", params.get("base_mode"))
        if "baseMode" in params and "base_mode" in params and params["baseMode"] != params["base_mode"]:
            raise WorkflowDomainError("WF_SYNC_FORM_INVALID", "endpoint_select baseMode aliases must agree")
        if mode is not None and mode not in {"src_base", "tgt_base", "file_sync"}:
            raise WorkflowDomainError("WF_SYNC_FORM_INVALID", "endpoint_select baseMode is unsupported")
        if "fileType" in params and params["fileType"] not in {"csv", "txt", "excel"}:
            raise WorkflowDomainError("WF_SYNC_FORM_INVALID", "endpoint_select fileType is unsupported")
        if "fileEncoding" in params and params["fileEncoding"] not in {"utf-8", "gbk", "gb18030"}:
            raise WorkflowDomainError("WF_SYNC_FORM_INVALID", "endpoint_select fileEncoding is unsupported")
        if "fileHeaderRows" in params and (
            isinstance(params["fileHeaderRows"], bool)
            or not isinstance(params["fileHeaderRows"], int)
            or params["fileHeaderRows"] < 0
        ):
            raise WorkflowDomainError("WF_SYNC_FORM_INVALID", "endpoint_select fileHeaderRows must be >= 0")
    elif node_type in {"field_map", "field_map_union"}:
        mappings = params.get("fieldMap")
        if mappings is not None:
            if not isinstance(mappings, list) or any(
                not isinstance(item, dict)
                or not ((isinstance(item.get("from"), str) and isinstance(item.get("to"), str))
                        or (isinstance(item.get("key"), str) and isinstance(item.get("value"), str)))
                for item in mappings
            ):
                raise WorkflowDomainError("WF_SYNC_FORM_INVALID", f"{node_type} fieldMap entries must be string pairs")
    elif node_type == "condition_set":
        for key in ("filterExpr", "incrementalColumn", "incrementalExpr"):
            if key in params and params[key] is not None and not isinstance(params[key], str):
                raise WorkflowDomainError("WF_SYNC_FORM_INVALID", f"condition_set {key} must be text")


# Design §3.1 workflow version states. publish() creates PUBLISHED rows; the
# DRAFT slot is reserved for the §4.1 结果转正式版本 path.
VALID_VERSION_STATUSES = ("DRAFT", "PUBLISHED", "RUNNING", "DISABLED", "ARCHIVED")


class WorkflowDomainError(ValueError):
    """Domain rejection carrying a stable machine code and HTTP status."""

    def __init__(self, code: str, msg: str, status: int = 400) -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.status = status

    def payload(self) -> dict[str, Any]:
        return {"code": self.code, "msg": self.msg, "data": None}


def snapshot_digest(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
    """sha256 over the canonical snapshot JSON (sorted nodes/edges, stable keys)."""
    canonical = json.dumps(
        {
            "nodes": sorted(nodes, key=lambda n: n["node_code"]),
            "edges": sorted(edges, key=lambda e: (e["from_node"], e["to_node"])),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class WorkflowRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # -- definitions --------------------------------------------------------

    def create_definition(
        self, project_id: int, name: str, description: str = "", workflow_type: str = "NORMAL"
    ) -> dict[str, Any]:
        workflow_type = workflow_type.strip().upper()
        if workflow_type not in WORKFLOW_TYPES:
            raise WorkflowDomainError("WF_TYPE_UNKNOWN", "workflow_type must be NORMAL, SYNC, or STREAM")
        existing = self._session.scalar(
            select(WorkflowDefinitionRecord).where(
                WorkflowDefinitionRecord.project_id == project_id,
                WorkflowDefinitionRecord.name == name,
            )
        )
        if existing is not None:
            raise WorkflowDomainError("WF_NAME_CONFLICT", f"workflow name {name!r} already exists in project", 409)
        record = WorkflowDefinitionRecord(
            project_id=project_id,
            name=name,
            description=description,
            workflow_type=workflow_type,
        )
        self._session.add(record)
        self._session.flush()
        return self._definition_payload(record, include_draft=False)

    def list_definitions(self, project_id: int) -> list[dict[str, Any]]:
        rows = self._session.scalars(
            select(WorkflowDefinitionRecord)
            .where(WorkflowDefinitionRecord.project_id == project_id)
            .order_by(WorkflowDefinitionRecord.id)
        ).all()
        return [self._definition_payload(row, include_draft=False) for row in rows]

    def get_definition(self, project_id: int, definition_id: int) -> dict[str, Any]:
        record = self._definition(project_id, definition_id)
        return self._definition_payload(record, include_draft=True)

    def update_definition(
        self,
        project_id: int,
        definition_id: int,
        name: str | None = None,
        description: str | None = None,
        workflow_type: str | None = None,
    ) -> dict[str, Any]:
        record = self._definition(project_id, definition_id)
        if name is not None and name != record.name:
            clash = self._session.scalar(
                select(WorkflowDefinitionRecord).where(
                    WorkflowDefinitionRecord.project_id == project_id,
                    WorkflowDefinitionRecord.name == name,
                )
            )
            if clash is not None:
                raise WorkflowDomainError("WF_NAME_CONFLICT", f"workflow name {name!r} already exists in project", 409)
            record.name = name
        if description is not None:
            record.description = description
        if workflow_type is not None:
            workflow_type = "NORMAL" if workflow_type == "ETL" else workflow_type
            if workflow_type not in WORKFLOW_TYPES:
                raise WorkflowDomainError("WF_WORKFLOW_TYPE_INVALID", "workflow_type must be NORMAL, SYNC, or STREAM")
            if workflow_type != record.workflow_type and record.current_version is not None:
                raise WorkflowDomainError(
                    "WF_WORKFLOW_TYPE_IMMUTABLE",
                    "a published workflow cannot change type; create a new definition for another workflow kind",
                    409,
                )
            draft_nodes = self._draft_nodes(definition_id)
            incompatible = [
                node.node_type
                for node in draft_nodes
                if (kind := _kind_for_component(node.node_type)) is not None and kind != workflow_type
            ]
            if workflow_type != "SYNC" and any(node.node_type == "SYNC" for node in draft_nodes):
                incompatible.append("SYNC")
            if incompatible:
                raise WorkflowDomainError(
                    "WF_WORKFLOW_TYPE_MISMATCH",
                    f"draft contains components incompatible with {workflow_type}: {sorted(set(incompatible))}",
                )
            record.workflow_type = workflow_type
        self._session.flush()
        return self._definition_payload(record, include_draft=False)

    def delete_definition(self, project_id: int, definition_id: int) -> None:
        record = self._definition(project_id, definition_id)
        if record.current_version is not None:
            raise WorkflowDomainError(
                "WF_DEFINITION_HAS_PUBLISHED",
                "definitions with published versions cannot be deleted (formal runs bind workflow_version_id)",
                409,
            )
        # Draft-only definition: drop the draft rows, then the definition itself.
        for node in self._session.scalars(
            select(WorkflowNodeRecord).where(WorkflowNodeRecord.definition_id == definition_id)
        ).all():
            self._session.delete(node)
        for edge in self._session.scalars(
            select(WorkflowEdgeRecord).where(WorkflowEdgeRecord.definition_id == definition_id)
        ).all():
            self._session.delete(edge)
        self._session.delete(record)
        self._session.flush()

    # -- draft editing (version_id NULL rows only) ---------------------------

    def upsert_draft_node(self, project_id: int, definition_id: int, node: dict[str, Any]) -> dict[str, Any]:
        definition = self._definition(project_id, definition_id)
        node_code = str(node["node_code"]).strip()
        node_type = node["node_type"]
        if node_type in RUNTIME_ONLY_TYPES:
            raise WorkflowDomainError("WF_RUNTIME_ONLY", f"{node_type} cannot be saved in a design graph")
        if node_type not in DESIGN_COMPONENT_TYPES and node_type not in LEGACY_NODE_TYPES:
            raise WorkflowDomainError("WF_NODE_TYPE_UNKNOWN", "node_type is not in the approved component catalogue")
        existing = self._session.scalar(
            select(WorkflowNodeRecord).where(
                WorkflowNodeRecord.definition_id == definition_id,
                WorkflowNodeRecord.version_id.is_(None),
                WorkflowNodeRecord.node_code == node_code,
            )
        )
        if node_type in LEGACY_NODE_TYPES:
            if existing is None or existing.node_type != node_type:
                raise WorkflowDomainError(
                    "WF_LEGACY_NODE_NEW_FORBIDDEN",
                    "legacy node types may only update an existing node of the same type",
                )
        ref = _component_ref(node_type, node)
        if node_type in DESIGN_COMPONENT_TYPES and ref is None:
            raise WorkflowDomainError(
                "WF_COMPONENT_REF_REQUIRED", "component_ref must be the immutable {type, version} pair"
            )
        if ref is not None:
            self._validate_component_ref(ref)
        incoming_kind = _kind_for_component(node_type)
        if incoming_kind is not None and incoming_kind != definition.workflow_type:
            raise WorkflowDomainError(
                "WF_WORKFLOW_TYPE_MISMATCH",
                f"{node_type} is {incoming_kind}, definition is {definition.workflow_type}",
            )
        existing_kinds = {
            kind
            for row in self._draft_nodes(definition_id)
            if row.node_code != node_code
            for kind in [_kind_for_component(row.node_type)]
            if kind is not None
        }
        if incoming_kind is not None and existing_kinds and existing_kinds != {incoming_kind}:
            raise WorkflowDomainError(
                "WF_WORKFLOW_TYPE_MISMATCH", f"{node_type} cannot be mixed with {sorted(existing_kinds)} components"
            )
        params = dict(node.get("params") or {})
        if node_type in {"endpoint_select", "field_map", "field_map_union", "condition_set"}:
            _validate_sync_form_params(node_type, params)
        forbidden = _forbidden_hidden_paths(params)
        if forbidden:
            raise WorkflowDomainError(
                "WF_HIDDEN_INPUT_WRITE", f"executor-owned inputs cannot be saved: {forbidden}"
            )
        if ref is not None:
            params["_componentRef"] = ref
        values: dict[str, Any] = {
            "node_type": node_type,
            "name": node.get("name") or node_code,
            "params_json": json.dumps(params, ensure_ascii=False, sort_keys=True),
            "position_x": node.get("position_x"),
            "position_y": node.get("position_y"),
        }
        if existing is None:
            record = WorkflowNodeRecord(definition_id=definition_id, version_id=None, node_code=node_code, **values)
            self._session.add(record)
        else:
            for key, value in values.items():
                setattr(existing, key, value)
            record = existing
        self._session.flush()
        return self._node_payload(record)

    def delete_draft_node(self, project_id: int, definition_id: int, node_code: str) -> None:
        self._definition(project_id, definition_id)
        record = self._session.scalar(
            select(WorkflowNodeRecord).where(
                WorkflowNodeRecord.definition_id == definition_id,
                WorkflowNodeRecord.version_id.is_(None),
                WorkflowNodeRecord.node_code == node_code,
            )
        )
        if record is None:
            raise WorkflowDomainError("WF_NODE_NOT_FOUND", f"draft node {node_code!r} not found", 404)
        # Cascade: edges touching the removed node lose their endpoints.
        for edge in self._draft_edges(definition_id):
            if edge.from_node == node_code or edge.to_node == node_code:
                self._session.delete(edge)
        self._session.delete(record)
        self._session.flush()

    def upsert_draft_edge(self, project_id: int, definition_id: int, edge: dict[str, Any]) -> dict[str, Any]:
        self._definition(project_id, definition_id)
        from_node = edge["from_node"]
        to_node = edge["to_node"]
        node_codes = {n.node_code for n in self._draft_nodes(definition_id)}
        if from_node not in node_codes or to_node not in node_codes:
            raise WorkflowDomainError(
                "WF_EDGE_INVALID",
                f"edge {from_node!r}->{to_node!r} must reference existing draft nodes",
            )
        existing = self._session.scalar(
            select(WorkflowEdgeRecord).where(
                WorkflowEdgeRecord.definition_id == definition_id,
                WorkflowEdgeRecord.version_id.is_(None),
                WorkflowEdgeRecord.from_node == from_node,
                WorkflowEdgeRecord.to_node == to_node,
            )
        )
        name = edge.get("name") or ""
        if existing is None:
            record = WorkflowEdgeRecord(
                definition_id=definition_id,
                version_id=None,
                from_node=from_node,
                to_node=to_node,
                name=name,
            )
            self._session.add(record)
        else:
            existing.name = name
            record = existing
        self._session.flush()
        return self._edge_payload(record)

    def delete_draft_edge(self, project_id: int, definition_id: int, from_node: str, to_node: str) -> None:
        self._definition(project_id, definition_id)
        record = self._session.scalar(
            select(WorkflowEdgeRecord).where(
                WorkflowEdgeRecord.definition_id == definition_id,
                WorkflowEdgeRecord.version_id.is_(None),
                WorkflowEdgeRecord.from_node == from_node,
                WorkflowEdgeRecord.to_node == to_node,
            )
        )
        if record is None:
            raise WorkflowDomainError("WF_EDGE_NOT_FOUND", f"draft edge {from_node!r}->{to_node!r} not found", 404)
        self._session.delete(record)
        self._session.flush()

    # -- publish (draft → immutable version snapshot) ------------------------

    def publish(
        self, project_id: int, definition_id: int, remark: str = "", published_by: int | None = None
    ) -> dict[str, Any]:
        definition = self._definition(project_id, definition_id)
        draft_nodes = self._draft_nodes(definition_id)
        if not draft_nodes:
            raise WorkflowDomainError("WF_DRAFT_EMPTY", "cannot publish a definition with an empty draft")
        draft_edges = self._draft_edges(definition_id)
        node_codes = {n.node_code for n in draft_nodes}
        for edge in draft_edges:
            if edge.from_node not in node_codes or edge.to_node not in node_codes:
                raise WorkflowDomainError(
                    "WF_EDGE_INVALID",
                    f"draft edge {edge.from_node!r}->{edge.to_node!r} references a missing node",
                )
        node_payloads = [self._node_payload(n) for n in draft_nodes]
        for node in node_payloads:
            if node["node_type"] in LEGACY_NODE_TYPES:
                raise WorkflowDomainError(
                    "WF_LEGACY_NODE_PUBLISH_FORBIDDEN", "migrate legacy nodes before publishing"
                )
            if node["node_type"] in RUNTIME_ONLY_TYPES:
                raise WorkflowDomainError("WF_RUNTIME_ONLY", "runtime-only nodes cannot be published")
            if node["node_type"] in DESIGN_COMPONENT_TYPES and node.get("component_ref") is None:
                raise WorkflowDomainError("WF_COMPONENT_REF_REQUIRED", "all design nodes require component_ref")
            if node.get("component_ref") is not None:
                self._validate_component_ref(node["component_ref"])
        edge_payloads = [self._edge_payload(e) for e in draft_edges]
        digest = snapshot_digest(node_payloads, edge_payloads)
        latest = self._session.scalar(
            select(func.max(WorkflowVersionRecord.version)).where(WorkflowVersionRecord.definition_id == definition_id)
        )
        version_number = int(latest or 0) + 1
        published_at = datetime.now(timezone.utc)
        version_row = WorkflowVersionRecord(
            definition_id=definition_id,
            version=version_number,
            status="PUBLISHED",
            remark=remark,
            snapshot_digest=digest,
            published_at=published_at,
            published_by=published_by,
        )
        self._session.add(version_row)
        self._session.flush()  # version_row.id
        for node in draft_nodes:
            self._session.add(
                WorkflowNodeRecord(
                    definition_id=definition_id,
                    version_id=version_row.id,
                    node_code=node.node_code,
                    node_type=node.node_type,
                    name=node.name,
                    params_json=node.params_json,
                    position_x=node.position_x,
                    position_y=node.position_y,
                )
            )
        for edge in draft_edges:
            self._session.add(
                WorkflowEdgeRecord(
                    definition_id=definition_id,
                    version_id=version_row.id,
                    from_node=edge.from_node,
                    to_node=edge.to_node,
                    name=edge.name,
                )
            )
        self._session.add(
            WorkflowPublishRecord(
                definition_id=definition_id,
                version_id=version_row.id,
                version=version_number,
                published_by=published_by,
                remark=remark,
                published_at=published_at,
            )
        )
        definition.current_version = version_number
        self._session.flush()
        return self._version_payload(version_row, node_count=len(node_payloads), edge_count=len(edge_payloads))

    # -- version queries -----------------------------------------------------

    def list_versions(self, project_id: int, definition_id: int) -> list[dict[str, Any]]:
        self._definition(project_id, definition_id)
        rows = self._session.scalars(
            select(WorkflowVersionRecord)
            .where(WorkflowVersionRecord.definition_id == definition_id)
            .order_by(WorkflowVersionRecord.version)
        ).all()
        return [self._version_payload(row) for row in rows]

    def get_version(self, project_id: int, definition_id: int, version: int) -> dict[str, Any]:
        self._definition(project_id, definition_id)
        row = self._session.scalar(
            select(WorkflowVersionRecord).where(
                WorkflowVersionRecord.definition_id == definition_id,
                WorkflowVersionRecord.version == version,
            )
        )
        if row is None:
            raise WorkflowDomainError("WF_VERSION_NOT_FOUND", f"workflow {definition_id} has no version {version}", 404)
        copy_nodes = [
            self._node_payload(n)
            for n in self._session.scalars(
                select(WorkflowNodeRecord)
                .where(WorkflowNodeRecord.definition_id == definition_id, WorkflowNodeRecord.version_id == row.id)
                .order_by(WorkflowNodeRecord.id)
            ).all()
        ]
        copy_edges = [
            self._edge_payload(e)
            for e in self._session.scalars(
                select(WorkflowEdgeRecord)
                .where(WorkflowEdgeRecord.definition_id == definition_id, WorkflowEdgeRecord.version_id == row.id)
                .order_by(WorkflowEdgeRecord.id)
            ).all()
        ]
        # Tamper evidence: the stored digest must still match the copied rows.
        if snapshot_digest(copy_nodes, copy_edges) != row.snapshot_digest:
            raise WorkflowDomainError(
                "WF_VERSION_IMMUTABLE", f"version {version} snapshot digest no longer matches its rows", 409
            )
        publish_record_row = self._session.scalar(
            select(WorkflowPublishRecord)
            .where(
                WorkflowPublishRecord.definition_id == definition_id,
                WorkflowPublishRecord.version == version,
            )
            .order_by(WorkflowPublishRecord.id)
        )
        payload = self._version_payload(row)
        payload["nodes"] = copy_nodes
        payload["edges"] = copy_edges
        payload["publish_record"] = (
            {
                "version_id": publish_record_row.version_id,
                "version": publish_record_row.version,
                "remark": publish_record_row.remark,
                "published_by": publish_record_row.published_by,
                "published_at": self._iso_z(publish_record_row.published_at),
            }
            if publish_record_row is not None
            else None
        )
        return payload

    def update_version_content(
        self, project_id: int, definition_id: int, version: int, remark: str | None = None
    ) -> dict[str, Any]:
        """Mutate a version row — DRAFT slots only; published rows are frozen (§3.1)."""
        self._definition(project_id, definition_id)
        row = self._session.scalar(
            select(WorkflowVersionRecord).where(
                WorkflowVersionRecord.definition_id == definition_id,
                WorkflowVersionRecord.version == version,
            )
        )
        if row is None:
            raise WorkflowDomainError("WF_VERSION_NOT_FOUND", f"workflow {definition_id} has no version {version}", 404)
        if row.status != "DRAFT":
            raise WorkflowDomainError(
                "WF_VERSION_IMMUTABLE",
                f"version {version} is {row.status}; published version rows are immutable",
                409,
            )
        if remark is not None:
            row.remark = remark
        self._session.flush()
        return self._version_payload(row)

    # -- payloads ------------------------------------------------------------

    @staticmethod
    def _iso_z(value: datetime) -> str:
        return value.isoformat().replace("+00:00", "Z")

    @staticmethod
    def _node_payload(row: WorkflowNodeRecord) -> dict[str, Any]:
        params = json.loads(row.params_json) if row.params_json else {}
        component_ref = params.pop("_componentRef", None)
        return {
            "node_code": row.node_code,
            "node_type": row.node_type,
            "name": row.name,
            "params": params,
            "component_ref": component_ref,
            "position_x": row.position_x,
            "position_y": row.position_y,
        }

    @staticmethod
    def _edge_payload(row: WorkflowEdgeRecord) -> dict[str, Any]:
        return {"from_node": row.from_node, "to_node": row.to_node, "name": row.name}

    @classmethod
    def _version_payload(
        cls, row: WorkflowVersionRecord, node_count: int | None = None, edge_count: int | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": row.id,  # workflow_version_id — FORMAL instances bind this (§4.2)
            "definition_id": row.definition_id,
            "version": row.version,
            "status": row.status,
            "remark": row.remark,
            "snapshot_digest": row.snapshot_digest,
            "published_at": cls._iso_z(row.published_at),
            "published_by": row.published_by,
        }
        if node_count is not None:
            payload["node_count"] = node_count
        if edge_count is not None:
            payload["edge_count"] = edge_count
        return payload

    def _definition_payload(self, record: WorkflowDefinitionRecord, include_draft: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "definition_id": record.id,
            "project_id": record.project_id,
            "name": record.name,
            "description": record.description,
            "workflow_type": "NORMAL" if record.workflow_type == "ETL" else record.workflow_type,
            "current_version": record.current_version,
            "tags": self.tags(record),
        }
        if include_draft:
            payload["draft"] = {
                "nodes": [self._node_payload(n) for n in self._draft_nodes(record.id)],
                "edges": [self._edge_payload(e) for e in self._draft_edges(record.id)],
            }
        return payload

    @staticmethod
    def tags(record: WorkflowDefinitionRecord) -> list[str]:
        try:
            value = json.loads(record.tags_json or "[]")
            return [str(item) for item in value if isinstance(item, str) and item.strip()]
        except (TypeError, ValueError):
            return []

    def list_categories(self) -> list[dict[str, Any]]:
        builtins = ("同步", "ETL", "流")
        rows = [{"id": f"builtin:{name}", "name": name, "builtin": True} for name in builtins]
        rows.extend({"id": f"custom:{row.id}", "name": row.name, "builtin": False}
                    for row in self._session.scalars(select(WorkflowCategoryRecord).order_by(WorkflowCategoryRecord.id)).all())
        return rows

    def create_category(self, name: str) -> dict[str, Any]:
        name = name.strip()
        if not name or name in {"同步", "ETL", "流"}:
            raise WorkflowDomainError("WF_CATEGORY_INVALID", "category name is invalid")
        if self._session.scalar(select(WorkflowCategoryRecord).where(WorkflowCategoryRecord.name == name)):
            raise WorkflowDomainError("WF_CATEGORY_EXISTS", "category already exists", 409)
        row = WorkflowCategoryRecord(name=name)
        self._session.add(row); self._session.flush()
        return {"id": f"custom:{row.id}", "name": row.name, "builtin": False}

    def delete_category(self, category_id: int) -> None:
        row = self._session.get(WorkflowCategoryRecord, category_id)
        if row is None:
            raise WorkflowDomainError("WF_CATEGORY_NOT_FOUND", "category not found", 404)
        for record in self._session.scalars(select(WorkflowDefinitionRecord)).all():
            tags = [tag for tag in self.tags(record) if tag != row.name]
            record.tags_json = json.dumps(tags, ensure_ascii=False)
        self._session.delete(row)

    def set_tags(self, definition_id: int, tags: list[str]) -> list[str]:
        record = self._session.get(WorkflowDefinitionRecord, definition_id)
        if record is None:
            raise WorkflowDomainError("WF_DEFINITION_NOT_FOUND", "workflow definition not found", 404)
        clean = list(dict.fromkeys(tag.strip() for tag in tags if isinstance(tag, str) and tag.strip()))
        record.tags_json = json.dumps(clean, ensure_ascii=False)
        return clean

    def _validate_component_ref(self, ref: dict[str, Any]) -> None:
        version_row = self._session.scalar(
            select(ComponentVersion)
            .join(Component, Component.id == ComponentVersion.component_id)
            .where(
                Component.type == ref["type"],
                ComponentVersion.type == ref["type"],
                ComponentVersion.version == ref["version"],
                Component.state.in_(("published", "offline")),
                or_(
                    and_(
                        ComponentVersion.state == "published",
                        Component.published_version == ComponentVersion.version,
                    ),
                    ComponentVersion.state == "offline",
                ),
            )
        )
        if version_row is None:
            raise WorkflowDomainError(
                "WF_COMPONENT_REF_UNKNOWN",
                "component_ref must identify the matching published/offline immutable component version",
            )

    def _definition(self, project_id: int, definition_id: int) -> WorkflowDefinitionRecord:
        record = self._session.get(WorkflowDefinitionRecord, definition_id)
        if record is None or record.project_id != project_id:
            raise WorkflowDomainError(
                "WF_DEFINITION_NOT_FOUND",
                f"workflow definition {definition_id} not found in project",
                404,
            )
        return record

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
