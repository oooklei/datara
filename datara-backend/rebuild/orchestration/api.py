"""编排网关：datara ↔ DolphinScheduler 的唯一业务入口（设计 §十）。

浏览器侧契约（宿主/自建页面调用，需 datara token）：

1. ``GET  /api/v1/rebuild/orchestration/datasources``
   海豚 UI 节点表单的数据源下拉真源（按项目及 dbx owner 可见性过滤，
   ``id`` 为 dbx connectionId）。
2. ``GET  /api/v1/rebuild/orchestration/session``
   宿主页 postMessage 下发的会话载荷（内部令牌 + 海豚用户名 + 海豚项目 code）。
3. ``/api/v1/rebuild/orchestration/scripts`` 与 ``.../scripts/{id}/content``
   节点表单「从脚本库选择」的脚本下拉与正文预览。
3b. ``/api/v1/rebuild/orchestration/workflow-definitions[/{code}[/release]]``
   工作流定义列表/上下线/删除（§10.5 B datara 自建页），代理海豚
   ``WorkflowDefinitionController``；画布本体的取数/保存由 iframe 内海豚 UI 自理。
3c. ``/api/v1/rebuild/orchestration/workflow-instances[...]`` 与
   ``.../task-instances[...]``
   运行监控（§10.5 B datara 自建页，§10.7 B1）：代理海豚
   ``WorkflowInstanceController`` / ``TaskInstanceController`` / ``LoggerController`` /
   ``ExecutorController``；海豚实例页本身不进 datara iframe（§10.10 R7）。
4. ``/api/v1/rebuild/orchestration/{worker-groups,environments,queues,clusters}``
   部署运维（§10.10 R1–R4）：代理海豚 Controller，worker 分组/环境按 owner
   隔离，队列/集群为全局资源仅 admin 可写。
4b. ``/api/v1/rebuild/orchestration/resources``（GET/POST/PUT/DELETE）与
   ``.../resources/download``
   部署运维（§10.10 R9 资源文件）：代理海豚 ``ResourcesController``，目录树按
   owner 裁剪，上传走 multipart、下载回二进制流。
5. ``POST|DELETE /api/v1/rebuild/orchestration/resources/{kind}/{key}/share``
   显式共享（按 datara 用户名授权可见）。
6. ``GET  /api/v1/rebuild/orchestration/monitor/*``
   监控中心（§10.11）：代理海豚 ``MonitorController`` 与 ``DataAnalysisController``，
   心跳 JSON 在后端解析并附离线判定，只读。
6b. ``/api/v1/rebuild/orchestration/alarm-rules``（GET/POST/PUT/DELETE）与
   ``.../alarm-records``
   告警桥接（§10.10 R6）：datara 项目级告警规则 CRUD 与触发记录查询；
   海豚告警组/实例/插件一律不接入，失败感知由 ``dispatch_alarm_scan``
   轮询海豚实例状态完成（``POST /internal/alarm/dispatch`` 为手动触发入口）。

内部通道契约（海豚 master/worker 调用，需固定内部令牌 + 网段白名单）：

7. ``GET  /internal/dbx/connections/{datasource_id}/params``
   海豚 master 组装 ``DataSourceParameters``（§10.9 方案 A）。
8. ``GET  /internal/scripts/{resource_id}/content``
   海豚 worker 按 ``scriptId`` 取脚本正文（§10.8 M6）。

内部通道三重守卫：固定内部令牌 → 来源网段白名单 → 可选用户归属校验；
每次调用都落 ``rebuild_sec_access_log``。
"""

from __future__ import annotations

import hmac
import base64
import hashlib
import ipaddress
import json
import logging
import os
import secrets
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, File, Form, Header, Query, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from rebuild.dbx.access import DbxConnectionAccess
from rebuild.dbx.client import DbxClient, DbxError
from rebuild.identity.contracts import Permission, Role, authorize
from rebuild.identity.models import UserRecord
from rebuild.identity.repository import UserRepository
from rebuild.orchestration.alarm import (
    CHANNELS,
    CHANNEL_SYSTEM,
    TRIGGERS,
    TRIGGER_FAILURE,
    TRIGGER_TIMEOUT,
    OrchestrationAlarmRecord,
    OrchestrationAlarmRepository,
    OrchestrationAlarmRuleRecord,
    dispatch_alarm_scan,
)
from rebuild.orchestration.ds_client import DsClient, DsClientError
from rebuild.orchestration.governance import (
    KIND_CLUSTER,
    KIND_ENVIRONMENT,
    KIND_QUEUE,
    KIND_RESOURCE_FILE,
    KIND_TASK_GROUP,
    KIND_WORKER_GROUP,
    KINDS,
    OrchestrationResourceAccess,
)
from rebuild.project.models import ProjectRecord
from rebuild.project.repository import ProjectRepository
from rebuild.resources.models import ResourceRecord
from rebuild.resources.repository import ResourceDomainError, ResourceRepository
from rebuild.sec.service import SecService

logger = logging.getLogger(__name__)

INTERNAL_TOKEN_HEADER = "X-Datara-Internal-Token"
INTERNAL_USER_HEADER = "X-Datara-User"

DEFAULT_INTERNAL_CIDRS = (
    "127.0.0.0/8",
    "::1/128",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
)

# datara ``kind`` → 海豚 DbType 枚举名（§10.9 映射表；缺失即不支持，保存期报错）。
_DS_DB_TYPE_BY_KIND = {
    "mysql": "MYSQL", "postgres": "POSTGRESQL", "postgresql": "POSTGRESQL",
    "oracle": "ORACLE", "clickhouse": "CLICKHOUSE", "hive": "HIVE",
}

# 各 kind 的 JDBC 组装参数，对齐海豚 MySQL/PostgreSQL DataSourceProcessor。
_JDBC_SPEC = {
    "mysql": {
        "prefix": "jdbc:mysql://",
        "driver": "com.mysql.cj.jdbc.Driver",
        "validation_query": "select 1",
    },
    "postgresql": {
        "prefix": "jdbc:postgresql://",
        "driver": "org.postgresql.Driver",
        "validation_query": "select version()",
    },
    "postgres": {
        "prefix": "jdbc:postgresql://",
        "driver": "org.postgresql.Driver",
        "validation_query": "select version()",
    },
    "oracle": {
        "prefix": "jdbc:oracle:thin:@",
        "driver": "oracle.jdbc.OracleDriver",
        "validation_query": "select 1 from dual",
    },
    "clickhouse": {
        "prefix": "jdbc:clickhouse://",
        "driver": "com.clickhouse.jdbc.ClickHouseDriver",
        "validation_query": "select 1",
    },
    "hive": {
        "prefix": "jdbc:hive2://",
        "driver": "org.apache.hive.jdbc.HiveDriver",
        "validation_query": "select 1",
    },
}


def _error(status: int, code: str, msg: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"code": code, "msg": msg, "data": None})


def _ok(data: Any) -> dict[str, Any]:
    return {"code": 0, "msg": "success", "data": data}


def _internal_expected_token() -> str:
    return os.getenv("DATARA_INTERNAL_TOKEN", "").strip()


def _issue_ds_embed_token(*, user: str, project_code: str, project_id: int) -> str:
    secret = os.getenv("DATARA_DS_EMBED_SECRET", "")
    if len(secret.encode("utf-8")) < 32:
        raise ValueError("DATARA_DS_EMBED_SECRET must be at least 32 bytes")
    claims = {"u": user, "p": project_code, "d": project_id,
              "exp": int(time.time()) + 900, "jti": secrets.token_hex(8)}
    raw = json.dumps(claims, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=")
    signature = hmac.new(secret.encode("utf-8"), encoded, hashlib.sha256).digest()
    return f"{encoded.decode('ascii')}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode('ascii')}"


def _internal_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    raw = os.getenv("DATARA_INTERNAL_ALLOWED_CIDRS", "").strip()
    entries = [item.strip() for item in raw.split(",") if item.strip()] if raw else list(DEFAULT_INTERNAL_CIDRS)
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for entry in entries:
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            logger.warning("datara_internal_cidr_invalid entry=%s", entry)
    return tuple(networks)


def _internal_guard(request: Request, provided_token: str) -> JSONResponse | None:
    """内部通道守卫；返回 ``None`` 表示放行。"""
    expected = _internal_expected_token()
    if not expected:
        return _error(503, "ORCH_INTERNAL_DISABLED", "internal channel is not configured (DATARA_INTERNAL_TOKEN empty)")
    if not provided_token or not hmac.compare_digest(provided_token.encode("utf-8"), expected.encode("utf-8")):
        return _error(401, "ORCH_INTERNAL_TOKEN_INVALID", "internal token mismatch")
    host = request.client.host if request.client else ""
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return _error(403, "ORCH_INTERNAL_IP_DENIED", f"source address {host!r} is not allowed")
    if not any(address in network for network in _internal_networks()):
        return _error(403, "ORCH_INTERNAL_IP_DENIED", f"source address {host} is not allowed")
    return None


def _audit(
    session: Session,
    *,
    user_name: str,
    action: str,
    target: str,
    allowed: bool,
    reason: str,
    request: Request | None = None,
) -> None:
    """内部通道审计；审计失败不得影响主流程。"""
    try:
        SecService(session).record_access(
            user_name=user_name or "ds-internal",
            action=action,
            target=target,
            rows_seen=0,
            allowed=allowed,
            reason=reason,
            request_id=(request.headers.get("x-request-id", "") if request is not None else ""),
        )
        session.commit()
    except Exception as exc:  # noqa: BLE001 - 审计失败不阻断编排
        session.rollback()
        logger.warning("orchestration_audit_failed action=%s target=%s error=%s", action, target, type(exc).__name__)


def _connection_params(config: dict[str, Any], spec: dict[str, str]) -> dict[str, Any]:
    """按海豚 ``*ConnectionParam`` 结构组装 connectionParams（JSON 字符串化前）。"""
    address = f"{spec['prefix']}{config['host']}:{config['port']}"
    database = str(config["database"])
    jdbc_url = f"{address}/{database}"
    return {
        "jdbcUrl": jdbc_url,
        "address": address,
        "database": database,
        "user": config.get("username", ""),
        # 海豚 ``aes-enable: false`` 时密码按明文处理（PasswordUtils.decodePassword 直返）。
        "password": config.get("password", ""),
        "driverClassName": spec["driver"],
        "validationQuery": spec["validation_query"],
    }


def _ds_project_name(project: ProjectRecord) -> str:
    return f"datara-{project.id}-{project.name}"[:100]


# -- §10.10 部署运维载荷 ----------------------------------------------------

WORKER_GROUP_PAGE_SIZE = 500

HEARTBEAT_TIMEOUT_ENV = "DATARA_DS_HEARTBEAT_TIMEOUT_SECONDS"
DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 30.0

_DS_DATETIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f")
_DS_DATETIME_OUTPUT = "%Y-%m-%d %H:%M:%S"

ANALYSIS_NODE_TYPES = ("MASTER", "WORKER", "ALERT_SERVER")

# 运行监控（§10.5 B）：宿主 query 键 → 海豚 query 键的白名单映射。
# 只透传白名单内的过滤条件，避免把任意参数灌进海豚 Controller。
_INSTANCE_FILTER_KEYS = (
    ("search_val", "searchVal"),
    ("state_type", "stateType"),
    ("host", "host"),
    ("executor_name", "executorName"),
    ("start_date", "startDate"),
    ("end_date", "endDate"),
)
_TASK_INSTANCE_FILTER_KEYS = (
    ("search_val", "searchVal"),
    ("task_name", "taskName"),
    ("task_code", "taskCode"),
    ("state_type", "stateType"),
    ("host", "host"),
    ("executor_name", "executorName"),
    ("start_date", "startDate"),
    ("end_date", "endDate"),
)

# 实例控制（§10.5 B）：宿主只允许对实例做这几种动作，其余 ExecuteType 不下发。
_EXECUTE_TYPES = (
    "STOP",
    "PAUSE",
    "RECOVER_SUSPENDED_PROCESS",
    "START_FAILURE_TASK_PROCESS",
    "REPEAT_RUNNING",
)


class WorkerGroupPayload(BaseModel):
    name: str = ""
    addrList: str = ""
    description: str = ""


class EnvironmentPayload(BaseModel):
    name: str = ""
    config: str = ""
    description: str = ""
    workerGroups: list[str] = []


class QueuePayload(BaseModel):
    queue: str = ""
    queueName: str = ""


class ClusterPayload(BaseModel):
    name: str = ""
    config: str = ""
    description: str = ""


class TaskGroupPayload(BaseModel):
    name: str = ""
    description: str = ""
    groupSize: int = 100


class CreateTaskGroupPayload(TaskGroupPayload):
    """``POST /task-groups`` 的请求体：``projectId`` 用于解析海豚 ``projectCode``。"""

    projectId: int


class SharePayload(BaseModel):
    username: str


class ResourceFileRenamePayload(BaseModel):
    """``PUT /resources`` 的请求体：``fullName`` 定位，``name`` 为新名（无扩展名=目录）。"""

    fullName: str = ""
    name: str = ""


class StartWorkflowInstancePayload(BaseModel):
    """``POST /workflow-instances/start`` 的请求体（§10.7 B1 试运行 / 正式启动）。

    只收宿主自建的运行监控页需要的字段；``scheduleTime`` 由本层补空串占位
    （海豚 ``ExecutorController`` 该参数 ``required`` 但 ``START_PROCESS`` 分支
    不下传 master，见 ``TriggerWorkflowExecutorDelegate``）。

    字段名沿用 camelCase：``http.ts`` 只对查询串做 camel→snake，JSON 体原样下发，
    与本文件其余载荷（``addrList``/``workerGroups``）一致。
    """

    projectId: int
    workflowDefinitionCode: int
    dryRun: bool = False
    failureStrategy: str = "CONTINUE"
    warningType: str = "NONE"
    workerGroup: str = "default"
    tenantCode: str = "default"
    environmentCode: int = -1
    startParams: dict[str, Any] = {}
    startNodeList: str = ""


class ControlWorkflowInstancePayload(BaseModel):
    """``POST /workflow-instances/{id}/control`` 的请求体。

    ``executeType`` 取海豚 ``ExecuteType`` 原词：停止 = STOP、暂停 = PAUSE、
    恢复挂起 = RECOVER_SUSPENDED_PROCESS、失败重试 = START_FAILURE_TASK_PROCESS、
    重跑 = REPEAT_RUNNING（§10.5 B）。
    """

    projectId: int
    executeType: str


class AlarmRulePayload(BaseModel):
    """``POST /alarm-rules`` 的请求体：项目级告警规则（§10.10 R6）。

    字段名沿用 camelCase（``http.ts`` 只转查询串，JSON 体原样下发）。
    """

    projectId: int
    workflowDefinitionCode: int = 0
    trigger: str = TRIGGER_FAILURE
    channel: str = CHANNEL_SYSTEM
    timeoutMinutes: int | None = None
    enabled: bool = True


class AlarmRuleUpdatePayload(BaseModel):
    """``PUT /alarm-rules/{id}`` 的请求体：全部字段可选，缺省即不改动。"""

    channel: str | None = None
    enabled: bool | None = None
    timeoutMinutes: int | None = None
    workflowDefinitionCode: int | None = None


def _heartbeat_timeout_seconds() -> float:
    raw = os.getenv(HEARTBEAT_TIMEOUT_ENV, "").strip()
    if not raw:
        return DEFAULT_HEARTBEAT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        logger.warning("datara_ds_heartbeat_timeout_invalid value=%s", raw)
        return DEFAULT_HEARTBEAT_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_HEARTBEAT_TIMEOUT_SECONDS


def _parse_ds_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    for fmt in _DS_DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _parse_heartbeat(raw: Any) -> dict[str, Any]:
    """海豚 ``Server.heartBeatInfo`` 是 JSON 字符串；解析失败按空处理，不影响列表。"""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("datara_ds_heartbeat_unparsable")
        return {}
    return payload if isinstance(payload, dict) else {}


def _server_row(server: dict[str, Any], *, now: datetime, timeout_seconds: float) -> dict[str, Any]:
    """把海豚 ``Server`` + 心跳 JSON 拉平为 datara 监控中心可直接渲染的行。"""
    beat = _parse_heartbeat(server.get("heartBeatInfo"))
    last = _parse_ds_datetime(server.get("lastHeartbeatTime"))
    age = (now - last).total_seconds() if last is not None else None
    return {
        "id": server.get("id"),
        "host": server.get("host"),
        "port": server.get("port"),
        "serverDirectory": server.get("serverDirectory"),
        "createTime": server.get("createTime"),
        "lastHeartbeatTime": server.get("lastHeartbeatTime"),
        "heartbeatAgeSeconds": round(age, 1) if age is not None else None,
        "heartbeatState": "unknown" if age is None else ("online" if age <= timeout_seconds else "offline"),
        "serverStatus": beat.get("serverStatus"),
        # 海豚 3.4.3 的 ``BaseHeartBeat`` 不含 loadAverage，字段保留为 null 以固定前端契约。
        "cpuUsage": beat.get("cpuUsage"),
        "memoryUsage": beat.get("memoryUsage"),
        "diskUsage": beat.get("diskUsage"),
        "loadAverage": beat.get("loadAverage"),
        "jvmCpuUsage": beat.get("jvmCpuUsage"),
        "jvmMemoryUsage": beat.get("jvmMemoryUsage"),
        "jvmHeapUsed": beat.get("jvmHeapUsed"),
        "jvmHeapMax": beat.get("jvmHeapMax"),
        "jvmNonHeapUsed": beat.get("jvmNonHeapUsed"),
        "jvmNonHeapMax": beat.get("jvmNonHeapMax"),
        "processId": beat.get("processId"),
        "startTime": beat.get("startupTime"),
        "reportTime": beat.get("reportTime"),
        "workerGroup": beat.get("workerGroup"),
        "threadPoolUsage": beat.get("threadPoolUsage"),
        "workerHostWeight": beat.get("workerHostWeight"),
        "heartbeat": beat,
    }


def _analysis_window(start_date: str, end_date: str) -> tuple[str, str] | JSONResponse:
    """海豚统计端点的时间窗：默认当天 0 点至当前，显式入参按 ``yyyy-MM-dd HH:mm:ss`` 校验。"""
    now = datetime.now()
    start = _parse_ds_datetime(start_date) if start_date else now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = _parse_ds_datetime(end_date) if end_date else now
    if start is None:
        return _error(400, "ORCH_MONITOR_DATE_INVALID", f"start_date {start_date!r} is not a valid datetime")
    if end is None:
        return _error(400, "ORCH_MONITOR_DATE_INVALID", f"end_date {end_date!r} is not a valid datetime")
    if start > end:
        return _error(400, "ORCH_MONITOR_DATE_INVALID", "start_date must not be later than end_date")
    return start.strftime(_DS_DATETIME_OUTPUT), end.strftime(_DS_DATETIME_OUTPUT)



def build_orchestration_router(
    session_factory: sessionmaker[Session],
    token_service: Any,
    active_tokens: set[str],
    project_permission_error: Callable[..., JSONResponse | None],
    ds_client_factory: Callable[[], DsClient] | None = None,
    dbx_client_factory: Callable[[], DbxClient] | None = None,
) -> APIRouter:
    router = APIRouter()
    make_ds_client = ds_client_factory or DsClient
    make_dbx_client = dbx_client_factory or DbxClient

    def principal(token: str, authorization: str) -> dict[str, Any] | None:
        raw = token or (authorization[7:] if authorization.startswith("Bearer ") else "")
        if not raw or raw not in active_tokens:
            return None
        try:
            claims = token_service.verify(raw)
        except ValueError:
            return None
        with session_factory() as session:
            if session.get(UserRecord, claims.get("user_id")) is None:
                return None
        return claims

    def unauthorized() -> JSONResponse:
        return _error(401, "1001", "invalid token")

    def require(claims: dict[str, Any], permission: Permission) -> JSONResponse | None:
        """角色级门禁；失败返回 403 信封。"""
        if authorize(claims.get("role"), permission):
            return None
        return _error(403, "1003", "permission denied")

    def ds_call(
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        form: dict[str, Any] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
    ) -> tuple[Any, JSONResponse | None]:
        """统一转调海豚；网络/业务失败一律收敛为 datara 信封，不抛给路由层。"""
        try:
            return make_ds_client().call(method, path, query=query, form=form, files=files), None
        except DsClientError as exc:
            return None, _error(exc.status, exc.code, exc.msg)

    def _is_admin(claims: dict[str, Any]) -> bool:
        return claims.get("role") == Role.ADMIN.value

    def _owner_view(claims: dict[str, Any]) -> tuple[int, bool]:
        return int(claims["user_id"]), _is_admin(claims)

    # -- 1. 数据源下拉真源 ---------------------------------------------------

    @router.get("/api/v1/rebuild/orchestration/datasources")
    def list_orchestration_datasources(
        project_id: int | None = Query(default=None),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        with session_factory() as session:
            repository = ProjectRepository(session)
            projects = (
                repository.list_all()
                if claims.get("role") == Role.ADMIN.value
                else repository.list_for_user(int(claims["user_id"]))
            )
            if project_id is not None:
                projects = [project for project in projects if project.id == project_id]
            visible_by_project = {
                project.id: DbxConnectionAccess(session).visible_ids(
                    project_id=project.id,
                    user_id=int(claims["user_id"]),
                    is_admin=_is_admin(claims),
                )
                for project in projects
            }
        if not visible_by_project:
            return _ok([])
        try:
            connections = make_dbx_client().list_connections()
        except DbxError:
            return _error(503, "ORCH_DBX_UNAVAILABLE", "dbx connections unavailable")
        items: list[dict[str, Any]] = []
        for project_id_value, visible_ids in visible_by_project.items():
            for connection in connections:
                connection_id = str(connection.get("id", ""))
                if not connection_id or (not _is_admin(claims) and connection_id not in visible_ids):
                    continue
                ds_type = _DS_DB_TYPE_BY_KIND.get(str(connection.get("db_type", "")).lower())
                if ds_type is None:
                    continue
                items.append({
                    "id": connection_id,
                    "name": connection.get("name", ""),
                    "type": ds_type,
                    "host": connection.get("host", ""),
                    "database": connection.get("database", ""),
                    "project_id": project_id_value,
                })
        return _ok(items)

    # -- 1b. 脚本库下拉与正文（节点表单「从脚本库选择」） ---------------------

    @router.get("/api/v1/rebuild/orchestration/scripts")
    def list_orchestration_scripts(
        project_id: int | None = Query(default=None),
        kind: str | None = Query(default=None),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        with session_factory() as session:
            repository = ProjectRepository(session)
            projects = (
                repository.list_all()
                if claims.get("role") == Role.ADMIN.value
                else repository.list_for_user(int(claims["user_id"]))
            )
            if project_id is not None:
                projects = [project for project in projects if project.id == project_id]
            resource_repository = ResourceRepository(session)
            items: list[dict[str, Any]] = []
            for project in projects:
                for meta in resource_repository.list_resources(project.id):
                    if kind is not None and meta["kind"] != kind:
                        continue
                    items.append({**meta, "project_id": project.id})
            return _ok(items)

    @router.get("/api/v1/rebuild/orchestration/scripts/{resource_id}/content")
    def orchestration_script_content(
        resource_id: int,
        version: int | None = Query(default=None),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        with session_factory() as session:
            row = session.get(ResourceRecord, resource_id)
            if row is None:
                return _error(404, "ORCH_SCRIPT_NOT_FOUND", f"script {resource_id} not found")
            denial = project_permission_error(session, row.project_id, claims, Permission.VIEW_ALL)
            if denial is not None:
                return denial
            target_version = version if version is not None else row.latest_version
            try:
                payload = ResourceRepository(session).read_version_text(row.project_id, resource_id, target_version)
            except ResourceDomainError as exc:
                return _error(exc.status, exc.code, exc.msg)
            return _ok({**payload, "kind": row.kind, "project_id": row.project_id})

    # -- 2. 会话载荷 ---------------------------------------------------------
    @router.get("/api/v1/rebuild/orchestration/session")
    def orchestration_session(
        project_id: int = Query(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        with session_factory() as session:
            denial = project_permission_error(session, project_id, claims, Permission.VIEW_ALL)
            if denial is not None:
                return denial
            project = session.get(ProjectRecord, project_id)
            if project is None:
                return _error(404, "ORCH_PROJECT_NOT_FOUND", f"project {project_id} not found")
            try:
                client = make_ds_client()
                ds_project = client.ensure_project(_ds_project_name(project), project.description or "")
            except DsClientError as exc:
                return _error(exc.status, exc.code, exc.msg)
            try:
                embed_token = _issue_ds_embed_token(
                    user=client.admin_user, project_code=str(ds_project.get("code", "")), project_id=project_id,
                )
            except ValueError:
                return _error(503, "ORCH_EMBED_DISABLED", "DolphinScheduler embed signing is not configured")
            payload = {
                "token": embed_token,
                # §10.3「海豚用户名映射由编排网关维护」：海豚侧只认已存在且启用的账号，
                # 未逐个开通的 datara 用户直接透传会被 LoginHandlerInterceptor 判 401。
                # 当前统一收敛到网关自身使用的海豚服务账号（与 ensure_project/ds_call 同源），
                # 逐用户 1:1 映射待海豚账号开通流程落地后在此处替换。
                "user": client.admin_user,
                # datara 项目 id：海豚侧任务组等 datara 项目级资源的归属键（§10.10 R8）。
                "projectId": project_id,
                "projectCode": str(ds_project.get("code", "")),
                "projectName": str(ds_project.get("name", "")),
                "apiBaseUrl": os.getenv("DATARA_PUBLIC_BASE_URL", "").rstrip("/"),
                "userToken": token or (authorization[7:] if authorization.startswith("Bearer ") else ""),
            }
            return _ok(payload)

    # -- 2b. 工作流定义列表（§10.5 B：datara 自建页，不进 iframe） -------------
    #
    # 列表/上下线/删除由 datara 页面承载（只调海豚 ``WorkflowDefinitionController``）；
    # 画布本体的取数/保存仍由 iframe 内海豚 UI 直连，不在此收口。

    def _workflow_definition_rows(
        claims: dict[str, Any],
        project_id: int,
        page_no: int,
        page_size: int,
        search_val: str,
    ) -> tuple[Any, JSONResponse | None]:
        project_code, error = _ds_project_code(claims, project_id)
        if error is not None:
            return None, error
        query: dict[str, Any] = {"pageNo": page_no, "pageSize": page_size}
        if search_val:
            query["searchVal"] = search_val
        payload, error = ds_call(
            "GET", f"/projects/{project_code}/workflow-definition", query=query
        )
        if error is not None:
            return None, error
        if not isinstance(payload, dict):
            return None, _error(502, "DS_WORKFLOW_DEFINITION_INVALID", "dolphinscheduler returned an unexpected paging payload")
        rows = payload.get("totalList")
        items = [
            {
                "code": row.get("code"),
                "name": row.get("name"),
                "state": row.get("state"),
                "releaseState": row.get("releaseState"),
                "scheduleReleaseState": row.get("scheduleReleaseState"),
                "createTime": row.get("createTime"),
                "updateTime": row.get("updateTime"),
                "description": row.get("description"),
                "userName": row.get("userName"),
                "projectName": row.get("projectName"),
                "executionType": row.get("executionType"),
            }
            for row in rows
            if isinstance(row, dict)
        ] if isinstance(rows, list) else []
        return (
            {
                "list": items,
                "total": payload.get("total", len(items)),
                "pageNo": page_no,
                "pageSize": page_size,
            },
            None,
        )

    @router.get("/api/v1/rebuild/orchestration/workflow-definitions")
    def list_workflow_definitions(
        project_id: int = Query(...),
        # wire 词形固定 snake_case：前端 ``http.ts`` 底座对 query 键统一做 camel→snake
        # 幂等转换，故此处不得再挂 camelCase alias（否则两段互斥、参数永不命中）。
        page_no: int = Query(default=1),
        page_size: int = Query(default=10),
        search_val: str = Query(default=""),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        if page_no < 1 or page_size < 1 or page_size > 200:
            return _error(400, "ORCH_INVALID_PAGE", "pageNo/pageSize out of range")
        data, error = _workflow_definition_rows(claims, project_id, page_no, page_size, search_val)
        if error is not None:
            return error
        return _ok(data)

    @router.post("/api/v1/rebuild/orchestration/workflow-definitions/{code}/release")
    def release_workflow_definition(
        code: int,
        project_id: int = Query(...),
        release_state: str = Query(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        if release_state not in ("ONLINE", "OFFLINE"):
            return _error(400, "ORCH_INVALID_RELEASE_STATE", "releaseState must be ONLINE or OFFLINE")
        project_code, error = _ds_project_code(claims, project_id)
        if error is not None:
            return error
        payload, error = ds_call(
            "POST",
            f"/projects/{project_code}/workflow-definition/{code}/release",
            query={"releaseState": release_state},
        )
        if error is not None:
            return error
        return _ok(payload)

    @router.delete("/api/v1/rebuild/orchestration/workflow-definitions/{code}")
    def delete_workflow_definition(
        code: int,
        project_id: int = Query(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        project_code, error = _ds_project_code(claims, project_id)
        if error is not None:
            return error
        payload, error = ds_call("DELETE", f"/projects/{project_code}/workflow-definition/{code}")
        if error is not None:
            return error
        return _ok(payload)

    # -- 2b-1. 项目工作流定时归集（海豚 SchedulerController） -----------------

    @router.get("/api/v1/rebuild/orchestration/workflow-schedules")
    def list_workflow_schedules(
        project_id: int = Query(...),
        page_no: int = Query(default=1),
        page_size: int = Query(default=10),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        if page_no < 1 or page_size < 1 or page_size > 200:
            return _error(400, "ORCH_INVALID_PAGE", "pageNo/pageSize out of range")
        project_code, error = _ds_project_code(claims, project_id)
        if error is not None:
            return error
        data, error = _paged_rows(
            f"/projects/{project_code}/schedules", page_no, page_size, {}, (),
        )
        if error is not None:
            return error
        return _ok(data)

    @router.post("/api/v1/rebuild/orchestration/workflow-schedules/{schedule_id}/{action}")
    def set_workflow_schedule_state(
        schedule_id: int,
        action: str,
        project_id: int = Query(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.TASK_WRITE)
        if denial is not None:
            return denial
        if schedule_id < 1 or action not in {"online", "offline"}:
            return _error(400, "ORCH_SCHEDULE_INVALID", "invalid schedule id or action")
        project_code, error = _ds_project_code(claims, project_id)
        if error is not None:
            return error
        payload, error = ds_call("POST", f"/projects/{project_code}/schedules/{schedule_id}/{action}")
        if error is not None:
            return error
        return _ok(payload)

    # -- 2c. 运行实例 / 任务实例 / 日志 / 启动与控制（§10.5 B，§10.7 B1） -----
    #
    # 运行监控页只调海豚 WorkflowInstanceController / TaskInstanceController /
    # LoggerController / ExecutorController；海豚实例页本身不进 datara iframe
    # （§10.10 R7）。海豚行形状（camelCase）已是稳定契约，本层原样透传，
    # 只做归属解析 + 参数白名单，不猜字段、不裁剪列。

    def _paged_rows(
        path: str,
        page_no: int,
        page_size: int,
        filters: dict[str, Any],
        key_map: tuple[tuple[str, str], ...],
        extra: dict[str, Any] | None = None,
    ) -> tuple[Any, JSONResponse | None]:
        """通用分页代理：白名单过滤键 + 直传过滤键 + ``totalList``/``total`` 收敛。

        ``extra`` 只接受调用方显式给定的海豚侧直传键（如 ``workflowDefinitionCode``），
        与 ``key_map`` 分开，避免把宿主参数名误当海豚参数名。
        """
        query: dict[str, Any] = {"pageNo": page_no, "pageSize": page_size}
        for source_key, ds_key in key_map:
            value = filters.get(source_key, "")
            if value not in ("", None):
                query[ds_key] = value
        if extra:
            query.update(extra)
        payload, error = ds_call("GET", path, query=query)
        if error is not None:
            return None, error
        if not isinstance(payload, dict):
            return None, _error(502, "DS_PAGING_INVALID", "dolphinscheduler returned an unexpected paging payload")
        rows = payload.get("totalList")
        items = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
        return (
            {
                "list": items,
                "total": payload.get("total", len(items)),
                "pageNo": page_no,
                "pageSize": page_size,
            },
            None,
        )

    def _instance_path(
        claims: dict[str, Any],
        project_id: int,
        instance_id: int,
        suffix: str = "",
    ) -> tuple[str | None, JSONResponse | None]:
        """解析实例在海豚侧的完整路径；``project_code`` 缺失/无权限一律收敛为信封。"""
        project_code, error = _ds_project_code(claims, project_id)
        if error is not None:
            return None, error
        return f"/projects/{project_code}/workflow-instances/{instance_id}{suffix}", None

    @router.get("/api/v1/rebuild/orchestration/workflow-instances")
    def list_workflow_instances(
        project_id: int = Query(...),
        page_no: int = Query(default=1),
        page_size: int = Query(default=10),
        workflow_definition_code: int | None = Query(default=None),
        search_val: str = Query(default=""),
        state_type: str = Query(default=""),
        host: str = Query(default=""),
        executor_name: str = Query(default=""),
        start_date: str = Query(default=""),
        end_date: str = Query(default=""),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        if page_no < 1 or page_size < 1 or page_size > 200:
            return _error(400, "ORCH_INVALID_PAGE", "pageNo/pageSize out of range")
        project_code, error = _ds_project_code(claims, project_id)
        if error is not None:
            return error
        data, error = _paged_rows(
            f"/projects/{project_code}/workflow-instances",
            page_no,
            page_size,
            {
                "search_val": search_val,
                "state_type": state_type,
                "host": host,
                "executor_name": executor_name,
                "start_date": start_date,
                "end_date": end_date,
            },
            _INSTANCE_FILTER_KEYS,
            # 0 = 海豚侧「不过滤」，故仅在有值时下发
            {"workflowDefinitionCode": workflow_definition_code} if workflow_definition_code else None,
        )
        if error is not None:
            return error
        return _ok(data)

    @router.get("/api/v1/rebuild/orchestration/workflow-instances/{instance_id}")
    def get_workflow_instance(
        instance_id: int,
        project_id: int = Query(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        path, error = _instance_path(claims, project_id, instance_id)
        if error is not None:
            return error
        data, error = ds_call("GET", path)
        if error is not None:
            return error
        return _ok(data)

    @router.get("/api/v1/rebuild/orchestration/workflow-instances/{instance_id}/tasks")
    def list_instance_tasks(
        instance_id: int,
        project_id: int = Query(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        path, error = _instance_path(claims, project_id, instance_id, "/tasks")
        if error is not None:
            return error
        data, error = ds_call("GET", path)
        if error is not None:
            return error
        return _ok(data)

    @router.get("/api/v1/rebuild/orchestration/workflow-instances/{instance_id}/gantt")
    def get_instance_gantt(
        instance_id: int,
        project_id: int = Query(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        path, error = _instance_path(claims, project_id, instance_id, "/view-gantt")
        if error is not None:
            return error
        data, error = ds_call("GET", path)
        if error is not None:
            return error
        return _ok(data)

    @router.get("/api/v1/rebuild/orchestration/workflow-instances/{instance_id}/variables")
    def get_instance_variables(
        instance_id: int,
        project_id: int = Query(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """变量桥只读查看（§10.7 D3）：回读海豚实例变量，供 datara 侧核对解析链。"""
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        path, error = _instance_path(claims, project_id, instance_id, "/view-variables")
        if error is not None:
            return error
        data, error = ds_call("GET", path)
        if error is not None:
            return error
        return _ok(data)

    @router.get("/api/v1/rebuild/orchestration/task-instances")
    def list_task_instances(
        project_id: int = Query(...),
        page_no: int = Query(default=1),
        page_size: int = Query(default=10),
        workflow_instance_id: int | None = Query(default=None),
        search_val: str = Query(default=""),
        task_name: str = Query(default=""),
        task_code: int | None = Query(default=None),
        state_type: str = Query(default=""),
        host: str = Query(default=""),
        executor_name: str = Query(default=""),
        start_date: str = Query(default=""),
        end_date: str = Query(default=""),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        if page_no < 1 or page_size < 1 or page_size > 200:
            return _error(400, "ORCH_INVALID_PAGE", "pageNo/pageSize out of range")
        project_code, error = _ds_project_code(claims, project_id)
        if error is not None:
            return error
        filters: dict[str, Any] = {
            "search_val": search_val,
            "task_name": task_name,
            "state_type": state_type,
            "host": host,
            "executor_name": executor_name,
            "start_date": start_date,
            "end_date": end_date,
        }
        if task_code is not None:
            filters["task_code"] = str(task_code)
        data, error = _paged_rows(
            f"/projects/{project_code}/task-instances",
            page_no,
            page_size,
            filters,
            _TASK_INSTANCE_FILTER_KEYS,
            # 0 = 海豚侧「不过滤」，故仅在有值时下发
            {"workflowInstanceId": workflow_instance_id} if workflow_instance_id else None,
        )
        if error is not None:
            return error
        return _ok(data)

    @router.get("/api/v1/rebuild/orchestration/task-instances/{task_instance_id}/log")
    def get_task_instance_log(
        task_instance_id: int,
        project_id: int = Query(...),
        skip_line_num: int = Query(default=0),
        limit: int = Query(default=200),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """任务实例日志（§10.7 B1）：海豚 LoggerController 不在 project 段下，
        故此处先做项目归属鉴权，再直连 ``/log/detail``。"""
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        if skip_line_num < 0 or limit < 1 or limit > 2000:
            return _error(400, "ORCH_INVALID_LOG_RANGE", "skipLineNum/limit out of range")
        _, error = _ds_project_code(claims, project_id)
        if error is not None:
            return error
        data, error = ds_call(
            "GET",
            "/log/detail",
            query={"taskInstanceId": task_instance_id, "skipLineNum": skip_line_num, "limit": limit},
        )
        if error is not None:
            return error
        # DS LoggerController 返回 {lineNum, message} —— message 含 \r\n 分行。
        # 前端期望 TaskInstanceLog[]（每行一个对象），这里做转换。
        start_line = int(data.get("lineNum", 0)) if isinstance(data, dict) else 0
        raw_msg = data.get("message", "") if isinstance(data, dict) else ""
        lines = raw_msg.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        logs = [
            {"lineNum": start_line + i, "message": ln}
            for i, ln in enumerate(lines)
        ]
        return _ok(logs)

    @router.post("/api/v1/rebuild/orchestration/workflow-instances/start")
    def start_workflow_instance(
        payload: StartWorkflowInstancePayload,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """启动实例（``dry_run=True`` = 试运行，§10.7 B1）。

        海豚 ``start-workflow-instance`` 的参数走 ``@RequestParam``，本层统一以
        query 透传（与海豚 UI 的 axios ``params`` 行为一致）。
        """
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.RUN_INSTANCE)
        if denial is not None:
            return denial
        if payload.failureStrategy not in ("CONTINUE", "END"):
            return _error(400, "ORCH_INVALID_FAILURE_STRATEGY", "failureStrategy must be CONTINUE or END")
        if payload.warningType not in ("NONE", "SUCCESS", "FAILURE", "ALL"):
            return _error(400, "ORCH_INVALID_WARNING_TYPE", "warningType must be NONE/SUCCESS/FAILURE/ALL")
        project_code, error = _ds_project_code(claims, payload.projectId)
        if error is not None:
            return error
        start_params = json.dumps(
            [{"prop": key, "value": value} for key, value in payload.startParams.items()],
            ensure_ascii=False,
        )
        data, error = ds_call(
            "POST",
            f"/projects/{project_code}/executors/start-workflow-instance",
            query={
                "workflowDefinitionCode": payload.workflowDefinitionCode,
                "scheduleTime": "",
                "failureStrategy": payload.failureStrategy,
                "warningType": payload.warningType,
                "startNodeList": payload.startNodeList,
                "workerGroup": payload.workerGroup,
                "tenantCode": payload.tenantCode,
                "environmentCode": payload.environmentCode,
                "startParams": start_params,
                "dryRun": 1 if payload.dryRun else 0,
            },
        )
        if error is not None:
            return error
        return _ok(data)

    @router.post("/api/v1/rebuild/orchestration/workflow-instances/{instance_id}/control")
    def control_workflow_instance(
        instance_id: int,
        payload: ControlWorkflowInstancePayload,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """实例控制（§10.5 B）：停止 / 暂停 / 恢复挂起 / 失败重试 / 重跑。"""
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.RUN_INSTANCE)
        if denial is not None:
            return denial
        if payload.executeType not in _EXECUTE_TYPES:
            return _error(
                400,
                "ORCH_INVALID_EXECUTE_TYPE",
                f"executeType must be one of {', '.join(_EXECUTE_TYPES)}",
            )
        project_code, error = _ds_project_code(claims, payload.projectId)
        if error is not None:
            return error
        data, error = ds_call(
            "POST",
            f"/projects/{project_code}/executors/execute",
            query={"workflowInstanceId": instance_id, "executeType": payload.executeType},
        )
        if error is not None:
            return error
        return _ok(data)

    # -- 3. 部署运维：运行资源与环境配置（§10.10） ----------------------------
    #
    # 统一形态：浏览器侧只认 datara 信封；海豚 Controller 的路径/参数形态由本层
    # 直传。业务键取海豚侧稳定标识（worker 分组用 name，环境/集群用 code，队列用
    # id 字符串），归属表据此隔离。

    def _visible_rows(
        claims: dict[str, Any],
        kind: str,
        items: list[dict[str, Any]],
        *,
        key_of: Callable[[dict[str, Any]], str],
        extra_of: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """按归属批量过滤并标注 ``ownerId`` / ``canManage``。"""
        user_id, is_admin = _owner_view(claims)
        keys = [key_of(item) for item in items]
        with session_factory() as session:
            access = OrchestrationResourceAccess(session)
            owners = access.owners_of(kind, keys)
            visible = access.visible_keys(kind, keys, user_id, is_admin=is_admin)
            rows: list[dict[str, Any]] = []
            for item in items:
                key = key_of(item)
                if key not in visible:
                    continue
                rows.append(
                    {
                        "resourceKey": key,
                        "ownerId": owners.get(key),
                        "canManage": access.can_manage(kind, key, user_id, is_admin=is_admin),
                        **extra_of(item),
                    }
                )
            return rows

    def _ds_items(data: Any, container: str = "totalList") -> list[dict[str, Any]]:
        """海豚列表统一解包：``{totalList: [...]}`` 或裸数组。"""
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict) and isinstance(data.get(container), list):
            return [item for item in data[container] if isinstance(item, dict)]
        return []

    def _worker_group_rows(claims: dict[str, Any]) -> tuple[list[dict[str, Any]], JSONResponse | None]:
        # CONFIG 来源的分组 id 为 null 且不计入 total，故 total 只能取条目数。
        data, error = ds_call(
            "GET",
            "/worker-groups",
            query={"pageNo": 1, "pageSize": WORKER_GROUP_PAGE_SIZE, "searchVal": ""},
        )
        if error is not None:
            return [], error
        items = _ds_items(data)
        rows = _visible_rows(
            claims,
            KIND_WORKER_GROUP,
            items,
            key_of=lambda item: str(item.get("name") or ""),
            extra_of=lambda item: {
                "id": item.get("id"),
                "name": item.get("name"),
                "addrList": item.get("addrList"),
                "description": item.get("description"),
                "systemDefault": bool(item.get("systemDefault")),
                "source": item.get("source"),
                "createTime": item.get("createTime"),
                "updateTime": item.get("updateTime"),
            },
        )
        return [row for row in rows if row["resourceKey"]], None

    def _find_worker_group(claims: dict[str, Any], name: str) -> tuple[dict[str, Any] | None, JSONResponse | None]:
        rows, error = _worker_group_rows(claims)
        if error is not None:
            return None, error
        for row in rows:
            if row["name"] == name:
                return row, None
        return None, _error(404, "ORCH_WORKER_GROUP_NOT_FOUND", f"worker group {name!r} not found")

    @router.get("/api/v1/rebuild/orchestration/worker-groups")
    def list_worker_groups(
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        rows, error = _worker_group_rows(claims)
        if error is not None:
            return error
        return _ok(rows)

    @router.post("/api/v1/rebuild/orchestration/worker-groups")
    def create_worker_group(
        payload: WorkerGroupPayload,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.EDIT_DEFINITION)
        if denial is not None:
            return denial
        name = payload.name.strip()
        if not name:
            return _error(400, "ORCH_WORKER_GROUP_NAME_REQUIRED", "worker group name is required")
        data, error = ds_call(
            "POST",
            "/worker-groups",
            form={"name": name, "addrList": payload.addrList, "description": payload.description},
        )
        if error is not None:
            return error
        with session_factory() as session:
            try:
                OrchestrationResourceAccess(session).claim(KIND_WORKER_GROUP, name, int(claims["user_id"]))
            except PermissionError:
                session.rollback()
                return _error(409, "ORCH_WORKER_GROUP_OWNED", f"worker group {name!r} is already owned by another user")
            session.commit()
        return _ok(data)

    @router.put("/api/v1/rebuild/orchestration/worker-groups/{name}")
    def update_worker_group(
        name: str,
        payload: WorkerGroupPayload,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.EDIT_DEFINITION)
        if denial is not None:
            return denial
        current, error = _find_worker_group(claims, name)
        if error is not None:
            return error
        assert current is not None
        if current["id"] is None:
            return _error(
                400,
                "ORCH_WORKER_GROUP_READONLY",
                f"worker group {name!r} is sourced from dolphinscheduler config and cannot be modified",
            )
        new_name = payload.name.strip() or name
        data, error = ds_call(
            "POST",
            "/worker-groups",
            form={
                "id": current["id"],
                "name": new_name,
                "addrList": payload.addrList or current["addrList"] or "",
                "description": payload.description,
            },
        )
        if error is not None:
            return error
        if new_name != name:
            with session_factory() as session:
                access = OrchestrationResourceAccess(session)
                access.release(KIND_WORKER_GROUP, name)
                try:
                    access.claim(KIND_WORKER_GROUP, new_name, int(claims["user_id"]))
                except PermissionError:
                    session.rollback()
                    return _error(409, "ORCH_WORKER_GROUP_OWNED", f"worker group {new_name!r} is already owned by another user")
                session.commit()
        return _ok(data)

    @router.delete("/api/v1/rebuild/orchestration/worker-groups/{name}")
    def delete_worker_group(
        name: str,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.EDIT_DEFINITION)
        if denial is not None:
            return denial
        current, error = _find_worker_group(claims, name)
        if error is not None:
            return error
        assert current is not None
        if current["id"] is None:
            return _error(
                400,
                "ORCH_WORKER_GROUP_READONLY",
                f"worker group {name!r} is sourced from dolphinscheduler config and cannot be deleted",
            )
        _, error = ds_call("DELETE", f"/worker-groups/{current['id']}")
        if error is not None:
            return error
        with session_factory() as session:
            OrchestrationResourceAccess(session).release(KIND_WORKER_GROUP, name)
            session.commit()
        return _ok({"name": name})

    def _environment_rows(claims: dict[str, Any]) -> tuple[list[dict[str, Any]], JSONResponse | None]:
        data, error = ds_call("GET", "/environment/query-environment-list")
        if error is not None:
            return [], error
        items = _ds_items(data)
        rows = _visible_rows(
            claims,
            KIND_ENVIRONMENT,
            items,
            key_of=lambda item: str(item.get("code") or ""),
            extra_of=lambda item: {
                "id": item.get("id"),
                "code": item.get("code"),
                "name": item.get("name"),
                "config": item.get("config"),
                "description": item.get("description"),
                "workerGroups": item.get("workerGroups") or [],
                "createTime": item.get("createTime"),
                "updateTime": item.get("updateTime"),
            },
        )
        return [row for row in rows if row["resourceKey"]], None

    @router.get("/api/v1/rebuild/orchestration/environments")
    def list_environments(
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        rows, error = _environment_rows(claims)
        if error is not None:
            return error
        return _ok(rows)

    @router.post("/api/v1/rebuild/orchestration/environments")
    def create_environment(
        payload: EnvironmentPayload,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.EDIT_DEFINITION)
        if denial is not None:
            return denial
        if not payload.name.strip():
            return _error(400, "ORCH_ENVIRONMENT_NAME_REQUIRED", "environment name is required")
        data, error = ds_call(
            "POST",
            "/environment/create",
            form={
                "name": payload.name.strip(),
                "config": payload.config,
                "description": payload.description,
                # 海豚按 JSON 数组字符串解析 workerGroups，裸名会被判为非法格式。
                "workerGroups": json.dumps(list(payload.workerGroups or []), ensure_ascii=False),
            },
        )
        if error is not None:
            return error
        code = str(data.get("code") if isinstance(data, dict) else "")
        with session_factory() as session:
            try:
                OrchestrationResourceAccess(session).claim(KIND_ENVIRONMENT, code, int(claims["user_id"]))
            except PermissionError:
                session.rollback()
                return _error(409, "ORCH_ENVIRONMENT_OWNED", f"environment {code!r} is already owned by another user")
            session.commit()
        return _ok({"code": data.get("code") if isinstance(data, dict) else data})

    @router.put("/api/v1/rebuild/orchestration/environments/{code}")
    def update_environment(
        code: str,
        payload: EnvironmentPayload,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.EDIT_DEFINITION)
        if denial is not None:
            return denial
        data, error = ds_call(
            "POST",
            "/environment/update",
            form={
                "code": code,
                "name": payload.name.strip(),
                "config": payload.config,
                "description": payload.description,
                "workerGroups": json.dumps(list(payload.workerGroups or []), ensure_ascii=False),
            },
        )
        if error is not None:
            return error
        return _ok({"code": code})

    @router.delete("/api/v1/rebuild/orchestration/environments/{code}")
    def delete_environment(
        code: str,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.EDIT_DEFINITION)
        if denial is not None:
            return denial
        _, error = ds_call("POST", "/environment/delete", form={"environmentCode": code})
        if error is not None:
            return error
        with session_factory() as session:
            OrchestrationResourceAccess(session).release(KIND_ENVIRONMENT, code)
            session.commit()
        return _ok({"code": code})

    def _queue_rows(claims: dict[str, Any]) -> tuple[list[dict[str, Any]], JSONResponse | None]:
        data, error = ds_call("GET", "/queues/list")
        if error is not None:
            return [], error
        items = _ds_items(data)
        rows = _visible_rows(
            claims,
            KIND_QUEUE,
            items,
            key_of=lambda item: str(item.get("id") or ""),
            extra_of=lambda item: {
                "id": item.get("id"),
                "queue": item.get("queue"),
                "queueName": item.get("queueName"),
                "createTime": item.get("createTime"),
                "updateTime": item.get("updateTime"),
            },
        )
        return [row for row in rows if row["resourceKey"]], None

    @router.get("/api/v1/rebuild/orchestration/queues")
    def list_queues(
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        rows, error = _queue_rows(claims)
        if error is not None:
            return error
        return _ok(rows)

    @router.post("/api/v1/rebuild/orchestration/queues")
    def create_queue(
        payload: QueuePayload,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        # 队列是全局资源配置：仅 admin 可写，其他角色只在节点表单选用。
        denial = require(claims, Permission.MANAGE_USER)
        if denial is not None:
            return denial
        if not payload.queue.strip() or not payload.queueName.strip():
            return _error(400, "ORCH_QUEUE_FIELDS_REQUIRED", "queue and queueName are required")
        data, error = ds_call(
            "POST",
            "/queues",
            form={"queue": payload.queue.strip(), "queueName": payload.queueName.strip()},
        )
        if error is not None:
            return error
        with session_factory() as session:
            try:
                OrchestrationResourceAccess(session).claim(KIND_QUEUE, str(data.get("id")), int(claims["user_id"]))
            except PermissionError:
                session.rollback()
                return _error(409, "ORCH_QUEUE_OWNED", "queue is already owned by another user")
            session.commit()
        return _ok(data)

    @router.put("/api/v1/rebuild/orchestration/queues/{queue_id}")
    def update_queue(
        queue_id: str,
        payload: QueuePayload,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.MANAGE_USER)
        if denial is not None:
            return denial
        data, error = ds_call(
            "PUT",
            f"/queues/{queue_id}",
            form={"queue": payload.queue.strip(), "queueName": payload.queueName.strip()},
        )
        if error is not None:
            return error
        return _ok(data)

    @router.delete("/api/v1/rebuild/orchestration/queues/{queue_id}")
    def delete_queue(
        queue_id: str,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.MANAGE_USER)
        if denial is not None:
            return denial
        _, error = ds_call("DELETE", f"/queues/{queue_id}")
        if error is not None:
            return error
        with session_factory() as session:
            OrchestrationResourceAccess(session).release(KIND_QUEUE, queue_id)
            session.commit()
        return _ok({"id": queue_id})

    def _cluster_rows(claims: dict[str, Any]) -> tuple[list[dict[str, Any]], JSONResponse | None]:
        data, error = ds_call("GET", "/cluster/query-cluster-list")
        if error is not None:
            return [], error
        items = _ds_items(data)
        rows = _visible_rows(
            claims,
            KIND_CLUSTER,
            items,
            key_of=lambda item: str(item.get("code") or ""),
            extra_of=lambda item: {
                "id": item.get("id"),
                "code": item.get("code"),
                "name": item.get("name"),
                "config": item.get("config"),
                "description": item.get("description"),
                "createTime": item.get("createTime"),
                "updateTime": item.get("updateTime"),
            },
        )
        return [row for row in rows if row["resourceKey"]], None

    @router.get("/api/v1/rebuild/orchestration/clusters")
    def list_clusters(
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        rows, error = _cluster_rows(claims)
        if error is not None:
            return error
        return _ok(rows)

    @router.post("/api/v1/rebuild/orchestration/clusters")
    def create_cluster(
        payload: ClusterPayload,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.MANAGE_USER)
        if denial is not None:
            return denial
        if not payload.name.strip():
            return _error(400, "ORCH_CLUSTER_NAME_REQUIRED", "cluster name is required")
        data, error = ds_call(
            "POST",
            "/cluster/create",
            form={"name": payload.name.strip(), "config": payload.config, "description": payload.description},
        )
        if error is not None:
            return error
        with session_factory() as session:
            try:
                OrchestrationResourceAccess(session).claim(
                    KIND_CLUSTER, str(data.get("code") if isinstance(data, dict) else ""), int(claims["user_id"])
                )
            except PermissionError:
                session.rollback()
                return _error(409, "ORCH_CLUSTER_OWNED", "cluster is already owned by another user")
            session.commit()
        return _ok(data)

    @router.put("/api/v1/rebuild/orchestration/clusters/{code}")
    def update_cluster(
        code: str,
        payload: ClusterPayload,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.MANAGE_USER)
        if denial is not None:
            return denial
        data, error = ds_call(
            "POST",
            "/cluster/update",
            form={"code": code, "name": payload.name.strip(), "config": payload.config, "description": payload.description},
        )
        if error is not None:
            return error
        return _ok(data)

    @router.delete("/api/v1/rebuild/orchestration/clusters/{code}")
    def delete_cluster(
        code: str,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.MANAGE_USER)
        if denial is not None:
            return denial
        _, error = ds_call("POST", "/cluster/delete", form={"clusterCode": code})
        if error is not None:
            return error
        with session_factory() as session:
            OrchestrationResourceAccess(session).release(KIND_CLUSTER, code)
            session.commit()
        return _ok({"code": code})

    # 任务组是项目级资源（§10.10 R8）：列表必须按 datara 项目解析出的
    # ``projectCode`` 收敛，不接受前端任意传码；归属键取海豚自增 ``id``。
    def _task_group_rows(claims: dict[str, Any], project_id: int) -> tuple[list[dict[str, Any]], JSONResponse | None]:
        project_code, error = _ds_project_code(claims, project_id)
        if error is not None:
            return [], error
        data, error = ds_call(
            "GET",
            "/task-group/query-list-by-projectCode",
            query={"pageNo": 1, "pageSize": WORKER_GROUP_PAGE_SIZE, "projectCode": project_code},
        )
        if error is not None:
            return [], error
        items = _ds_items(data)
        rows = _visible_rows(
            claims,
            KIND_TASK_GROUP,
            items,
            key_of=lambda item: str(item.get("id") or ""),
            extra_of=lambda item: {
                "id": item.get("id"),
                "projectCode": item.get("projectCode"),
                "name": item.get("name"),
                "description": item.get("description"),
                "groupSize": item.get("groupSize"),
                "status": item.get("status"),
                "createTime": item.get("createTime"),
                "updateTime": item.get("updateTime"),
            },
        )
        return [row for row in rows if row["resourceKey"]], None

    @router.get("/api/v1/rebuild/orchestration/task-groups")
    def list_task_groups(
        project_id: int = Query(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        rows, error = _task_group_rows(claims, project_id)
        if error is not None:
            return error
        return _ok(rows)

    @router.post("/api/v1/rebuild/orchestration/task-groups")
    def create_task_group(
        payload: CreateTaskGroupPayload,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.EDIT_DEFINITION)
        if denial is not None:
            return denial
        name = payload.name.strip()
        if not name:
            return _error(400, "ORCH_TASK_GROUP_NAME_REQUIRED", "task group name is required")
        project_code, error = _ds_project_code(claims, payload.projectId)
        if error is not None:
            return error
        data, error = ds_call(
            "POST",
            "/task-group/create",
            form={
                "name": name,
                "projectCode": project_code,
                "description": payload.description,
                "groupSize": payload.groupSize,
            },
        )
        if error is not None:
            return error
        task_group_id = str(data.get("id") if isinstance(data, dict) else "")
        with session_factory() as session:
            try:
                OrchestrationResourceAccess(session).claim(KIND_TASK_GROUP, task_group_id, int(claims["user_id"]))
            except PermissionError:
                session.rollback()
                return _error(409, "ORCH_TASK_GROUP_OWNED", f"task group {task_group_id!r} is already owned by another user")
            session.commit()
        return _ok(data)

    @router.put("/api/v1/rebuild/orchestration/task-groups/{task_group_id}")
    def update_task_group(
        task_group_id: str,
        payload: TaskGroupPayload,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.EDIT_DEFINITION)
        if denial is not None:
            return denial
        try:
            group_id = int(task_group_id)
        except ValueError:
            return _error(400, "ORCH_TASK_GROUP_ID_INVALID", f"task group id {task_group_id!r} is not a number")
        if not payload.name.strip():
            return _error(400, "ORCH_TASK_GROUP_NAME_REQUIRED", "task group name is required")
        user_id, is_admin = _owner_view(claims)
        with session_factory() as session:
            if not OrchestrationResourceAccess(session).can_manage(
                KIND_TASK_GROUP, task_group_id, user_id, is_admin=is_admin
            ):
                return _error(
                    403, "ORCH_TASK_GROUP_FORBIDDEN", f"only the owner of task group {task_group_id!r} can modify it"
                )
        data, error = ds_call(
            "POST",
            "/task-group/update",
            form={
                "id": group_id,
                "name": payload.name.strip(),
                "description": payload.description,
                "groupSize": payload.groupSize,
            },
        )
        if error is not None:
            return error
        return _ok(data)

    @router.delete("/api/v1/rebuild/orchestration/task-groups/{task_group_id}")
    def delete_task_group(
        task_group_id: str,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.EDIT_DEFINITION)
        if denial is not None:
            return denial
        try:
            group_id = int(task_group_id)
        except ValueError:
            return _error(400, "ORCH_TASK_GROUP_ID_INVALID", f"task group id {task_group_id!r} is not a number")
        user_id, is_admin = _owner_view(claims)
        with session_factory() as session:
            if not OrchestrationResourceAccess(session).can_manage(
                KIND_TASK_GROUP, task_group_id, user_id, is_admin=is_admin
            ):
                return _error(
                    403, "ORCH_TASK_GROUP_FORBIDDEN", f"only the owner of task group {task_group_id!r} can close it"
                )
        # 海豚 TaskGroupController 只提供 close-task-group/start-task-group，没有物理删除：
        # datara 侧的「删除」映射为关闭（停用），归属与共享同步释放。
        _, error = ds_call("POST", "/task-group/close-task-group", form={"id": group_id})
        if error is not None:
            return error
        with session_factory() as session:
            OrchestrationResourceAccess(session).release(KIND_TASK_GROUP, task_group_id)
            session.commit()
        return _ok({"id": task_group_id})

    # -- 3b. 部署运维：显式共享 ----------------------------------------------

    @router.post("/api/v1/rebuild/orchestration/resources/{kind}/{resource_key}/share")
    def share_orchestration_resource(
        kind: str,
        resource_key: str,
        payload: SharePayload,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        if kind not in KINDS:
            return _error(
                400,
                "ORCH_RESOURCE_KIND_INVALID",
                f"kind must be one of {', '.join(KINDS)}",
            )
        user_id, is_admin = _owner_view(claims)
        username = payload.username.strip()
        if not username:
            return _error(400, "ORCH_SHARE_USERNAME_REQUIRED", "username is required")
        with session_factory() as session:
            access = OrchestrationResourceAccess(session)
            if not access.can_manage(kind, resource_key, user_id, is_admin=is_admin):
                return _error(403, "ORCH_SHARE_FORBIDDEN", f"only the owner of {kind} {resource_key!r} can share it")
            target = UserRepository(session).find_by_username(username)
            if target is None:
                return _error(404, "ORCH_SHARE_USER_NOT_FOUND", f"user {username!r} not found")
            access.share(kind, resource_key, target.id)
            session.commit()
        return _ok({"kind": kind, "resourceKey": resource_key, "userId": target.id})

    @router.delete("/api/v1/rebuild/orchestration/resources/{kind}/{resource_key}/share")
    def unshare_orchestration_resource(
        kind: str,
        resource_key: str,
        username: str = Query(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        if kind not in KINDS:
            return _error(400, "ORCH_RESOURCE_KIND_INVALID", f"kind must be one of {', '.join(KINDS)}")
        user_id, is_admin = _owner_view(claims)
        username = username.strip()
        with session_factory() as session:
            access = OrchestrationResourceAccess(session)
            if not access.can_manage(kind, resource_key, user_id, is_admin=is_admin):
                return _error(403, "ORCH_SHARE_FORBIDDEN", f"only the owner of {kind} {resource_key!r} can share it")
            target = UserRepository(session).find_by_username(username)
            if target is None:
                return _error(404, "ORCH_SHARE_USER_NOT_FOUND", f"user {username!r} not found")
            access.unshare(kind, resource_key, target.id)
            session.commit()
        return _ok({"kind": kind, "resourceKey": resource_key, "userId": target.id})

    # -- 3d. 部署运维：资源文件（§10.10 R9） --------------------------------
    #
    # 海豚 ``ResourcesController`` 契约（datara 只暴露 FILE 类型）：
    #   目录树   GET    /resources/list?type=FILE      -> List<ResourceComponent>
    #   建目录   POST   /resources/directory            (type/name/currentDir)
    #   上传     POST   /resources                      (type/name/currentDir + multipart file)
    #   重命名   PUT    /resources                      (fullName/name；无扩展名=目录)
    #   删除     DELETE /resources?fullName=            (目录递归删除)
    #   下载     GET    /resources/download?fullName=   (二进制流，不解包)
    # 归属键取海豚 ``fullName``（相对路径）；全局资源：admin 全见，其他用户仅
    # 自己 + 显式共享，与 worker 分组/环境同规则。

    RESOURCE_FILE_TYPE = "FILE"

    def _resource_file_nodes() -> tuple[list[dict[str, Any]], JSONResponse | None]:
        data, error = ds_call("GET", "/resources/list", query={"type": RESOURCE_FILE_TYPE})
        if error is not None:
            return [], error
        return _ds_items(data), None

    def _flatten_resource_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        flat: list[dict[str, Any]] = []
        for node in nodes:
            flat.append(node)
            children = node.get("children")
            if isinstance(children, list):
                flat.extend(_flatten_resource_nodes([item for item in children if isinstance(item, dict)]))
        return flat

    def _resource_key(node: dict[str, Any]) -> str:
        return str(node.get("fullName") or "")

    def _visible_resource_tree(
        claims: dict[str, Any], nodes: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """按 owner 规则裁剪目录树：目录本身无归属，随可见子节点保留。"""
        user_id, is_admin = _owner_view(claims)
        keys = [key for key in (_resource_key(node) for node in _flatten_resource_nodes(nodes)) if key]
        with session_factory() as session:
            visible = OrchestrationResourceAccess(session).visible_keys(
                KIND_RESOURCE_FILE, keys, user_id, is_admin=is_admin
            )

        def keep(node: dict[str, Any]) -> dict[str, Any] | None:
            children = [
                child
                for child in (
                    keep(item) for item in node.get("children") or [] if isinstance(item, dict)
                )
                if child is not None
            ]
            if _resource_key(node) in visible or children:
                return {**node, "children": children}
            return None

        return [row for row in (keep(node) for node in nodes) if row is not None]

    def _claim_resource_file(
        claims: dict[str, Any], name: str, current_dir: str
    ) -> JSONResponse | None:
        """写操作后按海豚实际 ``fullName`` 登记归属（不猜路径分隔符）。"""
        nodes, error = _resource_file_nodes()
        if error is not None:
            return error
        candidates = [node for node in _flatten_resource_nodes(nodes) if str(node.get("name") or "") == name]
        if current_dir:
            preferred = [
                node for node in candidates if str(node.get("currentDir") or "") == current_dir
            ]
            candidates = preferred or candidates
        if not candidates:
            return None
        key = _resource_key(candidates[0])
        if not key:
            return None
        with session_factory() as session:
            try:
                OrchestrationResourceAccess(session).claim(
                    KIND_RESOURCE_FILE, key, int(claims["user_id"])
                )
            except PermissionError:
                session.rollback()
                return _error(
                    409,
                    "ORCH_RESOURCE_FILE_OWNED",
                    f"resource {key!r} is already owned by another user",
                )
            session.commit()
        return None

    @router.get("/api/v1/rebuild/orchestration/resources")
    def list_resource_files(
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        nodes, error = _resource_file_nodes()
        if error is not None:
            return error
        return _ok(_visible_resource_tree(claims, nodes))

    @router.post("/api/v1/rebuild/orchestration/resources")
    async def create_resource_file(
        name: str = Form(...),
        current_dir: str = Form(default="/"),
        file: UploadFile | None = File(default=None),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        """无 ``file`` = 建目录；带 ``file`` = 上传文件（multipart 直转海豚）。"""
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.EDIT_DEFINITION)
        if denial is not None:
            return denial
        resource_name = name.strip()
        if not resource_name:
            return _error(400, "ORCH_RESOURCE_FILE_NAME_REQUIRED", "resource name is required")
        # 海豚 ``AbstractResourceTransformer`` 只接受 ``/``（根）或租户资源根前缀，
        # 空串会被判为 ILLEGAL_RESOURCE_PATH，故此处收敛为根目录。
        parent = current_dir.strip() or "/"
        if file is None:
            _, error = ds_call(
                "POST",
                "/resources/directory",
                form={"type": RESOURCE_FILE_TYPE, "name": resource_name, "currentDir": parent},
            )
        else:
            content = await file.read()
            _, error = ds_call(
                "POST",
                "/resources",
                form={"type": RESOURCE_FILE_TYPE, "name": resource_name, "currentDir": parent},
                files={
                    "file": (
                        file.filename or resource_name,
                        content,
                        file.content_type or "application/octet-stream",
                    )
                },
            )
        if error is not None:
            return error
        claim_error = _claim_resource_file(claims, resource_name, parent)
        if claim_error is not None:
            return claim_error
        return _ok({"name": resource_name, "currentDir": parent})

    @router.put("/api/v1/rebuild/orchestration/resources")
    def rename_resource_file(
        payload: ResourceFileRenamePayload,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.EDIT_DEFINITION)
        if denial is not None:
            return denial
        full_name = payload.fullName.strip()
        new_name = payload.name.strip()
        if not full_name:
            return _error(400, "ORCH_RESOURCE_FILE_PATH_REQUIRED", "fullName is required")
        if not new_name:
            return _error(400, "ORCH_RESOURCE_FILE_NAME_REQUIRED", "name is required")
        user_id, is_admin = _owner_view(claims)
        with session_factory() as session:
            if not OrchestrationResourceAccess(session).can_manage(
                KIND_RESOURCE_FILE, full_name, user_id, is_admin=is_admin
            ):
                return _error(
                    403,
                    "ORCH_RESOURCE_FILE_FORBIDDEN",
                    f"only the owner of resource {full_name!r} can rename it",
                )
        _, error = ds_call("PUT", "/resources", form={"fullName": full_name, "name": new_name})
        if error is not None:
            return error
        parent = full_name.rsplit("/", 1)[0] if "/" in full_name else ""
        with session_factory() as session:
            OrchestrationResourceAccess(session).release_prefix(KIND_RESOURCE_FILE, full_name)
            session.commit()
        claim_error = _claim_resource_file(claims, new_name, parent)
        if claim_error is not None:
            return claim_error
        return _ok({"fullName": f"{parent}/{new_name}" if parent else new_name, "name": new_name})

    @router.delete("/api/v1/rebuild/orchestration/resources")
    def delete_resource_file(
        full_name: str = Query(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.EDIT_DEFINITION)
        if denial is not None:
            return denial
        if not full_name.strip():
            return _error(400, "ORCH_RESOURCE_FILE_PATH_REQUIRED", "full_name is required")
        user_id, is_admin = _owner_view(claims)
        with session_factory() as session:
            if not OrchestrationResourceAccess(session).can_manage(
                KIND_RESOURCE_FILE, full_name, user_id, is_admin=is_admin
            ):
                return _error(
                    403,
                    "ORCH_RESOURCE_FILE_FORBIDDEN",
                    f"only the owner of resource {full_name!r} can delete it",
                )
        _, error = ds_call("DELETE", "/resources", query={"fullName": full_name})
        if error is not None:
            return error
        with session_factory() as session:
            OrchestrationResourceAccess(session).release_prefix(KIND_RESOURCE_FILE, full_name)
            session.commit()
        return _ok({"fullName": full_name})

    @router.get("/api/v1/rebuild/orchestration/resources/download")
    def download_resource_file(
        full_name: str = Query(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        user_id, is_admin = _owner_view(claims)
        with session_factory() as session:
            if not OrchestrationResourceAccess(session).can_view(
                KIND_RESOURCE_FILE, full_name, user_id, is_admin=is_admin
            ):
                return _error(
                    403,
                    "ORCH_RESOURCE_FILE_FORBIDDEN",
                    f"resource {full_name!r} is not visible to you",
                )
        try:
            content, content_type = make_ds_client().download(
                "/resources/download", query={"fullName": full_name}
            )
        except DsClientError as exc:
            return _error(exc.status, exc.code, exc.msg)
        filename = full_name.rsplit("/", 1)[-1] or "resource"
        return Response(
            content=content,
            media_type=content_type or "application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # -- 3c. 监控中心（§10.11） ----------------------------------------------
    #
    # 具体路由必须先于 ``/monitor/{node_type}`` 注册，否则会被通配路径截获。

    @router.get("/api/v1/rebuild/orchestration/monitor/databases")
    def monitor_databases(
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        data, error = ds_call("GET", "/monitor/databases")
        if error is not None:
            return error
        rows = _ds_items(data)
        return _ok([{**row, "state": str(row.get("state") or "").upper()} for row in rows])

    @router.get("/api/v1/rebuild/orchestration/monitor/masters/workflow-executors")
    def monitor_master_workflow_executors(
        master_address: str = Query(default=""),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        data, error = ds_call("GET", "/monitor/masters/workflow-executors", query={"masterAddress": master_address})
        if error is not None:
            return error
        return _ok(_ds_items(data))

    @router.get("/api/v1/rebuild/orchestration/monitor/workers/task-executors")
    def monitor_worker_task_executors(
        server_address: str = Query(default=""),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        data, error = ds_call("GET", "/monitor/workers/task-executors", query={"serverAddress": server_address})
        if error is not None:
            return error
        return _ok(_ds_items(data))

    def _ds_project_code(claims: dict[str, Any], project_id: int) -> tuple[Any, JSONResponse | None]:
        """解析 datara 项目对应的海豚 ``projectCode``；权限与幂等建项都在此收敛。"""
        with session_factory() as session:
            denial = project_permission_error(session, project_id, claims, Permission.VIEW_ALL)
            if denial is not None:
                return None, denial
            project = session.get(ProjectRecord, project_id)
            if project is None:
                return None, _error(404, "ORCH_PROJECT_NOT_FOUND", f"project {project_id} not found")
            try:
                ds_project = make_ds_client().ensure_project(_ds_project_name(project), project.description or "")
            except DsClientError as exc:
                return None, _error(exc.status, exc.code, exc.msg)
        if not isinstance(ds_project, dict):
            return None, _error(502, "DS_PROJECT_INVALID", "dolphinscheduler returned an unexpected project payload")
        return ds_project.get("code"), None

    def _analysis_rows(
        claims: dict[str, Any],
        path: str,
        *,
        project_id: int,
        start_date: str,
        end_date: str,
    ) -> tuple[Any, JSONResponse | None]:
        """海豚 ``DataAnalysisController`` 代理：projectCode 由 datara 项目解析，拒绝前端任意值。"""
        project_code, error = _ds_project_code(claims, project_id)
        if error is not None:
            return None, error
        window = _analysis_window(start_date, end_date)
        if isinstance(window, JSONResponse):
            return None, window
        start, end = window
        return ds_call("GET", path, query={"projectCode": project_code, "startDate": start, "endDate": end})

    @router.get("/api/v1/rebuild/orchestration/monitor/task-state-count")
    def monitor_task_state_count(
        project_id: int = Query(...),
        start_date: str = Query(default=""),
        end_date: str = Query(default=""),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        data, error = _analysis_rows(
            claims, "/projects/analysis/task-state-count", project_id=project_id, start_date=start_date, end_date=end_date
        )
        if error is not None:
            return error
        return _ok(data)

    @router.get("/api/v1/rebuild/orchestration/monitor/workflow-state-count")
    def monitor_workflow_state_count(
        project_id: int = Query(...),
        start_date: str = Query(default=""),
        end_date: str = Query(default=""),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        data, error = _analysis_rows(
            claims,
            "/projects/analysis/workflow-state-count",
            project_id=project_id,
            start_date=start_date,
            end_date=end_date,
        )
        if error is not None:
            return error
        return _ok(data)

    @router.get("/api/v1/rebuild/orchestration/monitor/define-user-count")
    def monitor_define_user_count(
        project_id: int = Query(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        project_code, error = _ds_project_code(claims, project_id)
        if error is not None:
            return error
        data, error = ds_call("GET", "/projects/analysis/define-user-count", query={"projectCode": project_code})
        if error is not None:
            return error
        return _ok(data)

    @router.get("/api/v1/rebuild/orchestration/monitor/{node_type}")
    def monitor_servers(
        node_type: str,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        resolved = node_type.upper()
        if resolved not in ANALYSIS_NODE_TYPES:
            return _error(
                400,
                "ORCH_MONITOR_NODE_TYPE_INVALID",
                f"node_type must be one of {', '.join(ANALYSIS_NODE_TYPES)}",
            )
        data, error = ds_call("GET", f"/monitor/{resolved}")
        if error is not None:
            return error
        timeout_seconds = _heartbeat_timeout_seconds()
        now = datetime.now()
        return _ok([_server_row(row, now=now, timeout_seconds=timeout_seconds) for row in _ds_items(data)])

    # -- 4. 内部：连接参数 ---------------------------------------------------

    @router.get("/internal/dbx/connections/{datasource_id}/params")
    def internal_connection_params(
        datasource_id: str,
        request: Request,
        project_id: int = Query(...),
        x_datara_internal_token: str = Header(default=""),
        x_datara_user: str = Header(default=""),
    ):
        denied = _internal_guard(request, x_datara_internal_token)
        if denied is not None:
            return denied
        target = f"dbx_connection:{datasource_id}"
        with session_factory() as session:
            project = session.get(ProjectRecord, project_id)
            user = UserRepository(session).find_by_username(x_datara_user.strip()) if x_datara_user.strip() else None
            visible = (
                project is not None
                and user is not None
                and datasource_id in DbxConnectionAccess(session).visible_ids(
                    project_id=project_id, user_id=user.id, is_admin=user.role == Role.ADMIN.value,
                )
            )
            if not visible:
                _audit(
                    session,
                    user_name=x_datara_user,
                    action="read_connection_params",
                    target=target,
                    allowed=False,
                    reason="connection_not_visible_to_executor",
                    request=request,
                )
                return _error(404, "ORCH_DATASOURCE_NOT_FOUND", "connection not found in project")
            try:
                config = make_dbx_client().internal_connection(datasource_id)
            except DbxError:
                _audit(session, user_name=x_datara_user, action="read_connection_params",
                       target=target, allowed=False, reason="dbx_unavailable", request=request)
                return _error(503, "ORCH_DBX_UNAVAILABLE", "dbx connection unavailable")
            kind = str(config.get("db_type", "")).lower()
            spec = _JDBC_SPEC.get(kind)
            if spec is None:
                _audit(
                    session,
                    user_name=x_datara_user,
                    action="read_connection_params",
                    target=target,
                    allowed=False,
                    reason="unsupported_dbx_type",
                    request=request,
                )
                return _error(
                    400,
                    "ORCH_DATASOURCE_UNSUPPORTED",
                    f"dbx connection type {kind!r} has no dolphinscheduler mapping",
                )
            if not config.get("host") or not config.get("port") or not config.get("database"):
                _audit(session, user_name=x_datara_user, action="read_connection_params",
                       target=target, allowed=False, reason="dbx_connection_incomplete", request=request)
                return _error(422, "ORCH_DATASOURCE_INCOMPLETE", "dbx connection is incomplete")
            params = _connection_params(config, spec)
            _audit(
                session,
                user_name=x_datara_user,
                action="read_connection_params",
                target=target,
                allowed=True,
                reason=f"kind={kind}",
                request=request,
            )
            return _ok(
                {
                    "type": _DS_DB_TYPE_BY_KIND[kind],
                    # 海豚 createConnectionParams(String connectionJson) 需要 JSON 字符串。
                    "connectionParams": json.dumps(params, ensure_ascii=False),
                }
            )

    # -- 4. 内部：脚本正文 ---------------------------------------------------

    @router.get("/internal/scripts/{resource_id}/content")
    def internal_script_content(
        resource_id: int,
        request: Request,
        version: int | None = Query(default=None),
        x_datara_internal_token: str = Header(default=""),
        x_datara_user: str = Header(default=""),
    ):
        denied = _internal_guard(request, x_datara_internal_token)
        if denied is not None:
            return denied
        target = f"script:{resource_id}"
        with session_factory() as session:
            row = session.get(ResourceRecord, resource_id)
            if row is None:
                _audit(
                    session,
                    user_name=x_datara_user,
                    action="read_script_content",
                    target=target,
                    allowed=False,
                    reason="script_not_found",
                    request=request,
                )
                return _error(404, "ORCH_SCRIPT_NOT_FOUND", f"script {resource_id} not found")
            target_version = version if version is not None else row.latest_version
            try:
                payload = ResourceRepository(session).read_version_text(row.project_id, resource_id, target_version)
            except ResourceDomainError as exc:
                _audit(
                    session,
                    user_name=x_datara_user,
                    action="read_script_content",
                    target=target,
                    allowed=False,
                    reason=exc.code,
                    request=request,
                )
                return _error(exc.status, exc.code, exc.msg)
            _audit(
                session,
                user_name=x_datara_user,
                action="read_script_content",
                target=target,
                allowed=True,
                reason=f"version={target_version}",
                request=request,
            )
            return _ok({**payload, "kind": row.kind, "project_id": row.project_id})

    # -- 5. 告警规则与触发记录（§10.10 R6 告警桥接） --------------------------

    def _alarm_rule_row(rule: OrchestrationAlarmRuleRecord) -> dict[str, Any]:
        return {
            "id": rule.id,
            "projectId": rule.project_id,
            "workflowDefinitionCode": rule.workflow_definition_code,
            "trigger": rule.trigger,
            "channel": rule.channel,
            "timeoutMinutes": rule.timeout_minutes,
            "enabled": rule.enabled,
            "ownerId": rule.owner_id,
            "createTime": rule.create_time.isoformat() if rule.create_time else "",
            "updateTime": rule.update_time.isoformat() if rule.update_time else "",
        }

    def _alarm_record_row(record: OrchestrationAlarmRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "ruleId": record.rule_id,
            "projectId": record.project_id,
            "instanceId": record.instance_id,
            "workflowDefinitionCode": record.workflow_definition_code,
            "trigger": record.trigger,
            "title": record.title,
            "content": record.content,
            "channel": record.channel,
            "state": record.state,
            "createTime": record.create_time.isoformat() if record.create_time else "",
        }

    def _validate_alarm_rule(
        *, trigger: str, channel: str, timeout_minutes: int | None
    ) -> JSONResponse | None:
        if trigger not in TRIGGERS:
            return _error(400, "ORCH_ALARM_TRIGGER_INVALID", f"trigger must be one of {', '.join(TRIGGERS)}")
        if channel not in CHANNELS:
            return _error(400, "ORCH_ALARM_CHANNEL_INVALID", f"channel must be one of {', '.join(CHANNELS)}")
        if trigger == TRIGGER_TIMEOUT and not timeout_minutes:
            return _error(422, "ORCH_ALARM_TIMEOUT_REQUIRED", "timeoutMinutes is required for the timeout trigger")
        if timeout_minutes is not None and timeout_minutes <= 0:
            return _error(422, "ORCH_ALARM_TIMEOUT_INVALID", "timeoutMinutes must be a positive integer")
        return None

    @router.get("/api/v1/rebuild/orchestration/alarm-rules")
    def list_alarm_rules(
        project_id: int = Query(...),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        with session_factory() as session:
            denial = project_permission_error(session, project_id, claims, Permission.VIEW_ALL)
            if denial is not None:
                return denial
            rules = OrchestrationAlarmRepository(session).list_rules(project_id)
            return _ok([_alarm_rule_row(rule) for rule in rules])

    @router.post("/api/v1/rebuild/orchestration/alarm-rules")
    def create_alarm_rule(
        payload: AlarmRulePayload,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.EDIT_DEFINITION)
        if denial is not None:
            return denial
        invalid = _validate_alarm_rule(
            trigger=payload.trigger, channel=payload.channel, timeout_minutes=payload.timeoutMinutes
        )
        if invalid is not None:
            return invalid
        with session_factory() as session:
            denial = project_permission_error(session, payload.projectId, claims, Permission.EDIT_DEFINITION)
            if denial is not None:
                return denial
            repository = OrchestrationAlarmRepository(session)
            if repository.find_rule(payload.projectId, payload.workflowDefinitionCode, payload.trigger) is not None:
                return _error(
                    409,
                    "ORCH_ALARM_RULE_DUPLICATE",
                    "a rule with the same workflow and trigger already exists",
                )
            rule = repository.create_rule(
                project_id=payload.projectId,
                workflow_definition_code=payload.workflowDefinitionCode,
                trigger=payload.trigger,
                channel=payload.channel,
                timeout_minutes=payload.timeoutMinutes,
                owner_id=int(claims["user_id"]),
            )
            rule.enabled = payload.enabled
            session.commit()
            return _ok(_alarm_rule_row(rule))

    @router.put("/api/v1/rebuild/orchestration/alarm-rules/{rule_id}")
    def update_alarm_rule(
        rule_id: int,
        payload: AlarmRuleUpdatePayload,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.EDIT_DEFINITION)
        if denial is not None:
            return denial
        with session_factory() as session:
            repository = OrchestrationAlarmRepository(session)
            rule = repository.get_rule(rule_id)
            if rule is None:
                return _error(404, "ORCH_ALARM_RULE_NOT_FOUND", f"alarm rule {rule_id} not found")
            denial = project_permission_error(session, rule.project_id, claims, Permission.EDIT_DEFINITION)
            if denial is not None:
                return denial
            if payload.channel is not None and payload.channel not in CHANNELS:
                return _error(400, "ORCH_ALARM_CHANNEL_INVALID", f"channel must be one of {', '.join(CHANNELS)}")
            timeout_minutes = rule.timeout_minutes if payload.timeoutMinutes is None else payload.timeoutMinutes
            invalid = _validate_alarm_rule(
                trigger=rule.trigger, channel=payload.channel or rule.channel, timeout_minutes=timeout_minutes
            )
            if invalid is not None:
                return invalid
            repository.update_rule(
                rule,
                channel=payload.channel,
                enabled=payload.enabled,
                timeout_minutes=payload.timeoutMinutes,
                workflow_definition_code=payload.workflowDefinitionCode,
            )
            session.commit()
            return _ok(_alarm_rule_row(rule))

    @router.delete("/api/v1/rebuild/orchestration/alarm-rules/{rule_id}")
    def delete_alarm_rule(
        rule_id: int,
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.EDIT_DEFINITION)
        if denial is not None:
            return denial
        with session_factory() as session:
            repository = OrchestrationAlarmRepository(session)
            rule = repository.get_rule(rule_id)
            if rule is None:
                return _error(404, "ORCH_ALARM_RULE_NOT_FOUND", f"alarm rule {rule_id} not found")
            denial = project_permission_error(session, rule.project_id, claims, Permission.EDIT_DEFINITION)
            if denial is not None:
                return denial
            repository.delete_rule(rule)
            session.commit()
            return _ok({"id": rule_id})

    @router.get("/api/v1/rebuild/orchestration/alarm-records")
    def list_alarm_records(
        project_id: int = Query(...),
        limit: int = Query(default=100, ge=1, le=500),
        token: str = Header(default=""),
        authorization: str = Header(default=""),
    ):
        claims = principal(token, authorization)
        if claims is None:
            return unauthorized()
        denial = require(claims, Permission.VIEW_ALL)
        if denial is not None:
            return denial
        with session_factory() as session:
            denial = project_permission_error(session, project_id, claims, Permission.VIEW_ALL)
            if denial is not None:
                return denial
            records = OrchestrationAlarmRepository(session).list_records(project_id, limit=limit)
            return _ok([_alarm_record_row(record) for record in records])

    @router.post("/internal/alarm/dispatch")
    def internal_alarm_dispatch(
        request: Request,
        x_datara_internal_token: str = Header(default=""),
        x_datara_user: str = Header(default=""),
    ):
        """手动触发一次失败感知扫描（默认由后台间隔任务调用）。"""
        denied = _internal_guard(request, x_datara_internal_token)
        if denied is not None:
            return denied
        try:
            counts = dispatch_alarm_scan(session_factory, make_ds_client)
        except Exception as exc:  # noqa: BLE001 - 扫描失败按内部通道错误回执
            logger.warning("alarm_dispatch_failed error=%s", type(exc).__name__)
            return _error(500, "ORCH_ALARM_DISPATCH_FAILED", "alarm dispatch failed")
        with session_factory() as session:
            _audit(
                session,
                user_name=x_datara_user,
                action="alarm_dispatch",
                target="orchestration_alarm",
                allowed=True,
                reason=f"rules={counts['rules']},sent={counts['sent']},failed={counts['failed']}",
                request=request,
            )
        return _ok(counts)

    return router
