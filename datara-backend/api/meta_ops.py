"""表级元数据操作路由（I10 设计文档 §4.3，G10/G23/G24）。

- GET  .../tables/{tb}/ddl         SHOW CREATE TABLE / VIEW（浮层菜单「查看结构」）
- GET  .../tables/{tb}/count       行数统计
- POST /datasources/{id}/audit     删除/截断稽核：外键引用硬阻断 + 行数>0 强提醒 + 系统前缀提示
- GET  .../tables/{tb}/rows        编辑数据：按主键序加载行（offset/limit 分页）
- POST .../tables/{tb}/rows/apply  编辑数据事务应用：inserts/updates/deletes，失败整体回滚
- POST /datasources/{id}/import-csv CSV 导入：列映射 + executemany 分批 1000 事务插入，≤10 万行

路径中的库/表名一律经 quote_ident 校验（防注入）；值一律参数化传参。
"""

import csv
import io
import json
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import ApiError, get_current_user, require_perm
from api.ide import _jsonable
from common.db import get_db
from common.dsconn import open_connection, quote_ident
from common.log import get_logger
from common.models import DataSource, User
from common.resp import DS_NOT_FOUND, PARAM_INVALID, ok

logger = get_logger("api.meta_ops")

router = APIRouter(tags=["meta-ops"])

READ_TIMEOUT = 60
APPLY_ROW_CAP = 1000  # 单次 rows/apply 变更行数上限
IMPORT_ROW_CAP = 100_000  # CSV 导入数据行上限（裁定③）
IMPORT_BATCH = 1000  # executemany 批大小
MAX_FILE_BYTES = 256 * 1024 * 1024  # 上传文件字节上限（防超大文件占满内存）
_SYSTEM_PREFIXES = ("ods_", "dwd_", "dim_", "tmp_")


class AuditBody(BaseModel):
    db: str
    tb: str
    op: str  # drop | truncate


class ApplyBody(BaseModel):
    inserts: list[dict] = []
    updates: list[dict] = []
    deletes: list[dict] = []


def _conn_ds(db: Session, ds_id: int) -> DataSource:
    """取连接型数据源行（不存在 404 / 类型不支持 400）。"""
    row = db.get(DataSource, ds_id)
    if row is None:
        raise ApiError(DS_NOT_FOUND, status=404)
    if row.type not in ("mysql", "greatdb"):
        raise ApiError(PARAM_INVALID, "仅连接型数据源（mysql/greatdb）支持表操作", status=400)
    return row


def _idents(*names: str) -> tuple:
    """批量标识符校验 + 反引号包裹（任一不合法 → 400）。"""
    try:
        return tuple(quote_ident(n) for n in names)
    except ValueError as exc:
        raise ApiError(PARAM_INVALID, str(exc), status=400) from exc


def _open(ds: DataSource, db_name: str, read_timeout: Optional[int] = READ_TIMEOUT):
    """短连接包装（库不存在/网络失败 → 400 明确错误，不落 500）；read_timeout=None 不限（批量导入）。"""
    try:
        return open_connection(ds, db=db_name, read_timeout=read_timeout)
    except Exception as exc:  # noqa: BLE001
        raise ApiError(PARAM_INVALID, f"实例连接失败: {str(exc)[:300]}", status=400) from exc


def _primary_keys(cur, db_name: str, tb: str) -> list[str]:
    """主键列名（KEY_COLUMN_USAGE，建表序）。"""
    cur.execute(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE "
        "WHERE CONSTRAINT_NAME = 'PRIMARY' AND TABLE_SCHEMA = %s AND TABLE_NAME = %s "
        "ORDER BY ORDINAL_POSITION",
        (db_name, tb),
    )
    return [r[0] for r in cur.fetchall()]


@router.get("/datasources/{ds_id}/databases/{db_name}/tables/{table_name}/ddl")
def table_ddl(
    ds_id: int,
    db_name: str,
    table_name: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查看结构（G10）：SHOW CREATE TABLE；视图改 SHOW CREATE VIEW。"""
    ds = _conn_ds(db, ds_id)
    q_db, q_tb = _idents(db_name, table_name)
    conn = _open(ds, db_name)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
                (db_name, table_name),
            )
            row = cur.fetchone()
            if row is None:
                raise ApiError(PARAM_INVALID, f"表不存在: {db_name}.{table_name}", status=404)
            is_view = row[0] == "VIEW"
            cur.execute(f"SHOW CREATE VIEW {q_db}.{q_tb}" if is_view else f"SHOW CREATE TABLE {q_db}.{q_tb}")
            ddl = cur.fetchone()[1]
    finally:
        conn.close()
    return ok({"kind": "view" if is_view else "table", "ddl": ddl})


@router.get("/datasources/{ds_id}/databases/{db_name}/tables/{table_name}/count")
def table_count(
    ds_id: int,
    db_name: str,
    table_name: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """行数统计（精确 COUNT(*)；大表较慢，浮层菜单按需调用）。"""
    ds = _conn_ds(db, ds_id)
    q_tb = _idents(table_name)[0]
    conn = _open(ds, db_name)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {q_tb}")
            count = cur.fetchone()[0]
    finally:
        conn.close()
    return ok({"count": count})


@router.post("/datasources/{ds_id}/audit")
def table_audit(
    ds_id: int,
    body: AuditBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除/截断稽核（G10）：外键引用硬阻断；行数>0 强提醒；系统前缀提示。

    返回 {pass, checks[]}；pass=False 时前端禁止继续（实际 DROP/TRUNCATE 仍走 IDE 执行）。
    """
    ds = _conn_ds(db, ds_id)
    if body.op not in ("drop", "truncate"):
        raise ApiError(PARAM_INVALID, f"不支持的稽核操作: {body.op}（可选 drop/truncate）", status=400)
    _idents(body.db, body.tb)
    checks: list[dict] = []
    conn = _open(ds, body.db)
    try:
        with conn.cursor() as cur:
            # 1) 外键引用反查：有子表引用 → 硬阻断
            cur.execute(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE "
                "WHERE REFERENCED_TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME = %s",
                (body.db, body.tb),
            )
            fk_count = cur.fetchone()[0]
            if fk_count:
                checks.append(
                    {
                        "level": "block",
                        "code": "fk_reference",
                        "message": f"存在 {fk_count} 个外键引用本表，{body.op} 将导致依赖失效，已硬阻断",
                    }
                )
            # 2) 行数>0 → 强提醒（数据销毁风险）
            q_tb = quote_ident(body.tb)
            cur.execute(f"SELECT COUNT(*) FROM {q_tb}")
            rows = cur.fetchone()[0]
            if rows > 0:
                checks.append(
                    {
                        "level": "warn",
                        "code": "rows_not_empty",
                        "message": f"表内现有 {rows} 行数据，{body.op.upper()} 将不可恢复",
                    }
                )
            # 3) 系统前缀 → 提示（数仓分层表谨慎操作）
            if body.tb.lower().startswith(_SYSTEM_PREFIXES):
                checks.append(
                    {
                        "level": "info",
                        "code": "system_prefix",
                        "message": f"表名带数仓分层前缀（{'/'.join(_SYSTEM_PREFIXES)}），请确认非核心业务表",
                    }
                )
    finally:
        conn.close()
    passed = not any(c["level"] == "block" for c in checks)
    logger.info(
        "表稽核: ds=%s %s.%s op=%s → pass=%s checks=%d（操作人 %s）",
        ds.name, body.db, body.tb, body.op, passed, len(checks), user.user_name,
    )
    return ok({"pass": passed, "checks": checks})


@router.get("/datasources/{ds_id}/databases/{db_name}/tables/{table_name}/rows")
def table_rows(
    ds_id: int,
    db_name: str,
    table_name: str,
    offset: int = 0,
    limit: int = 200,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """编辑数据行加载（G23）：主键序 + offset/limit；无主键表不加排序（分页可能漂移）。

    返回 {columns, rows, total, pks}；rows 值经 _jsonable 安全化。
    """
    ds = _conn_ds(db, ds_id)
    q_tb = _idents(table_name)[0]
    offset = max(int(offset), 0)
    limit = min(max(int(limit), 1), 500)
    conn = _open(ds, db_name)
    try:
        with conn.cursor() as cur:
            pks = _primary_keys(cur, db_name, table_name)
            cur.execute(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
                (db_name, table_name),
            )
            columns = [r[0] for r in cur.fetchall()]
            if not columns:
                raise ApiError(PARAM_INVALID, f"表不存在: {db_name}.{table_name}", status=404)
            order = ""
            if pks:
                order = " ORDER BY " + ", ".join(quote_ident(pk) for pk in pks)
            cur.execute(f"SELECT * FROM {q_tb}{order} LIMIT %s OFFSET %s", (limit, offset))
            rows = [[_jsonable(v) for v in row] for row in cur.fetchall()]
            cur.execute(f"SELECT COUNT(*) FROM {q_tb}")
            total = cur.fetchone()[0]
    finally:
        conn.close()
    return ok({"columns": columns, "rows": rows, "total": total, "pks": pks, "offset": offset})


@router.post("/datasources/{ds_id}/databases/{db_name}/tables/{table_name}/rows/apply")
def table_rows_apply(
    ds_id: int,
    db_name: str,
    table_name: str,
    body: ApplyBody,
    user: User = Depends(require_perm("run_instance")),
    db: Session = Depends(get_db),
):
    """编辑数据事务应用（G23）：{inserts, updates, deletes} 单事务逐条应用。

    - inserts: [{col: value, ...}, ...]
    - updates: [{"keys": {pk: val, ...}, "data": {col: new_value, ...}}, ...]
    - deletes: [{pk: val, ...}, ...]
    任一条失败 → 整体 ROLLBACK（裁定③）；成功 COMMIT。总行数 ≤1000。
    """
    ds = _conn_ds(db, ds_id)
    q_tb = _idents(table_name)[0]
    total = len(body.inserts) + len(body.updates) + len(body.deletes)
    if total == 0:
        raise ApiError(PARAM_INVALID, "无待应用变更", status=400)
    if total > APPLY_ROW_CAP:
        raise ApiError(PARAM_INVALID, f"单次变更行数超上限 {APPLY_ROW_CAP}", status=400)

    conn = _open(ds, db_name)
    results: list[dict] = []
    applied = 0
    status = "success"
    error_msg: Optional[str] = None
    try:
        with conn.cursor() as cur:
            pks = _primary_keys(cur, db_name, table_name)
            if (body.updates or body.deletes) and not pks:
                raise ApiError(PARAM_INVALID, "该表无主键，不支持更新/删除（仅可追加行）", status=400)
            try:
                for i, item in enumerate(body.deletes):
                    if not item:
                        raise ValueError("删除行缺少主键值")
                    where = " AND ".join(f"{quote_ident(k)} = %s" for k in item)
                    cur.execute(f"DELETE FROM {q_tb} WHERE {where}", tuple(item.values()))
                    applied += 1
                    results.append({"op": "delete", "index": i, "ok": True, "affected": cur.rowcount})
                for i, item in enumerate(body.updates):
                    keys, data = item.get("keys") or {}, item.get("data") or {}
                    if not keys or not data:
                        raise ValueError("更新行缺少主键或变更值")
                    sets = ", ".join(f"{quote_ident(k)} = %s" for k in data)
                    where = " AND ".join(f"{quote_ident(k)} = %s" for k in keys)
                    cur.execute(
                        f"UPDATE {q_tb} SET {sets} WHERE {where}", (*data.values(), *keys.values())
                    )
                    applied += 1
                    results.append({"op": "update", "index": i, "ok": True, "affected": cur.rowcount})
                for i, item in enumerate(body.inserts):
                    if not item:
                        raise ValueError("追加行缺少字段值")
                    cols = ", ".join(quote_ident(k) for k in item)
                    marks = ", ".join(["%s"] * len(item))
                    cur.execute(f"INSERT INTO {q_tb} ({cols}) VALUES ({marks})", tuple(item.values()))
                    applied += 1
                    results.append({"op": "insert", "index": i, "ok": True, "affected": cur.rowcount})
                conn.commit()
            except Exception as exc:  # noqa: BLE001 单条失败 → 整体回滚
                conn.rollback()
                status = "rolled_back"
                error_msg = str(exc)[:2000]
                results.append({"op": "failed", "index": len(results), "ok": False, "error": error_msg})
    finally:
        conn.close()
    logger.info(
        "编辑数据应用: ds=%s %s.%s 增/改/删=%d/%d/%d → %s applied=%d（操作人 %s）",
        ds.name, db_name, table_name, len(body.inserts), len(body.updates), len(body.deletes),
        status, applied, user.user_name,
    )
    return ok({"status": status, "applied": applied, "error": error_msg, "results": results})


@router.post("/datasources/{ds_id}/import-csv")
async def import_csv(
    ds_id: int,
    db_name: str = Form(...),
    table_name: str = Form(...),
    mapping: str = Form(...),  # JSON：{csv列名: 表字段名}
    has_header: bool = Form(True),
    file: UploadFile = File(...),
    user: User = Depends(require_perm("run_instance")),
    db: Session = Depends(get_db),
):
    """CSV 导入（G24）：列映射 + executemany 分批 1000 事务插入；数据行 >10 万整单拒绝。

    has_header=False 时 CSV 列按 c1..cN 引用；导入失败整体回滚。
    """
    ds = _conn_ds(db, ds_id)
    q_tb = _idents(table_name)[0]
    try:
        col_map: dict = json.loads(mapping or "{}")
    except json.JSONDecodeError as exc:
        raise ApiError(PARAM_INVALID, f"mapping 不是合法 JSON: {exc}", status=400) from exc
    col_map = {str(k).strip(): str(v).strip() for k, v in col_map.items() if str(v).strip()}
    if not col_map:
        raise ApiError(PARAM_INVALID, "列映射为空", status=400)

    if (file.size or 0) > MAX_FILE_BYTES:
        raise ApiError(PARAM_INVALID, f"文件超过大小上限 {MAX_FILE_BYTES // 1024 // 1024}MB", status=400)
    raw = await file.read()
    # 编码探测：utf-8-sig 优先（兼容 BOM/Excel 导出），失败降级 gbk
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("gbk")
        except UnicodeDecodeError as exc:
            raise ApiError(PARAM_INVALID, "文件编码无法识别（仅支持 UTF-8/GBK）", status=400) from exc

    # 行级流式收集（超上限即停，内存 O(上限行) 而非 O(文件)）
    reader = csv.reader(io.StringIO(text))
    rows: list[list] = []
    max_keep = IMPORT_ROW_CAP + 2  # header + 余量
    over_cap = False
    for r in reader:
        if any(str(cell).strip() for cell in r):
            rows.append(r)
        if len(rows) > max_keep:
            over_cap = True
            break
    del text, raw  # 大字符串及时释放
    if over_cap:
        raise ApiError(
            PARAM_INVALID, f"数据行超过导入上限 {IMPORT_ROW_CAP} 行（裁定③）", status=400
        )
    if has_header:
        if not rows:
            raise ApiError(PARAM_INVALID, "CSV 文件为空", status=400)
        header = [str(c).strip() for c in rows[0]]
        data_rows = rows[1:]
        missing = [k for k in col_map if k not in header]
        if missing:
            raise ApiError(PARAM_INVALID, f"CSV 表头缺少映射列: {missing}", status=400)
        col_idx = [header.index(k) for k in col_map]
    else:
        data_rows = rows
        width = max((len(r) for r in rows), default=0)
        header = [f"c{i + 1}" for i in range(width)]
        unknown = [k for k in col_map if k not in header]
        if unknown:
            raise ApiError(PARAM_INVALID, f"映射列超出来源列数: {unknown}（共 {width} 列，用 c1..cN 引用）", status=400)
        col_idx = [header.index(k) for k in col_map]
    if len(data_rows) > IMPORT_ROW_CAP:
        raise ApiError(
            PARAM_INVALID,
            f"数据行 {len(data_rows)} 超过导入上限 {IMPORT_ROW_CAP} 行（裁定③）",
            status=400,
        )
    if not data_rows:
        raise ApiError(PARAM_INVALID, "CSV 无数据行", status=400)

    # 目标表字段校验（映射值必须存在于表结构）
    conn = _open(ds, db_name, read_timeout=None)  # 批量插入不限读超时
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s",
                (db_name, table_name),
            )
            table_cols = {r[0] for r in cur.fetchall()}
            invalid = [v for v in col_map.values() if v not in table_cols]
            if invalid:
                raise ApiError(PARAM_INVALID, f"目标表不存在字段: {invalid}", status=400)

            target_cols = list(col_map.values())
            cols_sql = ", ".join(quote_ident(c) for c in target_cols)
            marks = ", ".join(["%s"] * len(target_cols))
            sql = f"INSERT INTO {q_tb} ({cols_sql}) VALUES ({marks})"
            inserted = 0
            try:
                for start in range(0, len(data_rows), IMPORT_BATCH):
                    batch = []
                    for r in data_rows[start:start + IMPORT_BATCH]:
                        batch.append(
                            [_jsonable(r[i]) if i < len(r) else None for i in col_idx]
                        )
                    cur.executemany(sql, batch)
                    inserted += len(batch)
                conn.commit()
            except Exception as exc:  # noqa: BLE001 失败整体回滚
                conn.rollback()
                raise ApiError(PARAM_INVALID, f"导入失败已回滚: {str(exc)[:500]}", status=400) from exc
    finally:
        conn.close()
    logger.info(
        "CSV 导入: ds=%s %s.%s 映射=%d 列 行数=%d（操作人 %s）",
        ds.name, db_name, table_name, len(target_cols), inserted, user.user_name,
    )
    return ok({"imported": inserted, "columns": target_cols})
