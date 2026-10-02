"""src_db 执行器：JDBC 数据库读取（ETL 输入源）。

- 数据源解析：param.datasource → t_data_source
- SQL 查询：param.sql 或 param.table + param.where
- 输出：row_count + result_preview（前 200 行）
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS

PREVIEW_ROWS = 200


@register("src_db")
def execute(ctx) -> ExecResult:
    """执行数据库查询，返回行数和预览数据。"""
    param = ctx.param or {}
    ds_ref = param.get("datasource") or param.get("datasource_id")

    if not ds_ref:
        return ExecResult(FAILURE, {}, ["[src_db] 未指定数据源（datasource）"])

    ctx.log("[src_db] 数据源: %s" % ds_ref)
    ctx.log("[src_db] SQL: %s" % (param.get("sql") or param.get("table") or "未指定"))

    # TODO: 实现 JDBC 查询
    outputs = {
        "row_count": 0,
        "result_preview": {"columns": [], "rows": []},
    }
    return ExecResult(SUCCESS, outputs, [])
