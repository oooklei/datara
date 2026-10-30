"""datara ↔ dbx 数据源双入口双向同步适配层。

上行（datara → dbx）：数据源增删改后调用 :func:`push_datasource_to_dbx` 把记录
写入 dbx 连接；下行（dbx → datara）：定时调用 :func:`poll_dbx_connections` 拉取
含 datara 归属标记的连接并回灌 ``rebuild_project_datasource``。

冲突策略 E1b：``updatedAt`` 新者胜；dbx 侧连接用可扩展字段 ``external_config``
承载 datara 时间戳；缺失时降级四元组比对（name/host/port/database）且 datara 优先。
E1a：dbx 内非 datara 归属连接不导入 datara（靠 ``datara_ref`` 标记过滤）。
脱敏：password 不落盘、不入日志。

.. note:: 归属标记不能放在 dbx 的 ``url_params``：该字段是驱动 URL 查询串，
   MySQL/PG 驱动会拒绝未知参数（实测 ``datara_ref=...`` → 500
   ``Unknown connection URL parameter``）。``external_config`` 是不参与驱动
   校验的自由 JSON，且顶层键不被视为 inline secret，可安全承载标记。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import json
import logging
import urllib.request

from rebuild.datasource.contracts import DataSourceDraft
from rebuild.datasource.models import ProjectDatasourceRecord
from rebuild.datasource.repository import ProjectDatasourceRepository

logger = logging.getLogger(__name__)

DEFAULT_DBX_BASE_URL = "http://192.168.1.9:4224"
# dbx 以 DBX_PUBLIC_BASE_PATH=/ide 运行（Router 被 nest 到 /ide 下），
# 连接管理 API 自身挂在 /api 下，故完整路径为 /ide/api/connection/*。
DBX_BASE_PATH = "/ide/api"
DBX_LIST_PATH = f"{DBX_BASE_PATH}/connection/list"
DBX_SAVE_PATH = f"{DBX_BASE_PATH}/connection/save"
DBX_REF_KEY = "datara_ref"
DBX_UPDATED_AT_KEY = "datara_updated_at"
DBX_TIMEOUT_SECONDS = 10.0
MASK = "***"
_SHANGHAI = ZoneInfo("Asia/Shanghai")

# datara ``kind`` ↔ dbx ``db_type``：dbx 的 DatabaseType 由连接类型 yaml 生成，
# PostgreSQL 在 dbx 侧是 ``postgres``（不是 ``postgresql``）。
_DBX_DB_TYPE_BY_KIND = {"mysql": "mysql", "postgresql": "postgres"}
_KIND_BY_DBX_DB_TYPE = {"mysql": "mysql", "postgres": "postgresql"}

# (method, url, body_bytes, headers) -> parsed JSON object. 生产用 urllib，测试注入假传输。
Transport = Callable[[str, str, "bytes | None", dict[str, str]], dict[str, Any]]


def _now_shanghai() -> datetime:
    return datetime.now(_SHANGHAI).replace(tzinfo=None)


def _to_naive_shanghai(value: datetime) -> datetime:
    """把时间统一到 Asia/Shanghai 的 naive 墙钟时间，避免 aware/naive 比较歧义。"""
    if value.tzinfo is not None:
        return value.astimezone(_SHANGHAI).replace(tzinfo=None)
    return value


def _port_int(value: Any) -> Any:
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _http_request(
    base_url: str,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    timeout: float = DBX_TIMEOUT_SECONDS,
    transport: Transport | None = None,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + path
    data: bytes | None = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if transport is not None:
        return transport(method, url, data, headers)
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class DbxConnectionClient:
    """dbx 连接 HTTP 客户端（默认指向 192.168.1.9:4224）。"""

    def __init__(
        self,
        base_url: str = DEFAULT_DBX_BASE_URL,
        *,
        timeout: float = DBX_TIMEOUT_SECONDS,
        transport: Transport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport

    def list_connections(self) -> list[dict[str, Any]]:
        payload = self._request("GET", DBX_LIST_PATH)
        return _normalize_connection_list(payload)

    def save_connections(
        self, connections: list[dict[str, Any]], removed_ids: list[str]
    ) -> dict[str, Any]:
        # dbx 的 SaveConnectionsRequest 带 #[serde(rename_all = "camelCase")]：
        # 线上字段是 ``configs`` / ``removedIds``（不是 connections / removed_ids）。
        return self._request(
            "POST",
            DBX_SAVE_PATH,
            body={"configs": list(connections), "removedIds": list(removed_ids)},
        )

    def _request(
        self, method: str, path: str, *, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return _http_request(
            self.base_url, method, path, body=body, timeout=self.timeout, transport=self._transport
        )


def _normalize_connection_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("connections", "items", "data", "list"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _markers(connection: dict[str, Any]) -> dict[str, Any]:
    """读取承载在 ``external_config`` 里的 datara 归属标记。"""
    params = connection.get("external_config")
    return params if isinstance(params, dict) else {}


def _ref_of(connection: dict[str, Any]) -> str:
    return str(_markers(connection).get(DBX_REF_KEY, "") or "")


def _remote_timestamp(connection: dict[str, Any]) -> datetime | None:
    raw = _markers(connection).get(DBX_UPDATED_AT_KEY)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return _to_naive_shanghai(parsed)


def _four_tuple_local(record: ProjectDatasourceRecord) -> tuple[Any, Any, Any, Any]:
    return (record.name, record.host, _port_int(record.port), record.database_name)


def _four_tuple_remote(connection: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    return (
        connection.get("name"),
        connection.get("host"),
        _port_int(connection.get("port")),
        connection.get("database"),
    )


def resolve_conflict(local: ProjectDatasourceRecord, remote: dict[str, Any]) -> str:
    """返回 ``"local"`` / ``"remote"``，实现 E1b。

    双方都有 ``datara_updated_at`` 时按时间新者胜；任一缺失时降级四元组
    （name/host/port/database）比对——四元组一致视为同一连接，datara 优先
    （local）；不一致视为远端连接已变更，远端胜（remote）。
    """
    local_ts = _to_naive_shanghai(local.updated_at) if local.updated_at is not None else None
    remote_ts = _remote_timestamp(remote)
    if local_ts is not None and remote_ts is not None:
        return "remote" if remote_ts > local_ts else "local"
    if _four_tuple_local(local) == _four_tuple_remote(remote):
        return "local"
    return "remote"


def _record_to_connection(record: ProjectDatasourceRecord) -> dict[str, Any]:
    """datara 记录 → dbx 连接。``external_config`` 承载归属标记与 datara 时间戳。"""
    return {
        # 稳定 id 让 dbx 侧 upsert 幂等（datara 不直接沿用 dbx 自增 id）。
        "id": f"datara-{record.project_id}-{record.id}",
        "name": record.name,
        "db_type": _DBX_DB_TYPE_BY_KIND.get(record.kind, record.kind),
        "host": record.host,
        "port": record.port,
        "database": record.database_name,
        "username": record.username,
        "password": record.password,
        # 不能用 url_params：那是驱动 URL 查询串，MySQL/PG 驱动会拒绝未知参数。
        "external_config": {
            DBX_REF_KEY: f"{record.project_id}:{record.id}",
            DBX_UPDATED_AT_KEY: _now_shanghai().isoformat(),
        },
    }


def _remote_to_draft(remote: dict[str, Any]) -> DataSourceDraft:
    """dbx 连接 → datara 草稿。"""
    raw_kind = str(remote.get("db_type", remote.get("kind", ""))).strip().lower()
    return DataSourceDraft(
        name=str(remote.get("name", "")).strip(),
        kind=_KIND_BY_DBX_DB_TYPE.get(raw_kind, raw_kind),
        host=str(remote.get("host", "")).strip(),
        port=_port_int(remote.get("port")) or 0,
        database=str(remote.get("database", "")).strip(),
        username=str(remote.get("username", remote.get("user", ""))).strip(),
        password=str(remote.get("password", "") or ""),
    )


def _ref_datasource_id(connection: dict[str, Any]) -> int | None:
    tail = _ref_of(connection).partition(":")[2]
    try:
        return int(tail)
    except ValueError:
        return None


def _datara_owned_connections(client: DbxConnectionClient, prefix: str) -> list[dict[str, Any]]:
    """拉取 dbx 连接，过滤出 ``datara_ref`` 前缀匹配的项（E1a）。"""
    try:
        connections = client.list_connections()
    except Exception as exc:  # noqa: BLE001 - 下行失败不抛异常，记录后按空列表处理
        logger.warning("dbx_poll_list_failed prefix=%s error=%s", prefix, type(exc).__name__)
        return []
    return [connection for connection in connections if _ref_of(connection).startswith(prefix)]


def push_datasource_to_dbx(
    record: ProjectDatasourceRecord, *, client: DbxConnectionClient | None = None
) -> bool:
    """上行：把 datara 记录写入 dbx 连接。失败返回 False 并记日志，不抛异常。"""
    client = client or DbxConnectionClient()
    connection = _record_to_connection(record)
    try:
        client.save_connections([connection], removed_ids=[])
    except Exception as exc:  # noqa: BLE001 - 同步失败不应影响 datara 主流程
        logger.warning(
            "dbx_push_failed project_id=%s datasource_id=%s name=%s connection=%s error=%s",
            record.project_id,
            record.id,
            record.name,
            redact(connection),
            type(exc).__name__,
        )
        return False
    logger.info(
        "dbx_push_succeeded project_id=%s datasource_id=%s name=%s",
        record.project_id,
        record.id,
        record.name,
    )
    _SYNC_STATE_STORE.record(
        DbxSyncState(
            datasource_id=record.id,
            project_id=record.project_id,
            name=record.name,
            remote_key=str(connection.get("id", "")),
        )
    )
    return True


def poll_dbx_connections(
    project_id: int,
    *,
    client: DbxConnectionClient | None = None,
    session_factory: Any | None = None,
) -> int:
    """下行：把含 datara 归属标记的 dbx 连接回灌 datara，返回同步条数。

    - 不含 ``datara_ref`` 的连接一律跳过（不导入，E1a）；
    - 已存在的本地记录按 E1b 冲突策略决定是否用远端覆盖；
    - 本地缺失时按远端新建（回灌）；
    - ref 声明的 id 在本地不存在时，按 ``(project_id, name)`` 兜底 upsert：
      同名记录视为同一连接，按 E1b 决定是否覆盖，避免自增主键与 ref 声明
      id 不一致时重复建号并撞 ``uq_rebuild_project_datasource_name``；
    - 单条连接处理失败隔离：回滚后记录告警并跳过该条，不中断整个 project
      的下行同步。
    """
    if session_factory is None:
        raise ValueError("session_factory is required to poll dbx connections")
    client = client or DbxConnectionClient()
    prefix = f"{project_id}:"
    synced = 0
    with session_factory() as session:
        repository = ProjectDatasourceRepository(session)
        for remote in _datara_owned_connections(client, prefix):
            datasource_id = _ref_datasource_id(remote)
            if datasource_id is None:
                continue
            try:
                draft = _remote_to_draft(remote)
                local = repository.get(project_id, datasource_id)
                if local is None:
                    existing = repository.find_by_name(project_id, draft.name)
                    if existing is None:
                        repository.create(project_id, draft)
                        session.commit()
                        synced += 1
                        _record_poll_state(
                            datasource_id=datasource_id,
                            project_id=project_id,
                            name=draft.name,
                            remote_key=str(remote.get("id", "")),
                            conflict=False,
                        )
                    elif resolve_conflict(existing, remote) == "remote":
                        repository.update(existing, draft)
                        session.commit()
                        synced += 1
                        _record_poll_state(
                            datasource_id=datasource_id,
                            project_id=project_id,
                            name=draft.name,
                            remote_key=str(remote.get("id", "")),
                            conflict=True,
                        )
                elif resolve_conflict(local, remote) == "remote":
                    repository.update(local, draft)
                    session.commit()
                    synced += 1
                    _record_poll_state(
                        datasource_id=datasource_id,
                        project_id=project_id,
                        name=draft.name,
                        remote_key=str(remote.get("id", "")),
                        conflict=True,
                    )
            except Exception as exc:  # noqa: BLE001 - 单条失败隔离，不中断整个 project
                session.rollback()
                logger.warning(
                    "dbx_poll_connection_failed project_id=%s datasource_id=%s name=%s error=%s",
                    project_id,
                    datasource_id,
                    str(remote.get("name", "")),
                    type(exc).__name__,
                )
                continue
    return synced


@dataclass
class DbxSyncState:
    """单次同步的内存状态快照。

    当前仅驻留进程内存（进程重启即丢失）。如需跨重启去重或审计，可把本结构
    持久化到独立表（如 ``rebuild_datasource_dbx_sync_state``），以
    ``(project_id, datasource_id)`` 为唯一键——持久化属可选后续步骤。
    """

    datasource_id: int
    project_id: int
    name: str
    remote_key: str
    last_synced_at: datetime | None = None
    conflict_flag: bool = False


class DbxSyncStateStore:
    """``DbxSyncState`` 的进程内注册表（可选持久化）。"""

    def __init__(self) -> None:
        self._states: dict[tuple[int, int], DbxSyncState] = {}

    def record(self, state: DbxSyncState) -> None:
        state.last_synced_at = state.last_synced_at or _now_shanghai()
        self._states[(state.project_id, state.datasource_id)] = state

    def get(self, project_id: int, datasource_id: int) -> DbxSyncState | None:
        return self._states.get((project_id, datasource_id))

    def all(self) -> list[DbxSyncState]:
        return list(self._states.values())


_SYNC_STATE_STORE = DbxSyncStateStore()


def _record_poll_state(
    *,
    datasource_id: int,
    project_id: int,
    name: str,
    remote_key: str,
    conflict: bool,
) -> None:
    _SYNC_STATE_STORE.record(
        DbxSyncState(
            datasource_id=datasource_id,
            project_id=project_id,
            name=name,
            remote_key=remote_key,
            conflict_flag=conflict,
        )
    )


def redact(connection: dict[str, Any]) -> dict[str, Any]:
    """返回脱敏副本：敏感字段（password）以 ``***`` 替代，供日志/调试使用。"""
    redacted = dict(connection)
    if "password" in redacted:
        redacted["password"] = MASK
    return redacted
