"""C12 Shell 执行器（I3 设计文档 §7.2）：bash 执行脚本，stdout 逐行实时日志。"""

import os

from common.config import get_settings
from worker.executor import ExecResult, register
from worker.executors._proc import build_env, parse_kv_outputs, run_stream
from worker.state import FAILURE, KILL, SUCCESS


@register("shell")
def execute(ctx) -> ExecResult:
    """bash 运行 {tmp_dir}/{instance_id}/task_{task_id}.sh；exit 0 → success。"""
    param = ctx.param or {}
    script = str(param.get("script") or "")
    if not script.strip():
        return ExecResult(FAILURE, {}, ["[shell] 脚本内容为空"])

    run_dir = os.path.join(get_settings().tmp_dir, ctx.instance_id)
    os.makedirs(run_dir, exist_ok=True)
    script_path = os.path.join(run_dir, "task_%s.sh" % ctx.task_id)
    with open(script_path, "w", encoding="utf-8") as handle:
        handle.write(script)
    ctx.log("[shell] 运行目录: %s" % run_dir)

    code, stdout_text, killed = run_stream(
        ["bash", script_path], run_dir, build_env(param.get("env")), ctx.log, ctx.killed
    )
    if killed:
        ctx.log("[shell] 收到中断指令，子进程已终止")
        return ExecResult(KILL, {}, [])
    if code != 0:
        ctx.log("[shell] 退出码 %d → failure" % code)
        return ExecResult(FAILURE, parse_kv_outputs(stdout_text), [])
    ctx.log("[shell] 退出码 0 → success")
    return ExecResult(SUCCESS, parse_kv_outputs(stdout_text), [])
