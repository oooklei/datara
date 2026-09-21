"""worker 状态常量（与 master/state.py 同源，独立定义避免模块间耦合）。

- 实例状态：submitted/running/success/failure/kill
- 任务状态：submitted/waiting_dependency/running/success/failure/kill/skip/fault_tolerance/retry
- worker 只写 running 与终态（success/failure/kill），其余由 master 写
"""

SUCCESS = "success"
FAILURE = "failure"
RUNNING = "running"
KILL = "kill"
SKIP = "skip"
# 容错过渡态（§14 项10）：worker 容错认领失联任务时由 worker 写入（写权分工的例外）
FAULT_TOLERANCE = "fault_tolerance"

# 任务终态集合（worker 幂等校验用：重复投递时行已终态 → 丢弃）
TERMINAL_STATES = frozenset({SUCCESS, FAILURE, KILL, SKIP})
