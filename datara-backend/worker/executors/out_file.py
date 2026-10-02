"""out_file 执行器：文件写入（CSV/Excel/JSON）。

- 文件路径：param.filePath
- 格式：param.format（CSV/Excel/JSON）
- 输出：written_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("out_file")
def execute(ctx) -> ExecResult:
    """执行文件写入，返回写入行数。"""
    param = ctx.param or {}
    file_path = param.get("filePath")
    file_format = param.get("format", "CSV")

    if not file_path:
        return ExecResult(FAILURE, {}, ["[out_file] 未指定文件路径（filePath）"])

    ctx.log("[out_file] 文件: %s" % file_path)
    ctx.log("[out_file] 格式: %s" % file_format)

    # TODO: 实现文件写入
    outputs = {"written_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
