"""A6-20 DDL 文件解析（逆向导入 `.sql` → `[{name, comment, fields[]}]`）。

迁移源实锚 `datara-backend/common/sqlparser.py:289-337`（`parse_create_tables` 逐行照抄）。
**纯函数**：只依赖 `sqlglot`，不触库、不触网络 → 可差分锁定。

与 `rebuild/model/ddlgen.py`（模型 → DDL 文本）互为反向：本模块是 DDL 文本 → 契约字段。

注：`common/sqlparser.py` 其余部分（血缘 `StmtLineage`/`FieldMap` 等）属 17.2-21/22
血缘分片，不在本票范围；若后续血缘票需要，建议另立 `rebuild/lineage/` 承载，
避免把血缘语义混进 DDL 导入模块。
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp


def parse_create_tables(sql: str) -> list[dict]:
    """解析 CREATE TABLE → `[{name, comment, fields[]}]`。

    - `sqlglot.parse(read="mysql")`；语法错误上抛 `sqlglot.errors.ParseError`
      （调用方转 8010/400 并附行号）
    - 字段形状为 API 契约 camelCase；**仅取 CREATE TABLE**，其余语句忽略
    """
    out: list[dict] = []
    for stmt in sqlglot.parse(sql, read="mysql") or []:
        if not (isinstance(stmt, exp.Create) and stmt.kind == "TABLE"):
            continue
        schema = stmt.this
        if not isinstance(schema, exp.Schema):
            continue
        name = schema.this.name
        comment = ""
        props = stmt.args.get("properties")
        for p in (props.expressions if props else []):
            if isinstance(p, exp.SchemaCommentProperty):
                v = p.args.get("this")
                comment = v.name if isinstance(v, exp.Literal) else str(v or "")
        pk_cols: set[str] = set()
        for node in schema.expressions:
            if isinstance(node, exp.PrimaryKey):
                pk_cols.update(c.name for c in node.expressions)
        fields = []
        for coldef in schema.find_all(exp.ColumnDef):
            kind = coldef.kind
            dtype = ((getattr(kind.this, "value", "") or "VARCHAR")
                     if kind is not None else "VARCHAR").upper()
            params = [e.sql(dialect="mysql") for e in (kind.expressions if kind is not None else [])]
            cons = [c.args.get("kind") for c in (coldef.args.get("constraints") or [])
                    if c.args.get("kind") is not None]
            pk_inline = any(isinstance(k, exp.PrimaryKeyColumnConstraint) for k in cons)
            nullable = not any(isinstance(k, exp.NotNullColumnConstraint) for k in cons)
            d = next((k.this for k in cons if isinstance(k, exp.DefaultColumnConstraint)), None)
            cm = next((k.this for k in cons if isinstance(k, exp.CommentColumnConstraint)), None)
            fields.append({
                "name": coldef.name,
                "dataType": dtype,
                "length": str(params[0]) if params else "",
                "precision": str(params[1]) if len(params) > 1 else "",
                "nullable": nullable and not pk_inline,
                "defaultValue": (d.name if isinstance(d, exp.Literal)
                                 else d.sql(dialect="mysql")) if d is not None else "",
                "comment": cm.name if cm is not None else "",
                "isPk": coldef.name in pk_cols or pk_inline,
                "isPartition": False,
                "dictRef": "",
            })
        out.append({"name": name, "comment": comment, "fields": fields})
    return out
