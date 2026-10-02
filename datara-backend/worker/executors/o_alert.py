"""o_alert 执行器：实时告警（Stream 输出）。

- 告警条件：param.condition
- 告警级别：param.level（info/warning/critical）
- 输出：alert_count
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("o_alert")
def execute(ctx) -> ExecResult:
    """执行告警检查，返回告警次数。"""
    param = ctx.param or {}
    condition = param.get("condition")
    level = param.get("level", "info")

    if not condition:
        return ExecResult(FAILURE, {}, ["[o_alert] 未指定告警条件（condition）"])

    ctx.log("[o_alert] 告警条件: %s" % condition)
    ctx.log("[o_alert] 告警级别: %s" % level)

    # TODO: 实现告警检查
    outputs = {"alert_count": 0}
    return ExecResult(SUCCESS, outputs, [])
