"""op_expr 执行器：表达式/派生列（ETL 转换算子）。

- 表达式：param.expression
- 输出列：param.outputColumn
- 输出：processed_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("op_expr")
def execute(ctx) -> ExecResult:
    """执行表达式计算，返回处理行数。"""
    param = ctx.param or {}
    expression = param.get("expression")
    output_column = param.get("outputColumn")

    if not expression:
        return ExecResult(FAILURE, {}, ["[op_expr] 未指定表达式（expression）"])

    ctx.log("[op_expr] 表达式: %s" % expression)
    ctx.log("[op_expr] 输出列: %s" % output_column)

    # TODO: 实现表达式计算
    outputs = {"processed_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
