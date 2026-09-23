"""C22 文件读取执行器（I4 设计文档 §5.2，F62 自创核心）。

- 来源：数据源中心文件源（param.datasource）或手动参数（path/format/encoding/delimiter/header/sheet）
- 流式解析（CSV/TXT csv.reader / Excel openpyxl read_only）→ schema 推断（1000 行抽样）+ 空值率
- 注册临时数据三形态：table（目标库 TEXT 列批量物化，1000 行/批）/ resultset（抽样 JSON）/ file（登记路径）
- 保留策略 immediate/days/keep 落库；清扫/转正式归 master 收口（common/tmpdata）
- outputs：rows_count / columns / tmp_name（注册时）
"""

import time
from datetime import datetime, timedelta

from common.db import new_session
from common.dsconn import (
    FileSourceError,
    file_schema_preview,
    iter_rows,
    normalize_file_params,
    open_connection,
    parse_file_source,
    resolve_file_path,
)
from common.models import DataSource, TaskInstance, TmpData
from common.tmpdata import TMP_NAME_RE, tmp_table_name
from worker.executor import ExecResult, register
from worker.state import FAILURE, KILL, SUCCESS

INSERT_BATCH = 1000  # 物化批大小（内存约束，设计文档 §11）
KILL_CHECK_BATCHES = 50  # 每隔多少批检查一次 kill 中断
PREVIEW_ROWS = 200


def _lookup_datasource(ref):
    """按名称查 t_data_source，纯数字兜底按 id（与 sql.py 同口径）。"""
    session = new_session()
    try:
        ds = session.query(DataSource).filter(DataSource.name == ref).first()
        if ds is None and str(ref).isdigit():
            ds = session.get(DataSource, int(ref))
        return ds
    finally:
        session.close()


def _lookup_node_id(ctx) -> str:
    """画布节点 id（t_task_instance.node_id），缺失回退任务名。"""
    session = new_session()
    try:
        task = session.get(TaskInstance, ctx.task_id)
        return str(task.node_id or ctx.name or "node")
    finally:
        session.close()


def _resolve_spec(ctx, param):
    """来源模式二选一：数据源中心文件源 / 手动参数（表单联动保证只填一侧）。"""
    mode = str(param.get("mode") or ("datasource" if param.get("datasource") else "manual"))
    if mode == "datasource":
        ref = param.get("datasource")
        ds = _lookup_datasource(ref)
        if ds is None:
            raise FileSourceError("文件源数据源不存在: %s" % ref)
        if ds.type != "file":
            raise FileSourceError("数据源类型不是 file: %s(%s)" % (ds.name, ds.type))
        return parse_file_source(ds)
    return normalize_file_params(
        {
            "format": param.get("format"),
            "path": param.get("path"),
            "encoding": param.get("encoding"),
            "delimiter": param.get("delimiter"),
            "header": param.get("header"),
            "sheet": param.get("sheet"),
        }
    )


def _safe_columns(names: list) -> list:
    """表头 → 合法列名：去反引号/空白、空名补 col_N、重名追加序号。"""
    out, seen = [], {}
    for i, n in enumerate(names):
        s = str(n).strip().replace("`", "") or "col_%d" % (i + 1)
        if s in seen:
            seen[s] += 1
            s = "%s_%d" % (s, seen[s])
        else:
            seen[s] = 1
        out.append(s)
    return out


def _insert_batch(cur, conn, table: str, columns: list, batch: list) -> None:
    cols = ", ".join("`%s`" % c for c in columns)
    marks = ", ".join(["%s"] * len(columns))
    cur.executemany("INSERT INTO `%s` (%s) VALUES (%s)" % (table, cols, marks), batch)
    conn.commit()


def _materialize(ctx, ds, table: str, columns: list, rows_iter, log) -> tuple:
    """DROP+CREATE（TEXT 全量承载）+ 批量 INSERT；返回 (行数, 是否被中断)。"""
    conn = open_connection(ds, read_timeout=None)  # 物化不受 60s 限制
    inserted, batch_no = 0, 0
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS `%s`" % table)
            col_defs = ", ".join("`%s` TEXT NULL" % c for c in columns)
            cur.execute(
                "CREATE TABLE `%s` (%s) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4" % (table, col_defs)
            )
            conn.commit()
            batch = []
            for row in rows_iter:
                vals = ["" if v is None else str(v) for v in row[: len(columns)]]
                if len(vals) < len(columns):
                    vals += [""] * (len(columns) - len(vals))  # 短行补空（错位行容错）
                batch.append(tuple(vals))
                if len(batch) >= INSERT_BATCH:
                    _insert_batch(cur, conn, table, columns, batch)
                    inserted += len(batch)
                    batch_no += 1
                    batch = []
                    if batch_no % KILL_CHECK_BATCHES == 0 and ctx.killed():
                        return inserted, True
            if batch:
                _insert_batch(cur, conn, table, columns, batch)
                inserted += len(batch)
    finally:
        conn.close()
    return inserted, False


def _count_rows(ctx, spec, log) -> tuple:
    """流式计数（含表头行，不驻留内存）；返回 (原始行数, 是否被中断)。"""
    total, seen = 0, 0
    for _row in iter_rows(spec):
        total += 1
        seen += 1
        if seen % (INSERT_BATCH * KILL_CHECK_BATCHES) == 0 and ctx.killed():
            return total, True
    return total, False


def _data_rows(spec):
    """跳过表头行的数据行迭代器。"""
    first = True
    for row in iter_rows(spec):
        if first and spec.header:
            first = False
            continue
        first = False
        yield row


def _register_tmp(ctx, name, kind, ref, target_ds_id, rows_count, schema, preview, retention, keep_days):
    """upsert t_tmp_data（uk_tmp_name：重试/重复注册覆盖更新）。"""
    session = new_session()
    try:
        row = (
            session.query(TmpData)
            .filter(TmpData.instance_id == ctx.instance_id, TmpData.name == name)
            .first()
        )
        if row is None:
            row = TmpData(instance_id=ctx.instance_id, name=name)
            session.add(row)
        row.task_id = ctx.task_id
        row.node_id = _lookup_node_id(ctx)
        row.kind = kind
        row.ref = ref
        row.target_ds_id = target_ds_id
        row.rows_count = rows_count
        row.schema_json = schema
        row.preview_json = preview
        row.retention = retention
        row.expire_at = (
            datetime.now() + timedelta(days=keep_days)
            if retention == "days" and keep_days > 0
            else None
        )
        row.status = "active"
        session.commit()
    finally:
        session.close()


@register("file")
def execute(ctx) -> ExecResult:
    """C22 主流程：解析 → schema 推断 →（注册时）三形态产出 → 落 t_tmp_data。"""
    param = ctx.param or {}
    t0 = time.monotonic()

    # 1. 解析来源 + schema 推断（1000 行抽样）
    try:
        spec = _resolve_spec(ctx, param)
        ctx.log(
            "[file] 来源: %s（format=%s encoding=%s delimiter=%r header=%s sheet=%s）"
            % (spec.path, spec.format, spec.encoding, spec.delimiter, spec.header, spec.sheet)
        )
        schema, sample = file_schema_preview(spec)
        columns = [str(c["name"]) for c in schema.get("columns") or []]
        if not columns:
            ctx.log("[file] 文件无有效列（空文件或全空行）")
            return ExecResult(FAILURE, {}, [])
        ctx.log(
            "[file] 列数=%d 抽样=%d 行；类型推断: %s"
            % (
                len(columns),
                schema.get("sampledRows", 0),
                ", ".join("%s:%s" % (c["name"], c["type"]) for c in schema.get("columns") or []),
            )
        )
    except Exception as exc:  # noqa: BLE001 解析/路径失败 → failure
        ctx.log("[file] 解析失败: %r" % exc)
        return ExecResult(FAILURE, {}, [])

    outputs = {"columns": len(columns), "preview_rows": len(sample)}

    # 2. 未注册模式：仅统计与日志（预览网格数据经 t_tmp_data，未注册无预览）
    if not param.get("register", True):
        raw, killed = _count_rows(ctx, spec, ctx.log)
        if killed:
            ctx.log("[file] 收到中断指令，统计中止")
            return ExecResult(KILL, {}, [])
        rows_count = raw - 1 if spec.header and raw else raw
        ctx.log("[file] 未注册临时数据；数据行数=%d 耗时=%dms" % (rows_count, int((time.monotonic() - t0) * 1000)))
        outputs["rows_count"] = rows_count
        return ExecResult(SUCCESS, outputs, [])

    # 3. 注册参数校验
    # I12 T15 修 F3：表单键 tmpName 优先（避免与节点显示名 data.name 冲突）；旧契约 name 兼容
    name = str(param.get("tmpName") or param.get("name") or "").strip()
    kind = str(param.get("kind") or "table")
    retention = str(param.get("retention") or "immediate")
    if not TMP_NAME_RE.match(name):
        ctx.log("[file] 临时数据名非法: %r（需匹配 ^[a-z][a-z0-9_]{2,31}$）" % name)
        return ExecResult(FAILURE, {}, [])
    if kind not in ("table", "resultset", "file"):
        ctx.log("[file] 未知的临时数据形态: %s" % kind)
        return ExecResult(FAILURE, {}, [])
    if retention not in ("immediate", "days", "keep"):
        ctx.log("[file] 未知的保留策略: %s" % retention)
        return ExecResult(FAILURE, {}, [])

    # 4. 三形态产出
    rows_count, ref, target_ds_id = 0, None, None
    if kind == "table":
        ds = _lookup_datasource(str(param.get("targetDs") or "内置数仓-datara_dw"))
        if ds is None:
            ctx.log("[file] 物化目标数据源不存在: %s" % param.get("targetDs"))
            return ExecResult(FAILURE, {}, [])
        if ds.type not in ("mysql", "greatdb"):
            ctx.log("[file] 物化目标数据源类型不支持: %s(%s)" % (ds.name, ds.type))
            return ExecResult(FAILURE, {}, [])
        target_ds_id = ds.id
        table = tmp_table_name(ctx.instance_id, _lookup_node_id(ctx), name)
        ctx.log("[file] 物化临时表: %s.%s" % (ds.db_name, table))
        rows_count, killed = _materialize(ctx, ds, table, _safe_columns(columns), _data_rows(spec), ctx.log)
        if killed:
            ctx.log("[file] 收到中断指令，物化中止（已插入 %d 行）" % rows_count)
            return ExecResult(KILL, {"rows_count": rows_count}, [])
        ref = table
    else:  # resultset（仅抽样 JSON）/ file（登记既有路径）
        raw, killed = _count_rows(ctx, spec, ctx.log)
        if killed:
            ctx.log("[file] 收到中断指令，统计中止")
            return ExecResult(KILL, {}, [])
        rows_count = raw - 1 if spec.header and raw else raw
        if kind == "file":
            ref = str(resolve_file_path(spec.path))
            ctx.log("[file] 登记共享卷文件: %s" % ref)

    # 5. 落库注册 + 输出
    keep_days = int(param.get("keepDays") or 0)
    _register_tmp(
        ctx, name=name, kind=kind, ref=ref, target_ds_id=target_ds_id,
        rows_count=rows_count, schema=schema,
        preview={"columns": columns, "rows": sample[:PREVIEW_ROWS]},
        retention=retention, keep_days=keep_days,
    )
    outputs["rows_count"] = rows_count
    outputs["tmp_name"] = name
    ctx.log("[file] 已注册临时数据: %s（%s，ref=%s，%d 行，保留=%s）" % (name, kind, ref, rows_count, retention))
    ctx.log("[file] 耗时 %d ms" % int((time.monotonic() - t0) * 1000))
    return ExecResult(SUCCESS, outputs, [])
