"""op_join 执行器：Join 操作（ETL 转换算子）。

- Join 类型：param.joinType（inner/left/right/full）
- 左表键：param.leftKey
- 右表键：param.rightKey
- 输出：joined_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("op_join")
def execute(ctx) -> ExecResult:
    """执行 Join 操作，返回连接后行数。"""
    param = ctx.param or {}
    join_type = param.get("joinType", "inner")
    left_key = param.get("leftKey")
    right_key = param.get("rightKey")

    if not left_key or not right_key:
        return ExecResult(FAILURE, {}, ["[op_join] 未指定连接键（leftKey/rightKey）"])

    ctx.log("[op_join] 类型: %s" % join_type)
    ctx.log("[op_join] 左表键: %s" % left_key)
    ctx.log("[op_join] 右表键: %s" % right_key)

    # TODO: 实现 Join 操作
    outputs = {"joined_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
