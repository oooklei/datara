"""状态常量（02 文档 §1.1 全状态集 / 海豚 ExecutionStatus，设计文档 §3.3）。

- 实例状态：submitted/running/success/failure/kill（fault_tolerance 为过渡态，仅任务级）
- 任务状态：submitted/waiting_dependency/running/success/failure/kill/skip/fault_tolerance/retry
- 写权分工：submitted/retry/waiting_dependency/skip/fault_tolerance/kill 由 master 写；
  running/终态由 worker 上报、master 落库（逻辑节点全由 master 写）。
"""

SUBMITTED = "submitted"
WAITING_DEPENDENCY = "waiting_dependency"
RUNNING = "running"
SUCCESS = "success"
FAILURE = "failure"
KILL = "kill"
SKIP = "skip"
FAULT_TOLERANCE = "fault_tolerance"
RETRY = "retry"

# 任务终态集合：全部任务终态后才推进实例终态（skip 亦为终态，设计 §5.2）
TERMINAL_STATES = frozenset({SUCCESS, FAILURE, KILL, SKIP})

# 非终态（活动）集合：容错恢复/停止命令扫描对象
ACTIVE_STATES = frozenset({SUBMITTED, WAITING_DEPENDENCY, RUNNING, RETRY, FAULT_TOLERANCE})

# 实例态集合
INSTANCE_RUNNING_STATES = frozenset({SUBMITTED, RUNNING})
