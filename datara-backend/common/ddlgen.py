"""I18 DDL 方言生成器（纯函数）：mysql / greatdb / doris。

- 标识符一律经 dsconn.quote_ident 校验（与 meta_ops 同注入标准）
- 数据类型经 _TYPE_WHITELIST 白名单校验，length/precision 仅允许纯数字（防裸拼接注入）
- 字符串字面量统一反斜杠 + 单引号转义（MySQL/Doris 默认转义语义）
- 长度渲染：VARCHAR(n)/CHAR(n)/DECIMAL(p,s) 带参，其余裸类型大写
- is_partition 仅 doris 生效；mysql/greatdb 由 dialect_notes 提示不支持
- greatdb 与 mysql 同语系（dsconn 裁定②：GreatDB 走 MySQL 协议），无额外参数
- 字段入参形状为 API 契约 camelCase（见 api/model.py _field_row）
"""

import re
from typing import Optional

from common.dsconn import quote_ident

_TYPE_WHITELIST = frozenset({
    "TINYINT", "INT", "BIGINT", "VARCHAR", "CHAR", "DECIMAL",
    "DATE", "DATETIME", "DOUBLE", "TEXT",
})
_ARG_RE = re.compile(r"^\d{1,9}$")


def _lit(v: Optional[str]) -> str:
    """字符串字面量（反斜杠 + 单引号转义，MySQL/Doris 默认转义语义）。"""
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


def _ty(f: dict) -> str:
    t = str(f.get("dataType") or "VARCHAR").upper()
    if t not in _TYPE_WHITELIST:
        raise ValueError(f"不合法的数据类型: {t!r}")
    length = str(f.get("length") or "").strip()
    precision = str(f.get("precision") or "").strip()
    if length and not _ARG_RE.match(length):
        raise ValueError(f"不合法的长度: {length!r}")
    if precision and not _ARG_RE.match(precision):
        raise ValueError(f"不合法的精度: {precision!r}")
    if precision and not length:
        raise ValueError("精度需与长度同时填写")
    if t in ("VARCHAR", "CHAR") and length:
        return f"{t}({length})"
    if t == "DECIMAL" and length:
        return f"DECIMAL({length},{precision})" if precision else f"DECIMAL({length})"
    return t


def dialect_notes(fields: list[dict], engine: str) -> list[str]:
    """方言提示（前端预览区展示）。"""
    notes: list[str] = []
    if engine != "doris" and any(f.get("isPartition") for f in fields):
        notes.append("该引擎不支持分区声明")
    return notes


def gen_ddl(code: str, name: str, fields: list[dict], engine: str) -> str:
    """按方言生成 CREATE TABLE 文本（不落库）。

    标识符不合法直接 ValueError（路由转 400 MODEL_CODE_INVALID）。
    """
    if not fields:
        raise ValueError("字段列表为空")
    if engine not in ("mysql", "greatdb", "doris"):
        raise ValueError(f"不支持的引擎: {engine!r}")
    col_lines: list[str] = []
    pk_parts: list[str] = []
    part_parts: list[str] = []
    for f in fields:
        ident = quote_ident(str(f.get("name") or ""))
        seg = f"{ident} {_ty(f)}"
        if not f.get("nullable", True):
            seg += " NOT NULL"
        dv = f.get("defaultValue")
        if dv is not None and str(dv) != "":
            seg += f" DEFAULT {_lit(dv)}"
        seg += f" COMMENT {_lit(f.get('comment') or f.get('name') or '')}"
        col_lines.append(seg)
        if f.get("isPk"):
            pk_parts.append(ident)
        if f.get("isPartition"):
            part_parts.append(ident)

    lines = col_lines + (["PRIMARY KEY (" + ", ".join(pk_parts) + ")"] if pk_parts else [])
    body = ",\n  ".join(lines)

    if engine == "doris":
        head = (
            f"CREATE TABLE {quote_ident(code)} (\n  {body}\n)\n"
        )
        if part_parts:
            head += f"PARTITION BY RANGE({', '.join(part_parts)}) ()\n"
        dist = ", ".join(pk_parts) if pk_parts else quote_ident(str(fields[0]["name"]))
        return (
            head
            + f"DISTRIBUTED BY HASH({dist}) BUCKETS 10\n"
            + "PROPERTIES (\n"
            + "  'replication_num' = '1',\n"
            + "  'dynamic_partition.enable' = 'true',\n"
            + "  'dynamic_partition.time_unit' = 'DAY',\n"
            + "  'dynamic_partition.start' = '-30',\n"
            + "  'dynamic_partition.end' = '3',\n"
            + "  'dynamic_partition.prefix' = 'p'\n"
            + ")"
        )

    # mysql / greatdb（同语系）
    return (
        f"CREATE TABLE {quote_ident(code)} (\n  {body}\n"
        f") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT={_lit(name)}"
    )
