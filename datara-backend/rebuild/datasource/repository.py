"""项目数据源持久化读写，所有单记录访问均带 project_id 条件。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.datasource.contracts import DataSourceDraft
from rebuild.datasource.models import ProjectDatasourceRecord


class ProjectDatasourceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_project(self, project_id: int) -> list[ProjectDatasourceRecord]:
        return list(
            self._session.scalars(
                select(ProjectDatasourceRecord)
                .where(ProjectDatasourceRecord.project_id == project_id)
                .order_by(ProjectDatasourceRecord.id)
            )
        )

    def get(self, project_id: int, datasource_id: int) -> ProjectDatasourceRecord | None:
        return self._session.scalar(
            select(ProjectDatasourceRecord).where(
                ProjectDatasourceRecord.project_id == project_id,
                ProjectDatasourceRecord.id == datasource_id,
            )
        )

    def create(self, project_id: int, draft: DataSourceDraft) -> ProjectDatasourceRecord:
        record = ProjectDatasourceRecord(
            project_id=project_id,
            name=draft.name.strip(),
            kind=draft.kind.lower(),
            host=draft.host.strip(),
            port=draft.port,
            database_name=draft.database.strip(),
            username=draft.username.strip(),
            password=draft.password,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def update(self, record: ProjectDatasourceRecord, draft: DataSourceDraft) -> None:
        record.name = draft.name.strip()
        record.kind = draft.kind.lower()
        record.host = draft.host.strip()
        record.port = draft.port
        record.database_name = draft.database.strip()
        record.username = draft.username.strip()
        if draft.password:
            record.password = draft.password

    def delete(self, record: ProjectDatasourceRecord) -> None:
        self._session.delete(record)
