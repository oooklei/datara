"""I1 项目仓储。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.project.models import ProjectRecord


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, *, name: str, description: str, owner_id: int) -> ProjectRecord:
        if not name.strip():
            raise ValueError("project name is required")
        record = ProjectRecord(name=name.strip(), description=description, owner_id=owner_id)
        self._session.add(record)
        self._session.flush()
        return record

    def list_for_user(self, user_id: int) -> list[ProjectRecord]:
        return list(self._session.scalars(select(ProjectRecord).where(ProjectRecord.owner_id == user_id)))

