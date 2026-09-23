"""数据源中心路由（I4 设计文档 §3.2）：CRUD / 连通测试 / 库表树 / 实例临时数据。

- 类型：mysql / greatdb（同驱动，MySQL 协议兼容）/ file（params JSON 参数）
  / 流源注册化（09-21）：kafka（params.brokers）、redis（host+port+pwd）、
  mqtt（host+port+user+pwd）、http（params.baseUrl+headers）
- 密码明文存储与回显（09-18 裁定：内部系统，加密取消）
- 删除保护：graph_json params 行（key=datasource/datasource_id）引用 → 409
- 文件路径双侧校验：resolve_file_path 收敛 /datara/files（防目录穿越）
- 连通测试原则：注册必测（业务可靠性），连接性验证在注册/测试时做，流任务启动只校验 status
"""

import re
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.auth import ApiError, get_current_user, require_perm
from common.db import get_db
from common.dsconn import (
    FILES_ROOT,
    FileSourceError,
    file_schema_preview,
    normalize_file_params,
    open_connection,
    quote_ident,
    resolve_file_path,
    test_connection,
)
from common.log import get_logger
from common.models import DataSource, TmpData, User, WfDefinition
from common.resp import DEP_UNAVAILABLE, DS_NOT_FOUND, PARAM_INVALID, TMP_NOT_FOUND, fmt_dt, ok
from common.tmpdata import clean_tmp_data

logger = get_logger("api.datasource")

router = APIRouter(tags=["datasource"])

_DS_TYPES = ("mysql", "greatdb", "file", "kafka", "redis", "mqtt", "http")
_SYSTEM_DBS = ("information_schema", "mysql", "performance_schema", "sys")
# graph_json 节点 data 引用形态（09-18 实测修正）：data 对象属性
# "datasource":"<name>"（C11/C15/C22 表单）与 "targetDs":"<name>"（C22 物化目标）；
# 数字值（按 id 引用）单独匹配
_REF_RE = re.compile(r'"(?:datasource|targetDs)"\s*:\s*"([^"]*)"')
_REF_ID_RE = re.compile(r'"(?:datasource|targetDs)"\s*:\s*(\d+)')


class DsBody(BaseModel):
    """数据源新建/编辑请求体（字段对齐前端 DataSource：db/group 为前端名）。"""

    name: str
    type: str
    host: Optional[str] = None
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    db: Optional[str] = None
    user: Optional[str] = None
    pwd: Optional[str] = None
    env: Optional[str] = None
    group: Optional[str] = None
    tags: Optional[List[str]] = None
    params: Optional[dict] = None


def _validate(db: Session, body: DsBody, exclude_id: Optional[int] = None) -> None:
    """新建/编辑校验：类型白名单、名称非重、连接型 host/port 必填、文件参数合法、流源参数齐备。"""
    ds_type = (body.type or "").strip().lower()
    if ds_type not in _DS_TYPES:
        raise ApiError(
            PARAM_INVALID,
            f"不支持的数据源类型: {body.type}（可选 mysql/greatdb/file/kafka/redis/mqtt/http）",
            status=400,
        )
    name = (body.name or "").strip()
    if not name:
        raise ApiError(PARAM_INVALID, "数据源名称不能为空", status=400)
    dup = db.query(DataSource).filter(DataSource.name == name)
    if exclude_id is not None:
        dup = dup.filter(DataSource.id != exclude_id)
    if dup.first() is not None:
        raise ApiError(PARAM_INVALID, f"数据源名称已存在: {name}", status=400)
    params = dict(body.params or {})
    if ds_type in ("mysql", "greatdb"):
        if not (body.host or "").strip():
            raise ApiError(PARAM_INVALID, "连接型数据源 host 必填", status=400)
        if body.port is None:
            raise ApiError(PARAM_INVALID, "连接型数据源 port 必填", status=400)
    elif ds_type == "kafka":
        if not _parse_brokers(params.get("brokers")):
            raise ApiError(PARAM_INVALID, "Kafka 数据源 brokers 必填（host:port，逗号分隔多个）", status=400)
    elif ds_type == "redis":
        if not (body.host or "").strip() or body.port is None:
            raise ApiError(PARAM_INVALID, "Redis 数据源 host/port 必填", status=400)
    elif ds_type == "mqtt":
        if not (body.host or "").strip() or body.port is None:
            raise ApiError(PARAM_INVALID, "MQTT 数据源 host/port 必填", status=400)
    elif ds_type == "http":
        base = str(params.get("baseUrl") or "").strip()
        if not base.lower().startswith(("http://", "https://")):
            raise ApiError(PARAM_INVALID, "HTTP 数据源 baseUrl 必填且以 http(s):// 开头", status=400)
    else:  # file：params 形状校验 + 路径收敛校验（不触盘，存在性归连通测试）
        try:
            spec = normalize_file_params(body.params)
            resolve_file_path(spec.path)
        except FileSourceError as exc:
            raise ApiError(PARAM_INVALID, str(exc), status=400) from exc


def _user_map(db: Session) -> dict:
    return {u.id: u.user_name for u in db.query(User.id, User.user_name).all()}


def _payload(row: DataSource, user_map: dict) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "type": row.type,
        "host": row.host,
        "port": row.port,
        "db": row.db_name,
        "user": row.user,
        "pwd": row.pwd,  # 明文回显（09-18 裁定）
        "env": row.env,
        "group": row.group_name,
        "tags": row.tags or [],
        "params": row.params,
        "status": row.status,
        "owner": user_map.get(row.owner_id, ""),
        "createdAt": fmt_dt(row.create_time),
        "updateTime": fmt_dt(row.update_time),
    }


def _reference_count(db: Session, ds: DataSource) -> int:
    """扫 graph_json 引用数（按定义数计；名称或 id 命中均算）。"""
    count = 0
    for (graph,) in db.query(WfDefinition.graph_json).all():
        if not graph:
            continue
        refs = [m.group(1) for m in _REF_RE.finditer(graph)]
        refs += [m.group(1) for m in _REF_ID_RE.finditer(graph)]
        if ds.name in refs or str(ds.id) in refs:
            count += 1
            break
    return count


@router.get("/datasources")
def list_datasources(
    keyword: Optional[str] = None,
    env: Optional[str] = None,
    group: Optional[str] = None,
    ds_type: Optional[str] = Query(None, alias="type"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """数据源列表（keyword/env/group/type 筛选；pwd 明文回显——裁定）。"""
    query = db.query(DataSource)
    if keyword:
        query = query.filter(DataSource.name.like(f"%{keyword}%"))
    if env:
        query = query.filter(DataSource.env == env)
    if group:
        query = query.filter(DataSource.group_name == group)
    if ds_type:
        query = query.filter(DataSource.type == ds_type)
    rows = query.order_by(DataSource.id).all()
    user_map = _user_map(db)
    return ok([_payload(row, user_map) for row in rows])


@router.post("/datasources")
def create_datasource(
    body: DsBody,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """新建数据源（owner=当前用户；status 置空待首次测试）。"""
    _validate(db, body)
    row = DataSource(
        name=body.name.strip(),
        type=body.type.strip().lower(),
        host=(body.host or "").strip() or None,
        port=body.port,
        db_name=(body.db or "").strip() or None,
        user=(body.user or "").strip() or None,
        pwd=body.pwd or "",
        env=(body.env or "").strip() or None,
        group_name=(body.group or "").strip() or None,
        tags=body.tags or [],
        params=body.params,
        owner_id=user.id,
    )
    db.add(row)
    db.commit()
    logger.info("新建数据源: %s (type=%s)（操作人 %s）", row.name, row.type, user.user_name)
    return ok(_payload(row, {user.id: user.user_name}))


@router.put("/datasources/{ds_id}")
def update_datasource(
    ds_id: int,
    body: DsBody,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """编辑数据源（全量覆盖；status 保留原值；pwd 留空则保持原密码）。"""
    row = db.get(DataSource, ds_id)
    if row is None:
        raise ApiError(DS_NOT_FOUND, status=404)
    _validate(db, body, exclude_id=ds_id)
    row.name = body.name.strip()
    row.type = body.type.strip().lower()
    row.host = (body.host or "").strip() or None
    row.port = body.port
    row.db_name = (body.db or "").strip() or None
    row.user = (body.user or "").strip() or None
    if body.pwd:
        row.pwd = body.pwd
    row.env = (body.env or "").strip() or None
    row.group_name = (body.group or "").strip() or None
    row.tags = body.tags or []
    row.params = body.params
    db.commit()
    logger.info("编辑数据源: id=%s %s（操作人 %s）", ds_id, row.name, user.user_name)
    return ok(True)


@router.delete("/datasources/{ds_id}")
def delete_datasource(
    ds_id: int,
    user: User = Depends(require_perm("edit_definition")),
    db: Session = Depends(get_db),
):
    """删除数据源（被工作流引用时 409）。"""
    row = db.get(DataSource, ds_id)
    if row is None:
        raise ApiError(DS_NOT_FOUND, status=404)
    refs = _reference_count(db, row)
    if refs:
        raise ApiError(PARAM_INVALID, f"数据源被 {refs} 个工作流定义引用，无法删除", status=409)
    db.delete(row)
    db.commit()
    logger.info("删除数据源: id=%s %s（操作人 %s）", ds_id, row.name, user.user_name)
    return ok(True)


# ---------- 流源连通测试（kafka / redis / mqtt / http，09-21 注册化） ----------

def _parse_brokers(raw) -> List[tuple]:
    """brokers 串（"h1:9092,h2:9092"）→ [(host, port)]；缺省端口 9092；非法项跳过。"""
    out: List[tuple] = []
    for b in str(raw or "").split(","):
        b = b.strip()
        if not b:
            continue
        host, _, port = b.partition(":")
        host = host.strip()
        if not host:
            continue
        try:
            out.append((host, int(port or 9092)))
        except ValueError:
            continue
    return out


def _tcp_probe(host: str, port: int, timeout: float = 5.0) -> None:
    """TCP 可达性探测（协议级测试的兜底；失败抛 ValueError 可读原因）。"""
    import socket

    try:
        socket.create_connection((host, port), timeout=timeout).close()
    except OSError as exc:
        raise ValueError(f"TCP {host}:{port} 不可达: {exc}") from exc


def _test_kafka(row: DataSource) -> str:
    """Kafka：先 TCP 探测（快速失败），kafka-python 可用再拉元数据（协议级验证）。"""
    brokers = _parse_brokers((row.params or {}).get("brokers"))
    if not brokers:
        raise ValueError("brokers 未配置")
    for h, p in brokers:
        _tcp_probe(h, p)  # 任一不可达即 ValueError（5s 超时）
    try:
        from kafka import KafkaConsumer
    except ImportError:
        return f"连通成功（TCP {brokers[0][0]}:{brokers[0][1]} 可达；kafka-python 未安装，仅探测可达性）"
    try:
        consumer = KafkaConsumer(bootstrap_servers=[f"{h}:{p}" for h, p in brokers])
        try:
            topics = len(consumer.topics())
        finally:
            consumer.close()
        return f"连通成功（元数据获取正常，{topics} 个 topic）"
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Kafka 元数据获取失败: {exc}") from exc


def _test_redis(row: DataSource) -> str:
    """Redis：PING；redis 包不可用退 TCP。url 由 host/port/pwd/params.db 组装。"""
    try:
        import redis as redis_sync
    except ImportError:
        _tcp_probe(row.host, int(row.port))
        return f"连通成功（TCP {row.host}:{row.port} 可达；redis 未安装，仅探测可达性）"
    client = redis_sync.Redis.from_url(
        f"redis://{row.host}:{row.port}/{int((row.params or {}).get('db') or 0)}",
        password=row.pwd or None,
        decode_responses=True,
        socket_connect_timeout=5,
    )
    try:
        client.ping()
        return "连通成功（PING PONG）"
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Redis 连接失败: {exc}") from exc
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass


def _test_mqtt(row: DataSource) -> str:
    """MQTT：paho connect 后即断开（CONNACK 视为在线）；不可用退 TCP。"""
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        _tcp_probe(row.host, int(row.port))
        return f"连通成功（TCP {row.host}:{row.port} 可达；paho-mqtt 未安装，仅探测可达性）"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv311)
    if row.user or row.pwd:
        client.username_pw_set(row.user or "", row.pwd or "")
    try:
        client.connect(row.host, int(row.port), keepalive=30)
        client.disconnect()
        return f"连通成功（MQTT {row.host}:{row.port} CONNACK）"
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"MQTT 连接失败: {exc}") from exc
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass


def _test_http(row: DataSource) -> str:
    """HTTP：探测 baseUrl（默认 GET，2xx/3xx 在线）；鉴权头一并携带。"""
    import requests

    params = row.params or {}
    base = str(params.get("baseUrl") or "").strip()
    headers = {str(k): str(v) for k, v in (params.get("headers") or {}).items() if str(k).strip()}
    try:
        resp = requests.request(
            str(params.get("probeMethod") or "GET"), base, headers=headers or None, timeout=8,
            allow_redirects=True,
        )
    except requests.RequestException as exc:
        raise ValueError(f"HTTP 请求失败: {exc}") from exc
    if resp.status_code >= 400:
        raise ValueError(f"HTTP {resp.status_code}: {resp.text[:120]}")
    return f"连通成功（HTTP {resp.status_code}）"


@router.post("/datasources/{ds_id}/test")
def test_datasource(
    ds_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """连通测试：连接型 connect+SELECT 1；文件型 可读+解析头 5 行；流源协议级探测。status 回写。"""
    row = db.get(DataSource, ds_id)
    if row is None:
        raise ApiError(DS_NOT_FOUND, status=404)
    start = time.monotonic()
    detail: dict = {}
    try:
        if row.type == "file":
            spec = normalize_file_params(row.params)
            path = resolve_file_path(spec.path)
            if not path.is_file():
                raise FileSourceError(f"文件不存在: {spec.path}")
            schema, _ = file_schema_preview(spec, sample_limit=5, preview_limit=0)
            cols = len(schema.get("columns") or [])
            detail = {"columns": cols}
            msg = f"文件可读，解析 {cols} 列"
        elif row.type == "kafka":
            msg = _test_kafka(row)
        elif row.type == "redis":
            msg = _test_redis(row)
        elif row.type == "mqtt":
            msg = _test_mqtt(row)
        elif row.type == "http":
            msg = _test_http(row)
        else:
            test_connection(row)
            msg = "连通成功（SELECT 1）"
        status = "online"
    except Exception as exc:  # noqa: BLE001 任何失败均记 offline 并回显原因
        status = "offline"
        msg = str(exc)[:500]
    elapsed = int((time.monotonic() - start) * 1000)
    row.status = status
    db.commit()
    logger.info(
        "数据源连通测试: %s(%s) → %s %dms（操作人 %s）", row.name, row.type, status, elapsed, user.user_name
    )
    return ok({"status": status, "elapsedMs": elapsed, "message": msg, **detail})


@router.get("/datasources/files")
def list_data_files(user: User = Depends(get_current_user)):
    """共享卷 /datara/files 文件清单（注册向导文件源路径选择器；相对 posix 路径，含子目录）。"""
    root = FILES_ROOT
    files: list[str] = []
    if root.is_dir():
        for p in sorted(root.rglob("*")):
            if p.is_file() and not p.name.startswith("."):
                files.append(p.relative_to(root).as_posix())
    return ok(files)


@router.get("/datasources/{ds_id}/tree")
def datasource_tree(
    ds_id: int,
    db_filter: Optional[str] = Query(None, alias="db"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """库表树：连接型 → 库/表/字段三级（单次 INFORMATION_SCHEMA.COLUMNS 查询派生）；
    文件型 → 单文件 schema 推断 + 前 20 行抽样。"""
    row = db.get(DataSource, ds_id)
    if row is None:
        raise ApiError(DS_NOT_FOUND, status=404)

    if row.type == "file":
        try:
            spec = normalize_file_params(row.params)
            schema, sample = file_schema_preview(spec, sample_limit=1000, preview_limit=20)
        except FileSourceError as exc:
            raise ApiError(PARAM_INVALID, str(exc), status=400) from exc
        return ok({"kind": "file", "file": spec.path, "schema": schema, "sample": sample})

    conn = open_connection(row)
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW DATABASES")
            all_dbs = [r[0] for r in cur.fetchall()]
        dbs = [d for d in all_dbs if d not in _SYSTEM_DBS]
        if db_filter:
            dbs = [d for d in dbs if d == db_filter]
        columns: dict = {}
        if dbs:
            placeholders = ", ".join(["%s"] * len(dbs))
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE "
                    f"FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA IN ({placeholders}) "
                    "ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION",
                    dbs,
                )
                for schema_name, table_name, col_name, data_type in cur.fetchall():
                    columns.setdefault(schema_name, {}).setdefault(table_name, []).append(
                        {"name": col_name, "type": data_type}
                    )
    finally:
        conn.close()
    databases = [
        {
            "name": name,
            "tables": [{"name": t, "columns": cols} for t, cols in sorted(columns.get(name, {}).items())],
        }
        for name in dbs
    ]
    return ok({"kind": "connection", "databases": databases})


def _conn_ds(db: Session, ds_id: int) -> DataSource:
    """取连接型数据源行（I10 元数据端点族共用；不存在 404 / 类型不支持 400）。"""
    row = db.get(DataSource, ds_id)
    if row is None:
        raise ApiError(DS_NOT_FOUND, status=404)
    if row.type not in ("mysql", "greatdb"):
        raise ApiError(PARAM_INVALID, "仅连接型数据源（mysql/greatdb）支持元数据浏览", status=400)
    return row


def _open_conn(row: DataSource, db_name: Optional[str] = None):
    """短连接包装（连接失败 → 400 明确错误，不落 500）。"""
    try:
        return open_connection(row, db=db_name)
    except Exception as exc:  # noqa: BLE001
        raise ApiError(PARAM_INVALID, f"实例连接失败: {str(exc)[:300]}", status=400) from exc


@router.get("/datasources/{ds_id}/meta")
def datasource_meta(
    ds_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """实例属性卡（G2）：类型/版本/默认 Schema/执行超时/隔离级别；连通失败返回明确错误。"""
    row = _conn_ds(db, ds_id)
    version, isolation = None, None
    try:
        conn = open_connection(row)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT VERSION()")
                version = cur.fetchone()[0]
                # MySQL 8 = @@transaction_isolation；5.7 = @@tx_isolation（兜底）
                try:
                    cur.execute("SELECT @@transaction_isolation")
                    isolation = cur.fetchone()[0]
                except Exception:  # noqa: BLE001
                    cur.execute("SELECT @@tx_isolation")
                    isolation = cur.fetchone()[0]
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 连接/查询失败 → 明确错误（G2）
        raise ApiError(PARAM_INVALID, f"实例连接失败: {str(exc)[:300]}", status=400) from exc
    return ok(
        {
            "id": row.id,
            "name": row.name,
            "type": row.type,
            "host": row.host,
            "port": row.port,
            "version": version,
            "defaultSchema": row.db_name,
            "timeoutSec": 60,  # 执行超时常量（与 api/ide.py READ_TIMEOUT 同口径）
            "isolation": isolation,
        }
    )


@router.get("/datasources/{ds_id}/databases")
def list_databases(
    ds_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """库列表（G7 懒加载第一层；过滤系统库）。"""
    row = _conn_ds(db, ds_id)
    conn = _open_conn(row)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA ORDER BY SCHEMA_NAME")
            names = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()
    return ok([n for n in names if n not in _SYSTEM_DBS])


@router.get("/datasources/{ds_id}/databases/{db_name}/tables")
def list_tables_lazy(
    ds_id: int,
    db_name: str,
    kind: Optional[str] = None,  # table | view | 缺省全部
    keyword: Optional[str] = None,
    limit: int = 200,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """表/视图列表（G7 懒加载第二层；服务端 LIMIT 防大 schema 拖垮）。"""
    row = _conn_ds(db, ds_id)
    try:
        quote_ident(db_name)
    except ValueError as exc:
        raise ApiError(PARAM_INVALID, str(exc), status=400) from exc
    sql = (
        "SELECT TABLE_NAME, TABLE_TYPE, TABLE_ROWS, TABLE_COMMENT "
        "FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = %s"
    )
    params: list = [db_name]
    if kind in ("table", "view"):
        sql += " AND TABLE_TYPE = %s"
        params.append("BASE TABLE" if kind == "table" else "VIEW")
    if keyword:
        sql += " AND TABLE_NAME LIKE %s"
        params.append(f"%{keyword}%")
    sql += " ORDER BY TABLE_NAME LIMIT %s"
    params.append(min(max(int(limit), 1), 1000))
    conn = _open_conn(row)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            raw = cur.fetchall()
    finally:
        conn.close()
    tables = [
        {
            "name": name,
            "kind": "view" if ttype == "VIEW" else "table",
            "rows": rows_approx,  # InnoDB 估算值，仅展示用
            "comment": comment or "",
        }
        for name, ttype, rows_approx, comment in raw
    ]
    logger.info(
        "表列表(懒加载): ds=%s db=%s kind=%s kw=%r → %d 项（%s）",
        row.name, db_name, kind, keyword, len(tables), user.user_name,
    )
    return ok(tables)


@router.get("/datasources/{ds_id}/databases/{db_name}/tables/{table_name}/columns")
def list_columns(
    ds_id: int,
    db_name: str,
    table_name: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """字段全元信息（G7 第三层 / G9 hover Tooltip 共用，一次拉全）。"""
    row = _conn_ds(db, ds_id)
    try:
        quote_ident(db_name), quote_ident(table_name)
    except ValueError as exc:
        raise ApiError(PARAM_INVALID, str(exc), status=400) from exc
    conn = _open_conn(row)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, CHARACTER_MAXIMUM_LENGTH, "
                "NUMERIC_PRECISION, IS_NULLABLE, COLUMN_KEY, COLUMN_COMMENT, EXTRA, COLUMN_DEFAULT "
                "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s "
                "ORDER BY ORDINAL_POSITION",
                (db_name, table_name),
            )
            raw = cur.fetchall()
    finally:
        conn.close()
    if not raw:
        raise ApiError(PARAM_INVALID, f"表不存在或无字段: {db_name}.{table_name}", status=404)
    columns = [
        {
            "name": name,
            "dataType": data_type,
            "columnType": column_type,
            "length": char_len if char_len is not None else num_prec,
            "nullable": nullable == "YES",
            "key": key or "",
            "comment": comment or "",
            "extra": extra or "",
            "defaultValue": default_val,
        }
        for name, data_type, column_type, char_len, num_prec, nullable, key, comment, extra, default_val in raw
    ]
    return ok(columns)


@router.get("/datasources/{ds_id}/search")
def search_tables(
    ds_id: int,
    q: str,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """跨库表检索（G8：树未加载时后端查 INFORMATION_SCHEMA）。"""
    row = _conn_ds(db, ds_id)
    q = (q or "").strip()
    if not q:
        raise ApiError(PARAM_INVALID, "检索关键字为空", status=400)
    placeholders = ", ".join(["%s"] * len(_SYSTEM_DBS))
    sql = (
        "SELECT TABLE_SCHEMA, TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES "
        f"WHERE TABLE_NAME LIKE %s AND TABLE_SCHEMA NOT IN ({placeholders}) "
        "ORDER BY TABLE_SCHEMA, TABLE_NAME LIMIT %s"
    )
    params: list = [f"%{q}%", *_SYSTEM_DBS, min(max(int(limit), 1), 200)]
    conn = _open_conn(row)
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            raw = cur.fetchall()
    finally:
        conn.close()
    return ok(
        [
            {"db": schema, "name": name, "kind": "view" if ttype == "VIEW" else "table"}
            for schema, name, ttype in raw
        ]
    )


def _tmp_payload(row: TmpData) -> dict:
    return {
        "id": row.id,
        "instanceId": row.instance_id,
        "taskId": row.task_id,
        "nodeId": row.node_id,
        "name": row.name,
        "kind": row.kind,
        "ref": row.ref,
        "targetDsId": row.target_ds_id,
        "rowsCount": row.rows_count,
        "schema": row.schema_json,
        "preview": row.preview_json,
        "retention": row.retention,
        "expireAt": fmt_dt(row.expire_at),
        "status": row.status,
        "createTime": fmt_dt(row.create_time),
    }


@router.get("/tmp-data")
def list_tmp_data(
    instance_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """实例临时数据列表（C22 预览网格 / 实例详情「临时数据」区块数据源）。"""
    rows = db.query(TmpData).filter(TmpData.instance_id == instance_id).order_by(TmpData.id).all()
    return ok([_tmp_payload(row) for row in rows])


@router.delete("/tmp-data/{tmp_id}")
def manual_clean_tmp(
    tmp_id: int,
    user: User = Depends(require_perm("run_instance")),
    db: Session = Depends(get_db),
):
    """手动清理临时数据（实例详情「临时数据」区块按钮）：实体清扫 + status=cleaned。"""
    row = db.get(TmpData, tmp_id)
    if row is None:
        raise ApiError(TMP_NOT_FOUND, status=404)
    success = clean_tmp_data(db, row)  # 失败保持 active 供重试
    if success:
        row.status = "cleaned"
    db.commit()
    logger.info(
        "手动清理临时数据: id=%s %s(%s/%s) → %s（操作人 %s）",
        tmp_id, row.name, row.kind, row.ref, row.status, user.user_name,
    )
    return ok(True)


@router.get("/tmp-data/{tmp_id}/schemas")
def list_schemas(
    tmp_id: int,
    user: User = Depends(require_perm("run_instance")),
    db: Session = Depends(get_db),
):
    """列出实例临时数据的表结构（实例详情「临时数据」区块只读探表，不写库）。"""
    row = db.get(TmpData, tmp_id)
    if row is None:
        raise ApiError(TMP_NOT_FOUND, status=404)
    # I12 fix：schema 已由 file.py 落库（schema_json），直接返回零解析；物化临时表（kind=table）
    # 无文件 schema 时返回 []，前端凭 targetDsId 走既有 /datasources/{id}/schemas 探树
    return ok(row.schema_json or [])


@router.get("/datasources/{ds_id}/schemas")
def datasource_schemas(
    ds_id: int,
    user: User = Depends(require_perm("run_instance")),
    db: Session = Depends(get_db),
):
    """数据源三级 Schema 清单（源库/目标库面板只读探树，不写库）：连接型 → 库/表/字段
    （单次 INFORMATION_SCHEMA.COLUMNS 查询派生，镜像 datasource_tree 样板 @447-478）。"""
    row = _conn_ds(db, ds_id)  # 仅连接型（mysql/greatdb）；文件型走 tmp-data/文件预览通道
    conn = _open_conn(row)
    try:
        with conn.cursor() as cur:
            cur.execute("SHOW DATABASES")
            all_dbs = [r[0] for r in cur.fetchall()]
        dbs = [d for d in all_dbs if d not in _SYSTEM_DBS]
        columns: dict = {}
        if dbs:
            placeholders = ", ".join(["%s"] * len(dbs))
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE "
                    f"FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA IN ({placeholders}) "
                    "ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION",
                    dbs,
                )
                for schema_name, table_name, col_name, data_type in cur.fetchall():
                    columns.setdefault(schema_name, {}).setdefault(table_name, []).append(
                        {"name": col_name, "type": data_type}
                    )
    finally:
        conn.close()
    schemas = [
        {
            "db": name,
            "tables": [
                {"name": t, "columns": cols} for t, cols in sorted(columns.get(name, {}).items())
            ],
        }
        for name in sorted(dbs)
    ]
    return ok(schemas)


# ---------- 流源注册化 I12「选择代替填空」：Kafka topic 枚举 ----------

@router.get("/datasources/{ds_id}/topics")
def list_kafka_topics(
    ds_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """注册流源（Kafka）topic 列表（I12「选择代替填空」）：前端经注册数据源下拉选择，免手填。"""
    row = db.get(DataSource, ds_id)
    if row is None:
        raise ApiError(DS_NOT_FOUND, status=404)
    if row.type != "kafka":
        raise ApiError(PARAM_INVALID, "仅 Kafka 数据源支持 topic 枚举", status=400)
    brokers = _parse_brokers((row.params or {}).get("brokers"))
    if not brokers:
        raise ApiError(PARAM_INVALID, "Kafka 数据源 brokers 未配置", status=400)
    try:
        from kafka import KafkaConsumer

        # kafka-python 3.x 移除 api_version_auto_timeout_ms（首连探测超时改由
        # bootstrap_timeout_ms 承担）而 2.x 无后者；requirements 无上界 pin，
        # 按实际安装版本的合法参数二选一（探测上限 5s 语义不变）
        configs: dict = {
            "bootstrap_servers": [f"{h}:{p}" for h, p in brokers],
            "request_timeout_ms": 8000,
        }
        if "api_version_auto_timeout_ms" in KafkaConsumer.DEFAULT_CONFIG:
            configs["api_version_auto_timeout_ms"] = 5000
        else:
            configs["bootstrap_timeout_ms"] = 5000
        consumer = KafkaConsumer(**configs)
        try:
            topics = sorted(consumer.topics())
        finally:
            consumer.close()  # 资源释放铁律：无论枚举成败必须断开
    except ImportError as exc:  # noqa: BLE001 依赖缺失专用文案（对齐 _test_kafka 导入失败处理风格）
        raise ApiError(DEP_UNAVAILABLE, "topic 枚举失败：kafka-python 未安装", status=502) from exc
    except Exception as exc:  # noqa: BLE001 上游 Kafka 不可用 → 502 语义明确报错
        raise ApiError(DEP_UNAVAILABLE, f"topic 枚举失败：{exc}", status=502) from exc
    logger.info(
        "Kafka topic 枚举: id=%s %s → %d 个 topic（操作人 %s）",
        ds_id, row.name, len(topics), user.user_name,
    )
    return ok({"topics": topics})

