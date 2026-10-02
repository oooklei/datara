"""op_replace 执行器：查找替换（ETL 转换算子）。

- 查找值：param.searchValue
- 替换值：param.replaceValue
- 输出：replaced_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("op_replace")
def execute(ctx) -> ExecResult:
    """执行查找替换，返回替换后行数。"""
    param = ctx.param or {}
    search_value = param.get("searchValue")
    replace_value = param.get("replaceValue")

    if search_value is None:
        return ExecResult(FAILURE, {}, ["[op_replace] 未指定查找值（searchValue）"])

    ctx.log("[op_replace] 查找值: %s" % search_value)
    ctx.log("[op_replace] 替换值: %s" % replace_value)

    # TODO: 实现查找替换
    outputs = {"replaced_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
