"""Project-scoped dbx read/query gateway with datara owner filtering."""

from __future__ import annotations

from collections.abc import Callable
from uuid import uuid4

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

from rebuild.dbx import DbxClient, DbxError
from rebuild.dbx.access import DbxConnectionAccess, DbxObjectAccess
from rebuild.dbx.models import DbxConnectionOwnershipRecord, DbxConnectionShareRecord, DbxObjectShareRecord
from rebuild.identity.contracts import Permission, Role
from rebuild.identity.models import UserRecord


class ClaimRequest(BaseModel):
    owner_id: int | None = None
    username: str | None = None


class ShareRequest(BaseModel):
    user_id: int | None = None
    username: str | None = None


class ExecuteRequest(BaseModel):
    connection_id: str
    database: str
    sql: str
    schema_name: str | None = None
    max_rows: int | None = None


class ConnectionDraft(BaseModel):
    name: str
    db_type: str
    host: str
    port: int
    database: str
    username: str
    password: str | None = None


_PUBLIC_CONNECTION_FIELDS = ("id", "name", "db_type", "host", "port", "database", "username")


def build_dbx_router(
    session_factory: sessionmaker,
    current_user: Callable[[str], dict[str, object]],
    project_permission_error: Callable[..., JSONResponse | None],
    *,
    client_factory: Callable[[], DbxClient] = DbxClient,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/rebuild/dbx/projects/{project_id}", tags=["rebuild-dbx"])

    def context(project_id: int, authorization: str, permission: Permission):
        try:
            user = current_user(authorization)
        except ValueError:
            return JSONResponse(status_code=401, content={"code": 1001, "msg": "invalid token", "data": None})
        with session_factory() as session:
            denial = project_permission_error(session, project_id, user, permission)
        return denial if denial is not None else user

    def upstream_error(exc: DbxError) -> JSONResponse:
        status = 503 if exc.status == 503 else 502
        return JSONResponse(status_code=status, content={"code": status, "msg": "dbx unavailable", "data": None})

    def visible_ids(project_id: int, user: dict[str, object]) -> set[str]:
        with session_factory() as session:
            return DbxConnectionAccess(session).visible_ids(
                project_id=project_id,
                user_id=int(user["user_id"]),
                is_admin=user.get("role") == Role.ADMIN.value,
            )

    def require_connection(project_id: int, connection_id: str, user: dict[str, object]) -> JSONResponse | None:
        if connection_id in visible_ids(project_id, user):
            return None
        if user.get("role") == Role.ADMIN.value:
            try:
                if any(str(item.get("id")) == connection_id for item in client_factory().list_connections()):
                    return None
            except DbxError as exc:
                return upstream_error(exc)
        return JSONResponse(status_code=403, content={"code": 1003, "msg": "connection not shared", "data": None})

    @router.get("/connections")
    def list_connections(project_id: int, authorization: str = Header(default="")):
        user = context(project_id, authorization, Permission.DATASOURCE_READ)
        if isinstance(user, JSONResponse):
            return user
        try:
            remote = client_factory().list_connections()
        except DbxError as exc:
            return upstream_error(exc)
        ids = visible_ids(project_id, user)
        admin = user.get("role") == Role.ADMIN.value
        with session_factory() as session:
            ownership = {
                record.connection_id: record
                for record in session.scalars(
                    select(DbxConnectionOwnershipRecord).where(DbxConnectionOwnershipRecord.project_id == project_id)
                )
            }
            managed_ids = {
                connection_id for connection_id, record in ownership.items()
                if admin or record.owner_id == int(user["user_id"])
            }
        items = [
            {**{field: item.get(field) for field in _PUBLIC_CONNECTION_FIELDS if field in item},
             "can_manage": str(item.get("id")) in managed_ids,
             "can_claim": admin and str(item.get("id")) not in ownership}
            for item in remote if admin or str(item.get("id")) in ids
        ]
        return {"code": 0, "msg": "success", "data": {"items": items}}

    @router.post("/connections/{connection_id}/claim")
    def claim_connection(project_id: int, connection_id: str, body: ClaimRequest, authorization: str = Header(default="")):
        user = context(project_id, authorization, Permission.DATASOURCE_MANAGE)
        if isinstance(user, JSONResponse):
            return user
        if user.get("role") != Role.ADMIN.value:
            return JSONResponse(status_code=403, content={"code": 1003, "msg": "admin required", "data": None})
        try:
            if not any(str(item.get("id")) == connection_id for item in client_factory().list_connections()):
                return JSONResponse(status_code=404, content={"code": 4042, "msg": "connection not found", "data": None})
        except DbxError as exc:
            return upstream_error(exc)
        with session_factory() as session:
            if (body.owner_id is None) == (body.username is None):
                return JSONResponse(status_code=400, content={"code": 4001, "msg": "one owner required", "data": None})
            target = (
                session.get(UserRecord, body.owner_id)
                if body.owner_id is not None else
                session.scalar(select(UserRecord).where(UserRecord.username == body.username))
            )
            if target is None:
                return JSONResponse(status_code=404, content={"code": 4043, "msg": "owner not found", "data": None})
            target_id = target.id
            try:
                DbxConnectionAccess(session).claim(connection_id=connection_id, project_id=project_id, owner_id=target_id)
            except (PermissionError, ValueError):
                return JSONResponse(status_code=409, content={"code": 4091, "msg": "connection already claimed", "data": None})
            session.commit()
        return {"code": 0, "msg": "success", "data": {"connection_id": connection_id, "owner_id": target_id}}

    @router.post("/connections")
    def create_connection(project_id: int, body: ConnectionDraft, authorization: str = Header(default="")):
        user = context(project_id, authorization, Permission.DATASOURCE_MANAGE)
        if isinstance(user, JSONResponse):
            return user
        if not all((body.name.strip(), body.db_type.strip(), body.host.strip(), body.database.strip(), body.username.strip())) or not 1 <= body.port <= 65535:
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "invalid connection", "data": None})
        connection_id = f"datara-{uuid4().hex}"
        config = body.model_dump(exclude_none=True)
        config["id"] = connection_id
        try:
            client_factory().save_connection(config)
        except DbxError as exc:
            return upstream_error(exc)
        with session_factory() as session:
            DbxConnectionAccess(session).claim(connection_id=connection_id, project_id=project_id, owner_id=int(user["user_id"]))
            session.commit()
        return {"code": 0, "msg": "success", "data": {"connection_id": connection_id}}

    def require_manager(project_id: int, connection_id: str, user: dict[str, object]) -> JSONResponse | None:
        with session_factory() as session:
            owner = session.get(DbxConnectionOwnershipRecord, connection_id)
            if owner is not None and owner.project_id == project_id and (owner.owner_id == int(user["user_id"]) or user.get("role") == Role.ADMIN.value):
                return None
        return JSONResponse(status_code=403, content={"code": 1003, "msg": "connection owner required", "data": None})

    @router.put("/connections/{connection_id}")
    def update_connection(project_id: int, connection_id: str, body: ConnectionDraft, authorization: str = Header(default="")):
        user = context(project_id, authorization, Permission.DATASOURCE_MANAGE)
        if isinstance(user, JSONResponse):
            return user
        denial = require_manager(project_id, connection_id, user)
        if denial is not None:
            return denial
        try:
            current = next((item for item in client_factory().list_connections() if str(item.get("id")) == connection_id), None)
            if current is None:
                return JSONResponse(status_code=404, content={"code": 4042, "msg": "connection not found", "data": None})
            config = dict(current)
            config.update(body.model_dump(exclude_none=True))
            config["id"] = connection_id
            # DBX 0.6.60 expects a complete ConnectionConfig on save. An empty
            # password in Datara's edit form means keep the server-held secret.
            if not body.password:
                config["password"] = current.get("password", "")
            client_factory().save_connection(config)
        except DbxError as exc:
            return upstream_error(exc)
        return {"code": 0, "msg": "success", "data": {"connection_id": connection_id}}

    @router.post("/connections/{connection_id}/test")
    def test_connection(project_id: int, connection_id: str, authorization: str = Header(default="")):
        user = context(project_id, authorization, Permission.DATASOURCE_READ)
        if isinstance(user, JSONResponse):
            return user
        denial = require_connection(project_id, connection_id, user)
        if denial is not None:
            return denial
        try:
            dbx = client_factory()
            config = next((item for item in dbx.list_connections() if str(item.get("id")) == connection_id), None)
            if config is None:
                return JSONResponse(status_code=404, content={"code": 4042, "msg": "connection not found", "data": None})
            result = dbx.test_connection(config)
        except DbxError as exc:
            return upstream_error(exc)
        return {"code": 0, "msg": "success", "data": result}

    @router.delete("/connections/{connection_id}")
    def delete_connection(project_id: int, connection_id: str, authorization: str = Header(default="")):
        user = context(project_id, authorization, Permission.DATASOURCE_MANAGE)
        if isinstance(user, JSONResponse):
            return user
        denial = require_manager(project_id, connection_id, user)
        if denial is not None:
            return denial
        try:
            client_factory().remove_connection(connection_id)
        except DbxError as exc:
            return upstream_error(exc)
        with session_factory() as session:
            session.execute(delete(DbxConnectionShareRecord).where(DbxConnectionShareRecord.connection_id == connection_id))
            session.execute(delete(DbxConnectionOwnershipRecord).where(DbxConnectionOwnershipRecord.connection_id == connection_id))
            session.commit()
        return {"code": 0, "msg": "success", "data": {"connection_id": connection_id}}

    @router.post("/connections/{connection_id}/share")
    def share_connection(project_id: int, connection_id: str, body: ShareRequest, authorization: str = Header(default="")):
        user = context(project_id, authorization, Permission.DATASOURCE_MANAGE)
        if isinstance(user, JSONResponse):
            return user
        with session_factory() as session:
            if (body.user_id is None) == (body.username is None):
                return JSONResponse(status_code=400, content={"code": 4001, "msg": "one recipient required", "data": None})
            target = (
                session.get(UserRecord, body.user_id)
                if body.user_id is not None else
                session.scalar(select(UserRecord).where(UserRecord.username == body.username))
            )
            if target is None:
                return JSONResponse(status_code=404, content={"code": 4043, "msg": "user not found", "data": None})
            access = DbxConnectionAccess(session)
            owner = session.get(DbxConnectionOwnershipRecord, connection_id)
            if owner is None or owner.project_id != project_id or (owner.owner_id != int(user["user_id"]) and user.get("role") != Role.ADMIN.value):
                return JSONResponse(status_code=403, content={"code": 1003, "msg": "owner required", "data": None})
            target_id = target.id
            access.share(connection_id=connection_id, owner_id=owner.owner_id, user_id=target_id)
            session.commit()
        return {"code": 0, "msg": "success", "data": {"connection_id": connection_id, "user_id": target_id}}

    @router.get("/connections/{connection_id}/shares")
    def list_connection_shares(project_id: int, connection_id: str, authorization: str = Header(default="")):
        user = context(project_id, authorization, Permission.DATASOURCE_MANAGE)
        if isinstance(user, JSONResponse):
            return user
        denial = require_manager(project_id, connection_id, user)
        if denial is not None:
            return denial
        with session_factory() as session:
            rows = session.execute(
                select(DbxConnectionShareRecord.user_id, UserRecord.username)
                .join(UserRecord, UserRecord.id == DbxConnectionShareRecord.user_id)
                .where(DbxConnectionShareRecord.connection_id == connection_id)
                .order_by(UserRecord.username)
            ).all()
        return {"code": 0, "msg": "success", "data": {"items": [
            {"user_id": user_id, "username": username} for user_id, username in rows
        ]}}

    @router.delete("/connections/{connection_id}/shares/{user_id}")
    def unshare_connection(project_id: int, connection_id: str, user_id: int, authorization: str = Header(default="")):
        user = context(project_id, authorization, Permission.DATASOURCE_MANAGE)
        if isinstance(user, JSONResponse):
            return user
        denial = require_manager(project_id, connection_id, user)
        if denial is not None:
            return denial
        with session_factory() as session:
            owner = session.get(DbxConnectionOwnershipRecord, connection_id)
            if owner is None:
                return JSONResponse(status_code=404, content={"code": 4042, "msg": "connection not found", "data": None})
            DbxConnectionAccess(session).unshare(
                connection_id=connection_id, owner_id=owner.owner_id, user_id=user_id,
            )
            session.commit()
        return {"code": 0, "msg": "success", "data": {"connection_id": connection_id, "user_id": user_id}}

    def object_owner(project_id: int, kind: str, object_id: str, user: dict[str, object]):
        if kind not in {"sql-file", "sql-folder", "ai-conversation", "ai-config", "prompt-template"}:
            return JSONResponse(status_code=404, content={"code": 4042, "msg": "object type not found", "data": None})
        with session_factory() as session:
            owner = DbxObjectAccess(session).get(kind, object_id)
            if owner is None or owner.project_id != project_id:
                return JSONResponse(status_code=404, content={"code": 4042, "msg": "object not found", "data": None})
            if owner.owner_id != int(user["user_id"]) and user.get("role") != Role.ADMIN.value:
                return JSONResponse(status_code=403, content={"code": 1003, "msg": "object owner required", "data": None})
            return owner.owner_id

    @router.post("/objects/{kind}/{object_id}/claim")
    def claim_object(project_id: int, kind: str, object_id: str, body: ClaimRequest, authorization: str = Header(default="")):
        user = context(project_id, authorization, Permission.DATASOURCE_MANAGE)
        if isinstance(user, JSONResponse):
            return user
        if user.get("role") != Role.ADMIN.value:
            return JSONResponse(status_code=403, content={"code": 1003, "msg": "admin required", "data": None})
        if kind not in {"sql-file", "sql-folder", "ai-conversation", "ai-config", "prompt-template"}:
            return JSONResponse(status_code=404, content={"code": 4042, "msg": "object type not found", "data": None})
        if (body.owner_id is None) == (body.username is None):
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "one owner required", "data": None})
        try:
            library = client_factory()._request(
                "GET", "ai/configs" if kind == "ai-config" else
                "ai/conversations" if kind == "ai-conversation" else
                "prompt-templates" if kind == "prompt-template" else "saved-sql",
            )
        except DbxError as exc:
            return upstream_error(exc)
        group = library if kind in {"ai-conversation", "ai-config", "prompt-template"} and isinstance(library, list) else (
            library.get("folders" if kind == "sql-folder" else "files", []) if isinstance(library, dict) else []
        )
        item = next((row for row in group if isinstance(row, dict) and row.get("id") == object_id), None)
        if item is None or (kind not in {"ai-config", "prompt-template"} and not isinstance(item.get("connectionId"), str)):
            return JSONResponse(status_code=404, content={"code": 4042, "msg": "DBX object not found", "data": None})
        connection_id = item.get("connectionId") if kind not in {"ai-config", "prompt-template"} else None
        with session_factory() as session:
            target = (session.get(UserRecord, body.owner_id) if body.owner_id is not None else
                      session.scalar(select(UserRecord).where(UserRecord.username == body.username)))
            if target is None:
                return JSONResponse(status_code=404, content={"code": 4043, "msg": "owner not found", "data": None})
            if connection_id is not None:
                connection = session.get(DbxConnectionOwnershipRecord, connection_id)
                if connection is None or connection.project_id != project_id:
                    return JSONResponse(status_code=409, content={"code": 4091, "msg": "claim the DBX connection first", "data": None})
            try:
                DbxObjectAccess(session).claim(
                    kind=kind, object_id=object_id, project_id=project_id,
                    owner_id=target.id, connection_id=connection_id,
                )
                session.commit()
            except ValueError:
                session.rollback()
                return JSONResponse(status_code=409, content={"code": 4091, "msg": "DBX object already claimed", "data": None})
            target_id = target.id
        return {"code": 0, "msg": "success", "data": {"kind": kind, "object_id": object_id, "owner_id": target_id}}

    @router.post("/objects/{kind}/{object_id}/share")
    def share_object(project_id: int, kind: str, object_id: str, body: ShareRequest, authorization: str = Header(default="")):
        user = context(project_id, authorization, Permission.DATASOURCE_MANAGE)
        if isinstance(user, JSONResponse):
            return user
        owner_id = object_owner(project_id, kind, object_id, user)
        if isinstance(owner_id, JSONResponse):
            return owner_id
        if (body.user_id is None) == (body.username is None):
            return JSONResponse(status_code=400, content={"code": 4001, "msg": "one recipient required", "data": None})
        with session_factory() as session:
            target = (session.get(UserRecord, body.user_id) if body.user_id is not None else
                      session.scalar(select(UserRecord).where(UserRecord.username == body.username)))
            if target is None:
                return JSONResponse(status_code=404, content={"code": 4043, "msg": "user not found", "data": None})
            DbxObjectAccess(session).share(kind=kind, object_id=object_id, owner_id=owner_id, user_id=target.id)
            session.commit()
            target_id = target.id
        return {"code": 0, "msg": "success", "data": {"kind": kind, "object_id": object_id, "user_id": target_id}}

    @router.get("/objects/{kind}/{object_id}/shares")
    def list_object_shares(project_id: int, kind: str, object_id: str, authorization: str = Header(default="")):
        user = context(project_id, authorization, Permission.DATASOURCE_MANAGE)
        if isinstance(user, JSONResponse):
            return user
        owner_id = object_owner(project_id, kind, object_id, user)
        if isinstance(owner_id, JSONResponse):
            return owner_id
        with session_factory() as session:
            rows = session.execute(
                select(DbxObjectShareRecord.user_id, UserRecord.username)
                .join(UserRecord, UserRecord.id == DbxObjectShareRecord.user_id)
                .where(DbxObjectShareRecord.kind == kind, DbxObjectShareRecord.object_id == object_id)
                .order_by(UserRecord.username)
            ).all()
        return {"code": 0, "msg": "success", "data": {"items": [
            {"user_id": uid, "username": username} for uid, username in rows
        ]}}

    @router.delete("/objects/{kind}/{object_id}/shares/{user_id}")
    def unshare_object(project_id: int, kind: str, object_id: str, user_id: int, authorization: str = Header(default="")):
        user = context(project_id, authorization, Permission.DATASOURCE_MANAGE)
        if isinstance(user, JSONResponse):
            return user
        owner_id = object_owner(project_id, kind, object_id, user)
        if isinstance(owner_id, JSONResponse):
            return owner_id
        with session_factory() as session:
            DbxObjectAccess(session).unshare(kind=kind, object_id=object_id, owner_id=owner_id, user_id=user_id)
            session.commit()
        return {"code": 0, "msg": "success", "data": {"kind": kind, "object_id": object_id, "user_id": user_id}}

    @router.get("/connections/{connection_id}/databases")
    def databases(project_id: int, connection_id: str, authorization: str = Header(default="")):
        user = context(project_id, authorization, Permission.DATASOURCE_READ)
        if isinstance(user, JSONResponse):
            return user
        denial = require_connection(project_id, connection_id, user)
        if denial is not None:
            return denial
        try:
            data = client_factory().list_databases(connection_id)
        except DbxError as exc:
            return upstream_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    @router.get("/connections/{connection_id}/schemas")
    def schemas(project_id: int, connection_id: str, database: str = Query(), authorization: str = Header(default="")):
        user = context(project_id, authorization, Permission.DATASOURCE_READ)
        if isinstance(user, JSONResponse):
            return user
        denial = require_connection(project_id, connection_id, user)
        if denial is not None:
            return denial
        try:
            data = client_factory().list_schemas(connection_id, database)
        except DbxError as exc:
            return upstream_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    @router.get("/connections/{connection_id}/objects")
    def objects(project_id: int, connection_id: str, database: str = Query(), schema: str = Query(), authorization: str = Header(default="")):
        user = context(project_id, authorization, Permission.DATASOURCE_READ)
        if isinstance(user, JSONResponse):
            return user
        denial = require_connection(project_id, connection_id, user)
        if denial is not None:
            return denial
        try:
            data = client_factory().list_objects(connection_id, database, schema)
        except DbxError as exc:
            return upstream_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    @router.get("/connections/{connection_id}/columns")
    def columns(project_id: int, connection_id: str, database: str = Query(), schema: str = Query(), table: str = Query(), authorization: str = Header(default="")):
        user = context(project_id, authorization, Permission.DATASOURCE_READ)
        if isinstance(user, JSONResponse):
            return user
        denial = require_connection(project_id, connection_id, user)
        if denial is not None:
            return denial
        try:
            data = client_factory().list_columns(connection_id, database, schema, table)
        except DbxError as exc:
            return upstream_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    @router.post("/query/execute")
    def execute(project_id: int, body: ExecuteRequest, authorization: str = Header(default="")):
        user = context(project_id, authorization, Permission.EXECUTE_SQL)
        if isinstance(user, JSONResponse):
            return user
        denial = require_connection(project_id, body.connection_id, user)
        if denial is not None:
            return denial
        try:
            data = client_factory().execute_sql(connection_id=body.connection_id, database=body.database, sql=body.sql, schema=body.schema_name, max_rows=body.max_rows)
        except DbxError as exc:
            return upstream_error(exc)
        return {"code": 0, "msg": "success", "data": data}

    return router
