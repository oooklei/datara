"""p_join 执行器：Join（Stream 算子）。

- Join 类型：param.joinType
- 左流键：param.leftKey
- 右流键：param.rightKey
- 输出：joined_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("p_join")
def execute(ctx) -> ExecResult:
    """执行流 Join，返回连接后行数。"""
    param = ctx.param or {}
    join_type = param.get("joinType", "inner")
    left_key = param.get("leftKey")
    right_key = param.get("rightKey")

    if not left_key or not right_key:
        return ExecResult(FAILURE, {}, ["[p_join] 未指定连接键（leftKey/rightKey）"])

    ctx.log("[p_join] 类型: %s" % join_type)
    ctx.log("[p_join] 左流键: %s" % left_key)
    ctx.log("[p_join] 右流键: %s" % right_key)

    # TODO: 实现流 Join
    outputs = {"joined_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
