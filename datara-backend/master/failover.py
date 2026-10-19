"""容错恢复（F42 §3.4，对齐海豚 MasterFailoverService）：

leader 启动/接管时执行一次：扫描 running/submitted 实例 → recovery=1 →
- worker 任务：running 置 fault_tolerance 后重派（attempt 保留，日志续写 append）
- 逻辑节点：Runnable resume 模式重建（终态行重驱下游；延时按 delay_until 重算；
  依赖/循环状态重建）
- 无定义图（I1 smoke 实例）：仅重派 worker 任务，实例收口走状态消费 fallback
"""

import json
import threading

from common.db import new_session
from common.log import get_logger, set_instance_id
from common.models import TaskInstance, WorkflowInstance, WfDefinition, now
from master import state
from master.dag import parse_graph
from master.engine import WorkflowExecuteRunnable, comp_published_versions, register_runnable

logger = get_logger("master.failover")

# G-19 单一真源：worker 任务全集（故障转移时重派口径）— 由 components.catalog 统一定义
from components.catalog import WORKER_TYPES  # noqa: E402


# Successful instances are not replayed by repeated scans in this master process.
# Failed IDs remain pending until a later scan succeeds. A new process starts with
# an empty registry and performs the normal durable-state recovery scan again.
_RECOVERY_LOCK = threading.Lock()
_RECOVERED_INSTANCES: set[str] = set()
_FAILED_INSTANCES: set[str] = set()


def recover_running_instances(fence_token: int | None = None) -> int:
    """恢复活动实例，并只重试本进程此前失败的实例；返回本轮成功数。

    The registry prevents a repeated scan or a second LeaderGate in the same
    process from dispatching an already recovered attempt again. It is not a
    cross-process leader-fencing primitive.
    """
    with _RECOVERY_LOCK:
        session = new_session()
        try:
            instances = (
                session.query(WorkflowInstance)
                .filter(WorkflowInstance.state.in_(state.INSTANCE_RUNNING_STATES))
                .all()
            )
            ids = [inst.instance_id for inst in instances]
        finally:
            session.close()

        active_ids = set(ids)
        _RECOVERED_INSTANCES.intersection_update(active_ids)
        candidates = sorted((active_ids - _RECOVERED_INSTANCES) | (_FAILED_INSTANCES & active_ids))
        if candidates:
            logger.info("容错恢复扫描: %d 个未处理实例 %s", len(candidates), candidates)
        recovered = 0
        for instance_id in candidates:
            try:
                if _recover_one(instance_id, fence_token=fence_token):
                    _RECOVERED_INSTANCES.add(instance_id)
                    _FAILED_INSTANCES.discard(instance_id)
                    recovered += 1
                else:
                    _FAILED_INSTANCES.add(instance_id)
            except Exception as exc:  # noqa: BLE001 单实例恢复失败不阻断整体
                _FAILED_INSTANCES.add(instance_id)
                logger.exception("实例恢复失败，已加入同 leader 重扫: %s %r", instance_id, exc)
        if recovered:
            logger.info("容错恢复完成: %d 个实例已重建 Runnable", recovered)
        return recovered


def _recover_one(instance_id: str, fence_token: int | None = None) -> bool:
    """恢复单实例：任务重派标记 + Runnable 重建。返回是否成功。"""
    set_instance_id(instance_id)
    graph = None
    session = new_session()
    try:
        instance = session.query(WorkflowInstance).filter(WorkflowInstance.instance_id == instance_id).first()
        if instance is None:
            return False
        instance.recovery = 1
        if instance.state == state.SUBMITTED:
            instance.state = state.RUNNING
            if instance.start_time is None:
                instance.start_time = now()
        definition = None
        if instance.wf_code:
            definition = session.query(WfDefinition).filter(WfDefinition.code == instance.wf_code).first()
        if definition is not None and definition.graph_json:
            try:
                # D2 §9.6：物化器按源组件 published 版本注入 sys_exec 节点 componentRef
                # G-14：parse_graph 同时提取流子图（stream_spec），failover 恢复路径不注册
                # 流作业（流作业由 API 显式启停，不随批实例恢复自动拉起）。
                graph, _stream_spec = parse_graph(
                    json.loads(definition.graph_json), comp_versions=comp_published_versions(session)
                )
            except ValueError as exc:
                logger.warning("实例 %s 图解析失败（按无图恢复）: %s", instance_id, exc)
        tasks = session.query(TaskInstance).filter(TaskInstance.instance_id == instance_id).all()
        for task in tasks:
            ntype = task.node_type or (graph.node(task.node_id)["type"] if graph and task.node_id else "smoke")
            if ntype in WORKER_TYPES and task.state in (
                state.RUNNING,
                state.FAULT_TOLERANCE,
                state.SUBMITTED,
                state.RETRY,
            ):
                if task.state == state.RUNNING:
                    task.state = state.FAULT_TOLERANCE
            elif ntype not in WORKER_TYPES and task.state == state.RUNNING:
                task.state = state.SUBMITTED  # 逻辑节点交由 Runnable resume 重激活
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        set_instance_id(None)

    if graph is not None:
        # 变量重解析 + 日志续写由 Runnable resume 完成（fault_tolerance → 重派）
        runnable = WorkflowExecuteRunnable(instance_id, graph, resume=True, fence_token=fence_token)
        register_runnable(runnable)
        runnable.start()
        logger.info("实例 Runnable 已重建（resume）: %s", instance_id)
        return True
    # 无图（smoke）兜底：直接重派，收口走状态消费 fallback
    _redispatch_smoke(instance_id, fence_token=fence_token)
    return True


def _redispatch_smoke(instance_id: str, fence_token: int | None = None) -> None:
    """无图实例（I1 smoke）重派：按任务行原样再投消息（参数取实例 variables）。"""
    from common import queue

    session = new_session()
    try:
        instance = session.query(WorkflowInstance).filter(WorkflowInstance.instance_id == instance_id).first()
        tasks = session.query(TaskInstance).filter(TaskInstance.instance_id == instance_id).all()
        param = instance.variables if isinstance(instance.variables, dict) else {}
        for task in tasks:
            if task.state not in state.ACTIVE_STATES:
                continue
            task.state = state.SUBMITTED
            payload = {
                    "taskId": task.id,
                    "instanceId": instance_id,
                    "nodeType": task.node_type or "smoke",
                    "name": task.name or "smoke",
                    "attempt": int(task.attempt or 1),
                    "param": param,
                }
            priority = int(param.get("priority") or 3)
            if fence_token is None:
                queue.add_task(payload, priority=priority)
            else:
                queue.add_task_fenced(payload, priority=priority, fence_token=fence_token)
            logger.info("smoke 任务重派: task=%s", task.id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
