# P2-1 R6 执行引擎加固：DS 源码差异与验收清单

- 日期：2026-10-17
- 状态：只读源代码审查；不代表加固已实现或 GREEN。
- 范围：分阶段混合集成方案 §4 Phase 2、§7 P2-1 与 §8 议题 3 指定的四项：重试、容错、补数、优先级；不改业务代码。
- 证据基线：canonical main `a19baea`。DS 参考源码位于 `D:\dolphinscheduler-dev\dolphinscheduler-dev`。

## 1. 先消除 R6 命名冲突

本报告中的 **P2-1 R6 = 执行引擎加固**，即重试/容错/补数/优先级按 DolphinScheduler 语义逐项对照（设计 §4、§7）。它不同于：

1. P1 冻结宣言 §6 的 **R6 调度契约域**（`listQueue`、`listRuntimeEvents`、`listAlerts` 等 API）；该域已冻结的是契约，不表示 BE 已实现或 GREEN。
2. GREEN 接线计划中 **R6 调度 API 接线批**；计划明确三个查询端点仍待 BE。
3. 旧执行附录中称为 R7 的调度/任务中心域。

截至本报告基线，Datara 主线未发现 `datara-backend/rebuild/scheduling/`、`listQueue/listRuntimeEvents/listAlerts`、`TriggerKind` 或对应 schedule router。不得将以上 API 契约状态代替 P2-1 引擎能力评估，也不得因 API 缺失而误报本报告的四项已实现/未实现。

## 2. 四项能力差异矩阵

| 能力 | DolphinScheduler 已核语义 | Datara 当前代码事实 | 差异/风险判断 | GREEN 前应补的验收证据 |
|---|---|---|---|---|
| 自动重试 | 任务级 `failRetryTimes`、`failRetryInterval`；interval 单位为分钟。失败状态先检查预算再发 Retry 事件；按“失败结束时间 + interval”计算剩余等待时间，failover 后等待已过去则立即重试；重试创建新的 TaskInstance 并增加 retryTimes。相关 UI 默认每类 task 通常为 0 次、1 分钟。 | `datara-backend/master/engine.py:575-626` 按错误类别决策、检查预算、增加 `attempt`、保存 RETRY、注册内存 timer 并发 node_retry；`retry_classifier.py` 给 deterministic/transient/congestion/external 分类。`_resume_sweep`（`engine.py:2202-2238`）恢复 RETRY 行时按当前配置的 `retryIntervalSec` 重设 timer。现有专门测试仅见 `tests/test_retry_classifier.py:1-16`。 | 部分能力已存在，但语义并不等价：Transient 使用 1/5/25 秒退避、拥塞最短 30 秒、外部错误用配置间隔；DS 是 task interval 语义。Datara 的配置 `retryInterval` 经过 minutes→seconds，但退避层会覆盖部分配置间隔。持久化的 RETRY 状态没有足够证据证明原决策的 deadline/strategy 可恢复；重启后按配置间隔重算可能改变原等待。Datara task 行递增 attempt，与 DS 新建 TaskInstance/attempt 关联是不同实体模型。 | 配置单位/默认/预算测试；确定性错误不重试；退避策略与最大预算；原任务失败时间、事件和 attempt 关联；timer 到期触发 exactly-once/幂等；重启前后 deadline 保持；超时与重试竞争；任务级/项目级配置来源和审计原因。 |
| 容错与恢复 | DS 对持久化 workflow/task 状态做 Master failover 接管；`NEED_FAULT_TOLERANCE` 状态专门拒绝普通生命周期事件，避免状态机误转。自动重试的 failover 依 retry 事件恢复，不等于手动失败任务恢复；手工恢复可以重置 retry budget，应分开验证。 | `scheduler.py:49-70` 由 LeaderGate 首次成为 leader 时调用 `recover_running_instances()`；`master/failover.py:25-130` 扫描非终态 workflow，将 worker 的 RUNNING 标为 FAULT_TOLERANCE、逻辑节点置回 SUBMITTED，重建 Runnable 并重派；无图 smoke 路径另行重派。`engine.py:2202-2238` resume sweep 重驱终态下游并重建 delay/dependency/retry/loop 状态。 | 有恢复框架，但待核幂等边界：LeaderGate 在恢复调用前置 `_recovered=True`（`scheduler.py:62`），恢复异常后同一进程不会再次尝试；leader 重复接管/重复派发、worker 已执行但状态未落库、逻辑节点重驱副作用、VarPool 重新解析与快照一致性、retry deadline 变化也未被专测覆盖。当前检索到的 Datara tests 未发现 `recover_running_instances` 或端到端故障转移专用用例。手工失败恢复与系统 failover 不可合并成一个“重试”开关。 | 注入 master 崩溃窗口（提交前/后、dispatch 前/后、worker 已完成但状态未消费）；重复 leader 及重复消息；RUNNING/FAULT_TOLERANCE/SUBMITTED/RETRY 各状态恢复；同 run/attempt 关联、变量快照、日志续写及副作用幂等；人工失败恢复预算规则；恢复失败后同一 leader 可重试，且单实例失败不阻塞其他实例。 |
| 补数 / backfill | DS backfill 是日期/时间集合上的多 workflow instance 批次。UI 提供 SERIAL/PARALLEL、并行度或升/降序 executionOrder；默认 serial。API 校验/转换后传递 failureStrategy、taskDependType、priority、worker/environment、start params 与日期列表；可展开下游依赖；每个日期独立生成运行实例。 | `api/wf_definition.py:742-772` 校验日期格式与 end>=start 并投递 COMPLEMENT_DATA；`scheduler.py:318-357` 将 inclusive `dateFrom..dateTo` 展开为多条 START_PROCESS，传递日期、补数组、优先级；`parallel` 为布尔值，串行组通过 `_complement_group_blocked`（`scheduler.py:97-112`）检测同组活动实例后跳过本轮命令。 | 具备日粒度日期展开及基本串行组概念，不足以证明 DS 全链路语义：未发现 backfillTimeList/timezone、显式并行度、日期排序方向、startNodes/startParamList、失败策略/依赖类型继承、下游依赖展开、暂停/续跑/取消批次、每日期 runId↔batch/runGroup 映射与恢复幂等的等价实现。逐日命令按 priority/id 调度，不应推断其等同 DS executionOrder。 | 日期范围/时区/DST/边界校验；明确 SERIAL/PARALLEL/并行度/日期顺序；每日期 runId 及批次状态/进度；重复请求幂等与部分失败续跑；下游依赖展开参数继承；串行下一日期仅在前项策略允许后启动；并行限额实测；取消/重启恢复；结果和审计可按日期追踪。 |
| 优先级 | DS 的 workflow、task、task-group priority 是多个级别；`TaskExecution.compareTo()` 先比较 workflow，再 task，再 task-group，随后提交时间，数值较小代表 enum 优先级更高。手工启动 task priority 可被项目偏好覆盖。UI 工作流/任务表单默认 MEDIUM。DS 的 `SERIAL_PRIORITY` 是“停止旧实例、启动最新实例”策略，不等同于权重排序。 | `scheduler.py:74-82` 查询命令按 `Command.priority DESC, id ASC`；补数命令透传整数 priority；worker queue 将 4-5/3/1-2 映射到 high/normal/low。节点约束把 priority clamp 到 1..5。 | 目前源代码锚显示的是命令/worker 队列优先级，未证明 DS 式多级排序、相同级公平性、项目覆盖或补数与普通任务的优先级仲裁。DS 整数方向与 Datara 反向；直接比较会产生优先级反转。还必须把 SERIAL_PRIORITY 冲突策略与数值队列权重分开。 | 明确优先级枚举映射、workflow/task/task-group 多级排序和覆盖来源；同优先级 FIFO/公平性；高优先级持续流量下的低优先级防饥饿；补数、调度、手工运行混合队列排序；值越界/非法值校验；排序的持久化和恢复。 |

## 3. DolphinScheduler 源码锚点

### 重试与人工恢复

- `dolphinscheduler-master/src/main/java/org/apache/dolphinscheduler/server/master/engine/task/statemachine/TaskFailureStateAction.java:75-84`：失败后检查可重试并触发 retry。
- `.../task/lifecycle/event/TaskRetryLifecycleEvent.java:43-59`：重试预算与基于任务 endTime 的剩余间隔计算，单位换算为分钟。
- `dolphinscheduler-master/src/main/java/org/apache/dolphinscheduler/server/master/engine/task/execution/RetryTaskInstanceFactory.java:45-61`：新建重试 TaskInstance、retryTimes 递增、旧行处理。
- UI `dolphinscheduler-ui/src/views/projects/task/components/node/fields/use-failed.ts:21-43`；默认字段在具体 `tasks/use-*.ts` 中，应按任务类型核对。
- `dolphinscheduler-master/src/test/java/org/apache/dolphinscheduler/server/master/engine/task/lifecycle/event/TaskRetryLifecycleEventTest.java:47-78`：等待间隔、failover 后立即触发、重试次数耗尽。
- `.../FailedRecoverTaskInstanceFactoryTest.java:49+`：手工失败恢复重置预算；与自动重试分开。

### 容错

- `dolphinscheduler-master/src/main/java/org/apache/dolphinscheduler/server/master/engine/task/statemachine/TaskFailoverStateAction.java:26+`：NEED_FAULT_TOLERANCE 状态拒绝一般生命周期事件。
- `dolphinscheduler-master/src/test/java/org/apache/dolphinscheduler/server/master/engine/WorkflowInstanceFailoverTestCase.java:58,91,125+`：submitted/dispatched/running 等 failover 状态覆盖。
- `TaskRetryLifecycleEventTest.java:47-78` 还覆盖 failover 后重建已过期 retry event。

### 补数

- API/转换/校验链：`dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/service/impl/ExecutorServiceImpl.java:146`、`dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/validator/workflow/BackfillWorkflowRequestTransformer.java:55-90`、`dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/validator/workflow/BackfillWorkflowDTOValidator.java:47+`。
- 执行委托：`dolphinscheduler-api/src/main/java/org/apache/dolphinscheduler/api/executor/workflow/BackfillWorkflowExecutorDelegate.java:60-137,164-201`（SERIAL/PARALLEL、顺序/并行度、下游依赖展开与上下文传递）。
- 日期命令：`dolphinscheduler-master/src/main/java/org/apache/dolphinscheduler/server/master/engine/workflow/trigger/WorkflowBackfillTrigger.java:52-105`。
- UI：`dolphinscheduler-ui/src/views/projects/workflow/definition/components/start-modal.tsx:491-530`；默认 `definition/components/use-form.ts:52-65`。
- 测试：`dolphinscheduler-master/src/test/java/org/apache/dolphinscheduler/server/master/engine/WorkflowBackfillTestCase.java:45-64`、`SubWorkflowBackfillScheduleTimeInheritanceTestCase.java:43-82`。

### 优先级

- `dolphinscheduler-master/src/main/java/org/apache/dolphinscheduler/server/master/engine/task/execution/TaskExecution.java:186-211`：比较 workflow、task、task-group priority 与提交时间。
- `dolphinscheduler-common/src/main/java/org/apache/dolphinscheduler/common/enums/Priority.java:25-47`：优先级值表，enum code 较小优先级更高。
- UI：`dolphinscheduler-ui/src/views/projects/task/components/node/fields/use-task-priority.ts:79-85`；工作流 start/timing modal 的 priority 选择器；默认值 `workflow/definition/components/use-form.ts:52-65`。

## 4. 当前 Datara 测试证据盘点

- 找到 `datara-backend/tests/test_retry_classifier.py:1-16`：覆盖分类与退避纯函数，不覆盖 engine timer、持久恢复、attempt 预算或 end-to-end 状态转换。
- `tests/test_component_ref_backfill.py` 的 backfill 指 component reference 数据迁移，不能作为工作流补数验收证据。
- 本轮源码检索未发现工作流 backfill、leader failover、补数优先级仲裁的专用 Datara 测试；后续需在真实执行引擎补齐测试后才可声明能力通过。
- 本报告没有运行测试。上述测试项是建议门禁，不是已跑结果。

## 5. 工作量估算与实施拆分

依据当前“有部分实现、缺失持久化恢复/批次对象与专用执行测试”的源码差异，给出相对规模，不伪装为已评估人日：

| 子项 | 相对规模 | 粗估依据 | 关键不确定性 |
|---|---|---|---|
| 重试 deadline/attempt 语义、状态机与测试 | M；若持久化 attempt 实体则 L | 错误分类和退避骨架已存在；补 engine 生命周期、落库/恢复和幂等证据。 | 用户期望 DS 的分钟 interval，还是保留当前分类退避；attempt 是否独立实体；失败窗口边界。 |
| failover 恢复/重复投递和人工恢复区分 | L | leader 接管路径存在，但需恢复失败可重试、故障注入与端到端幂等证据。 | worker 外部副作用的幂等协议、变量快照、leader fencing 与恢复原语。 |
| backfill 日期边界、顺序/并行度/依赖展开 | M；若新增持久 batch API 则 L | 日期命令展开与串行组骨架已存在；补齐产品语义和执行/恢复覆盖。 | 日期清单/范围、时区、并行策略、部分失败和下游依赖范围的产品裁定。 |
| 多级 priority 与公平性 | S-M | 需统一 enum mapping、队列排序、多类命令竞争和防饥饿测试。 | 优先级取值/映射、项目覆盖、workflow/task/task-group 层级。 |
| 集成验收与 DS parity traceability | M-L | 把每项语义、配置、恢复结果映射到自动化场景并形成可追溯证据。 | Phase 2 验收运行环境、数据库/worker 数及故障注入设施。 |

整体暂估为 **L（四项既有骨架的加固，不是从零建调度器）**，置信度中低；不含远端真实 HA、长稳/性能测试和正式页面改造。若用户要求新增持久 attempt/batch 调度模型迁移或多主 fencing，整体上调为 XL。建议先裁定重试单位/attempt 模型、补数日期/时区/规模上限和优先级映射，再据 API/模型改动面、状态机路径数及故障覆盖给实施级日估算。此相对规模不能替代项目排期或业务语义裁定。

## 6. 建议的分批验收顺序

1. 冻结规范：区分 automatic retry、manual failed-task recovery、master failover；确定 attempt 模型、retry 单位/退避、优先级映射和 backfill batch/date-order/parallel semantics。
2. 重试与恢复：先实现并验证可持久恢复的 deadline/attempt，再注入故障窗口验证幂等和变量/日志连续性。
3. Backfill：显式创建可追踪 batch 和每日期 run，随后覆盖串并行、顺序、部分失败重启、下游依赖扩展。
4. Priority：实现并证明 workflow→task 两级排序及公平性，然后验证与 schedule/backfill/manual command 混排。
5. 逐项对照 DS 源码和测试，留下源锚、Datara 实现路径、自动化测试、运行环境与结果；任何一项缺证仍标 RED，不以旧版页面或已有 UI 字段推定后端能力。

本报告只完成差异盘点与建议验收面；Phase 2 正式实现需以冻结方案/契约为输入，不能将本报告等同于实现授权或 GREEN 声明。
