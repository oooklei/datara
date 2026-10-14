"""I1 身份 API 工厂，独立于旧 api/main.py。"""

from __future__ import annotations

from contextlib import asynccontextmanager
import hmac
import json
import os
from pathlib import Path

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from rebuild.common.db import Base
from rebuild.identity.contracts import Permission, Role, TokenService, authorize
from rebuild.identity.models import ProjectMemberRecord, UserRecord
from rebuild.identity.passwords import verify_password
from rebuild.datasource.contracts import DataSourceDraft, probe_datasource, validate_datasource
from rebuild.project.repository import ProjectRepository
from rebuild.project.models import ProjectRecord
from rebuild.governance.api import build_governance_router


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
            tables=[UserRecord.__table__, ProjectRecord.__table__, ProjectMemberRecord.__table__],
        )
        ensure_i1_schema()
        yield
        engine.dispose()

    app = FastAPI(title="Datara Rebuild API", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = session_factory

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
            draft = DataSourceDraft(**body.model_dump(exclude={"probe"}))
            result = probe_datasource(draft) if body.probe else validate_datasource(draft)
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
            current_user(authorization)
        except ValueError:
            return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})
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

    app.include_router(
        build_governance_router(
            session_factory,
            current_user,
            legacy_i18_import_enabled=legacy_i18_import_enabled,
            legacy_i22_source_reader_factory=legacy_i22_source_reader_factory,
            legacy_i23_source_reader_factory=legacy_i23_source_reader_factory,
            legacy_i19_source_reader_factory=legacy_i19_source_reader_factory,
            legacy_i20_source_reader_factory=legacy_i20_source_reader_factory,
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
