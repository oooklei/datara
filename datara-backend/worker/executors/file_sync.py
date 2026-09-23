"""C24 文件同步执行器（I12 设计 §3.1）：Excel/CSV/TXT 文件 → 库表，补齐同步类「文件源入仓」。

- 取文件：/datara/files 共享卷直读（file.py 同口径）；不在共享卷且配置 runtimeNode →
  SFTP 拉取到共享卷暂存（{instance_id}_filesync_ 前缀，对齐 D4 清扫口径），结束即清理
- 解析/类型推断：复用 dsconn.iter_rows + infer_schema（file.py 既有函数，不复制逻辑）
- 建表：auto_create 按推断类型映射 BIGINT/DOUBLE/TINYINT(1)/DATETIME/TEXT；src_flag 追加标识列
- 写入：append=INSERT / overwrite=先 TRUNCATE / src_flag=常量标识列（值=来源文件名）；
  批插复用 sync._insert_batch（脏行逐行回退计数为忽略行，不断流）
- 参数（I12 T11 修：键名统一 camelCase，对齐 C17/C22 惯例）：filePath/stagedPath（二选一）/
  fileName/fileType/delimiter/encoding/headerRows/targetDs/targetSchema/targetTable（或 {schema,table}）/
  autoCreate/ddl（留空推断）/writeMode/flagColumn/fieldMap
- 输出：rows_read/rows_written/rows_skipped/batch_id(=instance_id)
"""

import os
import time
from itertools import chain, islice

from common.dsconn import (
    FILES_ROOT,
    FileSourceError,
    infer_schema,
    iter_rows,
    normalize_file_params,
    open_connection,
    resolve_file_path,
)
from worker.executors.file import _safe_columns
from worker.executors.ssh import _connect, _lookup_node
from worker.executors.sync import SyncFail, _column_pairs, _insert_batch, _lookup_datasource
from worker.executor import ExecResult, register
from worker.state import FAILURE, KILL, SUCCESS

try:
    import paramiko
except ImportError:  # 依赖缺失不阻断 worker 进程，执行时按 failure 留痕
    paramiko = None

INSERT_BATCH = 1000        # 写端批大小（对齐 file.py/sync.py 口径）
KILL_CHECK_BATCHES = 50    # 每隔多少批检查一次 kill 中断
PROGRESS_BATCHES = 10      # 每隔多少批打一次进度日志
SAMPLE_LIMIT = 1000        # 类型推断抽样行数（file_schema_preview 同口径）
SKIP_THRESHOLD = 10 ** 15  # 坏行只计「忽略行」不断流（设计 §3.1 日志含忽略行数）

# infer_schema 类型 → DDL 类型（I12；str 兜底 TEXT）
_SQL_TYPES = {"int": "BIGINT", "float": "DOUBLE", "bool": "TINYINT(1)", "datetime": "DATETIME"}
_WRITE_MODES = ("append", "overwrite", "src_flag")


def _int_or(v, dft: int) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return dft


def _stage_remote(ctx, node, remote_path: str) -> str:
    """SFTP 拉取远端文件 → 共享卷暂存（{instance_id}_filesync_ 前缀），返回共享卷相对路径。"""
    if paramiko is None:
        raise FileSourceError("paramiko 未安装，无法经 SFTP 拉取远端文件")
    # I12 T11 修：_connect 签名为 5 参 (host, port, user, cred, ctx)，勿传节点名
    client = _connect(node.host, node.port, node.user or "root", node.auth or "", ctx)
    staged = "%s_filesync_%s" % (
        ctx.instance_id, os.path.basename(remote_path.replace("\\", "/")) or "file")
    local_path = FILES_ROOT / staged
    try:
        sftp = client.open_sftp()
        try:
            os.makedirs(FILES_ROOT, exist_ok=True)
            ctx.log("[file_sync] SFTP 拉取: %s@%s:%s → %s"
                    % (node.name, node.host, remote_path, local_path))
            sftp.get(remote_path, str(local_path))
        finally:
            sftp.close()
    finally:
        client.close()
    return staged


def _resolve_source(ctx, param: dict) -> tuple:
    """取文件：上传暂存路径/共享卷直读优先；否则经运行时节点 SFTP 拉取暂存。返回 (spec_path, 暂存相对路径|None)。"""
    # I12 T11 修：上传暂存备选来源（stagedPath，/datara/files 相对，与 filePath 二选一）——本地共享卷直读，不走 SFTP
    staged_in = str(param.get("stagedPath") or "").strip().strip("/")
    raw = str(param.get("filePath") or "").strip().rstrip("/")
    fname = str(param.get("fileName") or "").strip()
    if fname and not raw.endswith("/" + fname):  # 来源选到目录：拼接文件名
        raw = "%s/%s" % (raw, fname)
    if staged_in and not raw:
        local = resolve_file_path(staged_in)
        if not local.is_file():
            raise FileSourceError("上传暂存文件不存在: %s（请先经文件管理上传到 /datara/files）" % staged_in)
        return staged_in, None
    if not raw:
        raise FileSourceError("未配置文件来源（文件路径 / 上传暂存路径 二选一）")
    try:
        local = resolve_file_path(raw)
        if local.is_file():
            return raw, None
        if local.is_dir():
            raise FileSourceError("路径是目录而非文件: %s（请补文件名或选择具体文件）" % raw)
    except FileSourceError:
        pass  # 不在共享卷 → 走 SFTP 拉取
    node_ref = str(param.get("runtimeNode") or "").strip()
    if not node_ref:
        raise FileSourceError("文件不在共享卷且未配置运行时节点: %s" % raw)
    node = _lookup_node(node_ref)
    if node is None:
        raise FileSourceError("运行时节点不存在: %s" % node_ref)
    staged = _stage_remote(ctx, node, raw)
    return staged, staged


def _open_after_header(spec, header_rows: int):
    """打开文件迭代器并跳过表头块。返回 (数据迭代器, 表头行名|None, 底层生成器)。

    I12 T11 修：header_rows=0（无表头）时首行即数据行——peek 判空后经 chain 回注，
    不再静默丢弃（原实现抽样与写流各丢一次首行）；底层生成器单独返回供调用方
    及时 close()（chain 包装体无 close，且关闭生成器才能释放文件句柄）。
    """
    raw = iter_rows(spec)
    first = next(raw, None)
    if first is None:
        raise FileSourceError("文件为空: %s" % spec.path)
    if header_rows <= 0:
        return chain([first], raw), None, raw  # 无表头：首行即数据，回注不丢
    for _ in range(header_rows - 1):  # 附加表头行一并跳过
        if next(raw, None) is None:
            break
    return raw, [str(v).strip() for v in first], raw


@register("file_sync")
def execute(ctx) -> ExecResult:
    """C24 主流程：取文件 → 解析推断 → 目标端准备 → 批量写入 → 三行数输出。"""
    param = ctx.param or {}
    t0 = time.monotonic()
    log = ctx.log
    staged_rel = None
    conn = None
    rows_read = rows_written = skipped = 0
    try:
        # ---- 1. 取文件 + 解析参数 ----
        file_type = str(param.get("fileType") or "csv").strip().lower()
        file_type = {"xlsx": "excel", "xls": "excel"}.get(file_type, file_type)
        write_mode = str(param.get("writeMode") or "append").strip()
        if write_mode not in _WRITE_MODES:
            raise FileSourceError("未知写入模式: %s（append/overwrite/src_flag）" % write_mode)
        header_rows = max(0, _int_or(param.get("headerRows"), 1))
        spec_path, staged_rel = _resolve_source(ctx, param)
        spec = normalize_file_params({
            "format": file_type,
            "path": spec_path,
            "encoding": param.get("encoding") or "utf-8",
            "delimiter": param.get("delimiter"),
            "header": header_rows > 0,
        })
        log("[file_sync] 来源: %s（format=%s encoding=%s delimiter=%r 表头行=%d）"
            % (spec_path, spec.format, spec.encoding, spec.delimiter, header_rows))

        # ---- 2. 抽样 + 类型推断（样本读与写读独立 iterator，样本行不占用写流） ----
        sample_it, header_names, sample_raw = _open_after_header(spec, header_rows)
        sample = list(islice(sample_it, SAMPLE_LIMIT))
        sample_raw.close()  # I12 T11 修：抽样后立即释放文件句柄（写入阶段重开新流）
        inferred = infer_schema(sample, header=False).get("columns") or []
        if not inferred:
            if header_names is not None:
                raise FileSourceError("表头后无数据行: %s" % spec_path)
            raise FileSourceError("文件无有效列（全空行）: %s" % spec_path)
        # 列名：表头行优先（宽度按推断列对齐，缺名回退 col_N），无表头用 col_N
        columns = [
            header_names[i] if header_names is not None and i < len(header_names) and header_names[i]
            else str(inferred[i]["name"])
            for i in range(len(inferred))
        ]
        types = [str(c["type"]) for c in inferred]
        columns = _safe_columns(columns)
        log("[file_sync] 列数=%d 抽样=%d 行；类型推断: %s"
            % (len(columns), len(sample),
               ", ".join("%s:%s" % (c, t) for c, t in zip(columns, types))))

        # ---- 3. 目标端解析 + 列配对（复用 sync._column_pairs：field_map 优先，同名全列兜底） ----
        writer_ds = _lookup_datasource(str(param.get("targetDs") or ""))
        if writer_ds is None:
            raise FileSourceError("目标数据源不存在: %s" % param.get("targetDs"))
        if str(writer_ds.type or "").lower() not in ("mysql", "greatdb"):
            raise FileSourceError("目标数据源类型不支持: %s(%s)" % (writer_ds.name, writer_ds.type))
        target = param.get("targetTable")
        if isinstance(target, dict):  # 前端 table-picker schemaTable 形态
            schema_name, table = str(target.get("schema") or ""), str(target.get("table") or "")
        else:
            schema_name = str(param.get("targetSchema") or "")
            table = str(target or "")
        table = table.strip("`").strip()
        if not table:
            raise FileSourceError("未配置目标表（targetTable）")
        flag_column = str(param.get("flagColumn") or "src_schema").strip("`").strip() or "src_schema"
        field_map = param.get("fieldMap") if isinstance(param.get("fieldMap"), list) else []
        type_of = dict(zip(columns, types))
        src_cols, dst_cols = _column_pairs(
            [(c, "text") for c in columns], field_map, flag_column,
            "src_flag" if write_mode == "src_flag" else "union")
        col_types = [type_of.get(str(s), "str") for s in src_cols]

        # ---- 4. 目标端准备：auto_create 建表 / overwrite 清空 ----
        conn = open_connection(writer_ds, db=schema_name or None, read_timeout=None)
        with conn.cursor() as cur:
            cur.execute("SHOW TABLES LIKE %s", (table,))
            exists = cur.fetchone() is not None
        if not exists:
            if not param.get("autoCreate", True):
                raise FileSourceError("目标表不存在且未开启自动建表: %s" % table)
            # I12 T11 修：自定义 DDL 优先（前端可编辑覆盖，设计 §3.1）；留空按文件头推断
            custom_ddl = str(param.get("ddl") or "").strip()
            if custom_ddl:
                with conn.cursor() as cur:
                    cur.execute(custom_ddl)
                conn.commit()
                log("[file_sync] 按自定义 DDL 建表: %s（DDL 前 200 字: %s）" % (table, custom_ddl[:200]))
            else:
                defs = ["`%s` %s NULL" % (c, _SQL_TYPES.get(t, "TEXT")) for c, t in zip(dst_cols, col_types)]
                if write_mode == "src_flag":
                    defs.append("`%s` VARCHAR(64) NULL" % flag_column)
                with conn.cursor() as cur:
                    cur.execute("CREATE TABLE `%s` (%s) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
                                % (table, ", ".join(defs)))
                conn.commit()
                log("[file_sync] 已自动建表: %s（%d 列，按文件头推断类型）" % (table, len(dst_cols)))
        if write_mode == "overwrite":
            with conn.cursor() as cur:
                cur.execute("TRUNCATE TABLE `%s`" % table)
            conn.commit()
            log("[file_sync] 覆盖模式: 已清空目标表 %s" % table)
        flag_value = os.path.basename(spec_path.replace("\\", "/"))
        if write_mode == "src_flag":
            log("[file_sync] 标识列: %s=%s（常量，来源文件名）" % (flag_column, flag_value))

        # ---- 5. 批量写入（kill 检查 / 进度日志 / 脏行回退计忽略） ----
        write_it, _names, write_raw = _open_after_header(spec, header_rows)  # 写流重开，表头块同样跳过
        cur = conn.cursor()
        batch, batch_no = [], 0
        try:
            for row in write_it:
                vals = []
                for i in range(len(src_cols)):
                    v = row[i] if i < len(row) else ""
                    v = "" if v is None else str(v)
                    vals.append(None if v == "" else v)
                if write_mode == "src_flag":
                    vals.append(flag_value)
                if len(vals) < len(dst_cols):
                    vals += [None] * (len(dst_cols) - len(vals))  # 短行补空（错位行容错）
                rows_read += 1
                batch.append(tuple(vals))
                if len(batch) >= INSERT_BATCH:
                    skipped = _insert_batch(cur, conn, table, dst_cols, batch,
                                            SKIP_THRESHOLD, skipped, log)
                    rows_written += len(batch)
                    batch_no += 1
                    batch = []
                    if batch_no % KILL_CHECK_BATCHES == 0 and ctx.killed():
                        log("[file_sync] 收到中断指令，写入中止（已写 %d 行）" % rows_written)
                        return ExecResult(KILL, _outputs(ctx, rows_read, rows_written, skipped), [])
                    if batch_no % PROGRESS_BATCHES == 0:
                        log("[file_sync] 进度: 已读 %d / 已写 %d / 忽略 %d"
                            % (rows_read, rows_written, skipped))
            if batch:
                skipped = _insert_batch(cur, conn, table, dst_cols, batch,
                                        SKIP_THRESHOLD, skipped, log)
                rows_written += len(batch)
        finally:
            cur.close()
            write_raw.close()  # I12 T11 修：KILL 早退同样释放文件句柄（成功路径遍历尽后 close 幂等）

        log("[file_sync] 完成: 读 %d / 写 %d / 忽略 %d（耗时 %dms）"
            % (rows_read, rows_written, skipped, int((time.monotonic() - t0) * 1000)))
        return ExecResult(SUCCESS, _outputs(ctx, rows_read, rows_written, skipped), [])
    except SyncFail as exc:
        log("[file_sync] 失败: %s" % exc)
        return ExecResult(FAILURE, _outputs(ctx, rows_read, rows_written, skipped), [])
    except FileSourceError as exc:
        log("[file_sync] 参数/源错误: %s" % exc)
        return ExecResult(FAILURE, _outputs(ctx, rows_read, rows_written, skipped), [])
    except Exception as exc:  # noqa: BLE001 执行异常统一 failure
        log("[file_sync] 执行异常: %r" % exc)
        return ExecResult(FAILURE, _outputs(ctx, rows_read, rows_written, skipped), [])
    finally:
        if conn is not None:
            conn.close()
        if staged_rel is not None:  # SFTP 暂存文件即用即清（D4 清扫兜底口径）
            try:
                os.unlink(str(FILES_ROOT / staged_rel))
            except OSError:
                pass


def _outputs(ctx, rows_read: int, rows_written: int, rows_skipped: int) -> dict:
    """统一输出契约（I12 设计 §3.1：目标表 + 批次号 ${instance_id}）。"""
    return {
        "rows_read": rows_read,
        "rows_written": rows_written,
        "rows_skipped": rows_skipped,
        "batch_id": ctx.instance_id,
    }
