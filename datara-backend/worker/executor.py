"""执行器注册表与任务消费循环（I3 设计文档 §7.1，对齐海豚 TaskProcessor）。

- EXECUTORS: dict[node_type] → 执行函数（smoke + sql/shell/python/ssh/file/procedure/http 八类）
- 消费循环：XREADGROUP 任务流（high→normal→low）→ 幂等校验 → 置 running → 执行
  → 终态 + outputs → XADD 状态流（含 attempt）→ XACK
- 实时日志（F47）：置 running 先建日志文件（变量快照头 §10.3）+ t_task_log 索引，
  执行器经 LiveLog 增量 append（前端 2s 轮询读文件可见）
- 幂等（§3.2 at-least-once）：消息 attempt 与 DB 不符（陈旧投递）或 DB 已终态
  （重复投递）→ 直接丢弃
- 中断（§7.1）：执行器经 ctx.killed() 周期查 datara:kill:{taskId}，命中即中断
- 自愈（§3.4/§14 项10）：启动+周期 XAUTOCLAIM 认领 idle>60s 的 pending 消息（worker 失联遗留）；
  认领时 DB RUNNING → fault_tolerance 过渡（5s 可观察窗口）→ 按原 attempt 重跑（日志续写）
"""

import os
import socket
import threading
import time
from typing import Callable, NamedTuple, Optional

from common import queue
from common.config import get_settings
from common.db import new_session
from common.log import get_logger, set_instance_id
from common.models import TaskInstance, TaskLog, now
from worker.state import FAILURE, FAULT_TOLERANCE, KILL, RUNNING, TERMINAL_STATES

logger = get_logger("worker.executor")


class ExecResult(NamedTuple):
    """执行器统一返回：终态 + 输出参数 + 收尾日志行（过程日志经 ctx.log 实时写）。"""

    state: str
    outputs: dict
    logs: list


class TaskContext:
    """执行器上下文（§7.1 统一契约）。

    - param: 优先取 param_resolved（master 已完成变量替换，worker 零解析）
    - log(line): 实时日志增量回调（append 落盘，前端轮询可见）
    - killed(): kill 中断检查回调（执行器等待/循环内 1s 周期调用）
    """

    __slots__ = ("task_id", "instance_id", "node_type", "name", "attempt",
                 "param", "constraints", "log", "killed")

    def __init__(self, task_id, instance_id, node_type, name, attempt,
                 param, constraints, log, killed):
        self.task_id = task_id
        self.instance_id = instance_id
        self.node_type = node_type
        self.name = name
        self.attempt = attempt
        self.param = param
        self.constraints = constraints
        self.log = log
        self.killed = killed


# 执行器注册表（模块导入时由 @register 填充）
EXECUTORS: dict = {}


def register(node_type: str) -> Callable:
    """执行器注册装饰器：EXECUTORS[node_type] = func。"""

    def decorator(func: Callable) -> Callable:
        EXECUTORS[node_type] = func
        return func

    return decorator


def get_executor(node_type: str) -> Optional[Callable]:
    return EXECUTORS.get(node_type)


class LiveLog:
    """实时日志写入器：逐行 append + flush（F47）。

    append 模式保留重试/重新认领历史；线程安全（子进程读线程回调场景）。
    """

    def __init__(self, path: str):
        self._fh = open(path, "a", encoding="utf-8")
        self._lock = threading.Lock()

    def write(self, line) -> None:
        with self._lock:
            self._fh.write(str(line).rstrip("\n") + "\n")
            self._fh.flush()

    def close(self) -> None:
        with self._lock:
            try:
                self._fh.close()
            except Exception:  # noqa: BLE001 关闭失败不影响主流程
                pass


def _snapshot_lines(snapshot: dict, instance_id: str, node_name: str) -> list:
    """变量快照日志头（§10.3，明文不脱敏；与 master.engine._snapshot_lines 同格式）。"""
    lines = ["===== 变量快照 instance_id=%s node=%s =====" % (instance_id, node_name)]
    for name, item in (snapshot or {}).items():
        if isinstance(item, dict):
            lines.append("%s=%s  (%s)" % (name, item.get("value"), item.get("source")))
        else:
            lines.append("%s=%s" % (name, item))
    lines.append("=" * 44)
    return lines


def _open_live_log(instance_id: str, task_id: int, snapshot: dict, node_name: str) -> tuple:
    """建日志文件（append）并写入变量快照头。返回 (LiveLog, path)。"""
    log_dir = os.path.join(get_settings().log_dir, instance_id)
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, "%s.log" % task_id)
    live = LiveLog(path)
    for line in _snapshot_lines(snapshot, instance_id, node_name):
        live.write(line)
    return live, path


def _ensure_log_index(session, instance_id: str, task_id: int, path: str, host: str) -> None:
    """t_task_log 索引补齐（先查后插，重复投递/重新认领不重复插行）。"""
    exists = session.query(TaskLog).filter(TaskLog.task_instance_id == task_id).first()
    if exists is None:
        session.add(TaskLog(instance_id=instance_id, task_instance_id=task_id,
                            log_path=path, host=host))
        session.commit()


def handle_task(msg: dict, claimed: bool = False) -> None:
    """处理单条任务消息：幂等校验 → 容错过渡（认领）→ running → 执行 → 终态回写 + 上报。

    claimed=True 表示消息经 XAUTOCLAIM 认领（原执行 worker 失联）：RUNNING 先置
    fault_tolerance 过渡 2s 再重跑（§14 项10 状态轨迹；attempt 保留）。
    """
    task_id = msg.get("taskId")
    instance_id = msg.get("instanceId") or "-"
    node_type = msg.get("nodeType") or msg.get("type") or "smoke"
    name = str(msg.get("name") or "")
    attempt = int(msg.get("attempt") or 1)
    host = socket.gethostname()

    session = new_session()
    live = None
    try:
        task = session.get(TaskInstance, task_id)
        if task is None:
            logger.error("任务实例不存在，丢弃消息: %s", msg)
            return
        # 幂等校验：陈旧投递（attempt 不符）/ 重复投递（DB 已终态）→ 丢弃
        if int(task.attempt or 1) != attempt:
            logger.warning("陈旧投递丢弃（DB attempt=%s 消息 attempt=%s）: taskId=%s",
                           task.attempt, attempt, task_id)
            return
        if task.state in TERMINAL_STATES:
            logger.warning("任务已终态（%s），丢弃重复投递: taskId=%s", task.state, task_id)
            return
        set_instance_id(instance_id)

        # 容错认领过渡（§3.4/§14 项10）：前次执行节点失联，置 fault_tolerance 供前端/驱动
        # 观察到转派轨迹；attempt 保留，5s 过渡窗口后按原 attempt 重跑
        fault_claimed = False
        if claimed and task.state == RUNNING:
            fault_claimed = True
            task.state = FAULT_TOLERANCE
            session.commit()
            logger.warning("容错认领: taskId=%s 原 host=%s → fault_tolerance，5s 后重跑",
                           task_id, task.host)
            time.sleep(5)

        # 置 running
        task.state = RUNNING
        task.start_time = now()
        task.host = host
        session.commit()

        # 日志文件先建 + 变量快照头 + 索引（§7.1）
        live, log_path = _open_live_log(instance_id, task_id, msg.get("var_snapshot") or {}, name)
        if fault_claimed:
            live.write("[worker] 容错认领：前次执行节点失联（原 host=%s），按原 attempt=%s 重跑"
                       % (task.host or "-", attempt))
        _ensure_log_index(session, instance_id, task_id, log_path, host)

        # 执行（未注册类型 / 执行异常均按 failure 处理，日志留痕）
        executor = get_executor(node_type)
        if executor is None:
            live.write("[worker] 未注册的执行器类型: %s" % node_type)
            result = ExecResult(FAILURE, {}, [])
        else:
            ctx = TaskContext(
                task_id=task_id, instance_id=instance_id, node_type=node_type,
                name=name, attempt=attempt,
                param=msg.get("param_resolved") or msg.get("param") or {},
                constraints=msg.get("constraints") or {},
                log=live.write,
                killed=lambda: queue.check_kill(task_id),
            )
            try:
                result = executor(ctx)
            except Exception as exc:  # noqa: BLE001 执行异常转 failure
                logger.error("任务执行异常: taskId=%s %r", task_id, exc)
                live.write("[worker] 执行异常: %r" % exc)
                result = ExecResult(FAILURE, {}, [])

        # 超时中断（引擎 kill 标记 reason=timeout）→ 按 failure 收口（§14 项7：超时处 failure；
        # 用户停止 reason=stop 仍报 KILL → 实例 kill）
        if result.state == KILL and queue.check_kill(task_id) == "timeout":
            live.write("[worker] 任务超时（引擎中断），按 failure 收口")
            result = ExecResult(FAILURE, result.outputs, result.logs)

        # 收尾日志 + 关闭句柄
        for line in result.logs:
            live.write(line)
        live.write("[worker] 终态: %s" % result.state)
        live.close()
        live = None

        # 终态回写
        task.state = result.state
        task.end_time = now()
        task.outputs = result.outputs
        task.log_path = log_path
        session.commit()

        # 状态上报（含 attempt，master 比对防陈旧上报）+ 清理 kill 标记
        queue.add_state(
            {
                "taskId": task_id,
                "instanceId": instance_id,
                "attempt": attempt,
                "state": result.state,
                "outputs": result.outputs,
                "logPath": log_path,
                "host": host,
            }
        )
        queue.clear_kill(task_id)
        logger.info("任务完成: taskId=%s attempt=%s → %s", task_id, attempt, result.state)
    except Exception:
        session.rollback()
        raise
    finally:
        if live is not None:
            live.close()
        session.close()
        set_instance_id(None)


def run_loop(stop) -> None:
    """worker 主循环：XREADGROUP 消费任务流；异常只记日志不崩进程。"""
    logger.info("worker 消费循环启动（XREADGROUP datara:stream:tasks:*）")
    queue.ensure_all_groups()
    consumer = queue.worker_consumer()
    last_claim = 0.0
    while not stop.is_set():
        # 启动即认领一次 + 每 30s 周期认领（容错自愈）：接管失联 worker 的 pending 消息
        if time.time() - last_claim >= 30:
            last_claim = time.time()
            for stream, msg_id, msg in queue.claim_stale_tasks(consumer):
                try:
                    handle_task(msg, claimed=True)
                    queue.ack_task(stream, msg_id)
                except Exception as exc:  # noqa: BLE001 单任务异常不阻断循环
                    logger.error("认领任务处理异常: %s %r", msg, exc)
        try:
            msgs = queue.read_tasks(consumer=consumer, block_ms=1000)
        except Exception as exc:  # noqa: BLE001 redis 抖动重试
            logger.warning("取任务失败（2s 后重试）: %s", exc)
            stop.wait(2)
            continue
        for stream, msg_id, msg in msgs:
            try:
                handle_task(msg)
                queue.ack_task(stream, msg_id)
            except Exception as exc:  # noqa: BLE001 单任务异常不阻断循环
                logger.error("任务处理异常: %s %r", msg, exc)
    logger.info("worker 消费循环退出")


# 导入执行器实现，触发 @register 注册
from worker.executors import (  # noqa: E402,F401  注册副作用
    file,
    http,
    procedure,
    python,
    shell,
    smoke,
    sql,
    ssh,
    sync,
)
