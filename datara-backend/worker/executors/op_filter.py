"""op_filter 执行器：行过滤（ETL 转换算子）。

- 过滤条件：param.condition（SQL WHERE 表达式）
- 输入：上游数据
- 输出：filtered_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("op_filter")
def execute(ctx) -> ExecResult:
    """执行行过滤，返回过滤后行数。"""
    param = ctx.param or {}
    condition = param.get("condition")

    if not condition:
        return ExecResult(FAILURE, {}, ["[op_filter] 未指定过滤条件（condition）"])

    ctx.log("[op_filter] 过滤条件: %s" % condition)

    # TODO: 实现行过滤
    outputs = {"filtered_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
