"""o_doris 执行器：Doris 输出（Stream 输出）。

- 数据源：param.datasource
- 表名：param.table
- 输出：written_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("o_doris")
def execute(ctx) -> ExecResult:
    """执行 Doris 写入，返回写入行数。"""
    param = ctx.param or {}
    datasource = param.get("datasource")
    table = param.get("table")

    if not datasource or not table:
        return ExecResult(FAILURE, {}, ["[o_doris] 未指定数据源或表名"])

    ctx.log("[o_doris] 数据源: %s" % datasource)
    ctx.log("[o_doris] 表名: %s" % table)

    # TODO: 实现 Doris 写入
    outputs = {"written_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
