"""p_filter 执行器：过滤（Stream 算子）。

- 过滤条件：param.condition
- 输出：filtered_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("p_filter")
def execute(ctx) -> ExecResult:
    """执行流过滤，返回过滤后行数。"""
    param = ctx.param or {}
    condition = param.get("condition")

    if not condition:
        return ExecResult(FAILURE, {}, ["[p_filter] 未指定过滤条件（condition）"])

    ctx.log("[p_filter] 过滤条件: %s" % condition)

    # TODO: 实现流过滤
    outputs = {"filtered_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
