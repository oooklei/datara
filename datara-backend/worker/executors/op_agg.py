"""op_agg 执行器：聚合（ETL 转换算子）。

- 分组键：param.groupBy
- 聚合函数：param.aggregations（sum/avg/count/min/max）
- 输出：aggregated_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("op_agg")
def execute(ctx) -> ExecResult:
    """执行聚合操作，返回聚合后行数。"""
    param = ctx.param or {}
    group_by = param.get("groupBy")
    aggregations = param.get("aggregations", [])

    if not aggregations:
        return ExecResult(FAILURE, {}, ["[op_agg] 未指定聚合函数（aggregations）"])

    ctx.log("[op_agg] 分组键: %s" % group_by)
    ctx.log("[op_agg] 聚合函数: %s" % aggregations)

    # TODO: 实现聚合操作
    outputs = {"aggregated_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
