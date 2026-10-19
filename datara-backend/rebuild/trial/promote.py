"""Promote TRIAL run results to a formal workflow version (WF-21).

Design source: docs/increments/2026-10-14-datara-platform-rebuild-design.md §4.1/§3.1.

Flow:
  1. Load the TRIAL run's snapshot digest.
  2. Call WorkflowRepository.publish() to create a PUBLISHED workflow_version
     from the current draft (which must match the snapshot digest).
  3. Mark the workflow_instance as PROMOTED.

Idempotent: promoting the same run twice does not create duplicate versions
(the second publish bumps version number but the WBS requires idempotency —
we check if a version with the same digest already exists and return it).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.execution.models import WorkflowInstanceRecord
from rebuild.trial.repository import TrialSnapshotRepository
from rebuild.workflow.models import WorkflowVersionRecord
from rebuild.workflow.repository import WorkflowRepository


class PromoteError(ValueError):
    """Promotion rejection."""

    def __init__(self, code: str, msg: str, status: int = 400) -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.status = status


class TrialPromoter:
    """Promotes a TRIAL run to a formal workflow version."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._workflow = WorkflowRepository(session)

    def promote(
        self,
        *,
        definition_id: int,
        instance_id: int,
        project_id: int,
        remark: str = "",
        promoted_by: int | None = None,
    ) -> dict[str, Any]:
        """Promote a TRIAL instance's snapshot to a formal version.

        Returns the version payload. Idempotent: if a PUBLISHED version with the
        same snapshot digest already exists, returns it without creating a new one.
        """
        # 1. Verify the instance is a TRIAL.
        instance = self._session.get(WorkflowInstanceRecord, instance_id)
        if instance is None:
            raise PromoteError("WF_INSTANCE_NOT_FOUND", f"workflow instance {instance_id} not found", 404)
        if instance.instance_type != "TRIAL":
            raise PromoteError(
                "WF_PROMOTE_NOT_TRIAL",
                f"instance {instance_id} is {instance.instance_type}, only TRIAL runs can be promoted",
            )

        # 2. Get the snapshot digest bound to this instance.
        #    The instance's workflow_version_id is the snapshot_id for TRIAL.
        snapshot = TrialSnapshotRepository(self._session).get(instance.workflow_version_id)
        snapshot_digest = snapshot["snapshot_digest"]

        # 3. Check if a PUBLISHED version with this digest already exists (idempotent).
        existing = self._session.scalar(
            select(WorkflowVersionRecord).where(
                WorkflowVersionRecord.definition_id == definition_id,
                WorkflowVersionRecord.snapshot_digest == snapshot_digest,
                WorkflowVersionRecord.status == "PUBLISHED",
            )
        )
        if existing is not None:
            return {
                "version": existing.version,
                "status": existing.status,
                "snapshot_digest": existing.snapshot_digest,
                "idempotent": True,
            }

        # 4. Publish the current draft (must match the snapshot digest).
        version_payload = self._workflow.publish(
            project_id=project_id,
            definition_id=definition_id,
            remark=remark or f"promoted from trial run {instance_id}",
            published_by=promoted_by,
        )

        # 5. Verify the published version digest matches the snapshot.
        if version_payload["snapshot_digest"] != snapshot_digest:
            raise PromoteError(
                "WF_PROMOTE_DIGEST_MISMATCH",
                "current draft does not match the trial snapshot; re-snapshot before promoting",
                409,
            )

        # 6. Mark instance as promoted (via a log event; no PROMOTED state in the
        #    batch machine, so we append an execution event).
        from rebuild.execution.repository import ExecutionRepository

        ExecutionRepository(self._session).append_execution_event(
            workflow_instance_id=instance_id,
            event_kind="PROMOTED",
            payload_json=f'{{"version": {version_payload["version"]}}}',
        )
        self._session.flush()

        return {
            "version": version_payload["version"],
            "status": "PUBLISHED",
            "snapshot_digest": version_payload["snapshot_digest"],
            "idempotent": False,
        }
