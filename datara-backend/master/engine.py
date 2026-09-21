"""工作流执行引擎核心（F42/F44/F45，对齐海豚 WorkflowExecuteRunnable + EventService）。

- 每实例一个 WorkflowExecuteRunnable 线程：事件驱动拓扑推进 + 定时器轮询（延时/依赖/重试）
- 逻辑节点 C1~C10 master 内联执行（不占 worker）；数据节点 sql/shell/python/ssh 派发 worker
- 全部状态写库以 DB 为准；线程间经 Runnable 私有事件队列通信（状态消费线程路由）
- constraints 随消息从 graph_json 下发不入库（设计 §4）；重试/超时/失败策略 §8
"""

import os
import threading
from datetime import datetime, timedelta
from queue import Empty, Queue
from typing import Optional

from common import queue
from common.config import get_settings
from common.db import new_session
from common.log import get_logger, set_instance_id
from common.models import TaskInstance, TaskLog, WorkflowInstance, now
from master import state
from master.dag import Graph, loop_bodies
from master.variables import (
    VarResolver, clear_run_vars, eval_expr, get_run_vars,
    load_levels, set_run_vars, time_var,
)

logger = get_logger("master.engine")

POLL_INTERVAL_SEC = 10  # 定时器/kill 自查轮询周期
DEPENDENT_POLL_SEC = 10  # C9 依赖轮询周期
DEFAULT_MAX_ITERATIONS = 100  # C10 防死循环上限

# worker 派发类节点全集（I4 扩容：+procedure/http/file C15/C16/C22；I6 扩容：+sync F28）
# 超时扫描（check_timeouts）/容错重派（_resume_sweep）/执行器分派（_execute_node）共用
WORKER_TYPES = ("sql", "shell", "python", "ssh", "smoke", "procedure", "http", "file", "sync")


# ---------------- Runnable 注册表（状态消费/命令消费/超时扫描 共享） ----------------

_RUNNABLES: dict = {}
_RUNNABLES_LOCK = threading.Lock()


def register_runnable(runnable: "WorkflowExecuteRunnable") -> None:
    with _RUNNABLES_LOCK:
        _RUNNABLES[runnable.instance_id] = runnable


def get_runnable(instance_id: str) -> Optional["WorkflowExecuteRunnable"]:
    with _RUNNABLES_LOCK:
        return _RUNNABLES.get(instance_id)


def remove_runnable(instance_id: str) -> None:
    with _RUNNABLES_LOCK:
        _RUNNABLES.pop(instance_id, None)


def all_runnables() -> list:
    with _RUNNABLES_LOCK:
        return list(_RUNNABLES.values())


# ---------------- 工具 ----------------

def _snapshot_lines(snapshot: dict, instance_id: str, node_name: str) -> list:
    """变量快照日志头（§10.3，明文不脱敏）。"""
    lines = ["===== 变量快照 instance_id=%s node=%s =====" % (instance_id, node_name)]
    for name, item in (snapshot or {}).items():
        if isinstance(item, dict):
            lines.append("%s=%s  (%s)" % (name, item.get("value"), item.get("source")))
        else:
            lines.append("%s=%s" % (name, item))
    lines.append("=" * 44)
    return lines


def _append_task_log(instance_id: str, task_id: int, lines: list) -> str:
    """master 侧任务日志增量追加（逻辑节点；worker 同路径约定 {log_dir}/{instance_id}/{task_id}.log）。"""
    log_dir = os.path.join(get_settings().log_dir, instance_id)
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, "%s.log" % task_id)
    with open(path, "a", encoding="utf-8") as handle:
        for line in lines:
            handle.write(str(line) + "\n")
    return path


def _ensure_task_log_index(session, instance_id: str, task_id: int, path: str, host: str) -> None:
    exists = (
        session.query(TaskLog)
        .filter(TaskLog.task_instance_id == task_id)
        .first()
    )
    if exists is None:
        session.add(TaskLog(instance_id=instance_id, task_instance_id=task_id, log_path=path, host=host))


# ---------------- 执行 Runnable ----------------

class WorkflowExecuteRunnable(threading.Thread):
    """单实例执行线程：拓扑推进 + 逻辑节点内联 + 定时器（延时/依赖/重试）。"""

    def __init__(self, instance_id: str, graph: Graph, resume: bool = False):
        super().__init__(name="wf-run-%s" % instance_id, daemon=True)
        self.instance_id = instance_id
        self.graph = graph
        self.resume = resume
        self.events: Queue = Queue()
        self.wake = threading.Event()
        self.stop_flag = False
        self.killed = False

        self.rows: dict = {}       # {(node_id, loop_iter): {id,state,attempt,start_time,delay_until}}
        self.by_task_id: dict = {}  # {task_row_id: (node_id, loop_iter)}
        self.edge_status: dict = {}  # {(loop_iter, edge_idx): ready/skipped/broken}
        self.chosen: dict = {}     # {(node_id, loop_iter): 命中分支 dict|None}
        self.activated: set = set()
        self.loop_iter_now: dict = {}  # {loop_node_id: 当前迭代号}
        self.loop_members: dict = loop_bodies(graph)  # {loop_node_id: 体节点集}（§6.8）
        self.timers_delay: dict = {}   # {key: datetime}
        self.timers_retry: dict = {}   # {key: datetime}
        self.timers_dep: dict = {}     # {key: datetime}
        self.snapshots: dict = {}      # {node_name: snapshot} 实例级汇总
        self.resolver: Optional[VarResolver] = None
        self.fail_defaults: dict = {}  # 定时/补数下发的任务缺省重试参数

    # ---- 生命周期 ----

    def notify_kill(self) -> None:
        """STOP 命令通知（命令消费线程调用）。"""
        self.events.put({"kind": "kill"})

    def submit_state(self, payload: dict) -> None:
        """worker 终态上报路由（状态消费线程调用）。"""
        self.events.put({"kind": "task_state", "payload": payload})

    def run(self) -> None:
        set_instance_id(self.instance_id)
        try:
            self._load_context()
            self._load_rows()
            if self.resume:
                self._resume_sweep()
            else:
                self._mark_instance_running()
                for node_id in self.graph.start_nodes():
                    self._try_activate(node_id, 0)
            logger.info("Runnable 启动: instance=%s resume=%s", self.instance_id, self.resume)
            while not self.stop_flag:
                self._drain_events()
                self._on_timer(now())
                if self._check_instance_killed():
                    self._mark_all_killed()
                if self._all_terminal():
                    self._finalize()
                    break
                self.wake.wait(self._next_timeout())
                self.wake.clear()
        except Exception as exc:  # noqa: BLE001 实例线程防崩：异常落实例 failure
            logger.exception("Runnable 异常退出: instance=%s %r", self.instance_id, exc)
            self._fail_instance(str(exc))
        finally:
            remove_runnable(self.instance_id)
            set_instance_id(None)
            logger.info("Runnable 退出: instance=%s", self.instance_id)

    # ---- 上下文/行装载 ----

    def _load_context(self) -> None:
        session = new_session()
        try:
            instance = (
                session.query(WorkflowInstance)
                .filter(WorkflowInstance.instance_id == self.instance_id)
                .first()
            )
            if instance is None:
                raise ValueError("实例不存在: %s" % self.instance_id)
            variables = instance.variables if isinstance(instance.variables, dict) else {}
            env_group_id = variables.get("envGroupId")
            base = instance.schedule_time or instance.create_time or now()
            self.resolver = VarResolver(
                self.instance_id, instance.wf_code,
                load_levels(session, instance.wf_code, env_group_id), base,
            )
            self.fail_defaults = {
                "retryTimes": int(variables.get("failRetryTimes") or 0),
                "retryIntervalSec": int(variables.get("failRetryInterval") or 60) ,
            }
        finally:
            session.close()

    def _load_rows(self) -> None:
        session = new_session()
        try:
            rows = (
                session.query(TaskInstance)
                .filter(TaskInstance.instance_id == self.instance_id)
                .all()
            )
            for row in rows:
                key = (row.node_id or "", int(row.loop_iter or 0))
                self.rows[key] = {
                    "id": row.id, "state": row.state, "attempt": int(row.attempt or 1),
                    "start_time": row.start_time, "delay_until": row.delay_until,
                }
                self.by_task_id[row.id] = key
        finally:
            session.close()

    def _row(self, node_id: str, loop_iter: int) -> Optional[dict]:
        return self.rows.get((node_id, int(loop_iter)))

    def _node_type(self, node_id: str) -> str:
        return self.graph.node(node_id)["type"]

    def _node_data(self, node_id: str) -> dict:
        return self.graph.node(node_id)["data"]

    def _node_name(self, node_id: str) -> str:
        return str(self._node_data(node_id).get("name") or node_id)

    # ---- DB 写 ----

    def _save_row(self, key: tuple, outputs: Optional[dict] = None, log_lines: Optional[list] = None) -> None:
        """内存行 → DB 写通（状态/时间/输出/日志）。"""
        row = self.rows[key]
        session = new_session()
        try:
            task = session.get(TaskInstance, row["id"])
            if task is None:
                return
            task.state = row["state"]
            task.attempt = row["attempt"]
            task.start_time = row["start_time"]
            task.end_time = row.get("end_time")
            task.delay_until = row.get("delay_until")
            if outputs is not None:
                task.outputs = outputs
            if log_lines:
                path = _append_task_log(self.instance_id, row["id"], log_lines)
                task.log_path = path
                _ensure_task_log_index(session, self.instance_id, row["id"], path, task.host or "-")
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _set_state(self, key: tuple, st: str, outputs: Optional[dict] = None, log_lines: Optional[list] = None) -> None:
        row = self.rows[key]
        row["state"] = st
        if st in state.TERMINAL_STATES:
            row["end_time"] = now()
        self._save_row(key, outputs=outputs, log_lines=log_lines)

    def _mark_instance_running(self) -> None:
        session = new_session()
        try:
            instance = (
                session.query(WorkflowInstance)
                .filter(WorkflowInstance.instance_id == self.instance_id)
                .first()
            )
            if instance is not None and instance.state == state.SUBMITTED:
                instance.state = state.RUNNING
                instance.start_time = now()
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---- 事件消费 ----

    def _drain_events(self) -> None:
        while True:
            try:
                event = self.events.get_nowait()
            except Empty:
                return
            kind = event.get("kind")
            if kind == "task_state":
                self._apply_worker_state(event["payload"])
            elif kind == "kill":
                self.killed = True

    def _apply_worker_state(self, payload: dict) -> None:
        """worker 终态上报 → 行状态落库 → 重试判定 → 拓扑推进。"""
        task_id = payload.get("taskId")
        key = self.by_task_id.get(task_id)
        if key is None or key not in self.rows:
            logger.warning("状态上报无对应行（忽略）: %s", payload)
            return
        row = self.rows[key]
        if row["state"] in state.TERMINAL_STATES:
            return  # at-least-once 重复投递防护
        if payload.get("attempt") is not None and int(payload["attempt"]) != row["attempt"]:
            return  # 陈旧尝试的上报（重试后旧 worker 迟到），忽略
        st = payload.get("state") or state.FAILURE
        row["state"] = st
        row["end_time"] = now()
        self._save_row(key, outputs=payload.get("outputs"), log_lines=None)
        session = new_session()
        try:
            task = session.get(TaskInstance, row["id"])
            if task is not None:
                task.end_time = row["end_time"]
                task.outputs = payload.get("outputs")
                task.log_path = payload.get("logPath") or task.log_path
                task.host = payload.get("host") or task.host
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        if st == state.FAILURE and self._schedule_retry(key):
            return
        self._advance_downstream(key[0], key[1])

    # ---- 重试/超时（§8） ----

    def _constraints(self, node_id: str) -> dict:
        cons = self._node_data(node_id).get("constraints")
        cons = cons if isinstance(cons, dict) else {}
        retry_times = cons.get("retryTimes")
        retry_times = self.fail_defaults["retryTimes"] if retry_times is None else int(retry_times or 0)
        interval = cons.get("retryInterval")
        interval_sec = self.fail_defaults["retryIntervalSec"] if interval is None else int(interval or 1) * 60
        timeout_min = cons.get("timeoutMin")
        timeout_sec = 0 if timeout_min is not None and int(timeout_min or 0) <= 0 else int(timeout_min or 60) * 60
        return {
            "timeoutSec": timeout_sec,
            "retryTimes": max(0, retry_times),
            "retryIntervalSec": max(1, interval_sec),
            "failPolicy": str(cons.get("failPolicy") or "stop"),
            "priority": min(5, max(1, int(cons.get("priority") or 5))),
            "workerGroup": str(cons.get("workerGroup") or ""),
        }

    def _schedule_retry(self, key: tuple) -> bool:
        """失败重试：仍有余额 → 置 retry 延迟重派（返回 True 表示已安排）。"""
        node_id, loop_iter = key
        cons = self._constraints(node_id)
        row = self.rows[key]
        if row["attempt"] > cons["retryTimes"]:
            return False
        row["attempt"] += 1
        row["state"] = state.RETRY
        self.timers_retry[key] = now() + timedelta(seconds=cons["retryIntervalSec"])
        self._save_row(key, log_lines=[
            "[master] 第 %s 次重试将于 %s 秒后派发" % (row["attempt"] - 1, cons["retryIntervalSec"])])
        logger.info("任务重试安排: task=%s attempt=%s", row["id"], row["attempt"])
        return True

    def check_timeouts(self) -> None:
        """超时扫描（超时扫描线程调用）：running 的 worker 任务超时 → kill 标记 + failure。"""
        worker_types = WORKER_TYPES
        for key, row in list(self.rows.items()):
            if row["state"] != state.RUNNING or self._node_type(key[0]) not in worker_types:
                continue
            cons = self._constraints(key[0])
            if cons["timeoutSec"] <= 0 or row["start_time"] is None:
                continue
            if now() >= row["start_time"] + timedelta(seconds=cons["timeoutSec"]):
                queue.set_kill(row["id"], reason="timeout")  # worker 按 failure 收口（§14 项7）
                logger.warning("任务超时: task=%s timeout=%ss → failure", row["id"], cons["timeoutSec"])
                self._set_state(
                    key, state.FAILURE,
                    outputs={"error": "timeout", "timeoutSec": cons["timeoutSec"]},
                    log_lines=["[master] 任务超时（%s 秒），标记中断并置 failure" % cons["timeoutSec"]],
                )
                self._advance_downstream(key[0], key[1])

    # ---- 拓扑推进（§5.2） ----

    def _advance_downstream(self, source_id: str, loop_iter: int) -> None:
        """源节点终态 → 出边定级 → 尝试激活下游。"""
        node_type = self._node_type(source_id)
        row = self._row(source_id, loop_iter)
        source_state = row["state"] if row else state.SUCCESS
        # 分支节点仅在自身 success 时决策；skip 级联不做决策（出边全 skipped）
        is_branch = node_type in ("conditions", "switch") and source_state == state.SUCCESS
        branch = None
        if is_branch:
            bkey = (source_id, loop_iter)
            if bkey in self.chosen:
                branch = self.chosen[bkey]
            else:
                branch = self._decide_branch(source_id, loop_iter)
                self.chosen[bkey] = branch  # 决定即缓存（含 None=无命中）
        for edge in self.graph.succs[source_id]:
            if is_branch and (branch is None or not self.graph.branch_match(edge, branch)):
                status = "skipped"  # 分支未命中 / 无命中（§3.3 Skip 级联）
            elif source_state == state.SUCCESS:
                status = "ready"
            elif source_state == state.FAILURE:
                status = "ready" if self._constraints(source_id)["failPolicy"] == "continue" else "broken"
            elif source_state == state.SKIP:
                status = "skipped"
            else:  # kill
                status = "broken"
            self.edge_status[(loop_iter, edge["_idx"])] = status
        for edge in self.graph.succs[source_id]:
            self._try_activate(edge["target"], loop_iter)
        # 回边接线：回环边源节点终态 → Loop 重评（success）/ 循环中断（failure/kill）
        for back in self.graph.back_edges:
            if back["source"] != source_id:
                continue
            if source_state == state.SUCCESS:
                self._loop_tick(back["target"], self.loop_iter_now.get(back["target"], 0))
            elif source_state in (state.FAILURE, state.KILL):
                loop_key = (back["target"], 0)
                loop_row = self.rows.get(loop_key)
                if loop_row is not None and loop_row["state"] not in state.TERMINAL_STATES:
                    self._set_state(loop_key, state.FAILURE,
                                    log_lines=["[master] 循环体尾节点 %s 终止，循环中断" % source_id])
                    self._advance_downstream(back["target"], 0)

    def _pred_status(self, node_id: str, loop_iter: int) -> list:
        """前驱边状态列表 [(edge, status|None-pending, source_row)]。"""
        result = []
        for edge in self.graph.preds[node_id]:
            st = self.edge_status.get((loop_iter, edge["_idx"]))
            source_row = self._row(edge["source"], loop_iter)
            result.append((edge, st, source_row))
        return result

    def _loop_exit_gate_ok(self, node_id: str, loop_iter: int) -> bool:
        """循环出口闸门：前驱为回环边源节点时，须 Loop 终态 success 才放行（§6.8）。

        仅约束 iter0 行（出口链）；体节点迭代行（iter>0）体内推进不受闸门限制。
        """
        if loop_iter != 0:
            return True
        for edge in self.graph.preds[node_id]:
            for back in self.graph.back_edges:
                if back["source"] == edge["source"] and back["target"] != node_id:
                    loop_row = self._row(back["target"], 0)
                    if loop_row is None or loop_row["state"] != state.SUCCESS:
                        return False
        return True

    def _try_activate(self, node_id: str, loop_iter: int) -> None:
        key = (node_id, loop_iter)
        if key in self.activated:
            return
        preds = self._pred_status(node_id, loop_iter)
        if any(st is None for _e, st, _r in preds):
            return  # 有前驱未终态
        if not self._loop_exit_gate_ok(node_id, loop_iter):
            return
        row = self.rows.get(key)
        if row is None:
            return  # 无行（循环体下游首激活由 Loop 派发）
        if row["state"] != state.SUBMITTED:
            return  # 已激活/终态/等待中（重驱与恢复场景防重入）
        statuses = [st for _e, st, _r in preds]
        source_rows = [r for _e, _s, r in preds]
        if any(st == "broken" for st in statuses):
            self.activated.add(key)
            self._set_state(key, state.SKIP, log_lines=["[master] 前驱链路终止（failure/kill），级联跳过"])
            self._advance_downstream(node_id, loop_iter)
            return
        # 汇聚/合并语义（§6 C6/C7）
        node_type = self._node_type(node_id)
        if node_type == "join":
            policy = str(self._node_data(node_id).get("policy") or "all_terminal")
            src_states = [r["state"] if r else None for r in source_rows]
            if policy == "all_success" and any(s == state.SKIP for s in src_states):
                self._skip_cascade(key)
                return
            if policy == "any_success" and not any(s == state.SUCCESS for s in src_states):
                self._skip_cascade(key)
                return
        if node_type == "merge" and statuses and all(st == "skipped" for st in statuses):
            self._skip_cascade(key)
            return
        if statuses and all(st == "skipped" for st in statuses):
            self._skip_cascade(key)
            return
        self.activated.add(key)
        self._execute_node(key)

    def _skip_cascade(self, key: tuple) -> None:
        self.activated.add(key)
        self._set_state(key, state.SKIP, log_lines=["[master] 前驱全部跳过/未命中，级联 skip"])
        self._advance_downstream(key[0], key[1])

    # ---- 节点执行 ----

    def _execute_node(self, key: tuple) -> None:
        node_id, loop_iter = key
        node_type = self._node_type(node_id)
        data = self._node_data(node_id)
        row = self.rows[key]
        row["state"] = state.RUNNING
        row["start_time"] = now()

        # ④ 运行条件 / ⑥ 排除区块（§5.2 激活动作）
        scope = self._expr_scope(loop_iter, data)
        cond_expr = str(data.get("condition") or "")
        if cond_expr and not eval_expr(cond_expr, scope, self.resolver, loop_iter):
            self._set_state(key, state.SKIP, log_lines=["[master] 运行条件不满足: %s" % cond_expr])
            self._advance_downstream(node_id, loop_iter)
            return
        exclude = data.get("exclude") if isinstance(data.get("exclude"), dict) else {}
        if exclude.get("disabled"):
            self._set_state(key, state.SKIP, log_lines=["[master] 节点已禁用（⑥区块）"])
            self._advance_downstream(node_id, loop_iter)
            return
        skip_cond = str(exclude.get("skipCond") or "")
        if skip_cond and eval_expr(skip_cond, scope, self.resolver, loop_iter):
            self._set_state(key, state.SKIP, log_lines=["[master] 跳过条件命中: %s" % skip_cond])
            self._advance_downstream(node_id, loop_iter)
            return

        # 变量解析（F48，快照留档）；激活前刷新 C21 注入层缓存（variable 节点运行中写入）
        self.resolver.refresh_run_vars()
        resolved, snapshot = self.resolver.resolve_node(data, loop_iter)
        self.snapshots[self._node_name(node_id)] = snapshot

        handler = {
            "start": self._exec_start, "end": self._exec_end,
            "conditions": self._exec_conditions, "switch": self._exec_switch,
            "fork": self._exec_fork, "join": self._exec_join,
            "merge": self._exec_merge, "delay": self._exec_delay,
            "dependent": self._exec_dependent, "loop": self._exec_loop,
            "variable": self._exec_variable,
        }.get(node_type)
        if handler is not None:
            handler(key, resolved)
            return
        if node_type in WORKER_TYPES:
            self._dispatch_worker(key, resolved, snapshot)
            return
        self._set_state(key, state.FAILURE, outputs={"error": "executor_not_implemented"},
                        log_lines=["[master] 执行器未实现（后续增量注册）: %s" % node_type])
        self._advance_downstream(node_id, loop_iter)

    def _expr_scope(self, loop_iter: int, data: dict) -> dict:
        """条件/表达式作用域：已解析参数 + 三级变量 + C21 注入层 + 运行时变量。"""
        scope = {}
        for level in self.resolver.levels.values():
            scope.update(level)
        scope.update(self.resolver.run_vars_snapshot())
        rows = data.get("params")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict) and row.get("key"):
                    scope[str(row["key"])] = str(row.get("value") or "")
        scope.update(self.resolver.runtime_scope(loop_iter))
        return scope

    # ---- 逻辑节点内联执行（§6） ----

    def _exec_start(self, key: tuple, resolved: dict) -> None:
        self._set_state(key, state.SUCCESS,
                        outputs={"startTime": now().strftime("%Y-%m-%d %H:%M:%S")},
                        log_lines=_snapshot_lines(self.snapshots.get(self._node_name(key[0]), {}),
                                                  self.instance_id, self._node_name(key[0]))
                        + ["[master] 工作流启动，instance_id=%s" % self.instance_id])
        self._advance_downstream(key[0], key[1])

    def _exec_end(self, key: tuple, resolved: dict) -> None:
        merged = {}
        session = new_session()
        try:
            for _edge, _st, source_row in self._pred_status(key[0], key[1]):
                if source_row is None:
                    continue
                task = session.get(TaskInstance, source_row["id"])
                if task is not None and isinstance(task.outputs, dict):
                    merged.update(task.outputs)
        finally:
            session.close()
        self._set_state(key, state.SUCCESS, outputs={"summary": merged},
                        log_lines=["[master] 工作流结束"])
        self._advance_downstream(key[0], key[1])

    def _decide_branch(self, node_id: str, loop_iter: int) -> Optional[dict]:
        """C3 条件分支（按序首个命中）/ C4 切换（值匹配唯一分支，默认兜底）。"""
        data = self._node_data(node_id)
        branches = data.get("branches") if isinstance(data.get("branches"), list) else []
        scope = self._expr_scope(loop_iter, data)
        if self._node_type(node_id) == "conditions":
            for branch in branches:
                expr = str(branch.get("expr") or "")
                if expr and eval_expr(expr, scope, self.resolver, loop_iter):
                    return branch
            for branch in branches:  # 空表达式 = 默认分支（前端默认 br_no expr=''）
                if not str(branch.get("expr") or "").strip():
                    return branch
            return None
        # switch：判断变量值 → 值匹配
        value = None
        if data.get("variable"):
            value = scope.get(str(data["variable"]))
        elif data.get("expr"):
            value = eval_expr(str(data["expr"]), scope, self.resolver, loop_iter)
        elif "switch_value" in scope:
            value = scope.get("switch_value")
        text = "" if value is None else str(value)
        default = None
        for branch in branches:
            expr = str(branch.get("expr") or "")
            if expr == "*":
                default = branch
            elif expr == text:
                return branch
        return default

    def _exec_conditions(self, key: tuple, resolved: dict) -> None:
        branch = self._decide_branch(key[0], key[1])
        self.chosen[key] = branch
        name = branch.get("name") if branch else None
        self._set_state(key, state.SUCCESS,
                        outputs={"hitBranch": name},
                        log_lines=["[master] 条件分支命中: %s" % (name or "（无命中，下游全部跳过）")])
        self._advance_downstream(key[0], key[1])

    def _exec_switch(self, key: tuple, resolved: dict) -> None:
        branch = self._decide_branch(key[0], key[1])
        self.chosen[key] = branch
        self._set_state(key, state.SUCCESS,
                        outputs={"hitValue": (branch or {}).get("expr")},
                        log_lines=["[master] 切换命中: %s" % ((branch or {}).get("name") or "（默认/无命中）")])
        self._advance_downstream(key[0], key[1])

    def _exec_fork(self, key: tuple, resolved: dict) -> None:
        outs = len(self.graph.succs[key[0]])
        self._set_state(key, state.SUCCESS, outputs={"parallelism": outs},
                        log_lines=["[master] 并行分叉 %d 路" % outs])
        self._advance_downstream(key[0], key[1])

    def _exec_join(self, key: tuple, resolved: dict) -> None:
        summary = [{"source": e["source"], "state": (r["state"] if r else None)}
                   for e, _s, r in self._pred_status(key[0], key[1])]
        self._set_state(key, state.SUCCESS, outputs={"upstreams": summary},
                        log_lines=["[master] 汇聚放行（%d 路上游）" % len(summary)])
        self._advance_downstream(key[0], key[1])

    def _exec_merge(self, key: tuple, resolved: dict) -> None:
        first = None
        for _edge, st, source_row in self._pred_status(key[0], key[1]):
            if st == "ready" and source_row is not None:
                first = source_row
                break
        first_out = None
        if first is not None:
            session = new_session()
            try:
                task = session.get(TaskInstance, first["id"])
                first_out = task.outputs if task is not None else None
            finally:
                session.close()
        self._set_state(key, state.SUCCESS,
                        outputs={"from": first_out},
                        log_lines=["[master] 合并放行（首个到达上游）"])
        self._advance_downstream(key[0], key[1])

    def _exec_variable(self, key: tuple, resolved: dict) -> None:
        """C21 变量组件（I7 F51，设计 §3.1）：逐条求值变量表 → 注入实例运行时变量存储。

        - 类型：literal 字面量原样 / expr 表达式运行时求值（占位替换+simpleeval，失败按 False 留痕）
          / time 时间变量按 F49 求值器（值=时间模板如 yyyyMMdd-1）
        - 覆盖开关：开=直接写运行时存储（覆盖定义级同名变量）；关=仅当运行时与定义级均未定义时生效
        - 节点退出输出=所注入变量集（outputs.injected）；日志打印变量快照（F48 衔接）
        """
        node_id, loop_iter = key
        data = self._node_data(node_id)
        rows = data.get("vars") if isinstance(data.get("vars"), list) else []
        scope = self._expr_scope(loop_iter, data)
        run_existing = get_run_vars(self.instance_id)
        wf_defined = self.resolver.levels.get("workflow", {})
        items: dict = {}
        skipped: list = []
        for r in rows:
            if not isinstance(r, dict) or not str(r.get("name") or "").strip():
                continue
            name = str(r["name"]).strip()
            raw = str(r.get("value") or "")
            vtype = str(r.get("type") or "literal")
            if vtype == "expr":
                value = str(eval_expr(raw, scope, self.resolver, loop_iter))
            elif vtype == "time":
                value = time_var(raw, self.resolver.base_time)
            else:
                value = raw
            if not r.get("override") and (name in run_existing or name in wf_defined):
                skipped.append("%s（已定义，覆盖开关=关）" % name)
                continue
            items[name] = value
        set_run_vars(self.instance_id, items)
        self.resolver.refresh_run_vars()
        snapshot = {name: {"value": value, "source": "变量组件(C21)", "resolved": True}
                    for name, value in items.items()}
        self.snapshots[self._node_name(node_id)] = snapshot
        # C9 衔接（门 3 实测修复）：快照实时并入实例 variables（收口前被依赖方即可读）；
        # dict 拷贝后再赋值——原引用原地改 SQLAlchemy 不标记 dirty，会静默丢库
        try:
            session = new_session()
            try:
                inst = session.query(WorkflowInstance).filter(
                    WorkflowInstance.instance_id == self.instance_id).first()
                if inst is not None:
                    variables = dict(inst.variables) if isinstance(inst.variables, dict) else {}
                    variables["varSnapshot"] = {**(variables.get("varSnapshot") or {}), **snapshot}
                    inst.variables = variables
                    session.commit()
            finally:
                session.close()
        except Exception as exc:  # noqa: BLE001 快照落库失败不阻断注入
            logger.warning("实例变量快照落库失败: %r", exc)
        log_lines = ["[master] 变量组件注入 %d 项: %s" % (
            len(items), ", ".join("%s=%s" % (kv[0], kv[1]) for kv in items.items()) or "（空表）")]
        if skipped:
            log_lines.append("[master] 跳过未注入: %s" % "; ".join(skipped))
        self._set_state(key, state.SUCCESS, outputs={"injected": items},
                        log_lines=log_lines + _snapshot_lines(snapshot, self.instance_id, self._node_name(node_id)))
        self._advance_downstream(node_id, loop_iter)

    def _exec_delay(self, key: tuple, resolved: dict) -> None:
        """C8 延时：duration+unit 或 until（时间变量到点）；到期 success。"""
        data = self._node_data(key[0])
        until = None
        until_expr = str(data.get("until") or "")
        if until_expr:
            parsed = self.resolver.resolve_text(until_expr, {}, key[1], {})
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d %H:%M:%S", "%Y%m%d%H%M%S"):
                try:
                    until = datetime.strptime(parsed, fmt)
                    break
                except ValueError:
                    continue
        if until is None:
            duration = float(data.get("duration") or 0)
            unit = str(data.get("unit") or "秒")
            seconds = duration * {"时": 3600, "分": 60}.get(unit, 1)
            until = now() + timedelta(seconds=seconds)
        row = self.rows[key]
        row["delay_until"] = until
        self.timers_delay[key] = until
        self._save_row(key, log_lines=["[master] 延时至 %s" % until.strftime("%Y-%m-%d %H:%M:%S")])

    def _exec_dependent(self, key: tuple, resolved: dict) -> None:
        """C9 依赖：置 waiting_dependency，周期轮询被依赖工作流+节点状态（§6）。"""
        row = self.rows[key]
        row["state"] = state.WAITING_DEPENDENCY
        self.timers_dep[key] = now()
        self._save_row(key, log_lines=["[master] 等待依赖: %s" % (self._node_data(key[0]).get("deps") or "未配置")])

    def _parse_deps(self, node_id: str) -> list:
        """deps 解析（I7 升级，设计 §0②/§3.2）：双轨兼容。

        - 新格式 DependentDef[]：wf=定义 id（'wf_xxx' 或数字 code）、node=节点 id、cond=可选变量条件
        - 旧字符串（向后兼容）：'工作流code:节点名:期望状态' 多行/分号分隔，期望状态缺省 success
        """
        deps: list = []
        raw = self._node_data(node_id).get("deps")
        if isinstance(raw, list):
            session = new_session()
            try:
                for item in raw:
                    if not isinstance(item, dict) or not str(item.get("wf") or "").strip():
                        continue
                    wf_ref = str(item["wf"]).strip()
                    deps.append({
                        "wfRef": wf_ref,
                        "wfCode": self._resolve_wf_code(session, wf_ref),
                        "nodeRef": str(item.get("node") or "").strip(),
                        "nodeName": str(item.get("nodeName") or ""),
                        "cond": str(item.get("cond") or "").strip(),
                        "expected": "success",
                    })
            finally:
                session.close()
            return deps
        for chunk in str(raw or "").replace("；", ";").replace("，", ",").replace("\n", ";").split(";"):
            parts = [p.strip() for p in chunk.replace("：", ":").split(":") if p.strip()]
            if not parts:
                continue
            code = int(parts[0]) if parts[0].isdigit() else 0
            node_name = parts[1] if len(parts) > 1 else ""
            expected = parts[2] if len(parts) > 2 else "success"
            deps.append({"wfRef": str(code), "wfCode": code, "nodeRef": "",
                         "nodeName": node_name, "cond": "", "expected": expected})
        return deps

    def _resolve_wf_code(self, session, wf_ref: str) -> int:
        """依赖工作流引用解析：数字=code；'wf_xxx'=定义 id → code（查不到返回 0，依赖判定为不满足）。"""
        if wf_ref.isdigit():
            return int(wf_ref)
        from common.models import WfDefinition

        row = session.query(WfDefinition).filter(WfDefinition.id == wf_ref).first()
        if row is None:
            logger.warning("[dependent] 依赖工作流定义不存在: %s", wf_ref)
            return 0
        return int(row.code or 0)

    def _dep_cond_ok(self, dep: dict, instance, loop_iter: int, log_lines: list) -> bool:
        """C9 变量条件匹配（设计 §0②，意见② 范式）：'名=值' 等式，';'/'，' 可多条。

        左侧名取被依赖实例的变量值（运行时注入 > 实例 varSnapshot/variables）；
        右侧值经本实例变量链解析（如 wf.period=${wf.period}）。全部相等才通过。
        """
        if instance is None:
            log_lines.append("[dependent] 变量条件 [%s] 跳过：被依赖实例不存在" % dep["cond"])
            return False
        inst_vars = instance.variables if isinstance(instance.variables, dict) else {}
        scope: dict = {}
        snap = inst_vars.get("varSnapshot")
        if isinstance(snap, dict):
            for name, item in snap.items():
                if isinstance(name, str) and name:
                    scope[name] = str(item.get("value")) if isinstance(item, dict) else str(item)
        for name, value in inst_vars.items():
            if isinstance(name, str) and name and name != "varSnapshot" and not name.startswith("_"):
                scope.setdefault(name, str(value))
        scope.update(get_run_vars(instance.instance_id))
        ok = True
        for chunk in str(dep["cond"]).replace("；", ";").replace("，", ",").split(";"):
            text = chunk.strip()
            if not text:
                continue
            name, sep, expect = text.partition("=")
            name = name.strip()
            expect = expect.strip()
            if not name or not sep or not expect:
                log_lines.append("[dependent] 变量条件格式非法（应为 名=值）: %s" % text)
                ok = False
                continue
            dep_val = scope.get(name)
            exp_val = self.resolver.resolve_text(expect, {}, loop_iter, {})
            hit = dep_val is not None and str(dep_val) == str(exp_val)
            ok = ok and hit
            log_lines.append("[dependent] 变量条件 %s：%s（被依赖实例）%s %s（本实例解析）"
                             % (text, dep_val, "==" if hit else "!=", exp_val))
        return ok

    def _poll_dependent(self, key: tuple) -> None:
        node_id, loop_iter = key
        session = new_session()
        try:
            details = []
            ok = True
            check_lines: list = []
            for dep in self._parse_deps(node_id):
                instance = (
                    session.query(WorkflowInstance)
                    .filter(WorkflowInstance.wf_code == dep["wfCode"])
                    .order_by(WorkflowInstance.id.desc())
                    .first()
                )
                task = None
                if instance is not None:
                    tq = session.query(TaskInstance).filter(
                        TaskInstance.instance_id == instance.instance_id)
                    if dep["nodeRef"]:  # I7 新格式：按节点 id 精确匹配
                        task = tq.filter(TaskInstance.node_id == dep["nodeRef"]) \
                            .order_by(TaskInstance.id.desc()).first()
                    elif dep["nodeName"]:  # 旧格式：按节点名匹配
                        task = tq.filter(TaskInstance.name == dep["nodeName"]) \
                            .order_by(TaskInstance.id.desc()).first()
                actual = task.state if task is not None else None
                satisfied = (
                    actual is not None
                    and actual in state.TERMINAL_STATES
                    and (dep["expected"] == "done" or actual == dep["expected"])
                )
                wf_name = dep["nodeName"] or dep["nodeRef"] or "未配置节点"
                check_lines.append("[dependent] 依赖检查：WF:%s/节点%s=%s %s"
                                   % (dep["wfRef"] or dep["wfCode"], wf_name,
                                      actual or "无实例", "✓" if satisfied else "✗"))
                if satisfied and dep["cond"]:  # I7：节点成功后追加变量条件匹配
                    satisfied = self._dep_cond_ok(dep, instance, loop_iter, check_lines)
                ok = ok and satisfied
                details.append({**dep, "instanceId": instance.instance_id if instance else None,
                                "actual": actual, "satisfied": satisfied})
        finally:
            session.close()
        if ok:
            self.timers_dep.pop(key, None)
            self._set_state(key, state.SUCCESS, outputs={"deps": details},
                            log_lines=["[master] 依赖满足"] + check_lines)
            self._advance_downstream(node_id, loop_iter)
        else:
            self.timers_dep[key] = now() + timedelta(seconds=DEPENDENT_POLL_SEC)
            cons = self._constraints(node_id)
            row = self.rows[key]
            if cons["timeoutSec"] > 0 and row["start_time"] is not None \
                    and now() >= row["start_time"] + timedelta(seconds=cons["timeoutSec"]):
                self.timers_dep.pop(key, None)
                self._set_state(key, state.FAILURE, outputs={"deps": details},
                                log_lines=["[master] 依赖等待超时 → failure"] + check_lines)
                self._advance_downstream(node_id, loop_iter)

    # ---- C10 Loop（自创最小语义，§6.8） ----

    def _loop_should_terminate(self, node_id: str, loop_iter: int, scope: dict) -> bool:
        data = self._node_data(node_id)
        cond = str(data.get("condition") or "")
        if cond:
            return bool(eval_expr(cond, scope, self.resolver, loop_iter))
        collection = str(data.get("collection") or "").strip()
        if collection:
            resolved = self.resolver.resolve_text(collection, {}, loop_iter, {})
            items = [x for x in resolved.split(",") if x.strip()] if "," in resolved else None
            if items is not None:
                batch = max(1, int(data.get("batchSize") or 1))
                return loop_iter >= max(1, -(-len(items) // batch))
            if resolved.isdigit():
                return loop_iter >= int(resolved)
        return loop_iter >= 1  # 未配置终止条件：单轮即止

    def _exec_loop(self, key: tuple, resolved: dict) -> None:
        node_id, _loop_iter = key
        body = self.loop_members.get(node_id) or set()
        if not body:
            self._loop_finish(node_id, 0)  # 无回环边/空体：透传收口
            return
        scope = self._expr_scope(0, self._node_data(node_id))
        if self._loop_should_terminate(node_id, 0, scope):
            self._loop_finish(node_id, 0)
            return
        self._save_row(key, log_lines=["[master] 循环开始（迭代 1）"])  # RUNNING 落库（容错恢复依据）
        self.loop_iter_now[node_id] = 1
        self._loop_dispatch_body(node_id, 1)

    def _loop_tick(self, loop_node_id: str, iteration: int) -> None:
        """回边源节点成功 → Loop 重评终止条件：满足收口 / 不满足开下一迭代（§6.8）。

        iteration = 刚完成的一轮迭代号（run.loopIter 语义）。
        """
        loop_row = self.rows.get((loop_node_id, 0))
        if loop_row is None or loop_row["state"] in state.TERMINAL_STATES:
            return  # 已收口/中断（多回边或恢复重驱防重入）
        scope = self._expr_scope(iteration, self._node_data(loop_node_id))
        max_iter = int(self._node_data(loop_node_id).get("maxIterations") or DEFAULT_MAX_ITERATIONS)
        if self._loop_should_terminate(loop_node_id, iteration, scope):
            self._loop_finish(loop_node_id, iteration)
            return
        if iteration + 1 > max_iter:
            key = (loop_node_id, 0)
            self._set_state(key, state.FAILURE, outputs={"iterations": iteration},
                            log_lines=["[master] 超出最大迭代 %d → failure" % max_iter])
            self._advance_downstream(loop_node_id, 0)
            return
        self.loop_iter_now[loop_node_id] = iteration + 1
        self._loop_dispatch_body(loop_node_id, iteration + 1)

    def _loop_finish(self, loop_node_id: str, iterations: int) -> None:
        key = (loop_node_id, 0)
        self._set_state(key, state.SUCCESS, outputs={"iterations": iterations},
                        log_lines=["[master] 循环收口，共 %d 轮" % iterations])
        self._advance_downstream(loop_node_id, 0)
        self._loop_release_exit(loop_node_id)

    def _loop_release_exit(self, loop_node_id: str) -> None:
        """循环收口放行：回边源节点的非回环出边（循环体出口链）标记 ready@0 并尝试激活。"""
        back_idxs = {b["_idx"] for b in self.graph.back_edges if b["target"] == loop_node_id}
        for back in self.graph.back_edges:
            if back["target"] != loop_node_id:
                continue
            for edge in self.graph.succs.get(back["source"], []):
                if edge["_idx"] in back_idxs:
                    continue  # 回环边自身不标记
                self.edge_status[(0, edge["_idx"])] = "ready"
                self._try_activate(edge["target"], 0)

    def _loop_dispatch_body(self, loop_node_id: str, iteration: int) -> None:
        """新迭代：为循环体全体节点建 loop_iter=iteration 行，仅入口节点尝试激活（§6.8）。

        体节点不预建 iter0 行；Loop→入口边标记 ready@iteration，体内链路随推进激活。
        """
        body = self.loop_members.get(loop_node_id) or set()
        if not body:
            self._loop_finish(loop_node_id, iteration - 1)
            return
        entries: list = []
        for edge in self.graph.succs[loop_node_id]:
            if edge["target"] in body:
                self.edge_status[(iteration, edge["_idx"])] = "ready"
                if edge["target"] not in entries:
                    entries.append(edge["target"])
        for node_id in body:
            if (node_id, iteration) not in self.rows:
                self._create_row(node_id, iteration)
        for node_id in entries:
            self._try_activate(node_id, iteration)

    def _create_row(self, node_id: str, loop_iter: int) -> None:
        """新建任务实例行（Loop 迭代重跑；命令消费侧预建行之外的补充路径）。"""
        session = new_session()
        try:
            task = TaskInstance(
                instance_id=self.instance_id, node_id=node_id,
                node_type=self._node_type(node_id), name=self._node_name(node_id),
                state=state.SUBMITTED, attempt=1, loop_iter=loop_iter,
            )
            session.add(task)
            session.flush()
            row = {"id": task.id, "state": state.SUBMITTED, "attempt": 1,
                   "start_time": None, "delay_until": None}
            self.rows[(node_id, loop_iter)] = row
            self.by_task_id[task.id] = (node_id, loop_iter)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---- worker 派发 ----

    def _collect_partial_inputs(self, node_id: str, loop_iter: int) -> list:
        """GEdge.partial 最小消费闭环（I7 设计 §1.1）：派发前按入边 partial 声明
        拉取上游输出注册为下游输入（param.partialInputs），任务日志留痕对账。

        声明粒度：table=上游结果表名（对齐上游 outputs.tables k）、fields=字段子集、
        filter=行过滤、scope=周期/批次条件。字段子集与行过滤的物化执行后置，
        本期做声明透传 + 上游实体表解析（resolved/unresolved 留痕）。
        """
        items: list = []
        for edge in self.graph.preds[node_id]:
            p = edge.get("partial")
            if not isinstance(p, dict) or not str(p.get("table") or "").strip():
                continue
            src_row = self._row(edge["source"], loop_iter)
            upstream_ref, resolved = None, False
            if src_row is not None:
                session = new_session()
                try:
                    task = session.get(TaskInstance, src_row["id"])
                    outs = task.outputs if task is not None and isinstance(task.outputs, dict) else {}
                finally:
                    session.close()
                tables = outs.get("tables")
                if isinstance(tables, list):
                    for t in tables:
                        if isinstance(t, dict) and str(t.get("k") or "").strip() == str(p["table"]).strip():
                            upstream_ref = t.get("v")
                            resolved = True
                            break
            items.append({
                "source": self._node_name(edge["source"]),
                "table": p.get("table"),
                "fields": p.get("fields") if isinstance(p.get("fields"), list) else [],
                "filter": str(p.get("filter") or ""),
                "scope": str(p.get("scope") or "cycle"),
                "upstreamRef": upstream_ref,
                "resolved": resolved,
            })
        return items

    def _dispatch_worker(self, key: tuple, resolved: dict, snapshot: dict) -> None:
        node_id, _loop_iter = key
        data = self._node_data(node_id)
        cons = self._constraints(node_id)
        row = self.rows[key]
        param = {k: v for k, v in data.items()
                 if k not in ("params", "constraints", "condition", "exclude", "branches", "inputs", "outputs")}
        msg = {
            "taskId": row["id"],
            "instanceId": self.instance_id,
            "nodeType": self._node_type(node_id),
            "name": self._node_name(node_id),
            "attempt": row["attempt"],
            "param": param,
            "param_resolved": resolved,
            "var_snapshot": snapshot,
            "constraints": cons,
        }
        log_lines = ["[master] 任务已派发 worker（priority=%s）" % cons["priority"]]
        # I7 partial 消费闭环：声明注入下游输入参数，worker 侧可读 param.partialInputs
        partial_inputs = self._collect_partial_inputs(node_id, key[1])
        if partial_inputs:
            param["partialInputs"] = partial_inputs
            for pi in partial_inputs:
                log_lines.append(
                    "[master] 部分依赖 %s.table=%s（fields=%d, scope=%s）→ %s" % (
                        pi["source"], pi["table"], len(pi["fields"]), pi["scope"],
                        "实体 %s" % pi["upstreamRef"] if pi["resolved"] else "unresolved（上游未产出该结果表）"))
        queue.add_task(msg, priority=cons["priority"])
        self._save_row(key, log_lines=log_lines)
        logger.info("任务派发: task=%s node=%s type=%s", row["id"], node_id, self._node_type(node_id))

    # ---- 定时器 ----

    def _on_timer(self, current: datetime) -> None:
        for key, due in list(self.timers_delay.items()):
            if current >= due:
                self.timers_delay.pop(key, None)
                if self.rows[key]["state"] == state.RUNNING:
                    self._set_state(key, state.SUCCESS, outputs={"waitedUntil": due.strftime("%Y-%m-%d %H:%M:%S")},
                                    log_lines=["[master] 延时到期 → success"])
                    self._advance_downstream(key[0], key[1])
        for key, due in list(self.timers_retry.items()):
            if current >= due:
                self.timers_retry.pop(key, None)
                row = self.rows.get(key)
                if row is None or row["state"] != state.RETRY:
                    continue  # kill/终态后定时器不复活任务
                row["state"] = state.SUBMITTED
                row["start_time"] = None
                self._save_row(key)
                self.activated.discard(key)
                self._execute_node(key)
        for key, due in list(self.timers_dep.items()):
            if current >= due:
                row = self.rows.get(key)
                if row is None or row["state"] != state.WAITING_DEPENDENCY:
                    self.timers_dep.pop(key, None)  # 已终态/被杀：定时器失效
                    continue
                self._poll_dependent(key)

    def _next_timeout(self) -> float:
        deadlines = list(self.timers_delay.values()) + list(self.timers_retry.values()) \
            + list(self.timers_dep.values())
        if deadlines:
            delta = (min(deadlines) - now()).total_seconds()
            return max(0.5, min(delta, POLL_INTERVAL_SEC))
        return POLL_INTERVAL_SEC

    # ---- 终态推进/收口 ----

    def _all_terminal(self) -> bool:
        return bool(self.rows) and all(r["state"] in state.TERMINAL_STATES for r in self.rows.values())

    def _check_instance_killed(self) -> bool:
        if self.killed:
            return True
        session = new_session()
        try:
            instance = (
                session.query(WorkflowInstance)
                .filter(WorkflowInstance.instance_id == self.instance_id)
                .first()
            )
            return instance is not None and instance.state == state.KILL
        finally:
            session.close()

    def _mark_all_killed(self) -> None:
        for key, row in self.rows.items():
            if row["state"] not in state.TERMINAL_STATES:
                if self._node_type(key[0]) not in ("sql", "shell", "python", "ssh", "smoke") \
                        or row["state"] in (state.RUNNING, state.RETRY):
                    queue.set_kill(row["id"])
                row["state"] = state.KILL
                row["end_time"] = now()
                self._save_row(key, log_lines=["[master] 实例被停止，任务置 kill"])

    def _finalize(self) -> None:
        """实例终态：broken 链路残余任务统一 skip；kill > failure(终止策略) > success（§5.2）。"""
        for key, row in self.rows.items():
            if row["state"] not in state.TERMINAL_STATES:
                row["state"] = state.SKIP
                row["end_time"] = now()
                self._save_row(key, log_lines=["[master] 实例收口统一置 skip"])
        instance_state = state.SUCCESS
        if any(r["state"] == state.KILL for r in self.rows.values()):
            instance_state = state.KILL
        elif any(r["state"] == state.FAILURE and self._constraints(k[0])["failPolicy"] != "continue"
                 for k, r in self.rows.items()):
            instance_state = state.FAILURE
        merged_snapshot: dict = {}
        for snap in self.snapshots.values():
            for name, item in snap.items():
                merged_snapshot.setdefault(name, item)
        session = new_session()
        try:
            instance = (
                session.query(WorkflowInstance)
                .filter(WorkflowInstance.instance_id == self.instance_id)
                .first()
            )
            if instance is not None:
                instance.state = instance_state
                instance.end_time = now()
                variables = dict(instance.variables) if isinstance(instance.variables, dict) else {}
                variables["varSnapshot"] = merged_snapshot
                instance.variables = variables
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        logger.info("实例终态: %s → %s（任务 %d 个）", self.instance_id, instance_state, len(self.rows))

        # I4 临时数据收口（设计 §5.4）：immediate → 清扫置 cleaned；keep+成功 → RENAME 转正式表
        try:
            from common.tmpdata import finalize_instance_tmp

            finalize_instance_tmp(self.instance_id, success=(instance_state == state.SUCCESS))
        except Exception as exc:  # noqa: BLE001 收口清扫失败不阻断实例终态
            logger.error("临时数据收口失败: %s %r", self.instance_id, exc)

        # I7 C21 收口：清除实例运行时注入变量（Redis run_vars:{instance_id}，防残留泄漏）
        try:
            clear_run_vars(self.instance_id)
        except Exception as exc:  # noqa: BLE001 清除失败不阻断实例终态（有 TTL 兜底）
            logger.error("运行时变量收口清除失败: %s %r", self.instance_id, exc)

    def _fail_instance(self, reason: str) -> None:
        """Runnable 异常兜底：实例置 failure。"""
        try:
            session = new_session()
            try:
                instance = (
                    session.query(WorkflowInstance)
                    .filter(WorkflowInstance.instance_id == self.instance_id)
                    .first()
                )
                if instance is not None and instance.state not in state.TERMINAL_STATES:
                    instance.state = state.FAILURE
                    instance.end_time = now()
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception as exc:  # noqa: BLE001
            logger.error("实例兜底置败失败: %s %r", self.instance_id, exc)

    # ---- 容错恢复（failover 调用） ----

    def _resume_sweep(self) -> None:
        """恢复扫描：终态行重驱下游；worker 容错行重派；延时/依赖/重试定时器重装；
        循环状态重建。SUBMITTED 行随终态重驱自然激活（链路就绪才执行）。"""
        worker_types = WORKER_TYPES
        for key, row in list(self.rows.items()):
            node_id, loop_iter = key
            ntype = self._node_type(node_id)
            if row["state"] in state.TERMINAL_STATES:
                self._advance_downstream(node_id, loop_iter)
            elif row["state"] == state.RETRY:
                self.timers_retry[key] = now() + timedelta(seconds=self._constraints(node_id)["retryIntervalSec"])
            elif ntype == "delay" and row["state"] in (state.RUNNING, state.FAULT_TOLERANCE):
                row["state"] = state.RUNNING
                due = row.get("delay_until") or now()
                self.timers_delay[key] = due
                self.activated.add(key)
            elif ntype == "dependent" and row["state"] in (
                    state.WAITING_DEPENDENCY, state.RUNNING, state.FAULT_TOLERANCE):
                row["state"] = state.WAITING_DEPENDENCY
                self.timers_dep[key] = now()
                self.activated.add(key)
            elif ntype == "loop" and row["state"] == state.RUNNING:
                self.activated.add(key)
                self.loop_iter_now[node_id] = max(
                    [li for (nid, li) in self.rows if nid == node_id and li > 0] or [0])
            elif ntype == "loop" and row["state"] == state.SUCCESS:
                # 循环已收口：重驱出口链（边状态内存丢失，重新标记 ready@0 放行）
                self._loop_release_exit(node_id)
            elif ntype in worker_types and row["state"] in (state.FAULT_TOLERANCE, state.RUNNING):
                # 容错重派：attempt 保留，变量重解析后重新投递（worker 幂等校验兜底）
                row["state"] = state.RUNNING
                self.activated.add(key)
                resolved, snapshot = self.resolver.resolve_node(self._node_data(node_id), loop_iter)
                self.snapshots[self._node_name(node_id)] = snapshot
                self._dispatch_worker(key, resolved, snapshot)
