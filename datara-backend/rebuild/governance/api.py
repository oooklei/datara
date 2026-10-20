"""Project-scoped governance API for the isolated rebuild backend."""

from __future__ import annotations

import json
import logging
from collections import deque
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from rebuild.governance.models import (
    AssetFieldRecord,
    AssetMetadataExtensionRecord,
    AssetRecord,
    AssetTagRecord,
    AuditEventRecord,
    GovernanceTagRecord,
    LegacyTagDefinitionRecord,
    LegacyTagReferenceRecord,
    LineageEdgeRecord,
    QualityRuleRecord,
    QualityRunRecord,
    SemanticMetricRecord,
    StandardDefinitionRecord,
)
from rebuild.governance.service import GovernanceService
from rebuild.governance.legacy_migration_service import (
    I18_APPROVED_IMPORT_PROJECT_ID,
    build_i18_legacy_dry_run,
    i18_import_matches_approved_scope,
)
from rebuild.governance.legacy_source_reader import LegacyI18SourceReader
from rebuild.governance.legacy_source_reader import LegacyI22SourceReader
from rebuild.governance.legacy_source_reader import LegacyI23SourceReader
from rebuild.governance.legacy_source_reader import LegacyI19SourceReader
from rebuild.governance.legacy_source_reader import LegacyI20SourceReader
from rebuild.governance.legacy_source_reader import LegacyI21SourceReader
from rebuild.governance.legacy_i19_mapping import (
    I19ScopedTarget,
    I19TagTarget,
    LegacyI19MappingContext,
    map_i19_snapshot,
)
from rebuild.governance.legacy_i19_importer import (
    build_i19_mapping_context,
    execute_i19_legacy_import,
    i19_target_identity_digest,
)
from rebuild.governance.legacy_i23_preview import MAX_I23_PREVIEW_ROWS, build_i23_identity_preview
from rebuild.governance.legacy_i22_preview import build_i22_mapping_preview
from rebuild.governance.legacy_i20_preview import build_i20_mapping_preview
from rebuild.governance.legacy_i21_preview import build_i21_mapping_preview
from rebuild.governance.legacy_importer import LegacyImportRejected, execute_i18_legacy_import
from rebuild.governance.legacy_i20_importer import execute_i20_legacy_import
from rebuild.governance.legacy_i21_importer import execute_i21_legacy_import
from rebuild.governance.legacy_i22_importer import execute_i22_legacy_import
from rebuild.governance.check_engines import run_all_checks
from rebuild.governance.migration_checkpoints import CheckpointConflict
from rebuild.governance.snapshot_repository import LegacyI18TargetSnapshotRepository
from rebuild.identity.contracts import Permission
from rebuild.identity.models import UserRecord
from rebuild.project.models import ProjectRecord

logger = logging.getLogger(__name__)


class AssetFieldInput(BaseModel):
    field_name: str = Field(min_length=1, max_length=256)
    ordinal_position: int = Field(gt=0)
    data_type: str = Field(default="", max_length=128)
    nullable: bool = True
    description: str = ""


class AssetInput(BaseModel):
    source_system: str = Field(min_length=1, max_length=64)
    database_name: str = Field(min_length=1, max_length=128)
    schema_name: str = Field(default="", max_length=128)
    asset_name: str = Field(min_length=1, max_length=256)
    asset_type: str = Field(min_length=1, max_length=32)
    display_name: str = Field(default="", max_length=256)
    description: str = ""
    owner_name: str = Field(default="", max_length=128)
    domain_name: str = Field(default="", max_length=128)
    row_count: int | None = Field(default=None, ge=0)
    fields: list[AssetFieldInput] = Field(default_factory=list)


class TagInput(BaseModel):
    namespace: str = Field(default="business", min_length=1, max_length=64)
    tag_key: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=128)
    description: str = ""
    asset_id: int | None = Field(default=None, gt=0)


class TagAssignment(BaseModel):
    tag_ids: list[int] = Field(max_length=200)


class LineageInput(BaseModel):
    external_id: str = Field(min_length=1, max_length=256)
    source_asset_id: int = Field(gt=0)
    target_asset_id: int = Field(gt=0)
    source_field_name: str = Field(default="", max_length=256)
    target_field_name: str = Field(default="", max_length=256)
    lineage_type: str = Field(min_length=1, max_length=32)
    process_ref: str = Field(default="", max_length=256)


class QualityRuleInput(BaseModel):
    asset_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=128)
    expression: str = Field(min_length=1)
    severity: str = Field(default="warning", pattern="^(info|warning|error)$")
    enabled: bool = True


class LegacyI18ImportInput(BaseModel):
    source_digest: str = Field(pattern="^[0-9a-f]{64}$")
    target_digest: str = Field(pattern="^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=128)
    confirmation: str = Field(min_length=1, max_length=256)


class LegacyI19I20ImportInput(BaseModel):
    source_digest: str = Field(pattern="^[0-9a-f]{64}$")
    target_digest: str = Field(pattern="^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=1, max_length=128)
    confirmation: str = Field(min_length=1, max_length=256)


class StandardInput(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    data_type: str = Field(min_length=1, max_length=128)
    expression: str = ""
    description: str = ""
    status: str = Field(default="draft", pattern="^(draft|active|retired)$")


class MetricInput(BaseModel):
    code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    formula: str = Field(min_length=1)
    description: str = ""
    status: str = Field(default="draft", pattern="^(draft|active|retired)$")


class I23IdentitySelectionInput(BaseModel):
    source_id: str = Field(min_length=1, max_length=24, pattern="^[1-9][0-9]*$")
    target_user_id: int = Field(gt=0, strict=True)


class I23IdentityPreviewInput(BaseModel):
    selections: list[I23IdentitySelectionInput] = Field(default_factory=list, max_length=MAX_I23_PREVIEW_ROWS)


def build_governance_router(
    session_factory: sessionmaker[Session],
    current_user: Callable[[str], dict[str, object]],
    *,
    legacy_source_reader_factory: Callable[[], LegacyI18SourceReader] | None = None,
    legacy_i22_source_reader_factory: Callable[[], LegacyI22SourceReader] | None = None,
    legacy_i23_source_reader_factory: Callable[[], LegacyI23SourceReader] | None = None,
    legacy_i19_source_reader_factory: Callable[[], LegacyI19SourceReader] | None = None,
    legacy_i20_source_reader_factory: Callable[[], LegacyI20SourceReader] | None = None,
    legacy_i21_source_reader_factory: Callable[[], LegacyI21SourceReader] | None = None,
    legacy_i23_preview_user: Callable[[str], dict[str, object]] | None = None,
    legacy_i18_import_enabled: bool = False,
    legacy_i19_import_enabled: bool = False,
    legacy_i20_import_enabled: bool = False,
    legacy_i21_import_enabled: bool = False,
    legacy_i22_import_enabled: bool = False,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/rebuild/governance", tags=["rebuild-governance"])

    def fail(status: int, code: int, message: str) -> JSONResponse:
        return JSONResponse(status_code=status, content={"code": code, "msg": message, "data": None})

    def authenticate(authorization: str) -> dict[str, object] | JSONResponse:
        try:
            return current_user(authorization)
        except ValueError:
            return fail(401, 1001, "invalid token")

    def project_permission(
        session: Session, project_id: int, user: dict[str, object], permission: Permission
    ) -> ProjectRecord | JSONResponse:
        project, allowed = GovernanceService(session).project_access(project_id, user, permission)
        if project is None:
            return fail(404, 4041, "project not found")
        return project if allowed else fail(403, 1003, "project permission denied")

    @router.post("/projects/{project_id}/legacy/i19/mapping-preview")
    def legacy_i19_mapping_preview(project_id: int, authorization: str = Header(default="")):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        reader = None
        try:
            with session_factory() as session:
                target_url = session.get_bind().url
                target_backend = target_url.get_backend_name()
                if target_backend == "mysql" and target_url.database != "datara_rebuild_i0":
                    return fail(503, 5032, "target database is not the isolated rebuild schema")
                if target_backend not in {"mysql", "sqlite"}:
                    return fail(503, 5032, "unsupported target database for I19 mapping preview")
                if target_backend == "mysql":
                    session.connection().exec_driver_sql("SET TRANSACTION READ ONLY")
                permitted = project_permission(session, project_id, user, Permission.EDIT_DEFINITION)
                if isinstance(permitted, JSONResponse):
                    return permitted

                reader = (legacy_i19_source_reader_factory or LegacyI19SourceReader.from_runtime_env)()
                source_snapshot = reader.read_snapshot()
                target_ids: dict[tuple[str, str], int] = {}
                target_id_candidates: dict[tuple[str, str], list[int]] = {}
                target_identity_conflicts: set[tuple[str, str]] = set()
                asset_targets: dict[tuple[int, str, str], I19ScopedTarget] = {}
                asset_key_counts: dict[tuple[int, str, str], int] = {}
                extension_source_targets: dict[str, list[tuple[int, tuple[int, str, str], int]]] = {}
                extension_rows = session.execute(
                    select(AssetMetadataExtensionRecord, AssetRecord)
                    .join(AssetRecord, AssetRecord.id == AssetMetadataExtensionRecord.asset_id)
                    .where(
                        AssetRecord.project_id == project_id,
                        AssetMetadataExtensionRecord.source_system == "datara_meta",
                        AssetMetadataExtensionRecord.source_table == "t_meta_table_ext",
                    )
                ).all()
                for extension, asset in extension_rows:
                    if extension.source_id:
                        extension_source_targets.setdefault(extension.source_id, []).append(
                            (
                                asset.id,
                                (extension.legacy_datasource_id, extension.database_name, extension.table_name),
                                extension.id,
                            )
                        )
                    key = (extension.legacy_datasource_id, extension.database_name, extension.table_name)
                    asset_key_counts[key] = asset_key_counts.get(key, 0) + 1
                    asset_targets[key] = I19ScopedTarget(asset.id, project_id)
                asset_targets = {key: value for key, value in asset_targets.items() if asset_key_counts[key] == 1}
                for source_id, candidates in extension_source_targets.items():
                    identity = ("t_meta_table_ext", source_id)
                    if len(candidates) != 1:
                        target_identity_conflicts.add(identity)
                        continue
                    asset_id, key, extension_id = candidates[0]
                    exact_asset = asset_targets.get(key)
                    if exact_asset is None or exact_asset.target_id != asset_id:
                        target_identity_conflicts.add(identity)
                        continue
                    target_id_candidates.setdefault(identity, []).append(extension_id)

                tag_targets: dict[str, I19TagTarget] = {}
                tag_rows = session.execute(
                    select(LegacyTagDefinitionRecord, GovernanceTagRecord)
                    .join(
                        GovernanceTagRecord,
                        GovernanceTagRecord.id == LegacyTagDefinitionRecord.normalized_tag_id,
                    )
                    .where(
                        GovernanceTagRecord.project_id == project_id,
                        LegacyTagDefinitionRecord.source_system == "datara_meta",
                        LegacyTagDefinitionRecord.source_table == "t_meta_tag",
                    )
                ).all()
                for definition, tag in tag_rows:
                    if definition.source_id:
                        identity = ("t_meta_tag", definition.source_id)
                        target_id_candidates.setdefault(identity, []).append(definition.id)
                        if definition.source_id in tag_targets:
                            target_identity_conflicts.add(identity)
                            tag_targets.pop(definition.source_id, None)
                        elif identity not in target_identity_conflicts:
                            tag_targets[definition.source_id] = I19TagTarget(tag.id, project_id, definition.id)

                tagging_asset_targets: dict[tuple[str, str], I19ScopedTarget] = {}
                tagging_key_candidates: dict[tuple[str, str], list[I19ScopedTarget]] = {}
                reference_rows = session.execute(
                    select(LegacyTagReferenceRecord, AssetRecord)
                    .join(GovernanceTagRecord, GovernanceTagRecord.id == LegacyTagReferenceRecord.tag_id)
                    .outerjoin(AssetRecord, AssetRecord.id == LegacyTagReferenceRecord.resolved_asset_id)
                    .where(
                        LegacyTagReferenceRecord.project_id == project_id,
                        GovernanceTagRecord.project_id == project_id,
                        LegacyTagReferenceRecord.source_system == "datara_meta",
                        LegacyTagReferenceRecord.source_table == "t_meta_tagging",
                    )
                ).all()
                for reference, asset in reference_rows:
                    if reference.source_id:
                        identity = ("t_meta_tagging", reference.source_id)
                        target_id_candidates.setdefault(identity, []).append(reference.id)
                    if asset is not None and asset.project_id == project_id:
                        key = (reference.target_type, reference.target_key)
                        tagging_key_candidates.setdefault(key, []).append(I19ScopedTarget(asset.id, project_id))
                for key, candidates in tagging_key_candidates.items():
                    unique_ids = {candidate.target_id for candidate in candidates}
                    if len(unique_ids) == 1:
                        tagging_asset_targets[key] = candidates[0]
                for identity, candidates in target_id_candidates.items():
                    if len(candidates) == 1 and identity not in target_identity_conflicts:
                        target_ids[identity] = candidates[0]
                    else:
                        target_identity_conflicts.add(identity)

                context = LegacyI19MappingContext(
                    target_project_id=project_id,
                    target_ids=target_ids,
                    asset_targets=asset_targets,
                    tag_targets=tag_targets,
                    tagging_asset_targets=tagging_asset_targets,
                )
                target_identity_digest = i19_target_identity_digest(context)
                mapped = map_i19_snapshot(source_snapshot, context)
                mapped_rows = mapped.extensions + mapped.tag_references
                blocked_ids = {
                    (issue.source_table, issue.source_id) for issue in mapped.mapping_issues if issue.source_table
                }
                blocked_ids.update(target_identity_conflicts)
                blocked_ids.update(
                    (row.source_table, row.source_id)
                    for row in mapped_rows
                    if row.mapping_issues or not row.ready_to_import
                )
                blocked_ids.update(
                    (tag.definition.source_table, tag.definition.source_id)
                    for tag in mapped.tags
                    if tag.mapping_issues or tag.definition.mapping_issues or not tag.ready_to_import
                )
                dispositions = {"new_identity_candidate": 0, "target_identity_match": 0, "blocked": 0}
                entries = []
                for row in mapped_rows:
                    blocked = (row.source_table, row.source_id) in blocked_ids
                    disposition = (
                        "blocked"
                        if blocked
                        else "target_identity_match"
                        if row.target_id is not None
                        else "new_identity_candidate"
                    )
                    dispositions[disposition] += 1
                    entries.append(
                        {"source_table": row.source_table, "source_id": row.source_id, "disposition": disposition}
                    )
                for tag in mapped.tags:
                    row = tag.definition
                    blocked = (row.source_table, row.source_id) in blocked_ids
                    disposition = (
                        "blocked"
                        if blocked
                        else "target_identity_match"
                        if row.target_id is not None
                        else "new_identity_candidate"
                    )
                    dispositions[disposition] += 1
                    entries.append(
                        {"source_table": row.source_table, "source_id": row.source_id, "disposition": disposition}
                    )
                source_counts = dict(source_snapshot.counts)
                target_counts = {
                    "t_meta_table_ext": len(extension_rows),
                    "t_meta_tag": len(tag_rows),
                    "t_meta_tagging": len(reference_rows),
                }
                issues = [
                    {"code": issue.code, "source_table": issue.source_table, "source_id": issue.source_id}
                    for issue in mapped.mapping_issues
                ]
                issues.extend(
                    {"code": "ambiguous_target_identity", "source_table": table, "source_id": source_id}
                    for table, source_id in sorted(target_identity_conflicts)
                )
                data = {
                    "project_id": project_id,
                    "source": {
                        "schema": source_snapshot.schema,
                        "captured_at": source_snapshot.captured_at.isoformat(),
                        "digest": source_snapshot.digest,
                        "counts": source_counts,
                    },
                    "target": {
                        "project_id": project_id,
                        "captured_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
                        "identity_digest": target_identity_digest,
                        "counts": target_counts,
                    },
                    "preview": {
                        "counts": dispositions,
                        "entries": entries,
                        "issues": issues,
                        "parity_verified": False,
                        "import_enabled": False,
                    },
                }
                logger.info(
                    "legacy I19 mapping preview completed",
                    extra={"project_id": project_id, "source_counts": source_counts, "preview_counts": dispositions},
                )
                return {"code": 0, "msg": "success", "data": data}
        except ValueError:
            return fail(422, 4221, "legacy I19 snapshot or mapping is invalid")
        except Exception as exc:
            logger.error(
                "legacy I19 mapping preview failed",
                extra={"project_id": project_id, "error_type": type(exc).__name__},
            )
            return fail(503, 5031, "legacy I19 mapping preview is unavailable")
        finally:
            source_engine = getattr(reader, "engine", None)
            if source_engine is not None:
                source_engine.dispose()

    @router.post("/projects/{project_id}/legacy/i21/mapping-preview")
    def legacy_i21_mapping_preview(project_id: int, authorization: str = Header(default="")):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        reader = None
        try:
            with session_factory() as session:
                target_url = session.get_bind().url
                target_backend = target_url.get_backend_name()
                if target_backend == "mysql" and target_url.database != "datara_rebuild_i0":
                    return fail(503, 5032, "target database is not the isolated rebuild schema")
                if target_backend not in {"mysql", "sqlite"}:
                    return fail(503, 5032, "unsupported target database for I21 mapping preview")
                if target_backend == "mysql":
                    session.connection().exec_driver_sql("SET TRANSACTION READ ONLY")
                permitted = project_permission(session, project_id, user, Permission.EDIT_DEFINITION)
                if isinstance(permitted, JSONResponse):
                    return permitted

                reader = (legacy_i21_source_reader_factory or LegacyI21SourceReader.from_runtime_env)()
                source_snapshot = reader.read_snapshot()
                preview = build_i21_mapping_preview(session, project_id, source_snapshot)
                data = {
                    "project_id": project_id,
                    "source": {
                        "schema": preview.source_schema,
                        "captured_at": source_snapshot.captured_at.isoformat(),
                        "digest": preview.source_digest,
                        "counts": dict(preview.source_counts),
                    },
                    "target": {
                        "project_id": project_id,
                        "captured_at": preview.captured_at.isoformat(),
                        "identity_digest": preview.target_digest,
                        "counts": dict(preview.target_counts),
                    },
                    "preview": {
                        "counts": dict(preview.dispositions),
                        "entries": list(preview.entries),
                        "issues": [
                            {"code": issue.code, "source_table": issue.source_table, "source_id": issue.source_id}
                            for issue in preview.issues
                        ],
                        "parity_verified": False,
                        "import_enabled": False,
                    },
                }
                logger.info(
                    "legacy I21 mapping preview completed",
                    extra={
                        "project_id": project_id,
                        "source_counts": dict(preview.source_counts),
                        "preview_counts": dict(preview.dispositions),
                    },
                )
                return {"code": 0, "msg": "success", "data": data}
        except ValueError:
            return fail(422, 4221, "legacy I21 snapshot or mapping is invalid")
        except Exception as exc:
            logger.error(
                "legacy I21 mapping preview failed",
                extra={"project_id": project_id, "error_type": type(exc).__name__},
            )
            return fail(503, 5031, "legacy I21 mapping preview is unavailable")
        finally:
            source_engine = getattr(reader, "engine", None)
            if source_engine is not None:
                source_engine.dispose()

    @router.post("/legacy/i23/identity-preview")
    def legacy_i23_identity_preview(
        body: I23IdentityPreviewInput = Body(default_factory=I23IdentityPreviewInput),
        authorization: str = Header(default=""),
    ):
        if legacy_i23_preview_user is None:
            return fail(503, 5033, "I23 preview capability is unavailable")
        try:
            legacy_i23_preview_user(authorization)
        except PermissionError:
            return fail(403, 1003, "I23 preview capability required")
        except ValueError:
            return fail(401, 1001, "invalid token")

        selection_map: dict[str, int] = {}
        for selection in body.selections:
            if selection.source_id in selection_map:
                return fail(422, 4221, "duplicate I23 source selection")
            selection_map[selection.source_id] = selection.target_user_id

        reader = None
        try:
            with session_factory() as session:
                target_url = session.get_bind().url
                target_backend = target_url.get_backend_name()
                if target_backend == "mysql" and target_url.database != "datara_rebuild_i0":
                    return fail(503, 5032, "target database is not the isolated rebuild schema")
                if target_backend not in {"mysql", "sqlite"}:
                    return fail(503, 5032, "unsupported target database for I23 identity preview")
                if target_backend == "mysql":
                    session.connection().exec_driver_sql("SET TRANSACTION READ ONLY")
                reader = (legacy_i23_source_reader_factory or LegacyI23SourceReader.from_runtime_env)()
                source_snapshot = reader.read_snapshot(max_total_rows=MAX_I23_PREVIEW_ROWS)
                data = build_i23_identity_preview(session, source_snapshot, selection_map)
                logger.info(
                    "legacy I23 identity preview completed",
                    extra={
                        "source_counts": data["source"]["counts"],
                        "preview_counts": data["preview"]["counts"],
                    },
                )
                return {"code": 0, "msg": "success", "data": data}
        except ValueError:
            return fail(422, 4221, "legacy I23 snapshot or mapping is invalid")
        except Exception as exc:
            logger.error("legacy I23 identity preview failed", extra={"error_type": type(exc).__name__})
            return fail(503, 5031, "legacy I23 identity preview is unavailable")
        finally:
            source_engine = getattr(reader, "engine", None)
            if source_engine is not None:
                source_engine.dispose()

    @router.post("/projects/{project_id}/legacy/i22/mapping-preview")
    def legacy_i22_mapping_preview(project_id: int, authorization: str = Header(default="")):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        reader = None
        try:
            with session_factory() as session:
                permitted = project_permission(session, project_id, user, Permission.EDIT_DEFINITION)
                if isinstance(permitted, JSONResponse):
                    return permitted
                target_url = session.get_bind().url
                target_backend = target_url.get_backend_name()
                if target_backend == "mysql" and target_url.database != "datara_rebuild_i0":
                    return fail(503, 5032, "target database is not the isolated rebuild schema")
                if target_backend not in {"mysql", "sqlite"}:
                    return fail(503, 5032, "unsupported target database for I22 mapping preview")
                reader = (legacy_i22_source_reader_factory or LegacyI22SourceReader.from_runtime_env)()
                source_snapshot = reader.read_snapshot()
                preview = build_i22_mapping_preview(session, project_id, source_snapshot)
                data = {
                    "project_id": project_id,
                    "source": {
                        "schema": preview.source_schema,
                        "captured_at": source_snapshot.captured_at.isoformat(),
                        "digest": preview.source_digest,
                        "counts": dict(preview.source_counts),
                    },
                    "target": {
                        "project_id": project_id,
                        "captured_at": preview.captured_at.isoformat(),
                        "identity_digest": preview.target_digest,
                        "counts": dict(preview.target_counts),
                    },
                    "preview": {
                        "counts": dict(preview.dispositions),
                        "entries": list(preview.entries),
                        "issues": [
                            {
                                "code": issue.code,
                                "source_table": issue.source_table,
                                "source_id": issue.source_id,
                            }
                            for issue in preview.issues
                        ],
                        "parity_verified": False,
                        "import_enabled": False,
                    },
                }
                logger.info(
                    "legacy I22 mapping preview completed",
                    extra={
                        "project_id": project_id,
                        "source_counts": dict(preview.source_counts),
                        "preview_counts": dict(preview.dispositions),
                    },
                )
                return {"code": 0, "msg": "success", "data": data}
        except ValueError:
            return fail(422, 4221, "legacy I22 snapshot or mapping is invalid")
        except Exception as exc:
            logger.error(
                "legacy I22 mapping preview failed",
                extra={"project_id": project_id, "error_type": type(exc).__name__},
            )
            return fail(503, 5031, "legacy I22 mapping preview is unavailable")
        finally:
            source_engine = getattr(reader, "engine", None)
            if source_engine is not None:
                source_engine.dispose()

    @router.post("/projects/{project_id}/standards/check")
    def standards_check(project_id: int, authorization: str = Header(default="")):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        try:
            with session_factory() as session:
                permitted = project_permission(session, project_id, user, Permission.STANDARD_READ)
                if isinstance(permitted, JSONResponse):
                    return permitted
                reports = run_all_checks(session, project_id)
                data = {
                    "project_id": project_id,
                    "reports": [
                        {
                            "scope": report.scope,
                            "summary": report.summary,
                            "issues": [
                                {
                                    "engine": issue.engine,
                                    "scope": issue.scope,
                                    "severity": issue.severity,
                                    "message": issue.message,
                                    "source_id": issue.source_id,
                                }
                                for issue in report.issues
                            ],
                        }
                        for report in reports
                    ],
                }
                return {"code": 0, "msg": "success", "data": data}
        except ValueError:
            return fail(422, 4221, "invalid project or check parameters")
        except Exception as exc:
            logger.error(
                "standards check failed",
                extra={"project_id": project_id, "error_type": type(exc).__name__},
            )
            return fail(503, 5031, "standards check is unavailable")

    @router.post("/projects/{project_id}/legacy/i20/mapping-preview")
    def legacy_i20_mapping_preview(project_id: int, authorization: str = Header(default="")):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        reader = None
        try:
            with session_factory() as session:
                permitted = project_permission(session, project_id, user, Permission.EDIT_DEFINITION)
                if isinstance(permitted, JSONResponse):
                    return permitted
                target_url = session.get_bind().url
                target_backend = target_url.get_backend_name()
                if target_backend == "mysql" and target_url.database != "datara_rebuild_i0":
                    return fail(503, 5032, "target database is not the isolated rebuild schema")
                if target_backend not in {"mysql", "sqlite"}:
                    return fail(503, 5032, "unsupported target database for I20 mapping preview")
                reader = (legacy_i20_source_reader_factory or LegacyI20SourceReader.from_runtime_env)()
                source_snapshot = reader.read_snapshot()
                preview = build_i20_mapping_preview(session, project_id, source_snapshot)
                data = {
                    "project_id": project_id,
                    "source": {
                        "schema": preview.source_schema,
                        "captured_at": source_snapshot.captured_at.isoformat(),
                        "digest": preview.source_digest,
                        "counts": dict(preview.source_counts),
                    },
                    "target": {
                        "project_id": project_id,
                        "captured_at": preview.captured_at.isoformat(),
                        "identity_digest": preview.target_digest,
                        "counts": dict(preview.target_counts),
                    },
                    "preview": {
                        "counts": dict(preview.dispositions),
                        "entries": list(preview.entries),
                        "issues": [
                            {"code": issue.code, "source_table": issue.source_table, "source_id": issue.source_id}
                            for issue in preview.issues
                        ],
                        "parity_verified": False,
                        "import_enabled": False,
                    },
                }
                logger.info(
                    "legacy I20 mapping preview completed",
                    extra={
                        "project_id": project_id,
                        "source_counts": dict(preview.source_counts),
                        "preview_counts": dict(preview.dispositions),
                    },
                )
                return {"code": 0, "msg": "success", "data": data}
        except ValueError:
            return fail(422, 4221, "legacy I20 snapshot or mapping is invalid")
        except Exception as exc:
            logger.error(
                "legacy I20 mapping preview failed",
                extra={"project_id": project_id, "error_type": type(exc).__name__},
            )
            return fail(503, 5031, "legacy I20 mapping preview is unavailable")
        finally:
            if reader is not None:
                source_engine = getattr(reader, "engine", None)
                if source_engine is not None:
                    source_engine.dispose()

    @router.post("/projects/{project_id}/legacy/i19/import")
    def legacy_i19_import(
        project_id: int,
        body: LegacyI19I20ImportInput,
        authorization: str = Header(default=""),
    ):
        if not legacy_i19_import_enabled:
            return fail(503, 5034, "legacy I19 import is disabled")
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        try:
            actor_id = int(user.get("user_id", 0))
        except (TypeError, ValueError):
            actor_id = 0
        if actor_id <= 0:
            return fail(403, 1003, "a persisted operator identity is required for I19 import")

        reader = None
        try:
            with session_factory() as session:
                actor = session.get(UserRecord, actor_id)
                if actor is None:
                    return fail(403, 1003, "a persisted operator identity is required for I19 import")
                operator = {**user, "user_id": actor.id, "role": actor.role}
                permitted = project_permission(session, project_id, operator, Permission.EDIT_DEFINITION)
                if isinstance(permitted, JSONResponse):
                    return permitted
                target_url = session.get_bind().url
                target_backend = target_url.get_backend_name()
                if target_backend == "mysql" and target_url.database != "datara_rebuild_i0":
                    return fail(503, 5032, "target database is not the isolated rebuild schema")
                if target_backend == "sqlite" and target_url.database != ":memory:":
                    return fail(503, 5032, "file SQLite is not an allowed I19 import target")
                if target_backend not in {"mysql", "sqlite"}:
                    return fail(503, 5032, "unsupported target database for I19 import")
                expected_confirmation = f"IMPORT I19 {project_id} {body.source_digest} {body.target_digest}"
                if body.confirmation != expected_confirmation:
                    return fail(409, 4094, "explicit I19 confirmation does not match the supplied snapshots")
                reader = (legacy_i19_source_reader_factory or LegacyI19SourceReader.from_runtime_env)()
                source_snapshot = reader.read_snapshot()
                if source_snapshot.digest != body.source_digest:
                    return fail(409, 4094, "I19 source digest changed; request a fresh mapping preview")
                context = build_i19_mapping_context(session, project_id)
                if i19_target_identity_digest(context) != body.target_digest:
                    return fail(409, 4094, "I19 target digest changed; request a fresh mapping preview")

            result = execute_i19_legacy_import(
                session_factory,
                project_id=project_id,
                actor_id=actor_id,
                source_snapshot=source_snapshot,
                expected_source_digest=body.source_digest,
                expected_target_digest=body.target_digest,
                mapping_context_factory=build_i19_mapping_context,
                idempotency_key=body.idempotency_key,
            )
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "batch_id": result.batch_id,
                    "status": result.status,
                    "expected_count": result.expected_count,
                    "imported_count": result.imported_count,
                    "skipped_count": result.skipped_count,
                    "error_count": result.error_count,
                },
            }
        except (LegacyImportRejected, CheckpointConflict):
            return fail(409, 4094, "I19 import conflicts with the current source or target state")
        except ValueError:
            return fail(422, 4221, "legacy I19 snapshot or mapping is invalid")
        except Exception as exc:
            logger.error(
                "legacy I19 import failed",
                extra={"project_id": project_id, "error_type": type(exc).__name__},
            )
            return fail(503, 5031, "legacy I19 import is unavailable")
        finally:
            if reader is not None:
                source_engine = getattr(reader, "engine", None)
                if source_engine is not None:
                    source_engine.dispose()

    @router.post("/projects/{project_id}/legacy/i20/import")
    def legacy_i20_import(
        project_id: int,
        body: LegacyI19I20ImportInput,
        authorization: str = Header(default=""),
    ):
        if not legacy_i20_import_enabled:
            return fail(503, 5034, "legacy I20 import is disabled")
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        try:
            actor_id = int(user.get("user_id", 0))
        except (TypeError, ValueError):
            actor_id = 0
        if actor_id <= 0:
            return fail(403, 1003, "a persisted operator identity is required for I20 import")

        reader = None
        try:
            with session_factory() as session:
                actor = session.get(UserRecord, actor_id)
                if actor is None:
                    return fail(403, 1003, "a persisted operator identity is required for I20 import")
                operator = {**user, "user_id": actor.id, "role": actor.role}
                permitted = project_permission(session, project_id, operator, Permission.EDIT_DEFINITION)
                if isinstance(permitted, JSONResponse):
                    return permitted
                target_url = session.get_bind().url
                target_backend = target_url.get_backend_name()
                if target_backend == "mysql" and target_url.database != "datara_rebuild_i0":
                    return fail(503, 5032, "target database is not the isolated rebuild schema")
                if target_backend == "sqlite" and target_url.database != ":memory:":
                    return fail(503, 5032, "file SQLite is not an allowed I20 import target")
                if target_backend not in {"mysql", "sqlite"}:
                    return fail(503, 5032, "unsupported target database for I20 import")
                expected_confirmation = f"IMPORT I20 {project_id} {body.source_digest} {body.target_digest}"
                if body.confirmation != expected_confirmation:
                    return fail(409, 4094, "explicit I20 confirmation does not match the supplied snapshots")
                reader = (legacy_i20_source_reader_factory or LegacyI20SourceReader.from_runtime_env)()
                source_snapshot = reader.read_snapshot()
                if source_snapshot.digest != body.source_digest:
                    return fail(409, 4094, "I20 source digest changed; request a fresh mapping preview")
                preview = build_i20_mapping_preview(session, project_id, source_snapshot)
                if preview.target_digest != body.target_digest:
                    return fail(409, 4094, "I20 target digest changed; request a fresh mapping preview")

            result = execute_i20_legacy_import(
                session_factory,
                project_id=project_id,
                actor_id=actor_id,
                source_snapshot=source_snapshot,
                expected_source_digest=body.source_digest,
                expected_target_digest=body.target_digest,
                idempotency_key=body.idempotency_key,
            )
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "batch_id": result.batch_id,
                    "status": result.status,
                    "expected_count": result.expected_count,
                    "imported_count": result.imported_count,
                    "skipped_count": result.skipped_count,
                    "error_count": result.error_count,
                },
            }
        except (LegacyImportRejected, CheckpointConflict):
            return fail(409, 4094, "I20 import conflicts with the current source or target state")
        except ValueError:
            return fail(422, 4221, "legacy I20 snapshot or mapping is invalid")
        except Exception as exc:
            logger.error(
                "legacy I20 import failed",
                extra={"project_id": project_id, "error_type": type(exc).__name__},
            )
            return fail(503, 5031, "legacy I20 import is unavailable")
        finally:
            if reader is not None:
                source_engine = getattr(reader, "engine", None)
                if source_engine is not None:
                    source_engine.dispose()

    @router.post("/projects/{project_id}/legacy/i21/import")
    def legacy_i21_import(
        project_id: int,
        authorization: str = Header(default=""),
        body: dict = Body(...),
    ):
        if not legacy_i21_import_enabled:
            return fail(403, 4031, "legacy I21 import is disabled")
        try:
            user = authenticate(authorization)
            if isinstance(user, JSONResponse):
                return user
        except ValueError:
            return fail(401, 1001, "invalid token")

        reader = None
        try:
            with session_factory() as session:
                permitted = project_permission(session, project_id, user, Permission.EDIT_DEFINITION)
                if isinstance(permitted, JSONResponse):
                    return permitted
                target_url = session.get_bind().url
                target_backend = target_url.get_backend_name()
                if target_backend == "mysql" and target_url.database != "datara_rebuild_i0":
                    return fail(503, 5032, "target database is not the isolated rebuild schema")
                if target_backend not in {"mysql", "sqlite"}:
                    return fail(503, 5032, "unsupported target database for I21 import")
                reader = (legacy_i21_source_reader_factory or LegacyI21SourceReader.from_runtime_env)()
                source_snapshot = reader.read_snapshot()
                from rebuild.governance.legacy_i21_importer import build_i21_mapping_context, i21_target_identity_digest
                context = build_i21_mapping_context(session, project_id)
                target_digest = i21_target_identity_digest(context)
                actor_id = int(user["user_id"])
                idempotency_key = body.get("idempotency_key", "")
                if not idempotency_key:
                    return fail(422, 4221, "idempotency_key is required")
            result = execute_i21_legacy_import(
                session_factory,
                project_id=project_id,
                actor_id=actor_id,
                source_snapshot=source_snapshot,
                expected_source_digest=body.get("source_digest", source_snapshot.digest),
                expected_target_digest=body.get("target_digest", target_digest),
                idempotency_key=idempotency_key,
            )
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "batch_id": result.batch_id,
                    "status": result.status,
                    "expected_count": result.expected_count,
                    "imported_count": result.imported_count,
                    "skipped_count": result.skipped_count,
                    "error_count": result.error_count,
                },
            }
        except (LegacyImportRejected, CheckpointConflict):
            return fail(409, 4094, "I21 import conflicts with the current source or target state")
        except ValueError:
            return fail(422, 4221, "legacy I21 snapshot or mapping is invalid")
        except Exception as exc:
            logger.error(
                "legacy I21 import failed",
                extra={"project_id": project_id, "error_type": type(exc).__name__},
            )
            return fail(503, 5031, "legacy I21 import is unavailable")
        finally:
            if reader is not None:
                source_engine = getattr(reader, "engine", None)
                if source_engine is not None:
                    source_engine.dispose()

    @router.post("/projects/{project_id}/legacy/i22/import")
    def legacy_i22_import(
        project_id: int,
        authorization: str = Header(default=""),
        body: dict = Body(...),
    ):
        if not legacy_i22_import_enabled:
            return fail(403, 4031, "legacy I22 import is disabled")
        try:
            user = authenticate(authorization)
            if isinstance(user, JSONResponse):
                return user
        except ValueError:
            return fail(401, 1001, "invalid token")

        reader = None
        try:
            with session_factory() as session:
                permitted = project_permission(session, project_id, user, Permission.EDIT_DEFINITION)
                if isinstance(permitted, JSONResponse):
                    return permitted
                target_url = session.get_bind().url
                target_backend = target_url.get_backend_name()
                if target_backend == "mysql" and target_url.database != "datara_rebuild_i0":
                    return fail(503, 5032, "target database is not the isolated rebuild schema")
                if target_backend not in {"mysql", "sqlite"}:
                    return fail(503, 5032, "unsupported target database for I22 import")
                reader = (legacy_i22_source_reader_factory or LegacyI22SourceReader.from_runtime_env)()
                source_snapshot = reader.read_snapshot()
                from rebuild.governance.legacy_i22_importer import build_i22_mapping_context, i22_target_identity_digest
                context = build_i22_mapping_context(session, project_id)
                target_digest = i22_target_identity_digest(context)
                actor_id = int(user["user_id"])
                idempotency_key = body.get("idempotency_key", "")
                if not idempotency_key:
                    return fail(422, 4221, "idempotency_key is required")
            result = execute_i22_legacy_import(
                session_factory,
                project_id=project_id,
                actor_id=actor_id,
                source_snapshot=source_snapshot,
                expected_source_digest=body.get("source_digest", source_snapshot.digest),
                expected_target_digest=body.get("target_digest", target_digest),
                idempotency_key=idempotency_key,
            )
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "batch_id": result.batch_id,
                    "status": result.status,
                    "expected_count": result.expected_count,
                    "imported_count": result.imported_count,
                    "skipped_count": result.skipped_count,
                    "error_count": result.error_count,
                },
            }
        except (LegacyImportRejected, CheckpointConflict):
            return fail(409, 4094, "I22 import conflicts with the current source or target state")
        except ValueError:
            return fail(422, 4221, "legacy I22 snapshot or mapping is invalid")
        except Exception as exc:
            logger.error(
                "legacy I22 import failed",
                extra={"project_id": project_id, "error_type": type(exc).__name__},
            )
            return fail(503, 5031, "legacy I22 import is unavailable")
        finally:
            if reader is not None:
                source_engine = getattr(reader, "engine", None)
                if source_engine is not None:
                    source_engine.dispose()

    @router.post("/projects/{project_id}/legacy/i18/dry-run")
    def legacy_i18_dry_run(project_id: int, authorization: str = Header(default="")):
        try:
            user = authenticate(authorization)
            if isinstance(user, JSONResponse):
                return user
        except ValueError:
            return fail(401, 1001, "invalid token")

        reader = None
        try:
            with session_factory() as session:
                permitted = project_permission(session, project_id, user, Permission.EDIT_DEFINITION)
                if isinstance(permitted, JSONResponse):
                    return permitted
                target_url = session.get_bind().url
                target_backend = target_url.get_backend_name()
                if target_backend == "mysql" and target_url.database != "datara_rebuild_i0":
                    return fail(503, 5032, "target database is not the isolated rebuild schema")
                if target_backend not in {"mysql", "sqlite"}:
                    return fail(503, 5032, "unsupported target database for I18 dry-run")
                reader = (legacy_source_reader_factory or LegacyI18SourceReader.from_runtime_env)()
                source_snapshot = reader.read_snapshot()
                target_snapshot = LegacyI18TargetSnapshotRepository(session).read_project_snapshot(project_id)
                result = build_i18_legacy_dry_run(project_id, source_snapshot, target_snapshot)
                data = {
                    "project_id": project_id,
                    "source": {
                        "schema": source_snapshot.schema,
                        "captured_at": source_snapshot.captured_at.isoformat(),
                        "digest": source_snapshot.digest,
                        "counts": dict(source_snapshot.counts),
                    },
                    "target": {
                        "project_id": target_snapshot.project_id,
                        "captured_at": target_snapshot.captured_at.isoformat(),
                        "digest": target_snapshot.digest,
                        "identity_count": len(target_snapshot.row_fingerprints),
                    },
                    "plan": {
                        "counts": dict(result.plan.counts),
                        "ready_to_import": result.plan.ready_to_import,
                        "entries": [
                            {
                                "source_table": entry.source_table,
                                "source_id": entry.source_id,
                                "disposition": entry.disposition,
                                "disposition_reason": entry.disposition_reason,
                                "fingerprint": entry.fingerprint,
                                "mapping_notes": list(entry.mapping_notes),
                            }
                            for entry in result.plan.entries
                        ],
                        "import_order": [
                            {"source_table": table, "source_id": source_id}
                            for table, source_id in result.plan.import_order
                        ],
                        "issues": [
                            {
                                "code": issue.code,
                                "source_table": issue.source_table,
                                "source_id": issue.source_id,
                                "detail": issue.detail,
                            }
                            for issue in result.plan.blocking_issues
                        ],
                    },
                }
                logger.info(
                    "legacy I18 dry-run completed",
                    extra={
                        "project_id": project_id,
                        "source_counts": dict(source_snapshot.counts),
                        "plan_counts": dict(result.plan.counts),
                    },
                )
                return {"code": 0, "msg": "success", "data": data}
        except ValueError as exc:
            return fail(422, 4221, str(exc))
        except Exception as exc:
            logger.error(
                "legacy I18 dry-run snapshot failed",
                extra={"project_id": project_id, "error_type": type(exc).__name__},
            )
            return fail(503, 5031, "legacy I18 snapshot is unavailable")
        finally:
            source_engine = getattr(reader, "engine", None)
            if source_engine is not None:
                source_engine.dispose()

    @router.post("/projects/{project_id}/legacy/i18/import")
    def legacy_i18_import(
        project_id: int,
        body: LegacyI18ImportInput,
        authorization: str = Header(default=""),
    ):
        # Keep the default path completely inert: no source connection, target
        # snapshot query, checkpoint, or importer construction may occur.
        # The disabled check MUST come before any auth/permission check so that
        # a disabled import always returns 503 regardless of the caller.
        if not legacy_i18_import_enabled:
            return fail(503, 5034, "legacy I18 import is disabled")
        try:
            user = authenticate(authorization)
            if isinstance(user, JSONResponse):
                return user
        except ValueError:
            return fail(401, 1001, "invalid token")

        try:
            actor_id = int(user.get("user_id", 0))
        except (TypeError, ValueError):
            actor_id = 0
        if actor_id <= 0:
            return fail(403, 1003, "a persisted operator identity is required for I18 import")

        reader = None
        try:
            with session_factory() as session:
                actor = session.get(UserRecord, actor_id)
                if actor is None:
                    return fail(403, 1003, "a persisted operator identity is required for I18 import")
                operator = {**user, "user_id": actor.id, "role": actor.role}
                permitted = project_permission(session, project_id, operator, Permission.EDIT_DEFINITION)
                if isinstance(permitted, JSONResponse):
                    return permitted
                expected_confirmation = f"IMPORT I18 {project_id} {body.source_digest} {body.target_digest}"
                if body.confirmation != expected_confirmation:
                    return fail(409, 4094, "explicit I18 confirmation does not match the supplied snapshots")
                target_url = session.get_bind().url
                target_backend = target_url.get_backend_name()
                if target_backend == "mysql" and target_url.database != "datara_rebuild_i0":
                    return fail(503, 5032, "target database is not the isolated rebuild schema")
                if target_backend == "sqlite" and target_url.database != ":memory:":
                    return fail(503, 5032, "file SQLite is not an allowed I18 import target")
                if target_backend not in {"mysql", "sqlite"}:
                    return fail(503, 5032, "unsupported target database for I18 import")

                reader = (legacy_source_reader_factory or LegacyI18SourceReader.from_runtime_env)()
                source_snapshot = reader.read_snapshot()
                target_snapshot = LegacyI18TargetSnapshotRepository(session).read_project_snapshot(project_id)
                dry_run = build_i18_legacy_dry_run(project_id, source_snapshot, target_snapshot)
                if source_snapshot.digest != body.source_digest or target_snapshot.digest != body.target_digest:
                    return fail(409, 4095, "I18 source or target snapshot changed; run a fresh dry-run")
                if not i18_import_matches_approved_scope(project_id, dry_run.plan):
                    return fail(409, 4099, "latest I18 dry-run is outside the approved one-time import scope")
                if not dry_run.plan.ready_to_import:
                    return fail(409, 4096, "latest I18 dry-run contains conflicts or blocked rows")

                result = execute_i18_legacy_import(
                    session_factory,
                    project_id=project_id,
                    actor_id=actor_id,
                    source_snapshot=source_snapshot,
                    target_snapshot=target_snapshot,
                    idempotency_key=body.idempotency_key,
                )
                data = {
                    "batch_id": result.batch_id,
                    "status": result.status,
                    "expected_count": result.expected_count,
                    "imported_count": result.imported_count,
                    "skipped_count": result.skipped_count,
                    "error_count": result.error_count,
                }
                logger.info(
                    "legacy I18 import request completed",
                    extra={"project_id": project_id, "batch_id": result.batch_id, "status": result.status},
                )
                if result.status != "completed":
                    return JSONResponse(
                        status_code=409,
                        content={"code": 4097, "msg": "I18 import stopped with unresolved items", "data": data},
                    )
                return {"code": 0, "msg": "success", "data": data}
        except (LegacyImportRejected, CheckpointConflict) as exc:
            logger.warning(
                "legacy I18 import rejected",
                extra={"project_id": project_id, "error_type": type(exc).__name__},
            )
            return fail(409, 4098, "I18 import was rejected by a migration safety check")
        except ValueError as exc:
            return fail(422, 4221, str(exc))
        except Exception as exc:
            logger.error(
                "legacy I18 import failed",
                extra={"project_id": project_id, "error_type": type(exc).__name__},
            )
            return fail(503, 5031, "legacy I18 import is unavailable")
        finally:
            source_engine = getattr(reader, "engine", None)
            if source_engine is not None:
                source_engine.dispose()

    def write_audit(
        session: Session,
        *,
        user: dict[str, object],
        project_id: int,
        action: str,
        resource_type: str,
        resource_id: str,
        after: dict[str, object],
    ) -> None:
        GovernanceService(session).record_mutation(
            actor_id=int(user["user_id"]),
            project_id=project_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            after_json=json.dumps(after, ensure_ascii=False, separators=(",", ":")),
        )

    def stamp(value: datetime | None) -> str | None:
        return value.isoformat(sep=" ") if value else None

    def asset_payload(session: Session, asset: AssetRecord, *, detail: bool = False) -> dict[str, object]:
        tags = session.scalars(
            select(GovernanceTagRecord)
            .join(AssetTagRecord, AssetTagRecord.tag_id == GovernanceTagRecord.id)
            .where(AssetTagRecord.asset_id == asset.id)
            .order_by(GovernanceTagRecord.namespace, GovernanceTagRecord.tag_key)
        ).all()
        result: dict[str, object] = {
            "id": asset.id,
            "project_id": asset.project_id,
            "source_system": asset.source_system,
            "database_name": asset.database_name,
            "schema_name": asset.schema_name,
            "asset_name": asset.asset_name,
            "asset_type": asset.asset_type,
            "display_name": asset.display_name,
            "description": asset.description,
            "owner_name": asset.owner_name,
            "domain_name": asset.domain_name,
            "row_count": asset.row_count,
            "created_at": stamp(asset.created_at),
            "updated_at": stamp(asset.updated_at),
            "tags": [tag_payload(tag) for tag in tags],
        }
        if detail:
            fields = session.scalars(
                select(AssetFieldRecord)
                .where(AssetFieldRecord.asset_id == asset.id)
                .order_by(AssetFieldRecord.ordinal_position)
            ).all()
            runs = session.scalars(
                select(QualityRunRecord)
                .where(QualityRunRecord.asset_id == asset.id)
                .order_by(QualityRunRecord.generated_at.desc(), QualityRunRecord.id.desc())
                .limit(20)
            ).all()
            result["fields"] = [
                {
                    "id": field.id,
                    "field_name": field.field_name,
                    "ordinal_position": field.ordinal_position,
                    "data_type": field.data_type,
                    "nullable": field.nullable,
                    "description": field.description,
                    "created_at": stamp(field.created_at),
                    "updated_at": stamp(field.updated_at),
                }
                for field in fields
            ]
            result["quality_runs"] = [quality_run_payload(run) for run in runs]
        return result

    def tag_payload(tag: GovernanceTagRecord) -> dict[str, object]:
        return {
            "id": tag.id,
            "namespace": tag.namespace,
            "tag_key": tag.tag_key,
            "display_name": tag.display_name,
            "description": tag.description,
            "created_at": stamp(tag.created_at),
            "updated_at": stamp(tag.updated_at),
        }

    def quality_run_payload(run: QualityRunRecord) -> dict[str, object]:
        return {
            "id": run.id,
            "rule_id": run.rule_id,
            "status": run.status,
            "checked_rows": run.checked_rows,
            "success_rows": run.success_rows,
            "failed_rows": run.failed_rows,
            "skipped_rows": run.skipped_rows,
            "summary": json.loads(run.summary_json),
            "generated_at": stamp(run.generated_at),
        }

    def list_by_project(model, project_id: int, page: int, page_size: int, *, order_by=None):
        with session_factory() as session:
            query = select(model).where(model.project_id == project_id)
            count = session.scalar(select(func.count()).select_from(query.subquery())) or 0
            if order_by is None:
                order_by = model.id.desc()
            rows = session.scalars(query.order_by(order_by).offset((page - 1) * page_size).limit(page_size)).all()
            return count, rows

    @router.post("/projects/{project_id}/assets", status_code=201)
    def create_asset(project_id: int, body: AssetInput, authorization: str = Header(default="")):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        with session_factory() as session:
            permitted = project_permission(session, project_id, user, Permission.EDIT_DEFINITION)
            if isinstance(permitted, JSONResponse):
                return permitted
            asset = AssetRecord(
                project_id=project_id,
                source_system=body.source_system,
                database_name=body.database_name,
                schema_name=body.schema_name,
                asset_name=body.asset_name,
                asset_type=body.asset_type,
                display_name=body.display_name,
                description=body.description,
                owner_name=body.owner_name,
                domain_name=body.domain_name,
                row_count=body.row_count,
            )
            session.add(asset)
            try:
                session.flush()
                for item in body.fields:
                    session.add(AssetFieldRecord(asset_id=asset.id, **item.model_dump()))
                write_audit(
                    session,
                    user=user,
                    project_id=project_id,
                    action="asset.create",
                    resource_type="asset",
                    resource_id=str(asset.id),
                    after={"name": asset.asset_name, "schema": asset.schema_name, "type": asset.asset_type},
                )
                session.commit()
            except IntegrityError:
                session.rollback()
                return fail(409, 4091, "asset identity already exists")
            session.refresh(asset)
            return {"code": 0, "msg": "success", "data": asset_payload(session, asset, detail=True)}

    @router.get("/projects/{project_id}/assets")
    def list_assets(
        project_id: int,
        q: str = "",
        asset_type: str = "",
        domain: str = "",
        tag: str = "",
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
        authorization: str = Header(default=""),
    ):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        with session_factory() as session:
            permitted = project_permission(session, project_id, user, Permission.VIEW_ALL)
            if isinstance(permitted, JSONResponse):
                return permitted
            query = select(AssetRecord).where(AssetRecord.project_id == project_id)
            if q.strip():
                pattern = f"%{q.strip()}%"
                query = query.where(or_(AssetRecord.asset_name.ilike(pattern), AssetRecord.display_name.ilike(pattern)))
            if asset_type:
                query = query.where(AssetRecord.asset_type == asset_type)
            if domain:
                query = query.where(AssetRecord.domain_name == domain)
            if tag:
                query = (
                    query.join(AssetTagRecord)
                    .join(GovernanceTagRecord)
                    .where(GovernanceTagRecord.tag_key == tag)
                    .distinct()
                )
            total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
            rows = session.scalars(query.order_by(AssetRecord.id).offset((page - 1) * page_size).limit(page_size)).all()
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "list": [asset_payload(session, row) for row in rows],
                },
            }

    @router.get("/assets/{asset_id}")
    def get_asset(asset_id: int, authorization: str = Header(default="")):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        with session_factory() as session:
            asset = session.get(AssetRecord, asset_id)
            if asset is None:
                return fail(404, 4041, "asset not found")
            permitted = project_permission(session, asset.project_id, user, Permission.VIEW_ALL)
            if isinstance(permitted, JSONResponse):
                return permitted
            return {"code": 0, "msg": "success", "data": asset_payload(session, asset, detail=True)}

    @router.post("/projects/{project_id}/tags", status_code=201)
    def create_tag(project_id: int, body: TagInput, authorization: str = Header(default="")):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        with session_factory() as session:
            permitted = project_permission(session, project_id, user, Permission.EDIT_DEFINITION)
            if isinstance(permitted, JSONResponse):
                return permitted
            if body.asset_id is not None:
                asset = session.get(AssetRecord, body.asset_id)
                if asset is None or asset.project_id != project_id:
                    return fail(404, 4041, "asset not found in project")
            tag_values = body.model_dump(exclude={"asset_id"})
            tag = GovernanceTagRecord(project_id=project_id, **tag_values)
            session.add(tag)
            try:
                session.flush()
                if body.asset_id is not None:
                    session.add(AssetTagRecord(asset_id=body.asset_id, tag_id=tag.id))
                write_audit(
                    session,
                    user=user,
                    project_id=project_id,
                    action="tag.create_and_attach" if body.asset_id is not None else "tag.create",
                    resource_type="tag",
                    resource_id=str(tag.id),
                    after={"namespace": tag.namespace, "tag_key": tag.tag_key, "asset_id": body.asset_id},
                )
                session.commit()
            except IntegrityError:
                session.rollback()
                return fail(409, 4091, "tag identity already exists")
            session.refresh(tag)
            return {"code": 0, "msg": "success", "data": tag_payload(tag)}

    @router.put("/assets/{asset_id}/tags")
    def assign_asset_tags(asset_id: int, body: TagAssignment, authorization: str = Header(default="")):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        with session_factory() as session:
            asset = session.get(AssetRecord, asset_id)
            if asset is None:
                return fail(404, 4041, "asset not found")
            permitted = project_permission(session, asset.project_id, user, Permission.EDIT_DEFINITION)
            if isinstance(permitted, JSONResponse):
                return permitted
            tag_ids = set(body.tag_ids)
            tags = (
                session.scalars(
                    select(GovernanceTagRecord).where(
                        GovernanceTagRecord.project_id == asset.project_id, GovernanceTagRecord.id.in_(tag_ids)
                    )
                ).all()
                if tag_ids
                else []
            )
            if len(tags) != len(tag_ids):
                return fail(404, 4041, "one or more project tags not found")
            session.query(AssetTagRecord).filter(AssetTagRecord.asset_id == asset_id).delete()
            for tag in tags:
                session.add(AssetTagRecord(asset_id=asset_id, tag_id=tag.id))
            write_audit(
                session,
                user=user,
                project_id=asset.project_id,
                action="asset.tags.replace",
                resource_type="asset",
                resource_id=str(asset_id),
                after={"tag_ids": sorted(tag_ids)},
            )
            session.commit()
            return {"code": 0, "msg": "success", "data": {"asset_id": asset_id, "tag_ids": sorted(tag_ids)}}

    @router.post("/projects/{project_id}/lineage", status_code=201)
    def create_lineage(project_id: int, body: LineageInput, authorization: str = Header(default="")):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        with session_factory() as session:
            permitted = project_permission(session, project_id, user, Permission.EDIT_DEFINITION)
            if isinstance(permitted, JSONResponse):
                return permitted
            endpoints = session.scalars(
                select(AssetRecord).where(
                    AssetRecord.project_id == project_id,
                    AssetRecord.id.in_([body.source_asset_id, body.target_asset_id]),
                )
            ).all()
            if len({item.id for item in endpoints}) != 2 or body.source_asset_id == body.target_asset_id:
                return fail(400, 4001, "lineage endpoints must be two assets in this project")
            edge = LineageEdgeRecord(project_id=project_id, **body.model_dump())
            session.add(edge)
            try:
                session.flush()
                write_audit(
                    session,
                    user=user,
                    project_id=project_id,
                    action="lineage.create",
                    resource_type="lineage_edge",
                    resource_id=str(edge.id),
                    after={
                        "external_id": edge.external_id,
                        "source_asset_id": edge.source_asset_id,
                        "target_asset_id": edge.target_asset_id,
                    },
                )
                session.commit()
            except IntegrityError:
                session.rollback()
                return fail(409, 4091, "lineage identity already exists")
            return {"code": 0, "msg": "success", "data": {"id": edge.id, **body.model_dump()}}

    @router.get("/assets/{asset_id}/lineage")
    def get_lineage(
        asset_id: int,
        direction: str = Query(default="both", pattern="^(upstream|downstream|both)$"),
        depth: int = Query(default=3, ge=1, le=10),
        authorization: str = Header(default=""),
    ):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        with session_factory() as session:
            asset = session.get(AssetRecord, asset_id)
            if asset is None:
                return fail(404, 4041, "asset not found")
            permitted = project_permission(session, asset.project_id, user, Permission.VIEW_ALL)
            if isinstance(permitted, JSONResponse):
                return permitted
            visited = {asset_id}
            edges_by_id: dict[int, LineageEdgeRecord] = {}
            queue = deque([(asset_id, 0)])
            while queue:
                current_id, level = queue.popleft()
                if level >= depth:
                    continue
                predicates = []
                if direction in ("upstream", "both"):
                    predicates.append(LineageEdgeRecord.target_asset_id == current_id)
                if direction in ("downstream", "both"):
                    predicates.append(LineageEdgeRecord.source_asset_id == current_id)
                edges = session.scalars(
                    select(LineageEdgeRecord).where(LineageEdgeRecord.project_id == asset.project_id, or_(*predicates))
                ).all()
                for edge in edges:
                    edges_by_id[edge.id] = edge
                    next_id = edge.source_asset_id if edge.target_asset_id == current_id else edge.target_asset_id
                    if next_id not in visited:
                        visited.add(next_id)
                        queue.append((next_id, level + 1))
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "asset_id": asset_id,
                    "direction": direction,
                    "depth": depth,
                    "nodes": [
                        asset_payload(session, node)
                        for node in session.scalars(
                            select(AssetRecord).where(
                                AssetRecord.project_id == asset.project_id,
                                AssetRecord.id.in_(visited),
                            )
                        ).all()
                    ],
                    "edges": [
                        {
                            "id": edge.id,
                            "external_id": edge.external_id,
                            "source_asset_id": edge.source_asset_id,
                            "target_asset_id": edge.target_asset_id,
                            "source_field_name": edge.source_field_name,
                            "target_field_name": edge.target_field_name,
                            "lineage_type": edge.lineage_type,
                            "process_ref": edge.process_ref,
                            "created_at": stamp(edge.created_at),
                        }
                        for edge in edges_by_id.values()
                    ],
                },
            }

    @router.post("/projects/{project_id}/quality-rules", status_code=201)
    def create_quality_rule(project_id: int, body: QualityRuleInput, authorization: str = Header(default="")):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        with session_factory() as session:
            permitted = project_permission(session, project_id, user, Permission.EDIT_DEFINITION)
            if isinstance(permitted, JSONResponse):
                return permitted
            asset = session.get(AssetRecord, body.asset_id)
            if asset is None or asset.project_id != project_id:
                return fail(404, 4041, "asset not found in project")
            rule = QualityRuleRecord(project_id=project_id, **body.model_dump())
            session.add(rule)
            try:
                session.flush()
                write_audit(
                    session,
                    user=user,
                    project_id=project_id,
                    action="quality_rule.create",
                    resource_type="quality_rule",
                    resource_id=str(rule.id),
                    after={"name": rule.name, "asset_id": rule.asset_id},
                )
                session.commit()
            except IntegrityError:
                session.rollback()
                return fail(409, 4091, "quality rule name already exists")
            session.refresh(rule)
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "id": rule.id,
                    "project_id": project_id,
                    "asset_id": rule.asset_id,
                    "name": rule.name,
                    "expression": rule.expression,
                    "severity": rule.severity,
                    "enabled": rule.enabled,
                    "created_at": stamp(rule.created_at),
                    "updated_at": stamp(rule.updated_at),
                },
            }

    @router.get("/projects/{project_id}/quality-rules")
    def list_quality_rules(
        project_id: int,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
        authorization: str = Header(default=""),
    ):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        with session_factory() as session:
            permitted = project_permission(session, project_id, user, Permission.VIEW_ALL)
            if isinstance(permitted, JSONResponse):
                return permitted
            rules = session.scalars(
                select(QualityRuleRecord)
                .where(QualityRuleRecord.project_id == project_id)
                .order_by(QualityRuleRecord.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            total = (
                session.scalar(
                    select(func.count())
                    .select_from(QualityRuleRecord)
                    .where(QualityRuleRecord.project_id == project_id)
                )
                or 0
            )
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "total": total,
                    "list": [
                        {
                            "id": r.id,
                            "asset_id": r.asset_id,
                            "name": r.name,
                            "expression": r.expression,
                            "severity": r.severity,
                            "enabled": r.enabled,
                            "created_at": stamp(r.created_at),
                            "updated_at": stamp(r.updated_at),
                        }
                        for r in rules
                    ],
                },
            }

    @router.get("/projects/{project_id}/quality-runs")
    def list_quality_runs(
        project_id: int,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
        authorization: str = Header(default=""),
    ):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        with session_factory() as session:
            permitted = project_permission(session, project_id, user, Permission.VIEW_ALL)
            if isinstance(permitted, JSONResponse):
                return permitted
            query = select(QualityRunRecord).where(QualityRunRecord.project_id == project_id)
            total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
            runs = session.scalars(
                query.order_by(QualityRunRecord.generated_at.desc(), QualityRunRecord.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return {
                "code": 0,
                "msg": "success",
                "data": {"total": total, "list": [{"asset_id": r.asset_id, **quality_run_payload(r)} for r in runs]},
            }

    def add_definition(
        project_id: int, body: BaseModel, user: dict[str, object], model, resource: str, fields: dict[str, object]
    ):
        with session_factory() as session:
            permitted = project_permission(session, project_id, user, Permission.EDIT_DEFINITION)
            if isinstance(permitted, JSONResponse):
                return permitted
            record = model(project_id=project_id, **body.model_dump())
            session.add(record)
            try:
                session.flush()
                write_audit(
                    session,
                    user=user,
                    project_id=project_id,
                    action=f"{resource}.create",
                    resource_type=resource,
                    resource_id=str(record.id),
                    after={"code": getattr(record, "code", "")},
                )
                session.commit()
            except IntegrityError:
                session.rollback()
                return fail(409, 4091, f"{resource} code already exists")
            session.refresh(record)
            payload = {"id": record.id, "project_id": project_id, **fields}
            payload.update({key: getattr(record, key) for key in fields})
            payload["created_at"] = stamp(record.created_at)
            payload["updated_at"] = stamp(record.updated_at)
            return {"code": 0, "msg": "success", "data": payload}

    def list_definitions(
        project_id: int, user: dict[str, object], model, fields: tuple[str, ...], page: int, page_size: int
    ):
        with session_factory() as session:
            permitted = project_permission(session, project_id, user, Permission.VIEW_ALL)
            if isinstance(permitted, JSONResponse):
                return permitted
            total, rows = list_by_project(model, project_id, page, page_size)
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "total": total,
                    "list": [
                        {
                            "id": row.id,
                            "project_id": project_id,
                            **{field: getattr(row, field) for field in fields},
                            "created_at": stamp(row.created_at),
                            "updated_at": stamp(row.updated_at),
                        }
                        for row in rows
                    ],
                },
            }

    @router.post("/projects/{project_id}/standards", status_code=201)
    def create_standard(project_id: int, body: StandardInput, authorization: str = Header(default="")):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        return add_definition(
            project_id,
            body,
            user,
            StandardDefinitionRecord,
            "standard",
            {"code": "", "name": "", "data_type": "", "expression": "", "description": "", "status": ""},
        )

    @router.get("/projects/{project_id}/standards")
    def list_standards(
        project_id: int,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
        authorization: str = Header(default=""),
    ):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        return list_definitions(
            project_id,
            user,
            StandardDefinitionRecord,
            ("code", "name", "data_type", "expression", "description", "status"),
            page,
            page_size,
        )

    @router.post("/projects/{project_id}/metrics", status_code=201)
    def create_metric(project_id: int, body: MetricInput, authorization: str = Header(default="")):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        return add_definition(
            project_id,
            body,
            user,
            SemanticMetricRecord,
            "metric",
            {"code": "", "name": "", "formula": "", "description": "", "status": ""},
        )

    @router.get("/projects/{project_id}/metrics")
    def list_metrics(
        project_id: int,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
        authorization: str = Header(default=""),
    ):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        return list_definitions(
            project_id,
            user,
            SemanticMetricRecord,
            ("code", "name", "formula", "description", "status"),
            page,
            page_size,
        )

    @router.get("/projects/{project_id}/audit")
    def list_audit(
        project_id: int,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=200),
        authorization: str = Header(default=""),
    ):
        user = authenticate(authorization)
        if isinstance(user, JSONResponse):
            return user
        with session_factory() as session:
            permitted = project_permission(session, project_id, user, Permission.VIEW_ALL)
            if isinstance(permitted, JSONResponse):
                return permitted
            query = select(AuditEventRecord).where(AuditEventRecord.project_id == project_id)
            total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
            rows = session.scalars(
                query.order_by(AuditEventRecord.generated_at.desc(), AuditEventRecord.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return {
                "code": 0,
                "msg": "success",
                "data": {
                    "total": total,
                    "list": [
                        {
                            "id": row.id,
                            "actor_id": row.actor_id,
                            "action": row.action,
                            "resource_type": row.resource_type,
                            "resource_id": row.resource_id,
                            "request_id": row.request_id,
                            "after": json.loads(row.after_json),
                            "generated_at": stamp(row.generated_at),
                        }
                        for row in rows
                    ],
                },
            }

    return router
