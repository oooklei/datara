"""Project-scoped governance API for the isolated rebuild backend."""

from __future__ import annotations

import json
import logging
from collections import deque
from datetime import datetime
from typing import Callable

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from rebuild.governance.models import (
    AssetFieldRecord,
    AssetRecord,
    AssetTagRecord,
    AuditEventRecord,
    GovernanceTagRecord,
    LineageEdgeRecord,
    QualityRuleRecord,
    QualityRunRecord,
    SemanticMetricRecord,
    StandardDefinitionRecord,
)
from rebuild.governance.service import GovernanceService
from rebuild.governance.legacy_migration_service import build_i18_legacy_dry_run
from rebuild.governance.legacy_source_reader import LegacyI18SourceReader
from rebuild.governance.snapshot_repository import LegacyI18TargetSnapshotRepository
from rebuild.identity.contracts import Permission
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


def build_governance_router(
    session_factory: sessionmaker[Session],
    current_user: Callable[[str], dict[str, object]],
    *,
    legacy_source_reader_factory: Callable[[], LegacyI18SourceReader] | None = None,
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
                                "fingerprint": entry.fingerprint,
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
