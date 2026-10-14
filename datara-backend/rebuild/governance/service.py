"""Authorization and audit application services for governance mutations."""

from __future__ import annotations

from sqlalchemy.orm import Session

from rebuild.governance.contracts import authorize_project_access
from rebuild.governance.repository import GovernanceRepository
from rebuild.identity.contracts import Permission
from rebuild.project.models import ProjectRecord


class GovernanceService:
    def __init__(self, session: Session) -> None:
        self.repository = GovernanceRepository(session)

    def project_access(
        self, project_id: int, user: dict[str, object], permission: Permission
    ) -> tuple[ProjectRecord | None, bool]:
        actor_id = int(user["user_id"])
        project, member_role = self.repository.project_and_member_role(project_id, actor_id)
        if project is None:
            return None, False
        allowed = authorize_project_access(
            actor_id=actor_id,
            owner_id=project.owner_id,
            global_role=str(user["role"]),
            member_role=member_role,
            permission=permission,
        )
        return project, allowed

    def record_mutation(
        self,
        *,
        actor_id: int,
        project_id: int,
        action: str,
        resource_type: str,
        resource_id: str,
        after_json: str,
    ) -> None:
        self.repository.add_audit_event(
            actor_id=actor_id,
            project_id=project_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            after_json=after_json,
        )
