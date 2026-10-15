"""I1 身份 API 工厂，独立于旧 api/main.py。"""

from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from rebuild.common.db import Base
from rebuild.identity.contracts import Permission, Role, TokenService, authorize
from rebuild.identity.models import ProjectMemberRecord, UserRecord
from rebuild.identity.passwords import verify_password
from rebuild.datasource.contracts import DataSourceDraft, probe_datasource, validate_datasource
from rebuild.datasource.models import ProjectDatasourceRecord
from rebuild.datasource.metadata import metadata_catalog_for
from rebuild.datasource.pool import DatasourceEngineRegistry
from rebuild.datasource.repository import ProjectDatasourceRepository
from rebuild.project.repository import ProjectRepository
from rebuild.project.models import ProjectRecord
from rebuild.governance.api import build_governance_router

logger = logging.getLogger(__name__)


class LoginRequest(BaseModel):
    username: str
    password: str


class ProjectRequest(BaseModel):
    name: str
    description: str = ""


class DataSourceRequest(BaseModel):
    name: str
    kind: str
    host: str
    port: int
    database: str
    username: str
    password: str = ""
    probe: bool = False


class MemberRequest(BaseModel):
    username: str
    role: Role = Role.VIEWER


def create_app(
    database_url: str | None = None,
    *,
    token_secret: str | None = None,
    validation_key: str | None = None,
    legacy_i18_import_enabled: bool | None = None,
    legacy_i22_source_reader_factory=None,
    legacy_i23_source_reader_factory=None,
    legacy_i19_source_reader_factory=None,
    legacy_i20_source_reader_factory=None,
    legacy_i21_source_reader_factory=None,
) -> FastAPI:
    database_url = database_url or os.getenv("REBUILD_DB_URL")
    if not database_url:
        raise RuntimeError("REBUILD_DB_URL must be configured")
    token_secret = token_secret or os.getenv("REBUILD_TOKEN_SECRET")
    if not token_secret:
        raise RuntimeError("REBUILD_TOKEN_SECRET must be configured")
    validation_key = validation_key if validation_key is not None else os.getenv("REBUILD_VALIDATION_KEY")
    if legacy_i18_import_enabled is None:
        legacy_i18_import_enabled = os.getenv("REBUILD_LEGACY_I18_IMPORT_ENABLED", "false").strip().lower() in {
            "1",
            "true",
        }
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    pool_args = {"poolclass": StaticPool} if database_url.endswith(":memory:") else {}
    engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True, **pool_args)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    token_service = TokenService(secret=token_secret)
    validation_token_service = TokenService(secret=token_secret, ttl_seconds=900)
    active_tokens: set[str] = set()
    datasource_engines = DatasourceEngineRegistry()

    def ensure_i1_schema() -> None:
        """Apply additive I1 columns to the dedicated schema without touching legacy tables."""
        inspector = inspect(engine)
        with engine.begin() as connection:
            if "rebuild_user" in inspector.get_table_names():
                columns = {column["name"] for column in inspector.get_columns("rebuild_user")}
                for column in ("created_at", "updated_at"):
                    if column not in columns:
                        connection.execute(text(f"ALTER TABLE rebuild_user ADD COLUMN {column} DATETIME NULL"))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # I1 core tables only. R3 governance DDL is applied exclusively by its
        # versioned MigrationRunner after the R3-S7 remote gate.
        Base.metadata.create_all(
            engine,
            tables=[
                UserRecord.__table__,
                ProjectRecord.__table__,
                ProjectMemberRecord.__table__,
                ProjectDatasourceRecord.__table__,
            ],
        )
        ensure_i1_schema()
        yield
        datasource_engines.dispose_all()
        engine.dispose()

    app = FastAPI(title="Datara Rebuild API", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = session_factory
    app.state.datasource_engines = datasource_engines

    def pooled_connector(project_id: int, datasource_id: int):
        return lambda draft: datasource_engines.connect(project_id, datasource_id, draft)

    @app.get("/api/v1/rebuild/health")
    def health() -> dict[str, object]:
        return {"code": 0, "msg": "success", "data": {"service": "rebuild-api", "status": "ok"}}

    @app.get("/api/v1/rebuild/i2/status")
    def i2_status(authorization: str = Header(default="")):
        """Expose the latest I2 data-base evidence to the isolated validation page."""
        try:
            current_user(authorization)
        except ValueError:
            return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})
        report_path = Path(os.getenv("I2_RECONCILE_PATH", "/datara/logs/datagen/reconcile.json"))
        if not report_path.is_file():
            return JSONResponse(
                status_code=404,
                content={"code": 4042, "msg": "I2 reconcile report not found", "data": None},
            )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        samples_dir = Path(os.getenv("I2_SAMPLES_PATH", "/datara/files/samples"))
        data = {
            "generated_at": report.get("generated_at"),
            "mode": report.get("mode"),
            "seed": report.get("seed"),
            "summary": report.get("summary", {}),
            "databases": sorted(report.get("databases", {}).keys()),
            "samples": sorted(path.name for path in samples_dir.glob("orders_part.*")) if samples_dir.is_dir() else [],
        }
        return {"code": 0, "msg": "success", "data": data}

    @app.post("/api/v1/rebuild/login")
    def login(body: LoginRequest):
        with session_factory() as session:
            record = session.scalar(select(UserRecord).where(UserRecord.username == body.username))
            if record is None or not verify_password(body.password, record.password_hash):
                return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid credentials", "data": None})
            token = token_service.issue(user_id=record.id, username=record.username, role=Role(record.role))
            active_tokens.add(token)
            return {
                "code": 0,
                "msg": "success",
                "data": {"token": token, "user": {"id": record.id, "username": record.username, "role": record.role}},
            }

    @app.post("/api/v1/rebuild/validation-token")
    def validation_token(x_backend_validation_key: str = Header(default="")):
        """Exchange a server-held validation key for a short-lived test-runner token."""
        if not validation_key:
            return JSONResponse(
                status_code=404,
                content={"code": 4043, "msg": "validation bootstrap disabled", "data": None},
            )
        if not hmac.compare_digest(x_backend_validation_key, validation_key):
            return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid validation key", "data": None})
        token = validation_token_service.issue(user_id=0, username="validation-runner", role=Role.DEV)
        active_tokens.add(token)
        return {
            "code": 0,
            "msg": "success",
            "data": {"token": token, "user": {"id": 0, "username": "validation-runner", "role": Role.DEV.value}},
        }

    @app.post("/api/v1/rebuild/validation-capabilities/legacy-i23-preview")
    def issue_i23_preview_capability(x_backend_validation_key: str = Header(default="")):
        """Exchange the protected runner key for an I23-preview-only token."""
        if not validation_key:
            return JSONResponse(
                status_code=404,
                content={"code": 4043, "msg": "validation bootstrap disabled", "data": None},
            )
        if not hmac.compare_digest(x_backend_validation_key, validation_key):
            return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid validation key", "data": None})
        token = validation_token_service.issue(
            user_id=0,
            username="i23-preview-runner",
            role=Role.VIEWER,
            capability="legacy:i23:preview",
        )
        active_tokens.add(token)
        return {
            "code": 0,
            "msg": "success",
            "data": {"token": token, "capability": "legacy:i23:preview", "expires_in": 900},
        }

    def current_user(authorization: str) -> dict[str, object]:
        if not authorization.startswith("Bearer "):
            raise ValueError("missing bearer token")
        token = authorization[7:]
        if token not in active_tokens:
            raise ValueError("token revoked or unknown")
        claims = token_service.verify(token)
        if "capability" in claims:
            raise ValueError("scoped capability is not valid for ordinary API routes")
        return claims

    def project_permission_error(session, project_id: int, user: dict[str, object], permission: Permission):
        project = session.get(ProjectRecord, project_id)
        if project is None:
            return JSONResponse(status_code=404, content={"code": 4041, "msg": "project not found", "data": None})
        if user.get("role") == Role.ADMIN.value:
            return None
        if not authorize(user.get("role", ""), permission):
            return JSONResponse(status_code=403, content={"code": 1003, "msg": "permission denied", "data": None})
        user_id = int(user["user_id"])
        if project.owner_id == user_id:
            return None
        member = session.scalar(
            select(ProjectMemberRecord).where(
                ProjectMemberRecord.project_id == project_id,
                ProjectMemberRecord.user_id == user_id,
            )
        )
        if member is None or not authorize(member.role, permission):
            return JSONResponse(status_code=403, content={"code": 1003, "msg": "permission denied", "data": None})
        return None

    def datasource_payload(record: ProjectDatasourceRecord) -> dict[str, object]:
        return {
            "id": record.id,
            "project_id": record.project_id,
            "name": record.name,
            "kind": record.kind,
            "host": record.host,
            "port": record.port,
            "database": record.database_name,
            "username": record.username,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }

    def datasource_draft(record: ProjectDatasourceRecord) -> DataSourceDraft:
        return DataSourceDraft(
            name=record.name,
            kind=record.kind,
            host=record.host,
            port=record.port,
            database=record.database_name,
            username=record.username,
            password=record.password,
        )

    def current_i23_preview_capability(authorization: str) -> dict[str, object]:
        if not authorization.startswith("Bearer "):
            raise ValueError("missing bearer token")
        token = authorization[7:]
        if token not in active_tokens:
            raise ValueError("token revoked or unknown")
        claims = validation_token_service.verify(token)
        if claims.get("capability") != "legacy:i23:preview":
            raise PermissionError("I23 preview capability required")
        return claims

    @app.post("/api/v1/rebuild/logout")
    def logout(authorization: str = Header(default="")):
        if authorization.startswith("Bearer "):
            active_tokens.discard(authorization[7:])
        return {"code": 0, "msg": "success", "data": None}

    @app.post("/api/v1/rebuild/projects")
    def create_project(body: ProjectRequest, authorization: str = Header(default="")):
        try:
            user = current_user(authorization)
        except ValueError:
            return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})
        with session_factory() as session:
            project = ProjectRepository(session).create(
                name=body.name, description=body.description, owner_id=int(user["user_id"])
            )
            session.commit()
            return {"code": 0, "msg": "success", "data": {"id": project.id, "name": project.name}}

    @app.get("/api/v1/rebuild/projects")
    def list_projects(authorization: str = Header(default="")):
        try:
            user = current_user(authorization)
        except ValueError:
            return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})
        with session_factory() as session:
            projects = ProjectRepository(session).list_for_user(int(user["user_id"]))
            return {
                "code": 0,
                "msg": "success",
                "data": {"total": len(projects), "list": [{"id": p.id, "name": p.name} for p in projects]},
            }

    @app.post("/api/v1/rebuild/datasources/validate")
    def validate_datasource_endpoint(body: DataSourceRequest, authorization: str = Header(default="")):
        try:
            current_user(authorization)
            if body.probe:
                return JSONResponse(
                    status_code=400,
                    content={
                        "code": 4002,
                        "msg": "register a project datasource before testing its connection",
                        "data": None,
                    },
                )
            draft = DataSourceDraft(**body.model_dump(exclude={"probe"}))
            result = validate_datasource(draft)
        except ValueError as exc:
            code = 1001 if "token" in str(exc) else 4001
            status = 401 if code == 1001 else 400
            return JSONResponse(status_code=status, content={"code": code, "msg": str(exc), "data": None})
        if body.probe:
            return {"code": 0, "msg": "success", "data": result}
        return {
            "code": 0,
            "msg": "success",
            "data": {"name": result.draft.name, "kind": result.draft.kind, "capabilities": sorted(result.capabilities)},
        }

    @app.post("/api/v1/rebuild/datasources/profiles/{profile_id}/probe")
    def probe_datasource_profile(profile_id: str, authorization: str = Header(default="")):
        try:
            user = current_user(authorization)
        except ValueError:
            return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})
        if user.get("role") != Role.ADMIN.value:
            return JSONResponse(status_code=403, content={"code": 1003, "msg": "permission denied", "data": None})
        if profile_id != "mysql-src":
            return JSONResponse(
                status_code=404,
                content={"code": 4041, "msg": "datasource profile not found", "data": None},
            )
        connection_url = os.getenv("REBUILD_MYSQL_SRC_URL", "")
        if not connection_url:
            return JSONResponse(
                status_code=503,
                content={"code": 5031, "msg": "mysql-src runtime profile is not configured", "data": None},
            )
        try:
            parsed = make_url(connection_url)
            if parsed.get_backend_name() != "mysql" or not parsed.host or not parsed.database or not parsed.username:
                raise ValueError("invalid mysql-src profile")
            draft = DataSourceDraft(
                name="mysql-src",
                kind="mysql",
                host=parsed.host,
                port=parsed.port or 3306,
                database=parsed.database,
                username=parsed.username,
                password=parsed.password or "",
            )
            result = probe_datasource(draft)
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": str(exc), "data": None})
        return {"code": 0, "msg": "success", "data": result}

    @app.get("/api/v1/rebuild/projects/{project_id}/datasources")
    def list_project_datasources(project_id: int, authorization: str = Header(default="")):
        try:
            user = current_user(authorization)
        except ValueError:
            return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})
        with session_factory() as session:
            denied = project_permission_error(session, project_id, user, Permission.VIEW_ALL)
            if denied is not None:
                return denied
            records = ProjectDatasourceRepository(session).list_for_project(project_id)
            return {"code": 0, "msg": "success", "data": {"items": [datasource_payload(r) for r in records]}}

    @app.post("/api/v1/rebuild/projects/{project_id}/datasources", status_code=201)
    def create_project_datasource(project_id: int, body: DataSourceRequest, authorization: str = Header(default="")):
        try:
            user = current_user(authorization)
            draft = DataSourceDraft(**body.model_dump(exclude={"probe"}))
            validate_datasource(draft)
        except ValueError as exc:
            if "token" in str(exc):
                return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})
            return JSONResponse(status_code=400, content={"code": 4001, "msg": str(exc), "data": None})
        with session_factory() as session:
            denied = project_permission_error(session, project_id, user, Permission.EDIT_DEFINITION)
            if denied is not None:
                return denied
            repository = ProjectDatasourceRepository(session)
            try:
                record = repository.create(project_id, draft)
                session.commit()
            except IntegrityError:
                session.rollback()
                return JSONResponse(
                    status_code=409,
                    content={"code": 4091, "msg": "datasource name already exists in project", "data": None},
                )
            return JSONResponse(
                status_code=201, content={"code": 0, "msg": "success", "data": datasource_payload(record)}
            )

    @app.get("/api/v1/rebuild/projects/{project_id}/datasources/{datasource_id}")
    def get_project_datasource(project_id: int, datasource_id: int, authorization: str = Header(default="")):
        try:
            user = current_user(authorization)
        except ValueError:
            return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})
        with session_factory() as session:
            denied = project_permission_error(session, project_id, user, Permission.VIEW_ALL)
            if denied is not None:
                return denied
            record = ProjectDatasourceRepository(session).get(project_id, datasource_id)
            if record is None:
                return JSONResponse(
                    status_code=404, content={"code": 4042, "msg": "datasource not found", "data": None}
                )
            return {"code": 0, "msg": "success", "data": datasource_payload(record)}

    @app.put("/api/v1/rebuild/projects/{project_id}/datasources/{datasource_id}")
    def update_project_datasource(
        project_id: int, datasource_id: int, body: DataSourceRequest, authorization: str = Header(default="")
    ):
        try:
            user = current_user(authorization)
            draft = DataSourceDraft(**body.model_dump(exclude={"probe"}))
            validate_datasource(draft)
        except ValueError as exc:
            if "token" in str(exc):
                return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})
            return JSONResponse(status_code=400, content={"code": 4001, "msg": str(exc), "data": None})
        with session_factory() as session:
            denied = project_permission_error(session, project_id, user, Permission.EDIT_DEFINITION)
            if denied is not None:
                return denied
            repository = ProjectDatasourceRepository(session)
            record = repository.get(project_id, datasource_id)
            if record is None:
                return JSONResponse(
                    status_code=404, content={"code": 4042, "msg": "datasource not found", "data": None}
                )
            repository.update(record, draft)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return JSONResponse(
                    status_code=409,
                    content={"code": 4091, "msg": "datasource name already exists in project", "data": None},
                )
            datasource_engines.invalidate(project_id, datasource_id)
            return {"code": 0, "msg": "success", "data": datasource_payload(record)}

    @app.delete("/api/v1/rebuild/projects/{project_id}/datasources/{datasource_id}")
    def delete_project_datasource(project_id: int, datasource_id: int, authorization: str = Header(default="")):
        try:
            user = current_user(authorization)
        except ValueError:
            return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})
        with session_factory() as session:
            denied = project_permission_error(session, project_id, user, Permission.EDIT_DEFINITION)
            if denied is not None:
                return denied
            repository = ProjectDatasourceRepository(session)
            record = repository.get(project_id, datasource_id)
            if record is None:
                return JSONResponse(
                    status_code=404, content={"code": 4042, "msg": "datasource not found", "data": None}
                )
            repository.delete(record)
            session.commit()
            datasource_engines.invalidate(project_id, datasource_id)
            return {"code": 0, "msg": "success", "data": {"deleted": True, "id": datasource_id}}

    @app.post("/api/v1/rebuild/projects/{project_id}/datasources/{datasource_id}/test")
    def test_project_datasource(project_id: int, datasource_id: int, authorization: str = Header(default="")):
        try:
            user = current_user(authorization)
        except ValueError:
            return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})
        with session_factory() as session:
            denied = project_permission_error(session, project_id, user, Permission.EDIT_DEFINITION)
            if denied is not None:
                return denied
            record = ProjectDatasourceRepository(session).get(project_id, datasource_id)
            if record is None:
                return JSONResponse(
                    status_code=404, content={"code": 4042, "msg": "datasource not found", "data": None}
                )
            draft = DataSourceDraft(
                name=record.name,
                kind=record.kind,
                host=record.host,
                port=record.port,
                database=record.database_name,
                username=record.username,
                password=record.password,
            )
        try:
            result = probe_datasource(draft, connector=pooled_connector(project_id, datasource_id))
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": str(exc), "data": None})
        except Exception:
            return JSONResponse(
                status_code=502,
                content={"code": 5021, "msg": "datasource connection test failed", "data": None},
            )
        return {"code": 0, "msg": "success", "data": result}

    @app.get("/api/v1/rebuild/projects/{project_id}/datasources/{datasource_id}/schemas")
    def browse_datasource_schemas(
        project_id: int,
        datasource_id: int,
        after: str | None = None,
        limit: int = Query(default=100, ge=1, le=200),
        authorization: str = Header(default=""),
    ):
        try:
            user = current_user(authorization)
        except ValueError:
            return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})
        with session_factory() as session:
            denied = project_permission_error(session, project_id, user, Permission.VIEW_ALL)
            if denied is not None:
                return denied
            record = ProjectDatasourceRepository(session).get(project_id, datasource_id)
            if record is None:
                return JSONResponse(
                    status_code=404,
                    content={"code": 4042, "msg": "datasource not found", "data": None},
                )
            draft = datasource_draft(record)
        try:
            rows = metadata_catalog_for(draft, connector=pooled_connector(project_id, datasource_id)).schemas(
                after=after, limit=limit
            )
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": str(exc), "data": None})
        except Exception as exc:
            logger.warning(
                "metadata_browse_failed operation=schemas exception_type=%s sqlstate=%s",
                type(exc).__name__,
                getattr(exc, "sqlstate", None) or "-",
            )
            return JSONResponse(status_code=502, content={"code": 5022, "msg": "metadata browse failed", "data": None})
        items = rows[:limit]
        return {
            "code": 0,
            "msg": "success",
            "data": {"items": items, "next_after": items[-1] if len(rows) > limit else None, "limit": limit},
        }

    @app.get("/api/v1/rebuild/projects/{project_id}/datasources/{datasource_id}/objects")
    def browse_datasource_objects(
        project_id: int,
        datasource_id: int,
        schema: str = Query(min_length=1, max_length=255),
        after: str | None = Query(default=None, max_length=255),
        limit: int = Query(default=100, ge=1, le=200),
        authorization: str = Header(default=""),
    ):
        try:
            user = current_user(authorization)
        except ValueError:
            return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})
        with session_factory() as session:
            denied = project_permission_error(session, project_id, user, Permission.VIEW_ALL)
            if denied is not None:
                return denied
            record = ProjectDatasourceRepository(session).get(project_id, datasource_id)
            if record is None:
                return JSONResponse(
                    status_code=404,
                    content={"code": 4042, "msg": "datasource not found", "data": None},
                )
            draft = datasource_draft(record)
        try:
            rows = metadata_catalog_for(draft, connector=pooled_connector(project_id, datasource_id)).objects(
                schema, after=after, limit=limit
            )
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": str(exc), "data": None})
        except Exception as exc:
            logger.warning(
                "metadata_browse_failed operation=objects exception_type=%s sqlstate=%s",
                type(exc).__name__,
                getattr(exc, "sqlstate", None) or "-",
            )
            return JSONResponse(status_code=502, content={"code": 5022, "msg": "metadata browse failed", "data": None})
        items = rows[:limit]
        return {
            "code": 0,
            "msg": "success",
            "data": {
                "items": items,
                "next_after": items[-1]["name"] if len(rows) > limit else None,
                "limit": limit,
            },
        }

    @app.get("/api/v1/rebuild/projects/{project_id}/datasources/{datasource_id}/columns")
    def browse_datasource_columns(
        project_id: int,
        datasource_id: int,
        schema: str = Query(min_length=1, max_length=255),
        object_name: str = Query(min_length=1, max_length=255),
        limit: int = Query(default=200, ge=1, le=500),
        authorization: str = Header(default=""),
    ):
        try:
            user = current_user(authorization)
        except ValueError:
            return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})
        with session_factory() as session:
            denied = project_permission_error(session, project_id, user, Permission.VIEW_ALL)
            if denied is not None:
                return denied
            record = ProjectDatasourceRepository(session).get(project_id, datasource_id)
            if record is None:
                return JSONResponse(
                    status_code=404,
                    content={"code": 4042, "msg": "datasource not found", "data": None},
                )
            draft = datasource_draft(record)
        try:
            rows = metadata_catalog_for(draft, connector=pooled_connector(project_id, datasource_id)).columns(
                schema, object_name, limit=limit
            )
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": str(exc), "data": None})
        except Exception as exc:
            logger.warning(
                "metadata_browse_failed operation=columns exception_type=%s sqlstate=%s",
                type(exc).__name__,
                getattr(exc, "sqlstate", None) or "-",
            )
            return JSONResponse(status_code=502, content={"code": 5022, "msg": "metadata browse failed", "data": None})
        return {
            "code": 0,
            "msg": "success",
            "data": {"items": rows[:limit], "truncated": len(rows) > limit, "limit": limit},
        }

    app.include_router(
        build_governance_router(
            session_factory,
            current_user,
            legacy_i18_import_enabled=legacy_i18_import_enabled,
            legacy_i22_source_reader_factory=legacy_i22_source_reader_factory,
            legacy_i23_source_reader_factory=legacy_i23_source_reader_factory,
            legacy_i19_source_reader_factory=legacy_i19_source_reader_factory,
            legacy_i20_source_reader_factory=legacy_i20_source_reader_factory,
            legacy_i21_source_reader_factory=legacy_i21_source_reader_factory,
            legacy_i23_preview_user=current_i23_preview_capability,
        )
    )

    @app.post("/api/v1/rebuild/projects/{project_id}/members")
    def add_member(project_id: int, body: MemberRequest, authorization: str = Header(default="")):
        try:
            user = current_user(authorization)
            if not authorize(user["role"], Permission.MANAGE_USER):
                raise PermissionError("permission denied")
        except PermissionError as exc:
            return JSONResponse(status_code=403, content={"code": 1003, "msg": str(exc), "data": None})
        except ValueError:
            return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})
        with session_factory() as session:
            target = session.scalar(select(UserRecord).where(UserRecord.username == body.username))
            if target is None:
                return JSONResponse(status_code=404, content={"code": 4041, "msg": "user not found", "data": None})
            member = ProjectMemberRecord(project_id=project_id, user_id=target.id, role=body.role.value)
            session.add(member)
            session.commit()
            return {
                "code": 0,
                "msg": "success",
                "data": {"project_id": project_id, "username": body.username, "role": body.role.value},
            }

    return app
