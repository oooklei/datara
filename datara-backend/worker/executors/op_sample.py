"""op_sample 执行器：采样（ETL 转换算子）。

- 采样率：param.sampleRate（0-1）
- 输出：sampled_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("op_sample")
def execute(ctx) -> ExecResult:
    """执行采样操作，返回采样后行数。"""
    param = ctx.param or {}
    sample_rate = param.get("sampleRate", 0.1)

    try:
        sample_rate = float(sample_rate)
    except (TypeError, ValueError):
        sample_rate = 0.1

    if sample_rate <= 0 or sample_rate > 1:
        return ExecResult(FAILURE, {}, ["[op_sample] 采样率无效（sampleRate）"])

    ctx.log("[op_sample] 采样率: %s" % sample_rate)

    # TODO: 实现采样操作
    outputs = {"sampled_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
