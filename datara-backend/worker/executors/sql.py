"""C11 SQL 执行器（I3 设计文档 §7.2）：pymysql 连 t_data_source。

- 数据源解析：param.datasource（名称，前端字段）→ t_data_source；数字串兜底按 id
- 多语句按仓内词法器安全拆分并顺序执行：前置 pre → 主 sql → 后置 post
- transaction 支持 none/all/explicit；all 仅接受可事务化语句，explicit 必须自行闭合边界
- 查询：row_count 全量计数 + result_preview 前 200 行；非查询/DDL：影响行数
- 连接池：按数据源 id LRU（maxsize=8），取用时 ping 自愈断连
- 变量占位已在 master 侧替换下发（param_resolved），worker 零解析
"""

import re
import threading
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal
from typing import Callable

import pymysql
import sqlglot
from sqlglot import exp

from rebuild.sql_ide.readonly_preflight import ReadonlyBatchPreflightError, preflight_readonly_batch
from rebuild.sql_ide.statement_splitter import StatementSplitError, split_sql_statements
from worker.executor import ExecResult, register
from worker.lineage import collect_sql_lineage
from worker.state import FAILURE, KILL, SUCCESS

POOL_MAX = 8  # LRU 连接池上限
PREVIEW_ROWS = 200  # result_preview 截断行数（§7.1）
FETCH_BATCH = 500  # 批量取行批大小（避免大结果集一次性载入内存）

_conn_pool: "OrderedDict[int, pymysql.connections.Connection]" = OrderedDict()
_pool_lock = threading.Lock()

# 本期走 MySQL 协议的源类型（GreatDB/Doris/StarRocks 均兼容）
_MYSQL_LIKE = frozenset({"mysql", "greatdb", "doris", "starrocks"})
_TRANSACTION_MODES = frozenset({"none", "all", "explicit"})
_READONLY_QUERY_TYPES = (exp.Select, exp.Union, exp.Intersect, exp.Except)
_EXPLAINABLE_TYPES = _READONLY_QUERY_TYPES + (exp.Insert, exp.Update, exp.Delete)
_TRANSACTIONAL_TYPES = _EXPLAINABLE_TYPES


def _split_sql(text: str) -> list:
    """按 SQL 词法边界安全拆分语句，保留字符串与注释内的分号。"""
    return [statement.sql for statement in split_sql_statements(text or "", dialect="mysql")]


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
    """Checkout one connection exclusively; callers must release or discard it."""
    key = int(ds.id)
    with _pool_lock:
        conn = _conn_pool.pop(key, None)
    if conn is not None:
        try:
            conn.ping(reconnect=True)
            return conn
        except Exception:  # noqa: BLE001 断连失效 → 重建
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
    conn = pymysql.connect(
        host=ds.host,
        port=int(ds.port or 3306),
        user=ds.user or "root",
        password=ds.pwd or "",
        database=ds.db_name or None,
        charset="utf8mb4",
        autocommit=True,
        connect_timeout=10,
    )
    return conn


def _release_conn(ds, conn, log: Callable) -> None:
    """Return a healthy autocommit connection to the bounded idle LRU."""
    if getattr(conn, "_datara_discarded", False):
        return
    try:
        conn.ping(reconnect=False)
        if hasattr(conn, "get_autocommit") and not conn.get_autocommit():
            raise RuntimeError("connection autocommit invariant is false")
    except Exception as exc:  # noqa: BLE001
        log("[sql] connection is not reusable: %r" % exc)
        _discard_conn(ds, conn, log)
        return
    stale_connections = []
    with _pool_lock:
        previous = _conn_pool.pop(int(ds.id), None)
        if previous is not None and previous is not conn:
            stale_connections.append(previous)
        _conn_pool[int(ds.id)] = conn
        while len(_conn_pool) > POOL_MAX:
            _key, stale = _conn_pool.popitem(last=False)
            stale_connections.append(stale)
    for stale in stale_connections:
        try:
            stale.close()
        except Exception:  # noqa: BLE001
            pass


def _discard_conn(ds, conn, log: Callable) -> None:
    """Remove a possibly dirty connection from the LRU and close it."""
    if getattr(conn, "_datara_discarded", False):
        return
    key = int(ds.id)
    with _pool_lock:
        if _conn_pool.get(key) is conn:
            _conn_pool.pop(key, None)
    try:
        setattr(conn, "_datara_discarded", True)
    except Exception:  # noqa: BLE001
        pass
    try:
        conn.close()
    except Exception as exc:  # noqa: BLE001
        log("[sql] dirty connection close failed: %r" % exc)


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


def _is_readonly_statement(stmt: str) -> bool:
    """复用 SQL IDE 的安全函数白名单，并额外拒绝 MySQL 会话变量赋值。"""
    try:
        preflight_readonly_batch(stmt, dialect="mysql")
        parsed = [item for item in sqlglot.parse(stmt, read="mysql") if item is not None]
    except (ReadonlyBatchPreflightError, sqlglot.errors.ParseError, ValueError):
        return False
    return len(parsed) == 1 and not any(
        isinstance(node, exp.PropertyEQ) and isinstance(node.this, exp.Parameter)
        for node in parsed[0].walk()
    )


def _normalize_policy_sql(stmt: str) -> str:
    """Expose MySQL executable comments while discarding ordinary comments and hints."""
    def replace_block_comment(match: re.Match) -> str:
        content = match.group(1)
        if not content.startswith("!"):
            return " "
        executable = content[1:].lstrip()
        executable = re.sub(r"^\d{5,6}\s*", "", executable)
        return " %s " % executable

    normalized = re.sub(r"/\*(.*?)\*/", replace_block_comment, stmt, flags=re.DOTALL)
    normalized = re.sub(r"(?:--|#)[^\r\n]*", " ", normalized)
    return " ".join(normalized.upper().split())


def _is_transaction_control_statement(stmt: str) -> bool:
    """Detect statements that would escape the executor-owned all boundary."""
    normalized = _normalize_policy_sql(stmt)
    if re.match(r"^(?:BEGIN|COMMIT|ROLLBACK|SAVEPOINT|XA)\b", normalized):
        return True
    if re.match(r"^(?:START\s+TRANSACTION|RELEASE\s+SAVEPOINT)\b", normalized):
        return True
    return bool(
        re.match(
            r"^SET\s+(?:(?:SESSION|LOCAL|GLOBAL)\s+|@@(?:(?:SESSION|LOCAL|GLOBAL)\.)?)?AUTOCOMMIT\b",
            normalized,
        )
    )


def _is_implicit_commit_statement(stmt: str) -> bool:
    """Detect MySQL statements that cannot participate in an atomic all-mode batch."""
    normalized = _normalize_policy_sql(stmt)
    return bool(
        re.match(
            r"^(?:CREATE|ALTER|DROP|TRUNCATE|RENAME|GRANT|REVOKE|LOCK|UNLOCK|ANALYZE|CACHE|CHECK|FLUSH|"
            r"OPTIMIZE|REPAIR|RESET|INSTALL|UNINSTALL|LOAD)\b|^SET\s+PASSWORD\b",
            normalized,
        )
    )


def _explicit_transaction_effect(stmt: str) -> str | None:
    """Classify explicit transaction state changes for pooled-connection cleanup."""
    normalized = _normalize_policy_sql(stmt)
    if re.match(r"^(?:BEGIN|START\s+TRANSACTION)\b", normalized):
        return "open"
    if re.match(r"^COMMIT\b", normalized):
        return "close"
    if re.match(r"^ROLLBACK\b", normalized) and not re.match(r"^ROLLBACK(?:\s+WORK)?\s+TO\b", normalized):
        return "close"
    autocommit = re.match(
        r"^SET\s+(?:(?:SESSION|LOCAL|GLOBAL)\s+|@@(?:(?:SESSION|LOCAL|GLOBAL)\.)?)?AUTOCOMMIT\s*(?:=|:=)\s*(\w+)",
        normalized,
    )
    if autocommit:
        return "autocommit_on" if autocommit.group(1) in {"1", "ON", "TRUE"} else "autocommit_off"
    return None


def _is_transactional_statement(stmt: str) -> bool:
    """Fail-closed allow-list for transaction=all (query and transactional DML only)."""
    try:
        parsed = [item for item in sqlglot.parse(stmt, read="mysql") if item is not None]
    except (sqlglot.errors.ParseError, ValueError):
        return False
    if len(parsed) == 1 and isinstance(parsed[0], _TRANSACTIONAL_TYPES):
        return True
    return bool(re.match(r"^REPLACE\s+(?:INTO\s+)?", _normalize_policy_sql(stmt)))


def _is_explainable_statement(stmt: str) -> bool:
    """Return true for query and DML statements accepted by MySQL EXPLAIN."""
    try:
        parsed = [item for item in sqlglot.parse(stmt, read="mysql") if item is not None]
    except (sqlglot.errors.ParseError, ValueError):
        return False
    return len(parsed) == 1 and isinstance(parsed[0], _EXPLAINABLE_TYPES)


def _rollback(conn, log: Callable) -> bool:
    """Best-effort rollback which preserves the executor's original failure state."""
    try:
        conn.rollback()
        return True
    except Exception as exc:  # noqa: BLE001
        log("[sql] transaction rollback failed: %r" % exc)
        return False


def _cleanup_explicit_connection(ds, conn, log: Callable) -> bool:
    """Rollback explicit work and restore the pool's autocommit invariant when observable."""
    if not _rollback(conn, log):
        _discard_conn(ds, conn, log)
        return False
    try:
        if hasattr(conn, "get_autocommit") and not conn.get_autocommit():
            conn.autocommit(True)
    except Exception as exc:  # noqa: BLE001
        log("[sql] explicit transaction autocommit restore failed: %r" % exc)
        _discard_conn(ds, conn, log)
        return False
    return True


def _cancel_query(ds, conn, log: Callable) -> None:
    """Cancel an in-flight PyMySQL query through a short-lived control connection."""
    try:
        thread_id = int(conn.thread_id())
        control = pymysql.connect(
            host=ds.host, port=int(ds.port or 3306), user=ds.user or "root",
            password=ds.pwd or "", database=ds.db_name or None, charset="utf8mb4",
            autocommit=True, connect_timeout=5,
        )
        try:
            cursor = control.cursor()
            try:
                cursor.execute("KILL QUERY %d" % thread_id)
            finally:
                cursor.close()
        finally:
            control.close()
    except Exception as exc:  # noqa: BLE001
        log("[sql] KILL QUERY failed; discarding worker connection: %r" % exc)
        _discard_conn(ds, conn, log)


def _run_one_interruptible(conn, ds, stmt: str, log: Callable, killed: Callable) -> tuple[dict | None, bool]:
    """Run one statement while polling cancellation outside the blocking driver call."""
    done = threading.Event()
    outcome: dict[str, object] = {}

    def target() -> None:
        try:
            outcome["result"] = _run_one(conn, stmt, log)
        except BaseException as exc:  # propagate in the caller thread
            outcome["error"] = exc
        finally:
            done.set()

    worker = threading.Thread(target=target, name="sql-statement", daemon=True)
    worker.start()
    cancelled = False
    while not done.wait(0.1):
        if killed():
            cancelled = True
            _cancel_query(ds, conn, log)
            break
    if cancelled:
        done.wait(5)
        if not done.is_set():
            _discard_conn(ds, conn, log)
        return None, True
    error = outcome.get("error")
    if error is not None:
        raise error
    return outcome["result"], False  # type: ignore[return-value]


@register("sql")
def execute(ctx) -> ExecResult:
    """执行 pre → sql → post，并保留结果、血缘、统计与中断契约。"""
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

    transaction_mode = str(param.get("transaction") or "none").strip().lower()
    if transaction_mode not in _TRANSACTION_MODES:
        ctx.log("[sql] transaction 参数无效: %s" % transaction_mode)
        return ExecResult(FAILURE, {}, [])

    try:
        phases = (
            ("pre", "前置", _split_sql(str(param.get("pre") or ""))),
            ("sql", "主", _split_sql(str(param.get("sql") or ""))),
            ("post", "后置", _split_sql(str(param.get("post") or ""))),
        )
    except StatementSplitError as exc:
        ctx.log("[sql] SQL 词法分句失败: %s" % exc)
        return ExecResult(FAILURE, {}, [])
    if transaction_mode == "all":
        unsafe = next(
            (
                stmt
                for _phase_key, _phase_label, statements in phases
                for stmt in statements
                if not _is_transactional_statement(stmt)
            ),
            None,
        )
        if unsafe is not None:
            ctx.log("[sql] transaction=all 禁止事务控制或隐式提交语句: %s" % unsafe[:200].replace("\n", " "))
            return ExecResult(FAILURE, {}, [])
    if transaction_mode == "none":
        boundary = next(
            (
                stmt
                for _phase_key, _phase_label, statements in phases
                for stmt in statements
                if _is_transaction_control_statement(stmt)
            ),
            None,
        )
        if boundary is not None:
            ctx.log("[sql] transaction=none 禁止显式事务或 autocommit 控制语句")
            return ExecResult(FAILURE, {}, [])
    if transaction_mode == "explicit":
        unsupported = next(
            (stmt for _key, _label, statements in phases for stmt in statements
             if re.match(r"^XA\b", _normalize_policy_sql(stmt))),
            None,
        )
        if unsupported is not None:
            ctx.log("[sql] transaction=explicit 暂不支持 XA 事务")
            return ExecResult(FAILURE, {}, [])
    if param.get("readOnly"):
        rejected = next(
            (
                stmt
                for _phase_key, _phase_label, statements in phases
                for stmt in statements
                if not _is_readonly_statement(stmt)
            ),
            None,
        )
        if rejected is not None:
            ctx.log("[sql] readOnly 拒绝写操作或无法确认的语句: %s" % rejected[:200].replace("\n", " "))
            return ExecResult(FAILURE, {}, [])

    # Only strictly read-only batches that pass the IDE's function allow-list
    # may return to the idle pool.  DML is deliberately disposable too: values
    # and functions inside it can have session side effects that a top-level
    # statement-type check cannot prove safe (for example named locks or UDFs).
    pool_safe = transaction_mode in {"none", "all"} and all(
        _is_readonly_statement(stmt)
        for _phase_key, _phase_label, statements in phases
        for stmt in statements
    )

    try:
        conn = _get_conn(ds)
    except Exception as exc:  # noqa: BLE001 连接失败 → failure（日志含原因）
        ctx.log("[sql] 连接失败: %r" % exc)
        return ExecResult(FAILURE, {}, [])

    results = []
    execution_plan = []
    executed: list = []  # 已成功执行语句（血缘采集源；提交边界由 transaction 模式决定）
    outputs_count: dict = {}  # 血缘计数（成功终态随 outputs 上报）
    killed = False
    explicit_transaction_open = False
    explicit_autocommit_disabled = False
    state = SUCCESS
    try:
        if transaction_mode == "all":
            conn.begin()
        for phase_key, phase_label, statements in phases:
            for i, stmt in enumerate(statements, start=1):
                if ctx.killed():
                    killed = True
                    break
                ctx.log("[sql] %s语句#%d: %s" % (phase_label, i, stmt[:200].replace("\n", " ")))
                if phase_key == "sql" and param.get("explain") and _is_explainable_statement(stmt):
                    plan, cancelled = _run_one_interruptible(conn, ds, "EXPLAIN " + stmt, ctx.log, ctx.killed)
                    if cancelled:
                        killed = True
                        break
                    execution_plan.append(
                        {"statement": stmt, "columns": plan.get("columns", []), "rows": plan.get("rows", [])}
                    )
                result, cancelled = _run_one_interruptible(conn, ds, stmt, ctx.log, ctx.killed)
                if cancelled:
                    killed = True
                    break
                results.append(result)
                executed.append(stmt)
                if transaction_mode == "explicit":
                    effect = _explicit_transaction_effect(stmt)
                    if effect == "open":
                        explicit_transaction_open = True
                    elif effect == "close":
                        explicit_transaction_open = False
                    elif effect == "autocommit_off":
                        explicit_autocommit_disabled = True
                    elif effect == "autocommit_on":
                        explicit_transaction_open = False
                        explicit_autocommit_disabled = False
            if killed:
                break
        if not killed and ctx.killed():
            killed = True
        if transaction_mode == "all":
            if killed:
                if not _rollback(conn, ctx.log):
                    _discard_conn(ds, conn, ctx.log)
            else:
                conn.commit()
        elif transaction_mode == "explicit" and killed:
            _cleanup_explicit_connection(ds, conn, ctx.log)
        elif transaction_mode == "explicit" and (explicit_transaction_open or explicit_autocommit_disabled):
            _cleanup_explicit_connection(ds, conn, ctx.log)
            ctx.log("[sql] explicit 事务未闭合，已回滚并拒绝成功终态")
            state = FAILURE
    except Exception as exc:  # noqa: BLE001 SQL 错误 → failure
        if transaction_mode == "all":
            if not _rollback(conn, ctx.log):
                _discard_conn(ds, conn, ctx.log)
        elif transaction_mode == "explicit":
            _cleanup_explicit_connection(ds, conn, ctx.log)
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
        if pool_safe:
            _release_conn(ds, conn, ctx.log)
        else:
            _discard_conn(ds, conn, ctx.log)
        return ExecResult(state, {}, [])

    outputs = {"results": results, **outputs_count}
    if param.get("explain"):
        outputs["execution_plan"] = execution_plan
    queries = [r for r in results if r["kind"] == "query"]
    if queries:
        last = queries[-1]
        outputs["row_count"] = last["rowCount"]
        outputs["result_preview"] = {"columns": last["columns"], "rows": last["rows"]}
    if pool_safe:
        _release_conn(ds, conn, ctx.log)
    else:
        _discard_conn(ds, conn, ctx.log)
    return ExecResult(SUCCESS, outputs, [])
