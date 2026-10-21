"""Application service for the five frozen B7 operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from rebuild.sshnode.models import SshNodeRecord
from rebuild.sshnode.repository import SshNodeRepository


@dataclass(frozen=True)
class SshNodeInput:
    name: str
    host: str
    port: int
    ssh_user: str
    cred: str
    tags: list[str]
    enabled: bool


class SshNodeDomainError(RuntimeError):
    def __init__(self, code: int, message: str, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class SshNodeService:
    def __init__(self, session: Session, probe_func: Callable[[str, int, str, str], tuple[bool, str]]) -> None:
        self.session = session
        self.repository = SshNodeRepository(session)
        self.probe_func = probe_func

    def list(self) -> list[SshNodeRecord]:
        return self.repository.list()

    def create(self, value: SshNodeInput) -> SshNodeRecord:
        value = self._normalize(value)
        self._ensure_unique(value.name)
        record = SshNodeRecord(
            name=value.name,
            host=value.host,
            port=value.port,
            ssh_user=value.ssh_user,
            cred=value.cred,
            tags=value.tags,
            enabled=value.enabled,
        )
        try:
            self.repository.add(record)
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise SshNodeDomainError(4102, "SSH node name already exists", 409) from None
        return record

    def update(self, node_id: int, value: SshNodeInput) -> SshNodeRecord:
        record = self._required(node_id)
        value = self._normalize(value)
        self._ensure_unique(value.name, except_id=node_id)
        record.name = value.name
        record.host = value.host
        record.port = value.port
        record.ssh_user = value.ssh_user
        record.cred = value.cred
        record.tags = value.tags
        record.enabled = value.enabled
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise SshNodeDomainError(4102, "SSH node name already exists", 409) from None
        return record

    def delete(self, node_id: int) -> bool:
        record = self._required(node_id)
        self.repository.delete(record)
        self.session.commit()
        return True

    def probe(self, node_id: int) -> dict[str, object]:
        record = self._required(node_id)
        # Deliberately no mutation/commit: heartbeat state has one writer only.
        ok, message = self.probe_func(record.host, record.port, record.ssh_user, record.cred)
        return {"ok": bool(ok), "message": str(message)}

    def _required(self, node_id: int) -> SshNodeRecord:
        record = self.repository.get(node_id)
        if record is None:
            raise SshNodeDomainError(4101, "SSH node not found", 404)
        return record

    def _ensure_unique(self, name: str, except_id: int | None = None) -> None:
        duplicate = self.repository.find_by_name(name)
        if duplicate is not None and duplicate.id != except_id:
            raise SshNodeDomainError(4102, "SSH node name already exists", 409)

    @staticmethod
    def _normalize(value: SshNodeInput) -> SshNodeInput:
        name = value.name.strip()
        host = value.host.strip()
        if not name or not host:
            # R2: 4101-4103 are frozen domain-local literals, never resp.py imports.
            raise SshNodeDomainError(4103, "SSH node name and host are required", 400)
        return SshNodeInput(
            name=name,
            host=host,
            port=value.port,
            ssh_user=value.ssh_user.strip() or "root",
            cred=value.cred or "",
            tags=[item for item in dict.fromkeys(str(tag).strip() for tag in value.tags) if item],
            enabled=value.enabled,
        )
