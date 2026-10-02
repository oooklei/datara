"""op_dedup 执行器：去重（ETL 转换算子）。

- 去重键：param.keyColumns
- 输出：deduped_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("op_dedup")
def execute(ctx) -> ExecResult:
    """执行去重操作，返回去重后行数。"""
    param = ctx.param or {}
    key_columns = param.get("keyColumns", [])

    if not key_columns:
        return ExecResult(FAILURE, {}, ["[op_dedup] 未指定去重键（keyColumns）"])

    ctx.log("[op_dedup] 去重键: %s" % key_columns)

    # TODO: 实现去重操作
    outputs = {"deduped_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
