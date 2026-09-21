"""C13 Python 执行器（I3 设计文档 §7.2）：subprocess python 运行脚本。

requirements 字段本期仅校验格式并打印日志提示，不做运行时安装
（依赖预装归镜像层——运行时装依赖慢且不幂等，设计 §7.2）。
"""

import os
import re
import sys
from typing import Callable

from common.config import get_settings
from worker.executor import ExecResult, register
from worker.executors._proc import build_env, parse_kv_outputs, run_stream
from worker.state import FAILURE, KILL, SUCCESS

# 依赖行：包名[extras] 比较器版本（宽松校验，仅提示用）
_REQ_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[A-Za-z0-9.,_-]+\])?"
    r"(\s*(==|!=|<=|>=|~=|<|>|===)\s*[A-Za-z0-9.!*+_-]+)?(\s*;.*)?$"
)


def _check_requirements(text: str, log: Callable) -> None:
    """依赖清单逐行格式校验 + 提示（不安装）。"""
    lines = [ln.strip() for ln in (text or "").splitlines()]
    pkgs = [ln for ln in lines if ln and not ln.startswith("#")]
    if not pkgs:
        return
    log("[python] 依赖清单 %d 项：本期不做运行时安装，依赖需预装镜像层" % len(pkgs))
    for line in pkgs:
        if not _REQ_RE.match(line):
            log("[python] 依赖行格式可疑（已忽略）: %r" % line)


@register("python")
def execute(ctx) -> ExecResult:
    """python 运行 {tmp_dir}/{instance_id}/task_{task_id}.py；exit 0 → success。"""
    param = ctx.param or {}
    script = str(param.get("script") or "")
    if not script.strip():
        return ExecResult(FAILURE, {}, ["[python] 脚本内容为空"])

    _check_requirements(str(param.get("requirements") or ""), ctx.log)

    run_dir = os.path.join(get_settings().tmp_dir, ctx.instance_id)
    os.makedirs(run_dir, exist_ok=True)
    script_path = os.path.join(run_dir, "task_%s.py" % ctx.task_id)
    with open(script_path, "w", encoding="utf-8") as handle:
        handle.write(script)
    ctx.log("[python] 运行目录: %s（解释器 %s）" % (run_dir, sys.version.split()[0]))

    code, stdout_text, killed = run_stream(
        [sys.executable, script_path], run_dir,
        build_env({"PYTHONUNBUFFERED": "1", **(param.get("env") or {})}),
        ctx.log, ctx.killed,
    )
    if killed:
        ctx.log("[python] 收到中断指令，子进程已终止")
        return ExecResult(KILL, {}, [])
    if code != 0:
        ctx.log("[python] 退出码 %d → failure" % code)
        return ExecResult(FAILURE, parse_kv_outputs(stdout_text), [])
    ctx.log("[python] 退出码 0 → success")
    return ExecResult(SUCCESS, parse_kv_outputs(stdout_text), [])
