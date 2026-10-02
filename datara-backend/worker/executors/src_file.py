"""src_file 执行器：文件读取（CSV/Excel/JSON）。

- 文件路径：param.filePath
- 格式：param.format（CSV/Excel/JSON）
- 输出：row_count + result_preview
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("src_file")
def execute(ctx) -> ExecResult:
    """执行文件读取，返回行数和预览数据。"""
    param = ctx.param or {}
    file_path = param.get("filePath")
    file_format = param.get("format", "CSV")

    if not file_path:
        return ExecResult(FAILURE, {}, ["[src_file] 未指定文件路径（filePath）"])

    ctx.log("[src_file] 文件: %s" % file_path)
    ctx.log("[src_file] 格式: %s" % file_format)

    # TODO: 实现文件读取
    outputs = {
        "row_count": 0,
        "result_preview": {"columns": [], "rows": []},
    }
    return ExecResult(SUCCESS, outputs, [])
