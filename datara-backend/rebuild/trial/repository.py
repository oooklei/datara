"""TrialSnapshotRepository — draft snapshot lifecycle (WF-11).

Design source: docs/increments/2026-10-14-datara-platform-rebuild-design.md §4.1.

- create_from_draft(definition_id): reads the current draft node/edge rows
  (version_id NULL), computes snapshot_digest via the same canonical sha256 as
  the publish path, writes a snapshot row (status=ACTIVE). Idempotent: if a row
  with the same (definition_id, digest) already exists, returns it unchanged.
- get(snapshot_id): returns the snapshot with parsed node/edge JSON.
- mark_stale(definition_id): demotes all ACTIVE snapshots for a definition to
  STALE when a newer digest arrives (called inside create_from_draft).

Reuses snapshot_digest() from the workflow repository to guarantee digest
compatibility with the publish path (same canonical JSON algorithm).
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.trial.models import WorkflowDraftSnapshotRecord
from rebuild.workflow.models import WorkflowEdgeRecord, WorkflowNodeRecord
from rebuild.workflow.repository import snapshot_digest


class TrialSnapshotDomainError(ValueError):
    """Domain rejection carrying a stable machine code and HTTP status."""

    def __init__(self, code: str, msg: str, status: int = 400) -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.status = status

    def payload(self) -> dict[str, Any]:
        return {"code": self.code, "msg": self.msg, "data": None}


class TrialSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_from_draft(
        self, definition_id: int, created_by: int | None = None
    ) -> dict[str, Any]:
        """Capture the current editing draft as an immutable snapshot row.

        Idempotent: same (definition_id, digest) returns the existing row
        without creating a duplicate.
        """
        draft_nodes = self._draft_nodes(definition_id)
        draft_edges = self._draft_edges(definition_id)
        node_payloads = [self._node_payload(n) for n in draft_nodes]
        edge_payloads = [self._edge_payload(e) for e in draft_edges]
        digest = snapshot_digest(node_payloads, edge_payloads)

        existing = self._session.scalar(
            select(WorkflowDraftSnapshotRecord).where(
                WorkflowDraftSnapshotRecord.definition_id == definition_id,
                WorkflowDraftSnapshotRecord.snapshot_digest == digest,
            )
        )
        if existing is not None:
            # Idempotent: return the existing snapshot, do not create a new row.
            return self._snapshot_payload(existing)

        # Demote older ACTIVE snapshots for this definition to STALE.
        for old in self._session.scalars(
            select(WorkflowDraftSnapshotRecord).where(
                WorkflowDraftSnapshotRecord.definition_id == definition_id,
                WorkflowDraftSnapshotRecord.status == "ACTIVE",
            )
        ).all():
            old.status = "STALE"

        record = WorkflowDraftSnapshotRecord(
            definition_id=definition_id,
            snapshot_digest=digest,
            node_snapshot_json=json.dumps(node_payloads, ensure_ascii=False, sort_keys=True),
            edge_snapshot_json=json.dumps(edge_payloads, ensure_ascii=False, sort_keys=True),
            status="ACTIVE",
            created_by=created_by,
        )
        self._session.add(record)
        self._session.flush()
        return self._snapshot_payload(record)

    def get(self, snapshot_id: int) -> dict[str, Any]:
        record = self._session.get(WorkflowDraftSnapshotRecord, snapshot_id)
        if record is None:
            raise TrialSnapshotDomainError(
                "WF_SNAPSHOT_NOT_FOUND", f"draft snapshot {snapshot_id} not found", 404
            )
        return self._snapshot_payload(record)

    # -- payloads ------------------------------------------------------------

    @staticmethod
    def _node_payload(row: WorkflowNodeRecord) -> dict[str, Any]:
        return {
            "node_code": row.node_code,
            "node_type": row.node_type,
            "name": row.name,
            "params": json.loads(row.params_json) if row.params_json else {},
            "position_x": row.position_x,
            "position_y": row.position_y,
        }

    @staticmethod
    def _edge_payload(row: WorkflowEdgeRecord) -> dict[str, Any]:
        return {"from_node": row.from_node, "to_node": row.to_node, "name": row.name}

    @classmethod
    def _snapshot_payload(cls, row: WorkflowDraftSnapshotRecord) -> dict[str, Any]:
        return {
            "snapshot_id": row.id,
            "definition_id": row.definition_id,
            "snapshot_digest": row.snapshot_digest,
            "node_snapshot_json": json.loads(row.node_snapshot_json),
            "edge_snapshot_json": json.loads(row.edge_snapshot_json),
            "status": row.status,
            "created_by": row.created_by,
            "created_at": row.created_at.isoformat().replace("+00:00", "Z") if row.created_at else None,
        }

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
