"""out_db 执行器：JDBC 数据库写入（ETL 输出目标）。

- 数据源解析：param.datasource → t_data_source
- 写入模式：param.writeMode（append/replace）
- 输出：affected_rows
"""

from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


@register("out_db")
def execute(ctx) -> ExecResult:
    """执行数据库写入，返回影响行数。"""
    param = ctx.param or {}
    ds_ref = param.get("datasource") or param.get("datasource_id")

    if not ds_ref:
        return ExecResult(FAILURE, {}, ["[out_db] 未指定数据源（datasource）"])

    ctx.log("[out_db] 数据源: %s" % ds_ref)
    ctx.log("[out_db] 写入模式: %s" % (param.get("writeMode") or "append"))

    # TODO: 实现 JDBC 写入
    outputs = {"affected_rows": 0}
    return ExecResult(SUCCESS, outputs, [])
