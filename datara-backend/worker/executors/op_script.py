"""op_script 执行器：脚本引用（ETL/Stream 共享）。

- 脚本 ID：param.scriptId
- 脚本内容：param.code
- 语言：param.lang（SQL/Python/Shell）
- 输出：processed_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("op_script")
def execute(ctx) -> ExecResult:
    """执行脚本引用，返回处理行数。"""
    param = ctx.param or {}
    script_id = param.get("scriptId")
    code = param.get("code")
    lang = param.get("lang", "SQL")

    if not script_id and not code:
        return ExecResult(FAILURE, {}, ["[op_script] 未指定脚本（scriptId 或 code）"])

    ctx.log("[op_script] 脚本 ID: %s" % script_id)
    ctx.log("[op_script] 语言: %s" % lang)

    # TODO: 实现脚本引用
    outputs = {"processed_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
