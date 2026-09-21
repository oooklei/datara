"""容错恢复（F42 §3.4，对齐海豚 MasterFailoverService）：

leader 启动/接管时执行一次：扫描 running/submitted 实例 → recovery=1 →
- worker 任务：running 置 fault_tolerance 后重派（attempt 保留，日志续写 append）
- 逻辑节点：Runnable resume 模式重建（终态行重驱下游；延时按 delay_until 重算；
  依赖/循环状态重建）
- 无定义图（I1 smoke 实例）：仅重派 worker 任务，实例收口走状态消费 fallback
"""

import json

from common.db import new_session
from common.log import get_logger, set_instance_id
from common.models import TaskInstance, WorkflowInstance, WfDefinition, now
from master import state
from master.dag import parse_graph
from master.engine import WorkflowExecuteRunnable, register_runnable

logger = get_logger("master.failover")

WORKER_TYPES = ("sql", "shell", "python", "ssh", "smoke", "sync")  # I6 +sync


def recover_running_instances() -> int:
    """恢复全部未终态实例，返回恢复数量。"""
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
    if ids:
        logger.info("容错恢复开始: %d 个未终态实例 %s", len(ids), ids)
    recovered = 0
    for instance_id in ids:
        try:
            if _recover_one(instance_id):
                recovered += 1
        except Exception as exc:  # noqa: BLE001 单实例恢复失败不阻断整体
            logger.exception("实例恢复失败: %s %r", instance_id, exc)
    if recovered:
        logger.info("容错恢复完成: %d 个实例已重建 Runnable", recovered)
    return recovered


def _recover_one(instance_id: str) -> bool:
    """恢复单实例：任务重派标记 + Runnable 重建。返回是否成功。"""
    set_instance_id(instance_id)
    graph = None
    session = new_session()
    try:
        instance = (
            session.query(WorkflowInstance)
            .filter(WorkflowInstance.instance_id == instance_id)
            .first()
        )
        if instance is None:
            return False
        instance.recovery = 1
        if instance.state == state.SUBMITTED:
            instance.state = state.RUNNING
            if instance.start_time is None:
                instance.start_time = now()
        definition = None
        if instance.wf_code:
            definition = (
                session.query(WfDefinition)
                .filter(WfDefinition.code == instance.wf_code)
                .first()
            )
        if definition is not None and definition.graph_json:
            try:
                graph = parse_graph(json.loads(definition.graph_json))
            except ValueError as exc:
                logger.warning("实例 %s 图解析失败（按无图恢复）: %s", instance_id, exc)
        tasks = (
            session.query(TaskInstance)
            .filter(TaskInstance.instance_id == instance_id)
            .all()
        )
        for task in tasks:
            ntype = task.node_type or (
                graph.node(task.node_id)["type"] if graph and task.node_id else "smoke"
            )
            if ntype in WORKER_TYPES and task.state in (
                state.RUNNING, state.FAULT_TOLERANCE, state.SUBMITTED, state.RETRY,
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
        runnable = WorkflowExecuteRunnable(instance_id, graph, resume=True)
        register_runnable(runnable)
        runnable.start()
        logger.info("实例 Runnable 已重建（resume）: %s", instance_id)
        return True
    # 无图（smoke）兜底：直接重派，收口走状态消费 fallback
    _redispatch_smoke(instance_id)
    return True


def _redispatch_smoke(instance_id: str) -> None:
    """无图实例（I1 smoke）重派：按任务行原样再投消息（参数取实例 variables）。"""
    from common import queue

    session = new_session()
    try:
        instance = (
            session.query(WorkflowInstance)
            .filter(WorkflowInstance.instance_id == instance_id)
            .first()
        )
        tasks = (
            session.query(TaskInstance)
            .filter(TaskInstance.instance_id == instance_id)
            .all()
        )
        param = instance.variables if isinstance(instance.variables, dict) else {}
        for task in tasks:
            if task.state not in state.ACTIVE_STATES:
                continue
            task.state = state.FAULT_TOLERANCE
            queue.add_task(
                {
                    "taskId": task.id,
                    "instanceId": instance_id,
                    "nodeType": task.node_type or "smoke",
                    "name": task.name or "smoke",
                    "param": param,
                },
                priority=int(param.get("priority") or 3),
            )
            logger.info("smoke 任务重派: task=%s", task.id)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
