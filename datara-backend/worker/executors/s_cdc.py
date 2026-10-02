"""s_cdc 执行器：CDC 源（Stream 输入）。

- 数据源：param.datasource
- 表名：param.tables
- 输出：consumed_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("s_cdc")
def execute(ctx) -> ExecResult:
    """执行 CDC 消费，返回消费行数。"""
    param = ctx.param or {}
    datasource = param.get("datasource")
    tables = param.get("tables")

    if not datasource:
        return ExecResult(FAILURE, {}, ["[s_cdc] 未指定数据源（datasource）"])

    ctx.log("[s_cdc] 数据源: %s" % datasource)
    ctx.log("[s_cdc] 表名: %s" % tables)

    # TODO: 实现 CDC 消费
    outputs = {"consumed_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
