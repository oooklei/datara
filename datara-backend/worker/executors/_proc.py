"""shell/python 共享：子进程流式执行 + KEY=VALUE 输出解析（I3 设计文档 §7.1/§7.2）。

- run_stream：Popen 流式执行，stdout/stderr 合并逐行回调 log；读线程解除 readline
  阻塞，主循环 1s 周期检查 kill 标记，命中即 terminate（§7.1 中断检查）
- parse_kv_outputs：stdout 中 KEY=VALUE 行 → outputs（对齐海豚 ShellTask 约定）
"""

import os
import re
import subprocess
import threading
from queue import Empty, Queue
from typing import Callable

KILL_POLL_SEC = 1.0  # kill 标记检查周期（§7.1）

# KEY=VALUE 行（key 为合法标识符；允许中间点以兼容 wf.period 类变量名回显）
_KV_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*)=(.*)$")


def parse_kv_outputs(stdout_text: str) -> dict:
    """stdout 中 KEY=VALUE 行 → outputs.params。"""
    outputs = {}
    for line in (stdout_text or "").splitlines():
        matched = _KV_RE.match(line.strip())
        if matched:
            outputs[matched.group(1)] = matched.group(2).strip()
    return outputs


def build_env(extra: dict) -> dict:
    """环境变量注入：os.environ 副本 + param.env 覆盖（§7.2）。"""
    env = os.environ.copy()
    for key, value in (extra or {}).items():
        env[str(key)] = str(value)
    return env


def _terminate(proc: subprocess.Popen) -> None:
    """先 terminate 后 kill（5s 宽限）。"""
    try:
        proc.terminate()
    except OSError:
        return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def run_stream(cmd: list, cwd: str, env: dict, log: Callable, killed: Callable) -> tuple:
    """流式执行子进程，返回 (exit_code, stdout_text, killed)。

    逐行回调 log 实时落盘；killed() 命中 → terminate 子进程并返回 killed=True。
    """
    proc = subprocess.Popen(  # noqa: S603 容器内受控脚本执行
        cmd, cwd=cwd, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    lines_q: Queue = Queue()

    def _pump() -> None:
        try:
            for line in proc.stdout:
                lines_q.put(line)
        finally:
            lines_q.put(None)

    threading.Thread(target=_pump, daemon=True).start()

    chunks = []
    killed_flag = False
    while True:
        try:
            line = lines_q.get(timeout=KILL_POLL_SEC)
        except Empty:
            if killed():
                killed_flag = True
                _terminate(proc)
                break
            continue
        if line is None:
            break
        chunks.append(line)
        log(line.rstrip("\n"))

    code = proc.wait()

    # 排空残留行（terminate 后读线程缓冲区可能仍有输出）
    while True:
        try:
            line = lines_q.get_nowait()
        except Empty:
            break
        if line is None:
            break
        chunks.append(line)
        log(line.rstrip("\n"))

    return code, "".join(chunks), killed_flag
