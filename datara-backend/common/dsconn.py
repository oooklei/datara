"""数据源连接工厂与文件源解析器（I4 设计文档 §3.1）。

- open_connection：mysql/greatdb 同驱动（GreatDB 走 MySQL 协议，裁定②）；每次独立短连接
- 文件源：/datara/files 共享卷路径收敛（防目录穿越）+ CSV/TXT/Excel 流式解析
- infer_schema：抽样类型推断 + 空值率（api 库表树 / worker C22 共用纯函数）
- 密码明文直用（09-18 裁定：内部系统，加密取消）
"""

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from itertools import islice
from pathlib import Path, PurePosixPath
from typing import Iterator, Optional

from pymysql.connections import Connection

from common.models import DataSource

FILES_ROOT = Path("/datara/files")  # datara-files 共享卷挂载点（宿主机 /mnt/lei/datara/files）

CONNECT_TIMEOUT = 5  # 连接建立超时（秒）
DEFAULT_READ_TIMEOUT = 60  # 单语句读超时（秒，IDE 口径）

_FORMATS = ("csv", "txt", "excel")
_DT_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d")
_TYPED = ("int", "float", "bool", "datetime")  # 推断优先序（str 兜底）


class FileSourceError(ValueError):
    """文件源参数/路径不合法（api 侧转 400）。"""


# ---------- 连接型数据源（mysql / greatdb 同驱动） ----------

def open_connection(
    ds: DataSource,
    *,
    db: Optional[str] = None,
    read_timeout: Optional[int] = DEFAULT_READ_TIMEOUT,  # None = 不限（导出重放链路）
) -> Connection:
    """按数据源行打开 pymysql 短连接（不进常驻池，防长查询占满 api 进程连接）。

    - db 可覆盖 ds.db_name（IDE 切库场景）
    - greatdb 缺省端口 3316（仅数据源行未填 port 时兜底，前端表单已带缺省）
    """
    if ds.type not in ("mysql", "greatdb"):
        raise ValueError(f"不支持的连接型数据源类型: {ds.type}")
    default_port = 3316 if ds.type == "greatdb" else 3306
    return Connection(
        host=ds.host or "127.0.0.1",
        port=int(ds.port) if ds.port else default_port,
        user=ds.user or "root",
        password=ds.pwd or "",
        database=db or ds.db_name or None,
        charset="utf8mb4",
        connect_timeout=CONNECT_TIMEOUT,
        read_timeout=read_timeout,
        write_timeout=read_timeout,
    )


def test_connection(ds: DataSource) -> str:
    """连通测试：connect + SELECT 1；status 回写由调用方负责。"""
    conn = open_connection(ds)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    finally:
        conn.close()
    return "online"


# ---------- 标识符（库/表/字段名）校验：I10 元数据端点族共用 ----------

# 含连字符：I4/I8 同步表名形如 20260101-9999-i3t_x；反引号包裹后连字符无注入面
_IDENT_RE = re.compile(r"^[\w$-]+$", re.UNICODE)


def quote_ident(name: str) -> str:
    """SQL 标识符校验 + 反引号包裹（元数据拼接防注入；不合法字符直接拒绝）。"""
    name = (name or "").strip()
    if not _IDENT_RE.match(name):
        raise ValueError(f"不合法的标识符: {name!r}")
    return f"`{name}`"


# ---------- 文件源（数据源中心 type=file / C22 手动参数共用） ----------

@dataclass
class FileSpec:
    """文件源规范化参数。"""

    format: str  # csv / txt / excel
    path: str  # /datara/files 下路径（绝对或相对）
    encoding: str = "utf-8"
    delimiter: str = ","  # 单字符直传 csv；多字符/正则串（如 \|\.\|）走 re.split
    header: bool = True  # 首行是否表头
    sheet: Optional[str] = None  # Excel sheet 名（缺省第一个）


def normalize_file_params(params: Optional[dict]) -> FileSpec:
    """params JSON（数据源中心 / C22 手动参数）→ FileSpec（校验必填）。"""
    params = dict(params or {})
    fmt = str(params.get("format", "")).strip().lower()
    if fmt in ("xlsx", "xls"):
        fmt = "excel"
    if fmt not in _FORMATS:
        raise FileSourceError(f"不支持的文件格式: {params.get('format')!r}（可选 csv/txt/excel）")
    path = str(params.get("path", "")).strip()
    if not path:
        raise FileSourceError("文件路径为空")
    delimiter = params.get("delimiter")
    delimiter = str(delimiter) if delimiter not in (None, "") else ("\t" if fmt == "txt" else ",")
    if delimiter == "\\t":  # 表单友好写法
        delimiter = "\t"
    header_raw = params.get("header", True)
    if isinstance(header_raw, str):  # 表单字符串布尔容错
        header = header_raw.strip().lower() not in ("", "false", "0", "no")
    else:
        header = bool(header_raw)
    return FileSpec(
        format=fmt,
        path=path,
        encoding=str(params.get("encoding") or "utf-8"),
        delimiter=delimiter,
        header=header,
        sheet=str(params["sheet"]) if params.get("sheet") else None,
    )


def parse_file_source(ds: DataSource) -> FileSpec:
    """数据源中心 type=file 行 → FileSpec（立即校验路径收敛）。"""
    if ds.type != "file":
        raise FileSourceError(f"数据源类型不是 file: {ds.type}")
    return normalize_file_params(ds.params)


def resolve_file_path(path: str) -> Path:
    """把路径收敛到共享卷内（api/worker 双侧调用，防目录穿越）。

    - 允许 /datara/files/xxx 绝对路径或 xxx 相对路径
    - resolve 后必须仍位于 FILES_ROOT 之下（拒绝 .. 越界与符号链接逃逸）
    """
    if not path:
        raise FileSourceError("文件路径为空")
    raw = PurePosixPath(path.replace("\\", "/"))
    candidate = Path(str(raw)) if raw.is_absolute() else FILES_ROOT / raw
    try:
        resolved = candidate.resolve()
        root = FILES_ROOT.resolve()
    except OSError as exc:
        raise FileSourceError(f"路径解析失败: {path}（{exc}）") from exc
    if resolved != root and root not in resolved.parents:
        raise FileSourceError(f"路径越出共享卷 {FILES_ROOT}: {path}")
    return resolved


def iter_rows(spec: FileSpec) -> Iterator[list]:
    """流式产出文件行（含表头行，去留由调用方定；内存 O(1) 行级）。"""
    path = resolve_file_path(spec.path)
    if not path.is_file():
        raise FileSourceError(f"文件不存在或不可读: {spec.path}")
    if spec.format == "excel":
        yield from _iter_excel(path, spec)
        return
    with open(path, "r", encoding=spec.encoding, newline="") as fh:
        if len(spec.delimiter) == 1:
            # 单字符分隔：csv.reader 处理引号转义
            for row in csv.reader(fh, delimiter=spec.delimiter):
                yield row
        else:
            # 多字符/正则分隔串（如 \|\.\|）：逐行 re.split
            pattern = re.compile(spec.delimiter)
            for line in fh:
                yield pattern.split(line.rstrip("\r\n"))


def _iter_excel(path: Path, spec: FileSpec) -> Iterator[list]:
    """openpyxl read_only 流式迭代（大文件内存约束，对齐 I2 datagen 经验）。"""
    from openpyxl import load_workbook  # 局部导入：非文件源调用不加载 openpyxl

    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        if spec.sheet and spec.sheet not in wb.sheetnames:
            raise FileSourceError(f"sheet 不存在: {spec.sheet}（现有 {wb.sheetnames}）")
        ws = wb[spec.sheet] if spec.sheet else wb[wb.sheetnames[0]]
        for row in ws.iter_rows(values_only=True):
            yield ["" if v is None else str(v) for v in row]
    finally:
        wb.close()


def head_rows(spec: FileSpec, limit: int = 5) -> list[list]:
    """读前 limit 行（文件源连通测试：存在+可读+解析头 5 行推断列数）。"""
    return list(islice(iter_rows(spec), limit))


def file_schema_preview(
    spec: FileSpec, sample_limit: int = 1000, preview_limit: int = 200
) -> tuple[dict, list[list]]:
    """抽样 + 推断 + 预览一次完成（C22 执行器/库表树共用，避免重复读文件）。"""
    sample = list(islice(iter_rows(spec), sample_limit))
    schema = infer_schema(sample, header=spec.header)
    return schema, sample[:preview_limit]


# ---------- 类型推断（纯函数，无 IO） ----------

def _is_datetime(s: str) -> bool:
    try:
        datetime.fromisoformat(s)
        return True
    except ValueError:
        pass
    for fmt in _DT_FORMATS:
        try:
            datetime.strptime(s, fmt)
            return True
        except ValueError:
            continue
    return False


def _value_types(v: str) -> set[str]:
    """单个非空值可承认的类型集合（str 恒可承认）。"""
    s = v.strip()
    types = {"str"}
    try:
        int(s)
        types |= {"int", "float"}
    except ValueError:
        try:
            float(s)
            types.add("float")
        except ValueError:
            pass
    if s.lower() in ("true", "false"):
        types.add("bool")
    if _is_datetime(s):
        types.add("datetime")
    return types


def infer_schema(rows: list[list], header: bool = True) -> dict:
    """抽样行类型推断 + 空值率统计。

    返回 {"columns": [{name, type, nullRate}], "sampledRows": n}；
    type ∈ int/float/bool/datetime/str（取样本全承认的最细类型）。
    """
    if not rows:
        return {"columns": [], "sampledRows": 0}
    width = max(len(r) for r in rows)
    first = rows[0]
    names = [
        str(first[i]).strip()
        if header and i < len(first) and str(first[i]).strip()
        else f"col_{i + 1}"
        for i in range(width)
    ]
    body = rows[1:] if header else rows
    if not body:
        return {"columns": [{"name": n, "type": "str", "nullRate": 0.0} for n in names], "sampledRows": 0}
    total = len(body)
    columns = []
    for i in range(width):
        allowed: set[str] = set(_TYPED)
        nulls = 0
        for r in body:
            v = str(r[i]).strip() if i < len(r) else ""
            if not v:
                nulls += 1
            elif allowed:  # 已全 str 后仅数空值，跳过类型判定（计算优化）
                allowed &= _value_types(v) & set(_TYPED)
        final = next((t for t in _TYPED if t in allowed), "str")
        columns.append({"name": names[i], "type": final, "nullRate": round(nulls / total, 4)})
    return {"columns": columns, "sampledRows": total}
