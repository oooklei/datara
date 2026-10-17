"""Validation, storage, version chain and binding idempotency for R4-RESOURCE.

Contract source (frozen, A2 v2.1): R4-DEP-RES-API-contract-pending.md §2/§4
+ B2 §3 + FE resourceApi.ts (kind/extension/size constants).

- Uploads are multipart; the server re-validates kind/extension/size (20MB =
  20971520 bytes, aligned with the FE RESOURCE_MAX_SIZE_BYTES constant) and
  computes the sha256 lowercase hex digest itself — client claims are never
  trusted.
- Versions are monotonic and immutable (v1, v2, ...); content is stored on
  disk under REBUILD_RESOURCE_STORAGE_DIR (default ./resource_storage,
  gitignored) as {resource_id}/v{n} — the original filename is metadata only,
  never part of the storage path (no filename-injection surface).
- Binding idempotency: same slot + same payload → existing binding_id; same
  slot + different payload → RES_BINDING_CONFLICT (409).
- Published-version binding rejection is deferred until the workflow-registry
  domain lands on main (narrow-scope disclosure).
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from rebuild.resources.models import ResourceBindingRecord, ResourceRecord, ResourceVersionRecord

VALID_KINDS = ("sql", "python", "shell")

# Frozen with the FE constant RESOURCE_ALLOWED_EXTENSIONS (resourceApi.ts).
ALLOWED_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "sql": (".sql",),
    "python": (".py",),
    "shell": (".sh",),
}

MAX_SIZE_BYTES = 20 * 1024 * 1024  # 20971520; frozen with FE RESOURCE_MAX_SIZE_BYTES.


class ResourceDomainError(ValueError):
    """Domain rejection carrying a stable machine code and HTTP status (§4)."""

    def __init__(self, code: str, msg: str, status: int = 400) -> None:
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.status = status

    def payload(self) -> dict[str, Any]:
        return {"code": self.code, "msg": self.msg, "data": None}


def validate_kind(kind: Any) -> str:
    if not isinstance(kind, str) or kind not in VALID_KINDS:
        raise ResourceDomainError("RES_KIND_UNKNOWN", f"kind must be one of {list(VALID_KINDS)}")
    return kind


def validate_filename(kind: str, filename: str) -> str:
    if not isinstance(filename, str) or not filename.strip():
        raise ResourceDomainError("RES_TYPE_NOT_ALLOWED", "filename is required")
    dot = filename.rfind(".")
    extension = filename[dot:].lower() if dot >= 0 else ""
    if extension not in ALLOWED_EXTENSIONS[kind]:
        raise ResourceDomainError(
            "RES_TYPE_NOT_ALLOWED",
            f"kind={kind} only allows {list(ALLOWED_EXTENSIONS[kind])} extensions",
        )
    return filename


def validate_size(size: int) -> int:
    if size > MAX_SIZE_BYTES:
        raise ResourceDomainError("RES_SIZE_EXCEEDED", f"size exceeds the {MAX_SIZE_BYTES} byte limit")
    return size


def storage_dir() -> str:
    return os.getenv("REBUILD_RESOURCE_STORAGE_DIR", "./resource_storage")


def version_filename(resource_id: int, version: int) -> str:
    """Storage path relative to the storage dir: {resource_id}/v{version}."""
    return os.path.join(str(resource_id), f"v{version}")


class ResourceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    # -- queries ------------------------------------------------------------

    def list_resources(self, project_id: int, kind: str | None = None) -> list[dict[str, Any]]:
        query = select(ResourceRecord).where(ResourceRecord.project_id == project_id)
        if kind is not None:
            validate_kind(kind)
            query = query.where(ResourceRecord.kind == kind)
        rows = self._session.scalars(query.order_by(ResourceRecord.id)).all()
        return [
            {
                "resource_id": row.id,
                "name": row.name,
                "kind": row.kind,
                "size_bytes": row.size_bytes,
                "latest_version": row.latest_version,
            }
            for row in rows
        ]

    def _resource(self, project_id: int, resource_id: int) -> ResourceRecord:
        row = self._session.get(ResourceRecord, resource_id)
        if row is None or row.project_id != project_id:
            raise ResourceDomainError("RES_OBJECT_NOT_FOUND", f"resource {resource_id} not found in project", 404)
        return row

    # -- upload (multipart) -------------------------------------------------

    def save_upload(self, project_id: int, kind: str, filename: str, content: bytes) -> dict[str, Any]:
        """Validate + persist one immutable version; returns the version payload."""
        validate_kind(kind)
        validate_filename(kind, filename)
        validate_size(len(content))
        digest = hashlib.sha256(content).hexdigest()
        existing = self._session.scalar(
            select(ResourceRecord).where(ResourceRecord.project_id == project_id, ResourceRecord.name == filename)
        )
        uploaded_at = datetime.now(timezone.utc)
        if existing is None:
            resource = ResourceRecord(project_id=project_id, name=filename, kind=kind, size_bytes=len(content), latest_version=1)
            self._session.add(resource)
            self._session.flush()
            version_number = 1
        else:
            if existing.kind != kind:
                raise ResourceDomainError(
                    "RES_TYPE_NOT_ALLOWED",
                    f"resource {existing.id} already has kind={existing.kind}; kind is immutable per resource",
                )
            resource = existing
            version_number = existing.latest_version + 1
            existing.latest_version = version_number
            existing.size_bytes = len(content)
        relative_path = version_filename(resource.id, version_number)
        absolute_path = os.path.join(storage_dir(), relative_path)
        os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
        with open(absolute_path, "wb") as handle:
            handle.write(content)
        self._session.add(
            ResourceVersionRecord(
                resource_id=resource.id,
                version=version_number,
                size_bytes=len(content),
                digest=digest,
                storage_path=relative_path,
                uploaded_at=uploaded_at,
            )
        )
        self._session.flush()
        return {
            "resource_id": resource.id,
            "version": version_number,
            "size_bytes": len(content),
            "digest": digest,
            "uploaded_at": uploaded_at.isoformat().replace("+00:00", "Z"),
        }

    # -- version chain ------------------------------------------------------

    def list_versions(self, project_id: int, resource_id: int) -> list[dict[str, Any]]:
        self._resource(project_id, resource_id)
        rows = self._session.scalars(
            select(ResourceVersionRecord)
            .where(ResourceVersionRecord.resource_id == resource_id)
            .order_by(ResourceVersionRecord.version)
        ).all()
        return [self._version_payload(row) for row in rows]

    def get_version(self, project_id: int, resource_id: int, version: int) -> dict[str, Any]:
        self._resource(project_id, resource_id)
        row = self._session.scalar(
            select(ResourceVersionRecord).where(
                ResourceVersionRecord.resource_id == resource_id, ResourceVersionRecord.version == version
            )
        )
        if row is None:
            raise ResourceDomainError("RES_VERSION_NOT_FOUND", f"resource {resource_id} has no version {version}", 404)
        return self._version_payload(row)

    @staticmethod
    def _version_payload(row: ResourceVersionRecord) -> dict[str, Any]:
        return {
            "resource_id": row.resource_id,
            "version": row.version,
            "size_bytes": row.size_bytes,
            "digest": row.digest,
            "uploaded_at": row.uploaded_at.isoformat().replace("+00:00", "Z"),
        }

    # -- binding ------------------------------------------------------------

    def bind(
        self,
        project_id: int,
        workflow_id: int,
        workflow_version: int,
        task_id: str,
        resource_id: int,
        resource_version: int,
    ) -> tuple[int, bool]:
        """Bind a concrete version into a slot; returns (binding_id, created).

        Same slot + same payload → (existing_id, False); same slot + different
        payload → RES_BINDING_CONFLICT (409).
        """
        self._resource(project_id, resource_id)  # RES_OBJECT_NOT_FOUND for foreign/unknown ids
        version_row = self._session.scalar(
            select(ResourceVersionRecord).where(
                ResourceVersionRecord.resource_id == resource_id,
                ResourceVersionRecord.version == resource_version,
            )
        )
        if version_row is None:
            raise ResourceDomainError(
                "RES_VERSION_NOT_FOUND", f"resource {resource_id} has no version {resource_version}", 404
            )
        slot = self._session.scalar(
            select(ResourceBindingRecord).where(
                ResourceBindingRecord.project_id == project_id,
                ResourceBindingRecord.workflow_id == workflow_id,
                ResourceBindingRecord.workflow_version == workflow_version,
                ResourceBindingRecord.task_id == task_id,
            )
        )
        if slot is not None:
            if slot.resource_id != resource_id or slot.resource_version != resource_version:
                raise ResourceDomainError(
                    "RES_BINDING_CONFLICT",
                    "slot already bound to a different resource version",
                    409,
                )
            return slot.id, False
        binding = ResourceBindingRecord(
            project_id=project_id,
            workflow_id=workflow_id,
            workflow_version=workflow_version,
            task_id=task_id,
            resource_id=resource_id,
            resource_version=resource_version,
        )
        self._session.add(binding)
        self._session.flush()
        return binding.id, True
