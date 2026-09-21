"""C11 SQL 执行器（I3 设计文档 §7.2）：pymysql 连 t_data_source。

- 数据源解析：param.datasource（名称，前端字段）→ t_data_source；数字串兜底按 id
- 多语句分号拆分顺序执行：前置 pre → 主 sql → 后置 post；autocommit 逐语句提交
- 查询：row_count 全量计数 + result_preview 前 200 行；非查询/DDL：影响行数
- 连接池：按数据源 id LRU（maxsize=8），取用时 ping 自愈断连
- 变量占位已在 master 侧替换下发（param_resolved），worker 零解析
"""

import threading
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal
from typing import Callable

import pymysql

from worker.executor import ExecResult, register
from worker.lineage import collect_sql_lineage
from worker.state import FAILURE, KILL, SUCCESS

POOL_MAX = 8          # LRU 连接池上限
PREVIEW_ROWS = 200    # result_preview 截断行数（§7.1）
FETCH_BATCH = 500     # 批量取行批大小（避免大结果集一次性载入内存）

_conn_pool: "OrderedDict[int, pymysql.connections.Connection]" = OrderedDict()
_pool_lock = threading.Lock()

# 本期走 MySQL 协议的源类型（GreatDB/Doris/StarRocks 均兼容）
_MYSQL_LIKE = frozenset({"mysql", "greatdb", "doris", "starrocks"})


def _split_sql(text: str) -> list:
    """多语句分号拆分（空语句剔除，保序）。"""
    return [part.strip() for part in (text or "").split(";") if part.strip()]


def _lookup_datasource(ref):
    """按名称查 t_data_source，纯数字兜底按 id。"""
    from common.db import new_session
    from common.models import DataSource

    session = new_session()
    try:
        ds = session.query(DataSource).filter(DataSource.name == ref).first()
        if ds is None and str(ref).isdigit():
            ds = session.get(DataSource, int(ref))
        return ds
    finally:
        session.close()


def _get_conn(ds):
    """LRU 连接池取连接：命中 ping 自愈；未命中新建；超限淘汰最旧。"""
    key = int(ds.id)
    with _pool_lock:
        conn = _conn_pool.pop(key, None)
    if conn is not None:
        try:
            conn.ping(reconnect=True)
            with _pool_lock:
                _conn_pool[key] = conn
                _conn_pool.move_to_end(key)
            return conn
        except Exception:  # noqa: BLE001 断连失效 → 重建
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
    conn = pymysql.connect(
        host=ds.host, port=int(ds.port or 3306),
        user=ds.user or "root", password=ds.pwd or "",
        database=ds.db_name or None,
        charset="utf8mb4", autocommit=True, connect_timeout=10,
    )
    with _pool_lock:
        _conn_pool[key] = conn
        while len(_conn_pool) > POOL_MAX:
            _key, stale = _conn_pool.popitem(last=False)
            try:
                stale.close()
            except Exception:  # noqa: BLE001
                pass
    return conn


def _jsonable(value):
    """行值 JSON 安全化（bytes/datetime/Decimal → str；SQLAlchemy JSON 列要求）。"""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", errors="replace")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()  # date.isoformat() 不接受 sep（09-18 实测教训）
    return value


def _run_one(conn, stmt: str, log: Callable) -> dict:
    """执行单语句：查询 → 全量计数 + 预览前 200 行；非查询 → 影响行数。"""
    cur = conn.cursor()
    try:
        cur.execute(stmt)
        if cur.description is None:
            affected = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
            log("[sql] 非查询语句 → 影响行数 %d" % affected)
            return {"kind": "exec", "affected": affected, "columns": [], "rows": []}
        columns = [col[0] for col in cur.description]
        rows, total = [], 0
        while True:
            batch = cur.fetchmany(FETCH_BATCH)
            if not batch:
                break
            total += len(batch)
            remain = PREVIEW_ROWS - len(rows)
            if remain > 0:
                for row in batch[:remain]:
                    rows.append([_jsonable(v) for v in row])
        log("[sql] 查询语句 → 结果 %d 行（预览前 %d 行）" % (total, len(rows)))
        return {"kind": "query", "rowCount": total, "columns": columns, "rows": rows}
    finally:
        cur.close()


@register("sql")
def execute(ctx) -> ExecResult:
    """执行 pre → sql → post 多语句；outputs.results 全语句摘要 + 主查询预览。"""
    param = ctx.param or {}
    ds_ref = param.get("datasource") or param.get("datasource_id")
    if not ds_ref:
        return ExecResult(FAILURE, {}, ["[sql] 未指定数据源（datasource）"])
    ds = _lookup_datasource(ds_ref)
    if ds is None:
        return ExecResult(FAILURE, {}, ["[sql] 数据源不存在: %s" % ds_ref])
    if str(ds.type or "").lower() not in _MYSQL_LIKE:
        return ExecResult(FAILURE, {}, ["[sql] 暂不支持的数据源类型: %s（本期 MySQL 协议）" % ds.type])
    ctx.log("[sql] 数据源: %s (%s:%s/%s)" % (ds.name, ds.host, ds.port, ds.db_name))

    try:
        conn = _get_conn(ds)
    except Exception as exc:  # noqa: BLE001 连接失败 → failure（日志含原因）
        ctx.log("[sql] 连接失败: %r" % exc)
        return ExecResult(FAILURE, {}, [])

    results = []
    executed: list = []  # 已成功执行语句（血缘采集源，I5 F24；_run_one 无异常=已提交）
    outputs_count: dict = {}  # 血缘计数（成功终态随 outputs 上报）
    killed = False
    state = SUCCESS
    try:
        for phase, text in (("前置", param.get("pre")), ("主", param.get("sql")),
                            ("后置", param.get("post"))):
            for i, stmt in enumerate(_split_sql(str(text or "")), start=1):
                if ctx.killed():
                    killed = True
                    break
                ctx.log("[sql] %s语句#%d: %s" % (phase, i, stmt[:200].replace("\n", " ")))
                results.append(_run_one(conn, stmt, ctx.log))
                executed.append(stmt)
            if killed:
                break
    except Exception as exc:  # noqa: BLE001 SQL 错误 → failure
        ctx.log("[sql] 执行失败: %r" % exc)
        state = FAILURE
    if killed:
        ctx.log("[sql] 收到中断指令，执行中止")
        state = KILL

    # 血缘采集（I5 F24 旁路）：仅已成功语句，失败/中断不阻断终态；计数随成功 outputs 上报
    if executed:
        edges_n, fields_n = collect_sql_lineage(ctx, executed, ds.name, ds.db_name or "")
        if state == SUCCESS:
            outputs_count = {"lineage_edges": edges_n, "lineage_fields": fields_n}

    if state != SUCCESS:
        return ExecResult(state, {}, [])

    outputs = {"results": results, **outputs_count}
    queries = [r for r in results if r["kind"] == "query"]
    if queries:
        last = queries[-1]
        outputs["row_count"] = last["rowCount"]
        outputs["result_preview"] = {"columns": last["columns"], "rows": last["rows"]}
    return ExecResult(SUCCESS, outputs, [])
