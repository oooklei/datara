"""op_merge 执行器：合并/Union（ETL 转换算子）。

- 合并模式：param.mergeMode（union/unionAll）
- 输出：merged_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("op_merge")
def execute(ctx) -> ExecResult:
    """执行合并操作，返回合并后行数。"""
    param = ctx.param or {}
    merge_mode = param.get("mergeMode", "union")

    ctx.log("[op_merge] 合并模式: %s" % merge_mode)

    # TODO: 实现合并操作
    outputs = {"merged_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
