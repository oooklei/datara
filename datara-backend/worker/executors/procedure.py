"""C15 存储过程执行器（I4 设计文档 §6.1，对齐海豚 ProcedureTask）。

- params：datasource / db（库，缺省数据源库名）/ procedure（过程名）/ args=[{key, direction(IN|OUT), value}]
- IN 参数 %s 参数化传值；OUT 参数经 session 变量 @out_{key} 转接后 SELECT 回读
- OUT 值注册输出参数 out_{key}；影响行数入日志与 outputs.affected
"""

from common.db import new_session
from common.dsconn import open_connection
from common.models import DataSource
from worker.executor import ExecResult, register
from worker.state import FAILURE, SUCCESS


def _lookup_datasource(ref):
    """按名称查 t_data_source，纯数字兜底按 id（与 sql.py 同口径）。"""
    session = new_session()
    try:
        ds = session.query(DataSource).filter(DataSource.name == ref).first()
        if ds is None and str(ref).isdigit():
            ds = session.get(DataSource, int(ref))
        return ds
    finally:
        session.close()


@register("procedure")
def execute(ctx) -> ExecResult:
    """CALL 过程：IN 参数化、OUT 会话变量转接回读。"""
    param = ctx.param or {}
    ds_ref = param.get("datasource")
    if not ds_ref:
        ctx.log("[proc] 未指定数据源（datasource）")
        return ExecResult(FAILURE, {}, [])
    ds = _lookup_datasource(ds_ref)
    if ds is None:
        ctx.log("[proc] 数据源不存在: %s" % ds_ref)
        return ExecResult(FAILURE, {}, [])
    proc = str(param.get("procedure") or "").strip()
    if not proc:
        ctx.log("[proc] 未指定过程名（procedure）")
        return ExecResult(FAILURE, {}, [])
    db = str(param.get("db") or "").strip() or ds.db_name

    placeholders, values, out_keys = [], [], []
    for arg in param.get("args") or []:
        if not isinstance(arg, dict) or not str(arg.get("key") or "").strip():
            continue
        key = str(arg["key"]).strip()
        if str(arg.get("direction") or "IN").upper() == "OUT":
            placeholders.append("@out_%s" % key)
            out_keys.append(key)
        else:
            placeholders.append("%s")
            values.append(arg.get("value"))

    call = "CALL %s(%s)" % (proc, ", ".join(placeholders))
    ctx.log("[proc] 数据源: %s db=%s 语句: %s IN 值=%s" % (ds.name, db, call, values))
    conn = open_connection(ds, db=db, read_timeout=None)  # 过程耗时不受 60s 限制
    outputs = {}
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(call, values or None)
                affected = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                conn.commit()
                ctx.log("[proc] 执行完成，影响行数 %d" % affected)
            except Exception as exc:  # noqa: BLE001 CALL 失败 → failure
                ctx.log("[proc] 执行失败: %r" % exc)
                return ExecResult(FAILURE, {}, [])
            outputs["affected"] = affected
            if out_keys:
                cur.execute("SELECT %s" % ", ".join("@out_%s" % k for k in out_keys))
                row = cur.fetchone()
                for key, value in zip(out_keys, row or []):
                    outputs["out_%s" % key] = value if value is None else str(value)
                    ctx.log("[proc] OUT %s = %r" % (key, value))
    finally:
        conn.close()
    return ExecResult(SUCCESS, outputs, [])
