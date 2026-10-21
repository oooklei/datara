"""Database access for SSH nodes."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.sshnode.models import SshNodeRecord


class SshNodeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> list[SshNodeRecord]:
        return list(self.session.scalars(select(SshNodeRecord).order_by(SshNodeRecord.id)).all())

    def get(self, node_id: int) -> SshNodeRecord | None:
        return self.session.get(SshNodeRecord, node_id)

    def find_by_name(self, name: str) -> SshNodeRecord | None:
        return self.session.scalar(select(SshNodeRecord).where(SshNodeRecord.name == name))

    def add(self, record: SshNodeRecord) -> SshNodeRecord:
        self.session.add(record)
        self.session.flush()
        return record

    def delete(self, record: SshNodeRecord) -> None:
        # Frozen B7-4 behavior: do not inspect workflow execNodeTag references.
        self.session.delete(record)
