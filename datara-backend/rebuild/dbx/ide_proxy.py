"""Authenticated owner gate for the embedded, single-user dbx IDE API."""

from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import sessionmaker
from starlette.concurrency import run_in_threadpool

from rebuild.dbx import DbxClient, DbxError
from rebuild.dbx.access import DbxConnectionAccess, DbxObjectAccess
from rebuild.dbx.ai_owner import (
    KIND as AI_CONFIG_KIND, SHARED_REF, config_rows, global_instructions_from_state,
    owned_config, resolve_config, save_ai_user_preferences, selection_from_state,
    user_state, valid_config_id, visible_config_ids, visible_configs,
)
from rebuild.dbx.ide_route_manifest import SUPPORTED_DATA_ROUTES
from rebuild.dbx.ide_policy import (
    DbxIdeForbidden, canonical_connect_payload, classify_save, merge_connection_save_payload,
    referenced_connection_ids, require_visible, safe_connection_list, saved_sql_descendants, scoped_history_search,
)
from rebuild.dbx.models import DbxConnectionOwnershipRecord, DbxConnectionShareRecord, DbxObjectOwnershipRecord, DbxObjectShareRecord
from rebuild.identity.contracts import Permission, Role


class IdeSessionRegistry:
    def __init__(self, *, ttl_seconds: int = 900) -> None:
        self.ttl_seconds = ttl_seconds
        self._sessions: dict[str, tuple[str, int, float]] = {}

    def issue(self, token: str, project_id: int) -> str:
        opaque_id = secrets.token_urlsafe(32)
        self._sessions[opaque_id] = (token, project_id, time.monotonic() + self.ttl_seconds)
        return opaque_id

    def resolve(self, opaque_id: str) -> tuple[str, int] | None:
        entry = self._sessions.get(opaque_id)
        if entry is None:
            return None
        token, project_id, expires_at = entry
        if time.monotonic() >= expires_at:
            self._sessions.pop(opaque_id, None)
            return None
        return token, project_id


_BOOTSTRAP_READS = frozenset({
    "auth/check", "migration/status", "plugins", "version",
    "app-settings/sql-file-upload-max-bytes", "layout/sidebar",
    "layout/table-vgroups", "ssh/prompts", "ssh/prompts/pending",
})
_CONFIG_DOMAINS = ("ai/", "tunnel-profiles/", "prompt-templates")
_CONNECTION_OWNER_WRITES = frozenset({
    "connection/database-info/save", "connection/write-unlock",
    "connection/write-unlock/lock", "connection/forget-session-credential",
    "connection/replace-nacos-session-credential", "connection/disconnect",
    "connection/close-database", "connection/salesforce-oauth-browser-authorize",
    "connection/salesforce-oauth-device-start", "connection/salesforce-oauth-device-poll",
    "connection/salesforce-oauth-refresh", "connection/salesforce-oauth-password-login",
})
_CONNECTION_BLOCKED = frozenset({
    "connection/mcp/add", "connection/mcp/duplicate", "connection/mcp/remove",
})
_CONNECTION_ALLOWED = frozenset({
    "connection/check-health", "connection/close-database", "connection/connect",
    "connection/database-info", "connection/database-info/save", "connection/disconnect",
    "connection/final-proxy-port", "connection/forget-session-credential",
    "connection/identifier-quote", "connection/idle-closed-events", "connection/is-open",
    "connection/list", "connection/liveness-events", "connection/prewarm",
    "connection/replace-nacos-session-credential", "connection/salesforce-oauth-browser-authorize",
    "connection/salesforce-oauth-device-poll", "connection/salesforce-oauth-device-start",
    "connection/salesforce-oauth-password-login", "connection/salesforce-oauth-refresh",
    "connection/save", "connection/session-credential-status", "connection/test",
    "connection/test-info", "connection/test-ssh-tunnel", "connection/write-unlock",
    "connection/write-unlock/lock", "connection/write-unlock/state",
})
_AI_CONVERSATIONS = frozenset({"ai/conversation", "ai/conversations"})
_AI_CONFIG_ROUTES = frozenset({
    "ai/config", "ai/provider-configs", "ai/configs", "ai/config-item",
    "ai/default-config", "ai/chat-selection", "ai/complete", "ai/test-connection",
    "ai/models", "ai/model-effort", "ai/stream", "ai/agent-stream",
    "ai/cancel-stream", "ai/tool-approval",
})
_PROMPT_TEMPLATE_KIND = "prompt-template"


def is_supported_ide_route(path: str) -> bool:
    """Never infer authorization from a forged connection ID on an unknown API."""
    parts = path.split("/")
    dynamic_route = bool(
        all(parts) and (
            (len(parts) == 2 and parts[0] == "history")
            or (len(parts) == 2 and parts[0] == "saved-sql")
            or (len(parts) == 3 and parts[:2] == ["saved-sql", "folders"])
            or (len(parts) == 3 and parts[0] == "saved-sql" and parts[2] == "default-content")
            or (len(parts) == 4 and parts[:3] == ["query", "large-value", "download"])
        )
    )
    return (
        path in _BOOTSTRAP_READS
        or path in _CONNECTION_ALLOWED
        or path in SUPPORTED_DATA_ROUTES
        or dynamic_route
        or path in _AI_CONVERSATIONS
        or path in _AI_CONFIG_ROUTES
        or path == "prompt-templates"
        or (path.startswith("prompt-templates/") and len(parts) == 2 and bool(parts[1]))
        or (path.startswith("ai/config/") and len(parts) == 3 and bool(parts[2]))
        or (path.startswith("ai/conversation/") and len(path.split("/")) == 3)
    )


def build_dbx_ide_router(
    session_factory: sessionmaker,
    current_user: Callable[[str], dict[str, object]],
    project_permission_error: Callable[..., JSONResponse | None],
    *,
    client_factory: Callable[[], DbxClient] = DbxClient,
    registry: IdeSessionRegistry | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/rebuild/dbx", tags=["rebuild-dbx-ide"])
    registry = registry or IdeSessionRegistry()

    def denied(status: int = 403, message: str = "dbx IDE access denied") -> JSONResponse:
        return JSONResponse(status_code=status, content={"code": 1001 if status == 401 else 1003, "msg": message, "data": None})

    def authorize(token: str, project_id: int, permission: Permission) -> dict[str, object] | JSONResponse:
        try:
            user = current_user(f"Bearer {token}")
        except ValueError:
            return denied(401, "invalid token")
        with session_factory() as session:
            refusal = project_permission_error(session, project_id, user, permission)
        return refusal if refusal is not None else user

    @router.post("/projects/{project_id}/ide-session")
    def issue_ide_session(project_id: int, authorization: str = Header(default="")):
        if not authorization.startswith("Bearer "):
            return denied(401, "invalid token")
        token = authorization[7:]
        user = authorize(token, project_id, Permission.DATASOURCE_READ)
        if isinstance(user, JSONResponse):
            return user
        response = JSONResponse(content={"code": 0, "msg": "success", "data": {"expires_in": registry.ttl_seconds}})
        response.set_cookie(
            "datara_dbx_ide", registry.issue(token, project_id), max_age=registry.ttl_seconds,
            path="/ide/api", httponly=True, samesite="strict",
        )
        return response

    @router.api_route("/ide-proxy/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
    async def proxy_ide(path: str, request: Request):
        session = registry.resolve(request.cookies.get("datara_dbx_ide", ""))
        if session is None:
            return denied(401, "IDE session required")
        token, project_id = session
        if not path or path.startswith("/") or ".." in path.split("/"):
            return denied()
        if path.startswith(_CONFIG_DOMAINS) and not (
            path in _AI_CONVERSATIONS or path in _AI_CONFIG_ROUTES
            or path.startswith("ai/conversation/") or path.startswith("ai/config/")
            or path == "prompt-templates" or path.startswith("prompt-templates/")
        ):
            return denied(message="owner-scoped dbx configuration endpoint pending")
        if path in _CONNECTION_BLOCKED:
            return denied(message="connection modification requires the Datara owner API")
        if not is_supported_ide_route(path):
            return denied(message="unsupported dbx IDE endpoint")
        permission = Permission.DATASOURCE_MANAGE if path == "connection/save" or path in _CONNECTION_OWNER_WRITES or (path.startswith("history") and request.method == "DELETE") or (path.startswith("ai/conversation") and request.method != "GET") or (path in {"ai/configs", "ai/config-item", "ai/default-config"} and request.method != "GET") or (path.startswith("ai/config/") and request.method == "DELETE") or (path.startswith("prompt-templates") and request.method != "GET") else (
            Permission.EXECUTE_SQL if path.startswith("query/") or (path.startswith("schema/") and request.method != "GET") or path in {"history/save", "ai/agent-stream"} else Permission.DATASOURCE_READ
        )
        user = authorize(token, project_id, permission)
        if isinstance(user, JSONResponse):
            return user
        if path == "auth/check" and request.method == "GET":
            # The iframe is authenticated by the Datara IDE session. Forwarding
            # this check to dbx would ask for dbx's single-user cookie and send
            # the user to a second login screen once its direct API is locked.
            return {"authenticated": True, "required": False, "setup_required": False}
        admin = user.get("role") == Role.ADMIN.value
        user_id = int(user["user_id"])
        with session_factory() as db_session:
            access = DbxConnectionAccess(db_session)
            visible_ids = access.visible_ids(project_id=project_id, user_id=user_id, is_admin=admin)
            owners = db_session.query(DbxConnectionOwnershipRecord).filter_by(project_id=project_id).all()
            manageable_ids = {owner.connection_id for owner in owners if admin or owner.owner_id == user_id}

        dbx = client_factory()
        try:
            if admin:
                visible_ids = {str(row.get("id")) for row in dbx.list_connections()}
            if path == "connection/list" and request.method == "GET":
                rows = dbx.list_connections()
                return safe_connection_list(rows, visible_ids)

            if path == "ai/configs" and request.method == "GET":
                rows = config_rows(dbx._request("GET", path))
                with session_factory() as db_session:
                    return visible_configs(db_session, rows, project_id=project_id, user_id=user_id, admin=admin)
            if path == "ai/chat-selection" and request.method == "GET":
                with session_factory() as db_session:
                    selection = selection_from_state(db_session, project_id, user_id)
                    if selection is None:
                        return None
                    rows = config_rows(dbx._request("GET", "ai/configs"))
                    allowed = visible_config_ids(db_session, project_id=project_id, user_id=user_id, admin=admin, rows=rows)
                    selection = dict(selection)
                    if isinstance(selection.get("active"), dict) and selection["active"].get("configId") not in allowed:
                        selection["active"] = None
                    preferences = selection.get("effortPreferences")
                    if isinstance(preferences, list):
                        selection["effortPreferences"] = [item for item in preferences if isinstance(item, dict) and item.get("configId") in allowed]
                    return selection
            if path in {"ai/config", "ai/provider-configs"} and request.method == "GET":
                # Legacy single-user settings must not migrate into another user's workspace.
                return dbx._request("GET", path) if admin else (None if path == "ai/config" else {})
            if path == "prompt-templates" and request.method == "GET":
                rows = dbx._request("GET", path)
                if not isinstance(rows, list):
                    return denied(message="invalid DBX prompt templates")
                with session_factory() as db_session:
                    visible = DbxObjectAccess(db_session).visible_ids(
                        kind=_PROMPT_TEMPLATE_KIND, project_id=project_id, user_id=user_id, is_admin=admin,
                    )
                return [row for row in rows if isinstance(row, dict) and (admin or row.get("id") in visible)]
            if path == "prompt-templates/global-instructions" and request.method == "GET":
                with session_factory() as db_session:
                    return {"content": global_instructions_from_state(db_session, project_id, user_id)}

            if path == "ai/conversations" and request.method == "GET":
                rows = dbx._request("GET", path)
                if not isinstance(rows, list):
                    return denied(message="invalid AI conversations")
                with session_factory() as db_session:
                    owned = DbxObjectAccess(db_session).visible_ids(
                        kind="ai-conversation", project_id=project_id, user_id=user_id, is_admin=admin,
                    )
                return [row for row in rows if isinstance(row, dict)
                        and row.get("connectionId") in visible_ids
                        and (admin or row.get("id") in owned)]

            if path.startswith("ai/conversation/") and request.method == "DELETE":
                object_id = path.split("/")[-1]
                if not object_id:
                    return denied()
                with session_factory() as db_session:
                    access = DbxObjectAccess(db_session)
                    owner = access.get("ai-conversation", object_id)
                    if owner is None:
                        if not admin:
                            return denied()
                        rows = dbx._request("GET", "ai/conversations")
                        if not isinstance(rows, list) or not any(
                            isinstance(row, dict) and row.get("id") == object_id
                            and row.get("connectionId") in visible_ids for row in rows
                        ):
                            return denied()
                    elif owner.project_id != project_id or owner.connection_id not in visible_ids or (not admin and owner.owner_id != user_id):
                        return denied()
                    result = dbx._request("DELETE", path)
                    db_session.query(DbxObjectShareRecord).filter_by(kind="ai-conversation", object_id=object_id).delete()
                    db_session.query(DbxObjectOwnershipRecord).filter_by(kind="ai-conversation", object_id=object_id).delete()
                    db_session.commit()
                    return result

            if path == "history/options" and request.method == "GET":
                options = dbx._request("GET", path)
                if not isinstance(options, list):
                    return denied(message="invalid history options")
                return [item for item in options if isinstance(item, dict) and item.get("connection_id") in visible_ids]
            if path == "history" and request.method == "GET":
                query = dict(request.query_params)
                try:
                    limit = int(query.get("limit", "100"))
                    offset = int(query.get("offset", "0"))
                except ValueError:
                    return denied(message="invalid history pagination")
                if not 0 <= limit <= 200 or not 0 <= offset <= 5000:
                    return denied(message="history pagination out of range")
                if admin:
                    return dbx._request("GET", path, params=query)
                if not visible_ids or limit == 0:
                    return []
                entries: list[Any] = []
                cursor = None
                skipped = 0
                while len(entries) < limit:
                    frame: dict[str, Any] = {
                        "connections": [{"connection_id": item} for item in sorted(visible_ids)],
                        "limit": min(200, offset + limit - skipped - len(entries)),
                    }
                    if cursor is not None:
                        frame["cursor"] = cursor
                    if query.get("activity_kind"):
                        frame["activity_kind"] = query["activity_kind"]
                    page = dbx._request("POST", "history/search", payload=frame)
                    if not isinstance(page, dict) or not isinstance(page.get("entries"), list):
                        return denied(message="invalid history page")
                    batch = page["entries"]
                    if not batch:
                        break
                    take_from = min(len(batch), max(0, offset - skipped))
                    skipped += len(batch)
                    entries.extend(batch[take_from:take_from + limit - len(entries)])
                    cursor = page.get("next_cursor")
                    if cursor is None:
                        break
                return entries
            if path.startswith("history") and request.method == "DELETE":
                if not admin or (path != "history" and (not path.startswith("history/") or len(path.split("/")) != 2)):
                    return denied()
                return dbx._request("DELETE", path, params=dict(request.query_params))

            body_bytes = await request.body()
            if len(body_bytes) > 4 * 1024 * 1024:
                return denied(message="request too large")
            payload: dict[str, Any] = {}
            if body_bytes:
                try:
                    parsed = await request.json()
                except ValueError:
                    return denied(message="JSON request required")
                if not isinstance(parsed, dict):
                    return denied(message="JSON object required")
                payload = parsed
            query = dict(request.query_params)
            if path in {"ai/config-item", "ai/configs"} and request.method == "POST":
                items = [payload.get("config")] if path == "ai/config-item" else payload.get("configs")
                if not isinstance(items, list) or not items or any(not isinstance(item, dict) or not valid_config_id(item.get("id")) for item in items):
                    return denied(message="invalid AI configuration")
                if len({item["id"] for item in items}) != len(items):
                    return denied(message="duplicate AI configuration")
                rows = config_rows(dbx._request("GET", "ai/configs"))
                stored = {row["id"]: row for row in rows}
                with session_factory() as db_session:
                    access = DbxObjectAccess(db_session)
                    for item in items:
                        config_id = item["id"]
                        owner = access.get(AI_CONFIG_KIND, config_id)
                        if config_id in stored:
                            if owner is None or owner.project_id != project_id or (not admin and owner.owner_id != user_id):
                                return denied(message="AI configuration owner required")
                        elif owner is not None:
                            return denied(message="AI configuration ID reserved")
                        if isinstance(item.get("apiKey"), str) and item["apiKey"].startswith(SHARED_REF):
                            return denied(message="shared AI configuration is read only")
                    for item in items:
                        clean = dict(item, isDefault=False)
                        dbx._request("POST", "ai/config-item", payload={"config": clean})
                        if item["id"] not in stored:
                            access.claim(kind=AI_CONFIG_KIND, object_id=item["id"], project_id=project_id, owner_id=user_id)
                        if item.get("isDefault"):
                            user_state(db_session, project_id, user_id).default_config_id = item["id"]
                        db_session.commit()
                return None
            if path.startswith("ai/config/") and request.method == "DELETE":
                config_id = path.split("/", 2)[2]
                if not valid_config_id(config_id):
                    return denied()
                with session_factory() as db_session:
                    if not owned_config(db_session, config_id, project_id=project_id, user_id=user_id, admin=admin):
                        return denied(message="AI configuration owner required")
                    result = dbx._request("DELETE", path)
                    db_session.query(DbxObjectShareRecord).filter_by(kind=AI_CONFIG_KIND, object_id=config_id).delete()
                    db_session.query(DbxObjectOwnershipRecord).filter_by(kind=AI_CONFIG_KIND, object_id=config_id).delete()
                    db_session.commit()
                    return result
            if path == "ai/default-config" and request.method == "POST":
                config_id = payload.get("configId")
                rows = config_rows(dbx._request("GET", "ai/configs"))
                with session_factory() as db_session:
                    if config_id not in visible_config_ids(db_session, project_id=project_id, user_id=user_id, admin=admin, rows=rows):
                        return denied(message="AI configuration not shared")
                    user_state(db_session, project_id, user_id).default_config_id = config_id
                    db_session.commit()
                return None
            if path == "ai/chat-selection" and request.method == "POST":
                selection = payload.get("selection")
                if not isinstance(selection, dict):
                    return denied(message="invalid AI selection")
                rows = config_rows(dbx._request("GET", "ai/configs"))
                with session_factory() as db_session:
                    allowed = visible_config_ids(db_session, project_id=project_id, user_id=user_id, admin=admin, rows=rows)
                    active = selection.get("active")
                    if active is not None and (not isinstance(active, dict) or active.get("configId") not in allowed):
                        return denied(message="AI configuration not shared")
                    preferences = selection.get("effortPreferences", [])
                    if not isinstance(preferences, list) or any(not isinstance(item, dict) or item.get("configId") not in allowed for item in preferences):
                        return denied(message="invalid AI selection")
                    save_ai_user_preferences(db_session, project_id, user_id, selection=selection)
                    db_session.commit()
                return None
            if path == "prompt-templates/global-instructions" and request.method == "PUT":
                content = payload.get("content")
                if not isinstance(content, str) or len(content.strip()) > 8000:
                    return denied(message="invalid AI global instructions")
                with session_factory() as db_session:
                    save_ai_user_preferences(db_session, project_id, user_id, global_instructions=content.strip())
                    db_session.commit()
                return None
            if path == "prompt-templates" and request.method == "POST":
                template_id = payload.get("id")
                if not valid_config_id(template_id) or not isinstance(payload.get("name"), str) or not isinstance(payload.get("content"), str):
                    return denied(message="invalid prompt template")
                rows = dbx._request("GET", path)
                if not isinstance(rows, list):
                    return denied(message="invalid DBX prompt templates")
                stored_ids = {row.get("id") for row in rows if isinstance(row, dict)}
                with session_factory() as db_session:
                    access = DbxObjectAccess(db_session)
                    owner = access.get(_PROMPT_TEMPLATE_KIND, template_id)
                    if template_id in stored_ids:
                        if owner is None or owner.project_id != project_id or (not admin and owner.owner_id != user_id):
                            return denied(message="prompt template owner required")
                    elif owner is not None:
                        return denied(message="prompt template ID reserved")
                    result = dbx._request("POST", path, payload=payload)
                    if template_id not in stored_ids:
                        access.claim(kind=_PROMPT_TEMPLATE_KIND, object_id=template_id, project_id=project_id, owner_id=user_id)
                    db_session.commit()
                    return result
            if path.startswith("prompt-templates/") and request.method == "DELETE":
                template_id = path.split("/", 1)[1]
                if not valid_config_id(template_id):
                    return denied()
                with session_factory() as db_session:
                    if not owned_config(db_session, template_id, project_id=project_id, user_id=user_id,
                                        admin=admin, kind=_PROMPT_TEMPLATE_KIND):
                        return denied(message="prompt template owner required")
                    result = dbx._request("DELETE", path)
                    db_session.query(DbxObjectShareRecord).filter_by(kind=_PROMPT_TEMPLATE_KIND, object_id=template_id).delete()
                    db_session.query(DbxObjectOwnershipRecord).filter_by(kind=_PROMPT_TEMPLATE_KIND, object_id=template_id).delete()
                    db_session.commit()
                    return result
            if path in {"ai/complete", "ai/test-connection", "ai/models", "ai/model-effort", "ai/stream", "ai/agent-stream"} and request.method == "POST":
                request_frame = payload.get("request") if path in {"ai/complete", "ai/stream", "ai/agent-stream"} else payload
                supplied = request_frame.get("config") if isinstance(request_frame, dict) else None
                if not isinstance(supplied, dict):
                    return denied(message="saved AI configuration required")
                draft_check = path in {"ai/test-connection", "ai/models", "ai/model-effort"}
                shared_ref = str(supplied.get("apiKey", "")).startswith(SHARED_REF)
                if draft_check and not shared_ref:
                    resolved = supplied
                else:
                    rows = config_rows(dbx._request("GET", "ai/configs"))
                    with session_factory() as db_session:
                        resolved = resolve_config(db_session, rows, supplied, project_id=project_id, user_id=user_id, admin=admin)
                if resolved is None:
                    return denied(message="AI configuration not shared")
                if path == "ai/agent-stream":
                    connection_id = payload.get("connectionId")
                    confirmed_id = payload.get("confirmedConnectionId")
                    if connection_id not in visible_ids or (confirmed_id is not None and confirmed_id != connection_id):
                        return denied(message="AI agent connection not shared")
                payload = dict(payload)
                request_frame = dict(request_frame, config=resolved)
                if path in {"ai/complete", "ai/stream", "ai/agent-stream"}:
                    payload["request"] = request_frame
                else:
                    payload["config"] = resolved
                if path in {"ai/stream", "ai/agent-stream"}:
                    session_id = payload.get("sessionId", payload.get("session_id"))
                    if not isinstance(session_id, str) or not session_id or len(session_id) > 128:
                        return denied(message="invalid AI stream session")
                    payload["sessionId"] = f"{project_id}:{user_id}:{session_id}"
                    payload.pop("session_id", None)
                    upstream = await run_in_threadpool(dbx.open_stream, path, payload)

                    def stream_chunks():
                        with upstream:
                            while chunk := upstream.read(8192):
                                yield chunk

                    return StreamingResponse(stream_chunks(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})
                return dbx._request("POST", path, payload=payload)
            if path in {"ai/cancel-stream", "ai/tool-approval"} and request.method == "POST":
                session_id = payload.get("sessionId", payload.get("session_id"))
                if not isinstance(session_id, str) or not session_id or len(session_id) > 128:
                    return denied(message="invalid AI stream session")
                scoped = dict(payload, sessionId=f"{project_id}:{user_id}:{session_id}")
                scoped.pop("session_id", None)
                return dbx._request("POST", path, payload=scoped)
            if path == "ai/conversation" and request.method == "POST":
                conversation = payload.get("conversation")
                if not isinstance(conversation, dict):
                    return denied()
                object_id = conversation.get("id")
                connection_id = conversation.get("connectionId")
                if not isinstance(object_id, str) or not object_id or connection_id not in visible_ids:
                    return denied()
                with session_factory() as db_session:
                    access = DbxObjectAccess(db_session)
                    owner = access.get("ai-conversation", object_id)
                    if owner is not None:
                        if owner.project_id != project_id or owner.connection_id != connection_id or (not admin and owner.owner_id != user_id):
                            return denied()
                    else:
                        rows = dbx._request("GET", "ai/conversations")
                        if not isinstance(rows, list):
                            return denied(message="invalid AI conversations")
                        if any(isinstance(row, dict) and row.get("id") == object_id for row in rows):
                            return denied(message="legacy AI conversation requires admin claim")
                        access.claim(kind="ai-conversation", object_id=object_id, project_id=project_id,
                                     owner_id=user_id, connection_id=connection_id)
                    result = dbx._request("POST", path, payload=payload)
                    db_session.commit()
                    return result
            if path in _CONNECTION_OWNER_WRITES:
                ids = referenced_connection_ids(payload) | referenced_connection_ids(query)
                if not ids or not ids.issubset(manageable_ids):
                    return denied(message="connection owner required")
            if path == "saved-sql" and request.method == "GET":
                library = dbx._request("GET", path)
                if not isinstance(library, dict):
                    return denied(message="invalid SQL library")
                with session_factory() as db_session:
                    access = DbxObjectAccess(db_session)
                    folders = access.visible_ids(kind="sql-folder", project_id=project_id, user_id=user_id, is_admin=admin)
                    files = access.visible_ids(kind="sql-file", project_id=project_id, user_id=user_id, is_admin=admin)
                return {
                    "folders": [item for item in library.get("folders", []) if isinstance(item, dict) and item.get("connectionId") in visible_ids and (admin or item.get("id") in folders)],
                    "files": [item for item in library.get("files", []) if isinstance(item, dict) and item.get("connectionId") in visible_ids and (admin or item.get("id") in files)],
                }
            if path.startswith("saved-sql/") and path.endswith("/default-content") and request.method == "POST":
                parts = path.split("/")
                if len(parts) != 3 or not isinstance(payload.get("sql"), str):
                    return denied()
                with session_factory() as db_session:
                    owner = DbxObjectAccess(db_session).get("sql-file", parts[1])
                    if owner is None:
                        if not admin:
                            return denied()
                        library = dbx._request("GET", "saved-sql")
                        legacy = next((item for item in library.get("files", []) if isinstance(item, dict) and item.get("id") == parts[1]), None) if isinstance(library, dict) else None
                        if legacy is None or legacy.get("connectionId") not in visible_ids:
                            return denied()
                    elif owner.project_id != project_id or owner.connection_id not in visible_ids or (not admin and owner.owner_id != user_id):
                        return denied()
                return dbx._request("POST", path, payload=payload)
            if path.startswith("saved-sql/") and request.method in {"GET", "DELETE"}:
                parts = path.split("/")
                kind = "sql-folder" if len(parts) == 3 and parts[1] == "folders" else "sql-file" if len(parts) == 2 else ""
                object_id = parts[-1]
                if not kind or not object_id:
                    return denied()
                with session_factory() as db_session:
                    owner = DbxObjectAccess(db_session).get(kind, object_id)
                    allowed = owner is not None and owner.project_id == project_id and owner.connection_id in visible_ids
                    if allowed and not admin:
                        shared = DbxObjectAccess(db_session).visible_ids(kind=kind, project_id=project_id, user_id=user_id, is_admin=False)
                        allowed = object_id in shared and (request.method == "GET" or owner.owner_id == user_id)
                    if not allowed and not (admin and owner is None):
                        return denied()
                    affected = {(kind, object_id)}
                    if request.method == "DELETE" and kind == "sql-folder":
                        library = dbx._request("GET", "saved-sql")
                        if not isinstance(library, dict):
                            return denied(message="invalid SQL library")
                        affected = saved_sql_descendants(library, object_id)
                        for child_kind, child_id in affected:
                            child_owner = DbxObjectAccess(db_session).get(child_kind, child_id)
                            if child_owner is not None and (
                                child_owner.project_id != project_id or child_owner.connection_id not in visible_ids
                                or (not admin and child_owner.owner_id != user_id)
                            ):
                                return denied(message="SQL folder contains another owner's object")
                            if child_owner is None and not admin:
                                return denied(message="SQL folder contains an unclaimed object")
                    result = dbx._request(request.method, path)
                    if request.method == "DELETE":
                        for child_kind, child_id in affected:
                            db_session.query(DbxObjectShareRecord).filter_by(kind=child_kind, object_id=child_id).delete()
                            db_session.query(DbxObjectOwnershipRecord).filter_by(kind=child_kind, object_id=child_id).delete()
                        db_session.commit()
                    return result
            if path in {"saved-sql", "saved-sql/folders"} and request.method == "POST":
                kind = "sql-folder" if path.endswith("/folders") else "sql-file"
                object_id = payload.get("id")
                connection_id = payload.get("connectionId")
                if not isinstance(object_id, str) or not object_id or connection_id not in visible_ids:
                    return denied()
                with session_factory() as db_session:
                    access = DbxObjectAccess(db_session)
                    owner = access.get(kind, object_id)
                    library: dict[str, Any] | None = None
                    if owner is not None:
                        if owner.project_id != project_id or owner.connection_id != connection_id or (not admin and owner.owner_id != user_id):
                            return denied()
                    else:
                        library = dbx._request("GET", "saved-sql")
                        group = library.get("folders" if kind == "sql-folder" else "files", []) if isinstance(library, dict) else []
                        legacy = next((item for item in group if isinstance(item, dict) and item.get("id") == object_id), None)
                        if legacy is not None:
                            if not admin or legacy.get("connectionId") != connection_id:
                                return denied(message="legacy SQL object requires admin")
                        else:
                            access.claim(kind=kind, object_id=object_id, project_id=project_id, owner_id=user_id, connection_id=connection_id)
                    parent_id = payload.get("parentFolderId" if kind == "sql-folder" else "folderId")
                    if parent_id:
                        parent = access.get("sql-folder", str(parent_id))
                        if parent is None:
                            if library is None:
                                candidate = dbx._request("GET", "saved-sql")
                                library = candidate if isinstance(candidate, dict) else {}
                            folders = library.get("folders", []) if isinstance(library, dict) else []
                            legacy_parent = next((item for item in folders if isinstance(item, dict) and item.get("id") == parent_id), None)
                            if not admin or legacy_parent is None or legacy_parent.get("connectionId") != connection_id:
                                return denied(message="SQL folder owner required")
                        elif parent.project_id != project_id or parent.connection_id != connection_id or (not admin and parent.owner_id != user_id):
                            return denied(message="SQL folder owner required")
                    result = dbx._request("POST", path, payload=payload)
                    db_session.commit()
                    return result
            if path == "history/search" and request.method == "POST":
                if admin:
                    return dbx._request("POST", path, payload=payload)
                try:
                    scoped = scoped_history_search(payload, visible_ids)
                except DbxIdeForbidden:
                    return denied()
                if scoped is None:
                    return {"entries": [], "next_cursor": None, "total": 0}
                return dbx._request("POST", path, payload=scoped)
            referenced = referenced_connection_ids(payload) | referenced_connection_ids(query)
            if path == "connection/save" and request.method == "POST":
                rows = dbx.list_connections()
                stored = {str(row.get("id")): row for row in rows}
                stored_ids = {str(row.get("id")) for row in rows}
                try:
                    new_ids = classify_save(payload, stored_ids, manageable_ids)
                except DbxIdeForbidden:
                    return denied()
                payload = merge_connection_save_payload(payload, stored)
                result = dbx._request("POST", path, payload=payload)
                removed_ids = set(payload.get("removedIds", []))
                with session_factory() as db_session:
                    access = DbxConnectionAccess(db_session)
                    for connection_id in new_ids:
                        access.claim(connection_id=connection_id, project_id=project_id, owner_id=user_id)
                    if removed_ids:
                        db_session.query(DbxConnectionShareRecord).filter(DbxConnectionShareRecord.connection_id.in_(removed_ids)).delete(synchronize_session=False)
                        db_session.query(DbxConnectionOwnershipRecord).filter(DbxConnectionOwnershipRecord.connection_id.in_(removed_ids)).delete(synchronize_session=False)
                    db_session.commit()
                return result

            if path in {"connection/connect", "connection/test", "connection/test-info", "connection/test-ssh-tunnel"} and request.method == "POST":
                rows = dbx.list_connections()
                stored = {str(row.get("id")): row for row in rows}
                try:
                    payload = canonical_connect_payload(payload, stored, visible_ids)
                except DbxIdeForbidden:
                    return denied()
            elif referenced:
                try:
                    require_visible(payload, visible_ids)
                    require_visible(query, visible_ids)
                except DbxIdeForbidden:
                    return denied()
            elif request.method != "GET" or path not in _BOOTSTRAP_READS:
                return denied(message="unscoped dbx operation blocked")
            return dbx._request(request.method, path, params=query, payload=payload if body_bytes else None)
        except DbxError:
            return JSONResponse(status_code=502, content={"code": 502, "msg": "dbx unavailable", "data": None})

    return router
