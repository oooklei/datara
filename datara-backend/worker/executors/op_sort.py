"""op_sort 执行器：排序（ETL 转换算子）。

- 排序字段：param.sortBy
- 排序方向：param.order（asc/desc）
- 输出：sorted_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("op_sort")
def execute(ctx) -> ExecResult:
    """执行排序操作，返回排序后行数。"""
    param = ctx.param or {}
    sort_by = param.get("sortBy")
    order = param.get("order", "asc")

    if not sort_by:
        return ExecResult(FAILURE, {}, ["[op_sort] 未指定排序字段（sortBy）"])

    ctx.log("[op_sort] 排序字段: %s" % sort_by)
    ctx.log("[op_sort] 排序方向: %s" % order)

    # TODO: 实现排序操作
    outputs = {"sorted_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
