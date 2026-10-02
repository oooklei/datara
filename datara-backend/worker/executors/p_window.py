"""p_window 执行器：窗口（Stream 算子）。

- 窗口类型：param.windowType（tumbling/sliding/session）
- 窗口大小：param.windowSize
- 输出：windowed_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("p_window")
def execute(ctx) -> ExecResult:
    """执行窗口操作，返回窗口后行数。"""
    param = ctx.param or {}
    window_type = param.get("windowType", "tumbling")
    window_size = param.get("windowSize")

    if not window_size:
        return ExecResult(FAILURE, {}, ["[p_window] 未指定窗口大小（windowSize）"])

    ctx.log("[p_window] 窗口类型: %s" % window_type)
    ctx.log("[p_window] 窗口大小: %s" % window_size)

    # TODO: 实现窗口操作
    outputs = {"windowed_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
