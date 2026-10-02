"""C17 数据同步执行器（I6 设计文档 §4，F33；读写器分离，DataX/SeaTunnel 式）。

- 读端：MySQL/GreatDB（单 schema / 多 schema UNION ALL / 分区隔离 / 前缀多表探测）+ CSV/TXT/Excel 文件源
- readerWhere：连接型拼入 SQL WHERE（与增量条件 AND 组合，括号包裹）；文件型按 `列 op 值` 逐行过滤
- readerMatchType：exact（缺省，同名表）/ prefix（readerMatchPrefix 或表名前缀，逐库收集全部匹配表）
- 写端：MySQL/GreatDB；autoCreate 按源列建表（连接型同构复制 COLUMN_TYPE，文件型 TEXT）
- 合并策略（裁定①）：union=多表 UNION ALL 追加 / src_flag=UNION ALL+schema 标识列 /
  partition=每源 schema 独立目标表 {writerTable}_{schema尾段}
- 运行时探测（裁定②）：autoSchema=true 时 SHOW DATABASES 差集发现新增 schema 匹配表自动纳入
- 脏数据容忍（F33）：批插异常回退逐行定位，bad_rows 超 errorThreshold → failure
- 血缘（裁定④）：成功后表级边（每参与源表→目标表）+ 字段映射落库（worker.lineage 公共入口）
- outputs：read_rows/write_rows/bad_rows/skipped_rows/rows_per_sec/batch_id(=instance_id)/schemas_included
"""

import re
import time

from pymysql.cursors import SSCursor

from common.dsconn import (
    FileSourceError,
    file_schema_preview,
    iter_rows,
    normalize_file_params,
    open_connection,
)
from common.models import DataSource
from worker.executor import ExecResult, register
from worker.lineage import collect_sync_lineage
from worker.state import FAILURE, KILL, SUCCESS

_FILE_TYPES = frozenset({"csv", "txt", "excel"})
_CONN_TYPES = frozenset({"mysql", "greatdb"})
_STRATEGIES = frozenset({"union", "src_flag", "partition"})
_SYSTEM_DBS = frozenset({"information_schema", "mysql", "performance_schema", "sys"})

_INSERT_BATCH = 1000       # 写端批大小上限（脏数据逐行回退粒度）
_KILL_CHECK_BATCHES = 50   # 每隔多少批检查一次 kill 中断
_PROGRESS_BATCHES = 10     # 每隔多少批打一次进度日志


class SyncFail(Exception):
    """脏数据超阈值（failure 收口，携带根因）。"""


def _lookup_datasource(ref):
    """按名称查 t_data_source，纯数字兜底按 id（与 sql.py/file.py 同口径）。"""
    from common.db import new_session

    session = new_session()
    try:
        ds = session.query(DataSource).filter(DataSource.name == ref).first()
        if ds is None and str(ref).isdigit():
            ds = session.get(DataSource, int(ref))
        return ds
    finally:
        session.close()


def _backtick(name) -> str:
    """物理表名清洗：剥 ${tmp.*} 替换产物可能携带的反引号与空白。"""
    return str(name or "").strip().strip("`").strip()


def _source_columns(conn, schema: str, table: str) -> list:
    """源表列清单（INFORMATION_SCHEMA，ORDINAL_POSITION 序）：[(name, column_type)]。"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COLUMN_NAME, COLUMN_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
            (schema, table),
        )
        return [(str(r[0]), str(r[1])) for r in cur.fetchall()]


def _resolve_schemas(conn, param, table: str, match_type: str, log) -> list:
    """参与 schema 集（裁定②运行时探测）：已选集 + autoSchema 差集纳入 + 匹配表探测。

    返回 [(schema, 实际表名)]：exact 逐库校验同名表；prefix 按 pattern
    （readerMatchPrefix 非空则用之，否则 readerTable）逐库收集全部匹配表。
    无匹配表的库剔除，全部为空报参数错误。
    """
    pattern = ("%s%%" % (_backtick(param.get("readerMatchPrefix")) or table)
               if match_type == "prefix" else table)
    # 前端表单键 readerSchemasText（逗号分隔文本）优先；API/旧契约 readerSchemas（list）兜底
    raw_schemas = param.get("readerSchemasText") or param.get("readerSchemas") or []
    if isinstance(raw_schemas, str):  # 前端逗号分隔文本输入兼容（中英文逗号）
        raw_schemas = raw_schemas.replace("，", ",").split(",")
    picked = [str(s).strip() for s in raw_schemas if str(s).strip()]
    if not picked:
        # pymysql ≥2.x 的 conn.db 是 bytes（b'ec_retail'）——必须 str 化，否则进 picked 后
        # 与 SHOW DATABASES 的 str 集合比对全落空（missing 混 bytes 直接 join 崩）
        picked = [str(conn.db, "utf-8") if isinstance(conn.db, bytes) else str(conn.db)] if conn.db else []
    if not picked:
        raise FileSourceError("读端未指定 schema 且数据源未配置默认库")
    with conn.cursor() as cur:
        cur.execute("SHOW DATABASES")
        all_dbs = {str(r[0]) for r in cur.fetchall()}
    schemas = [s for s in picked if s in all_dbs]
    missing = [s for s in picked if s not in all_dbs]
    if missing:
        log("[sync] 已选 schema 不存在（剔除）: %s" % ", ".join(missing))
    if param.get("autoSchema", True):
        for db in sorted(all_dbs - set(picked)):
            if db in _SYSTEM_DBS:
                continue
            with conn.cursor() as cur:
                cur.execute("SHOW TABLES FROM `%s` LIKE %%s" % db, (pattern,))
                if cur.fetchone() is not None:
                    schemas.append(db)
                    log("[sync] 探测到新增 schema: %s（同名表纳入）" % db)
    if not schemas:
        raise FileSourceError("无可用参与 schema")
    pairs = []
    for s in schemas:
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES FROM `%s` LIKE %%s" % s, (pattern,))
            matched = [str(r[0]) for r in cur.fetchall()]
        if not matched:
            log("[sync] schema %s 无匹配表（剔除）: %s" % (s, pattern))
            continue
        if match_type == "prefix":
            pairs.extend((s, t) for t in matched)
        else:
            pairs.append((s, table))
    if not pairs:
        raise FileSourceError("参与 schema 下无匹配表: %s" % pattern)
    return pairs


def _schema_suffix(schema: str) -> str:
    """分区表后缀（裁定①）：schema 尾段，ec_retail_east → east。"""
    parts = str(schema).split("_")
    return parts[-1] if parts[-1] else schema


def _plan_targets(schemas: list, strategy: str, writer_table: str) -> list:
    """策略 → 目标表计划：[(物理目标表名, 源 schema, 源实际表名)]（union/src_flag 后两位为 None）。"""
    if strategy == "partition":
        return [("%s_%s" % (writer_table, _schema_suffix(s)), s, t) for s, t in schemas]
    return [(writer_table, None, None)]


def _column_pairs(first_cols: list, field_map: list, flag_column: str,
                  strategy: str) -> tuple:
    """源列/目标列配对：fieldMap 优先，空=同名全列；src_flag 目标侧追加标识列。"""
    if field_map:
        # 键名双兼容：执行器契约 {from,to} / 前端 kv-table 形态 {key,value}
        src_cols = [str(m.get("from") or m.get("key") or "").strip() for m in field_map]
        dst_cols = [str(m.get("to") or m.get("value") or "").strip() for m in field_map]
        if not all(src_cols) or not all(dst_cols):
            raise FileSourceError("字段映射存在空列名: %r" % field_map)
    else:
        src_cols = [c for c, _t in first_cols]
        dst_cols = list(src_cols)
    if strategy == "src_flag":
        dst_cols = dst_cols + [flag_column]
    return src_cols, dst_cols


def _create_target(conn, table: str, first_cols: list, dst_cols: list,
                   flag_column: str, strategy: str, is_file: bool) -> None:
    """autoCreate 建目标表：连接型同构 COLUMN_TYPE / 文件型 TEXT；src_flag 追加标识列。"""
    col_type = {name: ctype for name, ctype in first_cols}
    defs = []
    for c in dst_cols:
        if strategy == "src_flag" and c == flag_column:
            defs.append("`%s` VARCHAR(64) NULL" % c)
        elif is_file or c not in col_type:
            defs.append("`%s` TEXT NULL" % c)
        else:
            defs.append("`%s` %s NULL" % (c, col_type[c]))
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS `%s`" % table)
        cur.execute(
            "CREATE TABLE `%s` (%s) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
            % (table, ", ".join(defs))
        )
    conn.commit()


def _insert_batch(cur, conn, table: str, dst_cols: list, batch: list,
                  error_threshold: int, bad_rows: int, log) -> int:
    """批插 + 脏数据逐行回退定位；返回累计坏行数（超阈值抛 SyncFail）。"""
    cols_sql = ", ".join("`%s`" % c for c in dst_cols)
    marks = ", ".join(["%s"] * len(dst_cols))
    sql = "INSERT INTO `%s` (%s) VALUES (%s)" % (table, cols_sql, marks)
    try:
        cur.executemany(sql, batch)
        conn.commit()
        return bad_rows
    except Exception:  # noqa: BLE001 回退逐行定位坏行
        first_err = None
        for row in batch:
            try:
                cur.execute(sql, row)
                conn.commit()
            except Exception as row_exc:  # noqa: BLE001 坏行计数
                if first_err is None:
                    first_err = row_exc
                bad_rows += 1
        if first_err is not None:
            log("[sync] 脏数据: 本批定位坏行（示例: %r）" % first_err)
        if bad_rows > error_threshold:
            raise SyncFail("坏行数 %d 超过错误阈值 %d" % (bad_rows, error_threshold)) from first_err
        return bad_rows


def _pump(read_iter, writer_conn, target_table: str, dst_cols: list, batch_size: int,
          error_threshold: int, ctx, stat: dict) -> None:
    """统一搬运循环：迭代器 → 分批写（kill 检查/进度日志/脏数据回退），原地更新 stat。"""
    wcur = writer_conn.cursor()
    batch, batch_no = [], 0
    try:
        for row in read_iter:
            stat["read"] += 1
            batch.append(row)
            if len(batch) >= batch_size:
                stat["bad"] = _insert_batch(wcur, writer_conn, target_table, dst_cols,
                                            batch, error_threshold, stat["bad"], ctx.log)
                stat["write"] += len(batch)
                batch_no += 1
                batch = []
                if batch_no % _KILL_CHECK_BATCHES == 0 and ctx.killed():
                    raise KeyboardInterrupt
                if batch_no % _PROGRESS_BATCHES == 0:
                    ctx.log("[sync] 进度: 已读 %d / 已写 %d / 坏行 %d"
                            % (stat["read"], stat["write"], stat["bad"]))
        if batch:
            stat["bad"] = _insert_batch(wcur, writer_conn, target_table, dst_cols,
                                        batch, error_threshold, stat["bad"], ctx.log)
            stat["write"] += len(batch)
    finally:
        wcur.close()


def _sql_row_iter(conn, select_sql: str, batch_size: int):
    """SSCursor 流式读取（大结果集内存 O(batch)），逐行产出。"""
    cur = conn.cursor(SSCursor)
    try:
        cur.execute(select_sql)
        while True:
            rows = cur.fetchmany(batch_size)
            if not rows:
                break
            yield from rows
    finally:
        cur.close()


_WHERE_OPS = ("!=", ">=", "<=", "=", ">", "<")  # 文件行过滤操作符（顺序敏感：长操作符在前）


def _parse_file_where(expr, col_names: list) -> list:
    """文件读端 readerWhere 解析：AND 连接的 `列 op 值` 简单条件 → [(列下标, op, 值)]。

    值可带单/双引号（剥壳后按文本比对，两侧均可转 float 则数值比较）；
    SQL 式大写 AND 兼容（split 忽略大小写）；非法片段/未知列直接报参数错误。
    """
    text = str(expr or "").strip()
    if not text:
        return []
    conds = []
    for part in re.split(r"\s+AND\s+", text, flags=re.IGNORECASE):
        seg = part.strip()
        hit = None
        for op in _WHERE_OPS:
            pos = seg.find(op)
            if pos > 0:
                name = seg[:pos].strip().strip("`'\"").strip()
                raw = seg[pos + len(op):].strip()
                if name and raw:
                    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
                        raw = raw[1:-1]
                    if name in col_names:
                        hit = (col_names.index(name), op, raw)
                break
        if hit is None:
            raise FileSourceError("readerWhere 片段非法（仅支持 列 op 值，AND 连接）: %s" % seg)
        conds.append(hit)
    return conds


def _cell_match(cell, op: str, raw: str) -> bool:
    """单条件求值：两侧均可转 float 则数值比较，否则字符串比较（None 视为空串）。"""
    text = "" if cell is None else str(cell)
    try:
        left, right = float(text), float(raw)
    except ValueError:
        left, right = text, raw
    if op == "=":
        return left == right
    if op == "!=":
        return left != right
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    return left <= right


def _row_matches(row: list, conds: list) -> bool:
    """文件行是否满足全部过滤条件（列下标取值，缺列视为空）。"""
    for idx, op, raw in conds:
        if not _cell_match(row[idx] if idx < len(row) else None, op, raw):
            return False
    return True


def _build_union_sql(schemas: list, src_cols: list,
                     strategy: str, flag_column: str, where: str) -> str:
    """union/src_flag 生成 UNION ALL 语句（schemas=[(schema, 实际表名)]，src_flag 附加标识列）。"""
    cols_sql = ", ".join("`%s`" % c for c in src_cols)
    branches = []
    for s, t in schemas:
        if strategy == "src_flag":
            branches.append("SELECT %s, '%s' AS `%s` FROM `%s`.`%s`%s"
                            % (cols_sql, s.replace("'", "''"), flag_column, s, t, where))
        else:
            branches.append("SELECT %s FROM `%s`.`%s`%s" % (cols_sql, s, t, where))
    return "\nUNION ALL\n".join(branches)


@register("sync")
def execute(ctx) -> ExecResult:
    """C17 主流程：参数解析 → 读端计划 → 目标端准备 → 搬运 → 统计/血缘。"""
    param = ctx.param or {}
    t0 = time.monotonic()
    log = ctx.log
    strategy = str(param.get("strategy") or "union").strip()
    if strategy not in _STRATEGIES:
        return ExecResult(FAILURE, {}, ["[sync] 未知合并策略: %s" % strategy])
    match_type = "prefix" if str(param.get("readerMatchType") or "").strip().lower() == "prefix" else "exact"
    flag_column = _backtick(param.get("flagColumn") or "src_schema")
    writer_table = _backtick(param.get("writerTable"))
    if not writer_table:
        return ExecResult(FAILURE, {}, ["[sync] 未指定目标表（writerTable）"])
    batch_size = max(1, int(param.get("batchSize") or _INSERT_BATCH))
    error_threshold = int(param.get("errorThreshold") or 0)
    incremental = param.get("incremental") or {}
    if not incremental.get("column"):  # 前端平铺键兼容（incrementalColumn/incrementalExpr）
        flat_col = str(param.get("incrementalColumn") or "").strip()
        if flat_col:
            incremental = {"column": flat_col, "expr": str(param.get("incrementalExpr") or "")}
    field_map = param.get("fieldMap") or []

    reader_conn = writer_conn = None
    stat = {"read": 0, "write": 0, "bad": 0, "skip": 0}
    try:
        # ---- 读端解析（连接型 / 文件型） ----
        reader_type = str(param.get("readerType") or "").strip().lower()
        reader_ds = None  # 兜底路径已查的读端数据源对象；连接型分支复用，避免同 readerDs 二次查询
        if not reader_type and param.get("readerDs"):
            # 端点合一物化路径只发 readerDs（§3.2，无 readerType）：按数据源类型兜底推断（连接型分支内会再校验）
            reader_ds = _lookup_datasource(param.get("readerDs"))
            if reader_ds is not None:
                reader_type = str(reader_ds.type or "").strip().lower()
        if reader_type in _FILE_TYPES:
            file_params = dict(param.get("readerFile") or {})
            if not file_params:  # 前端平铺键兼容（readerPath/readerFormat/…）
                file_params = {
                    "format": str(param.get("readerFormat") or reader_type or "csv"),
                    "path": param.get("readerPath") or "",
                    "encoding": param.get("readerEncoding") or "utf-8",
                    "delimiter": param.get("readerDelimiter") or ",",
                    "header": param.get("readerHeader", True),
                    "sheet": param.get("readerSheet") or "",
                }
            spec = normalize_file_params(file_params)
            log("[sync] 文件读端: %s（format=%s delimiter=%r header=%s）"
                % (spec.path, spec.format, spec.delimiter, spec.header))
            schema_preview, _sample = file_schema_preview(spec, sample_limit=1000, preview_limit=0)
            first_cols = [(str(c["name"]), "text") for c in schema_preview.get("columns") or []]
            if not first_cols:
                return ExecResult(FAILURE, {}, ["[sync] 文件无有效列（空文件或全空行）"])
            file_conds = _parse_file_where(param.get("readerWhere"), [c for c, _t in first_cols])
            if file_conds:
                log("[sync] 文件行过滤: %d 项条件" % len(file_conds))
            schemas, reader_table, is_file = [""], "", True
        elif reader_type in _CONN_TYPES:
            if reader_ds is None:  # readerType 显式给出的旧路径：兜底未触发，此处才自查
                reader_ds = _lookup_datasource(param.get("readerDs"))
            if reader_ds is None:
                return ExecResult(FAILURE, {},
                                  ["[sync] 读端数据源不存在: %s" % param.get("readerDs")])
            if str(reader_ds.type or "").lower() not in _CONN_TYPES:
                return ExecResult(FAILURE, {}, ["[sync] 读端数据源类型不支持: %s" % reader_ds.type])
            reader_conn = open_connection(reader_ds, read_timeout=None)
            reader_table = _backtick(param.get("readerTable"))
            if not reader_table:
                return ExecResult(FAILURE, {}, ["[sync] 未指定读端表（readerTable）"])
            schemas = _resolve_schemas(reader_conn, param, reader_table, match_type, log)
            log("[sync] 参与表: %s" % ", ".join("%s.%s" % (s, t) for s, t in schemas))
            if match_type == "prefix":
                log("[sync] 前缀匹配命中表数: %d" % len(schemas))
            first_cols = _source_columns(reader_conn, schemas[0][0], schemas[0][1])
            if not first_cols:
                return ExecResult(FAILURE, {},
                                  ["[sync] 源表无列: %s.%s" % (schemas[0][0], schemas[0][1])])
            is_file = False
        else:
            return ExecResult(FAILURE, {}, ["[sync] 不支持的读端类型: %s" % reader_type])

        # ---- 写端准备 ----
        writer_ds = _lookup_datasource(param.get("writerDs"))
        if writer_ds is None:
            return ExecResult(FAILURE, {}, ["[sync] 写端数据源不存在: %s" % param.get("writerDs")])
        if str(writer_ds.type or "").lower() not in _CONN_TYPES:
            return ExecResult(FAILURE, {}, ["[sync] 写端数据源类型不支持: %s" % writer_ds.type])
        writer_conn = open_connection(writer_ds, read_timeout=None)

        plan = _plan_targets(schemas, strategy, writer_table)
        src_cols, dst_cols = _column_pairs(first_cols, field_map, flag_column, strategy)
        for target_table, _s, _t in plan:
            with writer_conn.cursor() as cur:
                cur.execute("SHOW TABLES LIKE %s", (target_table,))
                exists = cur.fetchone() is not None
            if not exists:
                if param.get("autoCreate", True):
                    _create_target(writer_conn, target_table, first_cols, dst_cols,
                                   flag_column, strategy, is_file)
                    log("[sync] 已自动建表: %s（%d 列）" % (target_table, len(dst_cols)))
                else:
                    raise FileSourceError("目标表不存在且未开启自动建表: %s" % target_table)
            elif param.get("truncate"):
                with writer_conn.cursor() as cur:
                    cur.execute("TRUNCATE TABLE `%s`" % target_table)
                writer_conn.commit()
                log("[sync] 已清空目标表: %s" % target_table)

        # ---- 搬运 ----
        try:
            if is_file:
                def file_rows():
                    skip_header = spec.header
                    for row in iter_rows(spec):
                        if skip_header:
                            skip_header = False
                            continue
                        if file_conds and not _row_matches(row, file_conds):
                            stat["skip"] += 1
                            continue
                        vals = [None if v is None or str(v) == "" else str(v)
                                for v in row[: len(dst_cols)]]
                        if len(vals) < len(dst_cols):
                            vals += [None] * (len(dst_cols) - len(vals))
                        yield tuple(vals)

                _pump(file_rows(), writer_conn, plan[0][0], dst_cols,
                      batch_size, error_threshold, ctx, stat)
            else:
                conds = []
                if incremental and incremental.get("column"):
                    conds.append("(`%s` >= '%s')" % (
                        _backtick(incremental["column"]),
                        str(incremental.get("expr") or "").replace("'", "''")))
                reader_where = str(param.get("readerWhere") or "").strip()
                if reader_where:
                    # 内部工具：表达式原样拼入，括号包裹隔离 AND 优先级
                    conds.append("(%s)" % reader_where)
                where = " WHERE %s" % " AND ".join(conds) if conds else ""
                if strategy == "partition":
                    for target_table, schema, src_table in plan:
                        select_sql = ("SELECT %s FROM `%s`.`%s`%s"
                                      % (", ".join("`%s`" % c for c in src_cols),
                                         schema, src_table, where))
                        ctx.log("[sync] 抽取: %s" % select_sql[:300].replace("\n", " "))
                        _pump(_sql_row_iter(reader_conn, select_sql, batch_size),
                              writer_conn, target_table, dst_cols,
                              batch_size, error_threshold, ctx, stat)
                else:
                    select_sql = _build_union_sql(schemas, src_cols,
                                                  strategy, flag_column, where)
                    ctx.log("[sync] 抽取: %s" % select_sql[:300].replace("\n", " "))
                    _pump(_sql_row_iter(reader_conn, select_sql, batch_size),
                          writer_conn, plan[0][0], dst_cols,
                          batch_size, error_threshold, ctx, stat)
        except KeyboardInterrupt:
            log("[sync] 收到中断指令，搬运中止（已写 %d 行）" % stat["write"])
            return ExecResult(KILL, {"read_rows": stat["read"], "write_rows": stat["write"]}, [])

        secs = max(time.monotonic() - t0, 0.001)
        rps = round(stat["write"] / secs, 1)
        outputs = {
            "read_rows": stat["read"],
            "write_rows": stat["write"],
            "bad_rows": stat["bad"],
            "skipped_rows": stat["skip"],
            "rows_per_sec": rps,
            "batch_id": ctx.instance_id,
            # prefix 模式输出 "schema.table" 形态；exact 维持 schema 名单（旧契约）
            "schemas_included": [] if is_file else (
                ["%s.%s" % (s, t) for s, t in schemas] if match_type == "prefix"
                else [s for s, _t in schemas]),
        }
        log("[sync] 完成: 读 %d / 写 %d / 坏行 %d / 过滤跳过 %d（%.1f 行/s，耗时 %dms）"
            % (stat["read"], stat["write"], stat["bad"], stat["skip"], rps, int(secs * 1000)))

        # ---- 血缘（裁定④，旁路；空写不落避免零行边噪音） ----
        if stat["write"] > 0:
            fields = [{"from_field": s, "to_field": d}
                      for s, d in zip(src_cols, dst_cols) if d != flag_column]
            if is_file:
                edges = [{"from": "", "to": plan[0][0], "stmt": "", "fields": fields}]
            elif strategy == "partition":
                edges = [{"from": "%s.%s" % (s, t), "to": tbl, "stmt": "",
                          "fields": fields} for tbl, s, t in plan]
            else:
                stmt = _build_union_sql(schemas, src_cols, strategy, flag_column, where)
                edges = [{"from": "%s.%s" % (s, t), "to": plan[0][0],
                          "stmt": stmt, "fields": fields} for s, t in schemas]
            collect_sync_lineage(ctx, edges, writer_ds.name)

        return ExecResult(SUCCESS, outputs, [])
    except SyncFail as exc:
        log("[sync] 失败: %s" % exc)
        return ExecResult(FAILURE, {}, [])
    except FileSourceError as exc:
        log("[sync] 参数/源错误: %s" % exc)
        return ExecResult(FAILURE, {}, [])
    except Exception as exc:  # noqa: BLE001 执行异常统一 failure
        import traceback
        log("[sync] 执行异常: %r" % exc)
        log("[sync] 堆栈: %s" % traceback.format_exc())
        return ExecResult(FAILURE, {}, [])
    finally:
        if reader_conn is not None:
            reader_conn.close()
        if writer_conn is not None:
            writer_conn.close()
