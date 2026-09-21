"""smoke 执行器：echo hello + 分片 sleep（冒烟链路第③步；I3 接入 ctx 契约）。"""

import socket
import time

from worker.executor import ExecResult, register
from worker.state import KILL, SUCCESS


@register("smoke")
def execute(ctx) -> ExecResult:
    """sleep(delaySec，默认 1，分片 1s 支持中断) → 成功并输出回显参数。"""
    param = ctx.param or {}
    name = param.get("name") or ctx.name or "smoke"
    try:
        delay = int(param.get("delaySec") or 1)
    except (TypeError, ValueError):
        delay = 1
    delay = max(delay, 0)

    ctx.log("[smoke] 任务: %s" % name)
    ctx.log("[smoke] echo hello")
    ctx.log("[smoke] sleep %ss ..." % delay)
    for _ in range(delay):
        if ctx.killed():
            ctx.log("[smoke] 收到中断指令")
            return ExecResult(KILL, {}, [])
        time.sleep(1)
    ctx.log("[smoke] 完成（worker=%s）" % socket.gethostname())

    outputs = {"echo": "hello", "delaySec": delay, "workerHost": socket.gethostname()}
    return ExecResult(SUCCESS, outputs, [])
