"""op_select 执行器：字段选择（ETL 转换算子）。

- 选择字段：param.columns
- 输出：processed_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("op_select")
def execute(ctx) -> ExecResult:
    """执行字段选择，返回处理行数。"""
    param = ctx.param or {}
    columns = param.get("columns", [])

    if not columns:
        return ExecResult(FAILURE, {}, ["[op_select] 未指定选择字段（columns）"])

    ctx.log("[op_select] 选择字段: %s" % columns)

    # TODO: 实现字段选择
    outputs = {"processed_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
