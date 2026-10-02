"""op_split 执行器：拆分（ETL 转换算子）。

- 拆分字段：param.splitColumn
- 分隔符：param.delimiter
- 输出：split_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("op_split")
def execute(ctx) -> ExecResult:
    """执行拆分操作，返回拆分后行数。"""
    param = ctx.param or {}
    split_column = param.get("splitColumn")
    delimiter = param.get("delimiter", ",")

    if not split_column:
        return ExecResult(FAILURE, {}, ["[op_split] 未指定拆分字段（splitColumn）"])

    ctx.log("[op_split] 拆分字段: %s" % split_column)
    ctx.log("[op_split] 分隔符: %s" % delimiter)

    # TODO: 实现拆分操作
    outputs = {"split_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
