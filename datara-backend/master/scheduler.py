"""核心调度循环（I3，设计文档 §3.1）：

① 命令消费线程（2s）：t_command(wait) 按类型展开
   START_PROCESS → 建实例+任务行 → Runnable；COMPLEMENT_DATA → 按日期展开 N 条 START_PROCESS
   REPEAT_RUNNING → 新实例复用变量快照；START_FAILURE_TASKS → 失败链路重置续跑；STOP → kill
② 状态消费线程：XREADGROUP task_state → 路由 Runnable 事件队列（无 Runnable 走 DB 直收兜底）
③ 定时调度线程（schedule.py）④ 超时扫描线程 ⑤ 容错恢复（failover.py，LeaderGate 首次过闸执行一次）

LeaderGate：仅 leader 执行 ①~④；首次成为 leader 时同步跑一次容错恢复（幂等单次）。
"""

import json
import socket
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional

from common import queue
from common.db import new_session
from common.log import get_logger, set_instance_id
from common.models import Command, TaskInstance, WorkflowInstance, now
from master import state
from master.dag import loop_bodies, parse_graph
from master.engine import WorkflowExecuteRunnable, all_runnables, get_runnable, register_runnable, remove_runnable
from master.failover import recover_running_instances

logger = get_logger("master.scheduler")

# I12-D1 补齐对齐 engine.py 全集（当前模块内未直接引用，保留导出以防外部引用旧全集）；I12 +file_sync/notify C24/C26
WORKER_TYPES = ("sql", "shell", "python", "ssh", "smoke", "procedure", "http", "file", "sync", "file_sync", "notify")


def generate_instance_id(wf_code: int) -> str:
    """运行实例编号：{yyyyMMddHHmmss}-{wf_code}-{4位随机}。"""
    timestamp = time.strftime("%Y%m%d%H%M%S")
    return "%s-%s-%s" % (timestamp, wf_code, uuid.uuid4().hex[:4])


# ---------------- LeaderGate ----------------

class LeaderGate:
    """选主联动闸门：仅 leader 放行；首次放行时执行一次容错恢复（线程安全单次）。"""

    def __init__(self, heartbeat):
        self.heartbeat = heartbeat
        self._lock = threading.Lock()
        self._recovered = False

    def check(self) -> bool:
        if not getattr(self.heartbeat, "is_master", False):
            return False
        if not self._recovered:
            with self._lock:
                if not self._recovered:
                    self._recovered = True
                    try:
                        recover_running_instances()
                    except Exception as exc:  # noqa: BLE001 恢复失败不阻塞引擎（下轮重启可再试）
                        logger.error("容错恢复执行异常: %s", exc)
        return True


# ---------------- 命令消费 ----------------

def consume_commands() -> int:
    """消费一批 wait 命令（优先级降序）；补数串行组阻塞的命令跳过留待下轮。返回处理条数。"""
    session = new_session()
    handled = 0
    try:
        commands = (
            session.query(Command)
            .filter(Command.state == "wait")
            .order_by(Command.priority.desc(), Command.id.asc())
            .limit(20)
            .all()
        )
        session.close()
        for command in commands:
            param = command.command_param if isinstance(command.command_param, dict) else {}
            if _complement_group_blocked(param):
                continue
            _handle_command(command, param)
            handled += 1
        return handled
    finally:
        session.close()


def _complement_group_blocked(param: dict) -> bool:
    """串行补数控制：同 complement_group 存在未终态实例 → 本轮跳过该命令。"""
    group = param.get("complementGroup")
    if not group:
        return False
    session = new_session()
    try:
        instances = (
            session.query(WorkflowInstance)
            .filter(WorkflowInstance.state.in_(state.INSTANCE_RUNNING_STATES))
            .all()
        )
        for inst in instances:
            variables = inst.variables if isinstance(inst.variables, dict) else {}
            if variables.get("complementGroup") == group:
                return True
        return False
    finally:
        session.close()


def _handle_command(command: Command, param: dict) -> None:
    """单命令处理：置 execute → 按类型展开 → done/fail（失败原因写命令参数）。"""
    session = new_session()
    try:
        command.state = "execute"
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    try:
        handler = {
            "START_PROCESS": _cmd_start,
            "START_PROCESS_SMOKE": _cmd_smoke,
            "COMPLEMENT_DATA": _cmd_complement,
            "REPEAT_RUNNING": _cmd_repeat_running,
            "START_FAILURE_TASKS": _cmd_failure_tasks,
            "STOP": _cmd_stop,
        }.get(command.command_type, _cmd_unknown)
        handler(command, param)
        _finish_command(command.id, "done", None)
    except Exception as exc:  # noqa: BLE001 单命令失败不影响其他命令
        logger.exception("命令处理失败: commandId=%s %s %r", command.id, command.command_type, exc)
        _finish_command(command.id, "fail", str(exc))


def _finish_command(command_id: int, result: str, error: Optional[str]) -> None:
    session = new_session()
    try:
        command = session.get(Command, command_id)
        if command is None:
            return
        command.state = result
        if error:
            param = command.command_param if isinstance(command.command_param, dict) else {}
            param["error"] = error
            command.command_param = param
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _cmd_unknown(command: Command, param: dict) -> None:
    raise ValueError("未知命令类型: %s" % command.command_type)


def _parse_schedule_time(param: dict) -> Optional[datetime]:
    raw = param.get("scheduleTime")
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(raw), fmt)
        except ValueError:
            continue
    return None


def _load_graph(session, wf_code: int):
    """定义 → Graph（无定义/解析失败抛 ValueError，命令置 fail）。"""
    from common.models import WfDefinition

    definition = session.query(WfDefinition).filter(WfDefinition.code == wf_code).first()
    if definition is None or not definition.graph_json:
        raise ValueError("工作流定义不存在或画布为空: wfCode=%s" % wf_code)
    graph = parse_graph(json.loads(definition.graph_json))
    return definition, graph


def _create_instance(session, command: Command, param: dict, wf_code: int, wf_version: int,
                     graph) -> WorkflowInstance:
    """建实例（submitted）+ 逐节点预建任务行（loop_iter=0, attempt=1）。"""
    instance_id = generate_instance_id(wf_code)
    schedule_time = _parse_schedule_time(param)
    variables = dict(param)
    if schedule_time is not None:
        variables["scheduleTime"] = schedule_time.strftime("%Y-%m-%d %H:%M:%S")
    instance = WorkflowInstance(
        instance_id=instance_id,
        wf_code=wf_code,
        wf_version=wf_version,
        state=state.SUBMITTED,
        host=socket.gethostname(),
        variables=variables,
        command_type=command.command_type,
        run_mode=str(param.get("runMode") or "manual"),
        schedule_time=schedule_time,
    )
    session.add(instance)
    session.flush()
    if graph is not None:
        # 循环体节点不预建 iter0 行（每迭代由引擎按 loop_iter=k 建行，§6.8）
        body_nodes: set = set()
        for members in loop_bodies(graph).values():
            body_nodes |= members
        for node_id, node in graph.nodes.items():
            if node_id in body_nodes:
                continue
            session.add(TaskInstance(
                instance_id=instance_id,
                node_id=node_id,
                node_type=node["type"],
                name=str(node["data"].get("name") or node_id),
                state=state.SUBMITTED,
                attempt=1,
                loop_iter=0,
            ))
        session.flush()
    return instance


def _spawn_runnable(instance_id: str, graph) -> None:
    runnable = WorkflowExecuteRunnable(instance_id, graph, resume=False)
    register_runnable(runnable)
    runnable.start()


def _cmd_start(command: Command, param: dict) -> None:
    wf_code = int(param.get("wfCode") or 0)
    session = new_session()
    try:
        definition, graph = _load_graph(session, wf_code)
        instance = _create_instance(
            session, command, param, wf_code,
            int(param.get("wfVersion") or definition.version or 0), graph,
        )
        session.commit()
        instance_id = instance.instance_id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    _spawn_runnable(instance_id, graph)
    logger.info("实例已启动: %s（wf=%s runMode=%s）", instance_id, wf_code, param.get("runMode") or "manual")


def _cmd_smoke(command: Command, param: dict) -> None:
    """I1 冒烟链路兼容：单 smoke 任务、无图。"""
    session = new_session()
    try:
        instance = _create_instance(session, command, param, 0, 0, None)
        task = TaskInstance(
            instance_id=instance.instance_id, node_type="smoke",
            name=param.get("name") or "smoke", state=state.SUBMITTED, attempt=1,
        )
        session.add(task)
        session.commit()
        task_id = task.id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    queue.add_task(
        {"taskId": task_id, "instanceId": instance.instance_id, "type": "smoke",
         "name": param.get("name") or "smoke", "attempt": 1,
         "param": param, "param_resolved": param, "var_snapshot": {}, "constraints": {}},
        priority=int(param.get("priority") or 3),
    )
    logger.info("冒烟实例已启动: %s（task %s）", instance.instance_id, task_id)


def _cmd_complement(command: Command, param: dict) -> None:
    """补数展开（§9.2）：按日期范围写 N 条 START_PROCESS（串行组由消费侧控制）。"""
    date_from = str(param.get("dateFrom") or "")
    date_to = str(param.get("dateTo") or "")
    start = datetime.strptime(date_from, "%Y-%m-%d")
    end = datetime.strptime(date_to, "%Y-%m-%d")
    if end < start:
        raise ValueError("补数日期范围非法: %s ~ %s" % (date_from, date_to))
    parallel = bool(param.get("parallel"))
    group = param.get("complementGroup") or generate_instance_id(int(param.get("wfCode") or 0))
    wf_code = int(param.get("wfCode") or 0)
    session = new_session()
    try:
        definition, _graph = _load_graph(session, wf_code)
        current = start
        count = 0
        while current <= end:
            session.add(Command(
                command_type="START_PROCESS",
                command_param={
                    "wfCode": wf_code,
                    "wfVersion": int(param.get("wfVersion") or definition.version or 0),
                    "runMode": "complement",
                    "scheduleTime": current.strftime("%Y-%m-%d %H:%M:%S"),
                    "envGroupId": param.get("envGroupId"),
                    "complementGroup": None if parallel else group,
                    "complementDate": current.strftime("%Y-%m-%d"),
                },
                priority=int(param.get("priority") or 3),
            ))
            current = current + timedelta(days=1)
            count += 1
        session.commit()
        logger.info("补数展开: wf=%s %s ~ %s 共 %d 实例（%s）",
                    wf_code, date_from, date_to, count, "并行" if parallel else "串行组 " + group)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _cmd_repeat_running(command: Command, param: dict) -> None:
    """整实例重跑（§9.3）：新 instance_id、任务行全量新建、复用原实例变量快照。"""
    origin_id = str(param.get("instanceId") or "")
    session = new_session()
    graph = None
    try:
        origin = (
            session.query(WorkflowInstance)
            .filter(WorkflowInstance.instance_id == origin_id)
            .first()
        )
        if origin is None:
            raise ValueError("原实例不存在: %s" % origin_id)
        variables = origin.variables if isinstance(origin.variables, dict) else {}
        instance_id = generate_instance_id(origin.wf_code)
        new_instance = WorkflowInstance(
            instance_id=instance_id,
            wf_code=origin.wf_code,
            wf_version=origin.wf_version,
            state=state.SUBMITTED,
            host=socket.gethostname(),
            variables=dict(variables),
            command_type=command.command_type,
            run_mode=origin.run_mode or "manual",
            schedule_time=origin.schedule_time,
        )
        session.add(new_instance)
        session.flush()
        if origin.wf_code:
            _definition, graph = _load_graph(session, origin.wf_code)
            body_nodes: set = set()
            for members in loop_bodies(graph).values():
                body_nodes |= members
            for node_id, node in graph.nodes.items():
                if node_id in body_nodes:
                    continue  # 循环体节点每迭代建行（不预建 iter0）
                session.add(TaskInstance(
                    instance_id=instance_id, node_id=node_id, node_type=node["type"],
                    name=str(node["data"].get("name") or node_id),
                    state=state.SUBMITTED, attempt=1, loop_iter=0,
                ))
            session.flush()
        elif not variables:
            raise ValueError("原实例无定义且无参数，无法重跑: %s" % origin_id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    if graph is not None:
        _spawn_runnable(instance_id, graph)
        logger.info("整实例重跑: %s → %s", origin_id, instance_id)
    else:
        _cmd_smoke(command, {**(variables or {}), "instanceId": instance_id})
        logger.info("整实例重跑（smoke 兜底）: %s", origin_id)


def _cmd_failure_tasks(command: Command, param: dict) -> None:
    """失败节点重跑（§9.3）：failure 任务及其下游（非 success）重置，同实例续跑。"""
    instance_id = str(param.get("instanceId") or "")
    session = new_session()
    try:
        instance = (
            session.query(WorkflowInstance)
            .filter(WorkflowInstance.instance_id == instance_id)
            .first()
        )
        if instance is None:
            raise ValueError("实例不存在: %s" % instance_id)
        _definition, graph = _load_graph(session, instance.wf_code)
        tasks = (
            session.query(TaskInstance)
            .filter(TaskInstance.instance_id == instance_id)
            .all()
        )
        failed_ids = {t.node_id for t in tasks if t.state == state.FAILURE and t.node_id}
        if not failed_ids:
            raise ValueError("实例无失败任务: %s" % instance_id)
        # 失败节点 + 后代闭包（沿非回环出边）
        reset_ids = set(failed_ids)
        frontier = list(failed_ids)
        while frontier:
            nid = frontier.pop()
            for edge in graph.succs.get(nid, []):
                if edge["target"] not in reset_ids:
                    reset_ids.add(edge["target"])
                    frontier.append(edge["target"])
        for task in tasks:
            if task.node_id in reset_ids and task.state != state.SUCCESS:
                task.state = state.SUBMITTED
                task.attempt = 1
                task.end_time = None
                task.delay_until = None
                task.outputs = None
        # 实例回 running（Runnable resume 重驱失败链路）
        if instance.state not in state.INSTANCE_RUNNING_STATES:
            instance.state = state.RUNNING
            instance.end_time = None
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    old = get_runnable(instance_id)
    if old is not None:
        old.stop_flag = True
        remove_runnable(instance_id)
    _spawn_runnable(instance_id, graph)
    logger.info("失败节点重跑: %s（重置 %s 个节点链路）", instance_id, len(reset_ids))


def _cmd_stop(command: Command, param: dict) -> None:
    """停止实例（§8）：实例 kill + 未终态任务 kill + kill 标记；逻辑节点由 Runnable 自查中断。"""
    instance_id = str(param.get("instanceId") or "")
    session = new_session()
    try:
        instance = (
            session.query(WorkflowInstance)
            .filter(WorkflowInstance.instance_id == instance_id)
            .first()
        )
        if instance is None:
            raise ValueError("实例不存在: %s" % instance_id)
        instance.state = state.KILL
        tasks = (
            session.query(TaskInstance)
            .filter(TaskInstance.instance_id == instance_id)
            .all()
        )
        for task in tasks:
            if task.state not in state.TERMINAL_STATES:
                task.state = state.KILL
                task.end_time = now()
                queue.set_kill(task.id)
        session.commit()
        logger.info("实例停止: %s", instance_id)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    runnable = get_runnable(instance_id)
    if runnable is not None:
        runnable.notify_kill()


# ---------------- 状态消费 ----------------

def consume_state_reports() -> bool:
    """消费一批任务状态上报 → 路由 Runnable（无 Runnable 走 DB 直收兜底）。"""
    msgs = queue.read_states(consumer=queue.master_consumer(), block_ms=1, count=10)
    if not msgs:
        return False
    for msg_id, payload in msgs:
        try:
            runnable = get_runnable(str(payload.get("instanceId") or ""))
            if runnable is not None and runnable.is_alive():
                runnable.submit_state(payload)
            else:
                _apply_state_direct(payload)
        finally:
            queue.ack_state(msg_id)
    return True


def _apply_state_direct(msg: dict) -> None:
    """无 Runnable 兜底（I1 语义）：任务终态落库 + 同实例全终态推进实例终态。"""
    session = new_session()
    try:
        task = session.get(TaskInstance, msg.get("taskId"))
        if task is None:
            logger.warning("状态上报对应任务不存在: %s", msg)
            return
        set_instance_id(task.instance_id)
        task.state = msg.get("state") or state.FAILURE
        task.end_time = now()
        task.outputs = msg.get("outputs")
        task.log_path = msg.get("logPath")
        task.host = msg.get("host")

        instance = (
            session.query(WorkflowInstance)
            .filter(WorkflowInstance.instance_id == task.instance_id)
            .first()
        )
        if instance is not None and instance.state in state.INSTANCE_RUNNING_STATES:
            if instance.state == state.SUBMITTED:
                instance.state = state.RUNNING
                instance.start_time = now()
            tasks = (
                session.query(TaskInstance)
                .filter(TaskInstance.instance_id == task.instance_id)
                .all()
            )
            if tasks and all(t.state in state.TERMINAL_STATES for t in tasks):
                if any(t.state == state.KILL for t in tasks):
                    instance.state = state.KILL
                elif any(t.state == state.FAILURE for t in tasks):
                    instance.state = state.FAILURE
                else:
                    instance.state = state.SUCCESS
                instance.end_time = now()
                logger.info("实例终态（fallback）: %s → %s", task.instance_id, instance.state)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        set_instance_id(None)
        session.close()


# ---------------- 服务循环 ----------------

def command_loop(stop, gate: LeaderGate) -> None:
    """① 命令消费线程（2s/轮）。"""
    logger.info("命令消费线程启动（2s/轮）")
    queue.ensure_all_groups()
    while not stop.is_set():
        if gate.check():
            try:
                consume_commands()
            except Exception as exc:  # noqa: BLE001 服务循环防崩
                logger.error("命令消费异常: %s", exc)
        stop.wait(2)
    logger.info("命令消费线程退出")


def state_loop(stop, gate: LeaderGate) -> None:
    """② 状态消费线程（1s/轮）。"""
    logger.info("状态消费线程启动（1s/轮）")
    while not stop.is_set():
        if gate.check():
            try:
                for _ in range(10):
                    if not consume_state_reports():
                        break
            except Exception as exc:  # noqa: BLE001
                logger.error("状态消费异常: %s", exc)
        stop.wait(1)
    logger.info("状态消费线程退出")


def timeout_loop(stop, gate: LeaderGate) -> None:
    """④ 超时扫描线程（10s/轮）：委托各 Runnable 检查自身 running 任务。"""
    logger.info("超时扫描线程启动（10s/轮）")
    while not stop.is_set():
        if gate.check():
            for runnable in all_runnables():
                try:
                    runnable.check_timeouts()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("超时扫描异常（instance=%s）: %s", runnable.instance_id, exc)
        stop.wait(10)
    logger.info("超时扫描线程退出")
