"""op_cep 执行器：CEP 引擎（Stream 算子）。

- 模式：param.pattern
- 输出：matched_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("op_cep")
def execute(ctx) -> ExecResult:
    """执行 CEP 模式匹配，返回匹配行数。"""
    param = ctx.param or {}
    pattern = param.get("pattern")

    if not pattern:
        return ExecResult(FAILURE, {}, ["[op_cep] 未指定模式（pattern）"])

    ctx.log("[op_cep] 模式: %s" % pattern)

    # TODO: 实现 CEP 模式匹配
    outputs = {"matched_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
