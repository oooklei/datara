"""sqlglot 血缘解析器（I5 设计文档 §3，F20~F23）：SQL 语句 → 表级/字段级血缘。

- 纯函数：不触库、不抛出（解析异常该语句记 parse_error 日志、返回空血缘，
  血缘是旁路，绝不阻断任务执行）
- mysql 方言；表名未限定库时补 default_db（SQL 节点执行数据源所在库），
  血缘节点名统一 db.table
- CTE 名不算实体表（其 SELECT 体内来源正常收集）；CTE 别名引用列在字段级
  归属为 CTE 名本身
- 覆盖形态：INSERT..SELECT / INSERT..VALUES / CREATE..AS SELECT / UPDATE；
  纯 SELECT/SHOW/DESC 等无目标语句返回的 StmtLineage 无 to_tables，
  由调用侧（worker）跳过不落库
"""

from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from common.log import get_logger

_log = get_logger("common.sqlparser")

_STMT_MAX = 2000     # 语句原文截断（对齐 t_lineage_edge.stmt）
_TRANSFORM_MAX = 1000  # 表达式截断（对齐 t_lineage_field.transform）


@dataclass
class FieldMap:
    """字段级映射：目标字段 ← 来源字段 + 加工表达式（F22/F23）。"""

    to_table: str
    to_field: str
    from_table: str = ""   # 空串 = 常量/无来源
    from_field: str = ""
    transform: str = ""    # mysql 方言回写，如 "o.amount * 0.9"


@dataclass
class StmtLineage:
    """单语句血缘：表级输入/输出 + 字段级映射。"""

    stmt_no: int                 # 语句序号（1 起）
    stmt: str                    # 语句文本（回写，截断 2000）
    from_tables: list = field(default_factory=list)  # 输入表（去重保序）
    to_tables: list = field(default_factory=list)    # 输出表
    fields: list = field(default_factory=list)       # list[FieldMap]


def _short_sql(node) -> str:
    """表达式 mysql 方言回写（截断）。"""
    try:
        return node.sql(dialect="mysql")[:_TRANSFORM_MAX]
    except Exception:  # noqa: BLE001 回写失败不留 transform
        return ""


def _stmt_text(stmt) -> str:
    try:
        return stmt.sql(dialect="mysql")[:_STMT_MAX]
    except Exception:  # noqa: BLE001
        return ""


def _target_table(node):
    """Insert/Create/Update 目标定位：Schema(Table)/Alias(Table)/Table → Table。"""
    if isinstance(node, exp.Schema):
        node = node.this
    if isinstance(node, exp.Alias):
        node = node.this
    return node if isinstance(node, exp.Table) else None


def _target_columns(node) -> list:
    """INSERT 显式目标列（INSERT INTO t (a, b) SELECT ...）→ ['a', 'b']。"""
    if isinstance(node, exp.Schema):
        return [c.name for c in node.expressions
                if isinstance(c, (exp.Column, exp.Identifier))]
    return []


def _qual_name(tbl: exp.Table, default_db: str, cte_names: set) -> str:
    """表名限定：未指定库补 default_db；CTE 名保持原名（非实体表）。"""
    name = tbl.name
    if name in cte_names:
        return name
    db = tbl.db or ""
    if db:
        return "%s.%s" % (db, name)
    if default_db:
        return "%s.%s" % (default_db, name)
    return name


def _collect_tables(root, target_names: set, cte_names: set, default_db: str) -> list:
    """输入表收集：树内全部 Table - 目标 - CTE（去重保序）。"""
    out, seen = [], set()
    if root is None:
        return out
    for tbl in root.find_all(exp.Table):
        qn = _qual_name(tbl, default_db, cte_names)
        if tbl.name in cte_names or qn in target_names or qn in seen:
            continue
        seen.add(qn)
        out.append(qn)
    return out


def _alias_map(root, default_db: str, cte_names: set) -> dict:
    """别名/表名 → 限定名映射（字段级来源归属用）。"""
    amap: dict = {}
    if root is None:
        return amap
    for tbl in root.find_all(exp.Table):
        qn = _qual_name(tbl, default_db, cte_names)
        amap[tbl.alias_or_name] = qn
        amap.setdefault(tbl.name, qn)
    return amap


def _select_body(node):
    """取 SELECT 主体：剥 Subquery；Union 取左支（各支列语义一致）。"""
    if isinstance(node, exp.Subquery):
        return _select_body(node.this)
    if isinstance(node, exp.Union):
        return _select_body(node.this)
    return node if isinstance(node, exp.Select) else None


def _output_name(proj, idx: int) -> str:
    """投影输出名：别名 > 列名 > 表达式文本兜底。"""
    name = ""
    try:
        name = proj.output_name or ""
    except Exception:  # noqa: BLE001
        name = ""
    if not name and isinstance(proj, exp.Column):
        name = proj.name
    if not name:
        try:
            name = proj.alias_or_name or ""
        except Exception:  # noqa: BLE001
            name = ""
    return name or ("expr_%d" % (idx + 1))


def _resolve_from_table(col: exp.Column, amap: dict, scope, default_db: str,
                        cte_names: set) -> str:
    """来源列归属表：有前缀查别名映射；无前缀在唯一来源表（含 CTE 名）时归属之。"""
    prefix = col.table or ""
    if prefix:
        return amap.get(prefix, prefix)
    uniq = {_qual_name(t, default_db, cte_names) for t in scope.find_all(exp.Table)}
    return uniq.pop() if len(uniq) == 1 else ""


def _field_maps(body, to_table: str, target_cols: list, amap: dict,
                default_db: str, cte_names: set) -> list:
    """SELECT 投影 → 字段映射（Star/列数不齐时退化为跳过对应投影）。"""
    maps, seen = [], set()
    if body is None:
        return maps
    projs = list(body.expressions or [])
    if target_cols and len(target_cols) != len(projs):
        target_cols = []  # 显式列数与投影数不齐 → 退化用投影别名
    for idx, proj in enumerate(projs):
        if isinstance(proj, exp.Star):
            continue  # SELECT * 无法静态定字段来源，本期不落字段级
        to_field = target_cols[idx] if target_cols else _output_name(proj, idx)
        if not to_field:
            continue
        inner = proj.this if isinstance(proj, exp.Alias) else proj
        transform = _short_sql(inner)  # 别名剥离：transform 只留表达式体
        src_cols = list(proj.find_all(exp.Column))
        if not src_cols:  # 常量/函数无来源列
            key = (to_field, "", "")
            if key not in seen:
                seen.add(key)
                maps.append(FieldMap(to_table, to_field, "", "", transform))
            continue
        for col in src_cols:
            ft = _resolve_from_table(col, amap, body, default_db, cte_names)
            key = (to_field, ft, col.name)
            if key not in seen:
                seen.add(key)
                maps.append(FieldMap(to_table, to_field, ft, col.name, transform))
    return maps


def _parse_insert(stmt, default_db: str):
    tgt = _target_table(stmt.this)
    if tgt is None:
        return None
    target = _qual_name(tgt, default_db, set())
    cte_names = {c.alias_or_name for c in stmt.find_all(exp.CTE)}
    target_names = {target}
    src = stmt.expression
    # CTE 可能挂在 Insert 层（MySQL: INSERT INTO t WITH x AS (...) SELECT ...），
    # 来源表/别名映射按整条语句收集，目标表由 target_names 排除
    froms = _collect_tables(stmt, target_names, cte_names, default_db)
    body = _select_body(src)
    fields = []
    if body is not None:
        amap = _alias_map(stmt, default_db, cte_names)
        fields = _field_maps(body, target, _target_columns(stmt.this),
                             amap, default_db, cte_names)
    return froms, [target], fields


def _parse_create(stmt, default_db: str):
    kind = str(stmt.args.get("kind") or "").upper()
    if kind not in ("TABLE", "VIEW"):
        return None
    tgt = _target_table(stmt.this)
    if tgt is None:
        return None
    target = _qual_name(tgt, default_db, set())
    cte_names = {c.alias_or_name for c in stmt.find_all(exp.CTE)}
    src = stmt.expression
    froms = _collect_tables(stmt, {target}, cte_names, default_db)
    body = _select_body(src)
    fields = []
    if body is not None:
        amap = _alias_map(stmt, default_db, cte_names)
        fields = _field_maps(body, target, [], amap, default_db, cte_names)
    return froms, [target], fields


def _parse_update(stmt, default_db: str):
    tgt = _target_table(stmt.this)
    if tgt is None:
        return None
    target = _qual_name(tgt, default_db, set())
    cte_names = {c.alias_or_name for c in stmt.find_all(exp.CTE)}
    amap = _alias_map(stmt, default_db, cte_names)
    froms = _collect_tables(stmt, {target}, cte_names, default_db)
    fields = []
    for eq in stmt.expressions:
        if not isinstance(eq, exp.EQ):
            continue
        left, right = eq.this, eq.expression
        to_field = left.name if isinstance(left, exp.Column) else _short_sql(left)
        if not to_field:
            continue
        transform = _short_sql(right) if right is not None else ""
        src_cols = list(right.find_all(exp.Column)) if right is not None else []
        if not src_cols:
            fields.append(FieldMap(target, to_field, "", "", transform))
            continue
        for col in src_cols:
            ft = _resolve_from_table(col, amap, stmt, default_db, cte_names)
            fields.append(FieldMap(target, to_field, ft, col.name, transform))
    return froms, [target], fields


def _parse_stmt(no: int, stmt, default_db: str):
    """单语句解析 → StmtLineage；无目标语句（纯 SELECT 等）返回 None。"""
    if isinstance(stmt, exp.Insert):
        parsed = _parse_insert(stmt, default_db)
    elif isinstance(stmt, exp.Create):
        parsed = _parse_create(stmt, default_db)
    elif isinstance(stmt, exp.Update):
        parsed = _parse_update(stmt, default_db)
    else:
        return None
    if parsed is None:
        return None
    froms, tos, fields = parsed
    return StmtLineage(no, _stmt_text(stmt), froms, tos, fields)


def parse_sql_lineage(sql: str, default_db: str = "") -> list:
    """SQL 全文 → 逐语句血缘（解析容错：单语句异常不抛出，记日志跳过）。"""
    if not sql or not sql.strip():
        return []
    try:
        stmts = sqlglot.parse(sql, read="mysql")
    except Exception as exc:  # noqa: BLE001 整段解析失败 → 空血缘
        _log.warning("[sqlparser] parse_error（整段）: %r", exc)
        return []
    out = []
    for no, stmt in enumerate(stmts, start=1):
        if stmt is None:
            continue
        try:
            item = _parse_stmt(no, stmt, default_db)
            if item is not None:
                out.append(item)
        except Exception as exc:  # noqa: BLE001 单语句异常 → 跳过不阻断
            _log.warning("[sqlparser] parse_error 语句#%d: %r", no, exc)
    return out
