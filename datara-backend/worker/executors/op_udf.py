"""op_udf 执行器：UDF 调用（ETL 转换算子）。

- UDF 名称：param.udfName
- 输入参数：param.inputParams
- 输出：processed_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("op_udf")
def execute(ctx) -> ExecResult:
    """执行 UDF 调用，返回处理行数。"""
    param = ctx.param or {}
    udf_name = param.get("udfName")
    input_params = param.get("inputParams", [])

    if not udf_name:
        return ExecResult(FAILURE, {}, ["[op_udf] 未指定 UDF 名称（udfName）"])

    ctx.log("[op_udf] UDF 名称: %s" % udf_name)
    ctx.log("[op_udf] 输入参数: %s" % input_params)

    # TODO: 实现 UDF 调用
    outputs = {"processed_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
