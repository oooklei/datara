"""Persistence operations shared by the rebuild governance API and services."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.governance.models import AuditEventRecord
from rebuild.identity.models import ProjectMemberRecord
from rebuild.project.models import ProjectRecord


class GovernanceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def project_and_member_role(self, project_id: int, actor_id: int) -> tuple[ProjectRecord | None, str | None]:
        project = self.session.get(ProjectRecord, project_id)
        if project is None:
            return None, None
        membership = self.session.scalar(
            select(ProjectMemberRecord).where(
                ProjectMemberRecord.project_id == project_id,
                ProjectMemberRecord.user_id == actor_id,
            )
        )
        return project, membership.role if membership else None

    def add_audit_event(
        self,
        *,
        actor_id: int,
        project_id: int,
        action: str,
        resource_type: str,
        resource_id: str,
        after_json: str,
    ) -> AuditEventRecord:
        event = AuditEventRecord(
            actor_id=actor_id,
            project_id=project_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            after_json=after_json,
        )
        self.session.add(event)
        return event
