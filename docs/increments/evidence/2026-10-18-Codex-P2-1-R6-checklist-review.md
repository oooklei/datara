# Codex 评审回执：P2-1 R6 加固清单

- 评审对象：`docs/increments/2026-10-18-R6加固清单.md`，提交 `e89580b`
- 评审输入：P2-1 监督派单 #189、Trae 领单 #192、交付 #194；Datara 源码基线 `8ac32c5`；DS 只读快照 `D:\dolphinscheduler-dev\dolphinscheduler-dev`
- 评审方式：三路并行只读复核（DS 语义/源码、Datara 实现现状、治理与验收门禁），主评审回锚；未运行测试（本次仅文档评审）
- 结论：**有条件通过作为起草交付；未达到实施输入冻结条件。** 四能力和六列齐全，结构及 O7 估算方式符合派单；下列 P1 事实/编号问题须修订后，才能进入契约裁定和实施级门禁，不代表任何功能 GREEN 或实施授权。

## 1. 评审结果汇总

| 编号 | 分类/级别 | 位置 | 结论 | 处理要求 |
|---|---|---|---|---|
| R1 | 问题 / P1 | §1 容错现状、§2 D2 | **不通过该处事实判断** | Datara 已有独立人工失败任务恢复与 retry budget 重置路径；改成“实现已存在，待验证其与 DS FailedRecover 的等价范围并补边界测试”。 |
| R2 | 问题 / P1 | §1 自动重试现状 | **部分通过** | 节点级 constraint 按分钟换算秒；workflow variable `failRetryInterval` 则原样作为 `retryIntervalSec` fallback。必须拆明两条配置来源、单位和生效优先级，当前不能笼统写“配置按分钟换算”。 |
| R3 | 问题 / P1 | §1 容错差距/建议 | **部分通过** | `_recovered` 先置位的风险成立，但每个实例恢复异常会被内部捕获后继续；“成功后置位”本身不能重试失败实例。需设计失败实例重扫/重试机制；“单实例失败不阻断其他实例”是现有行为，不列为新增能力。 |
| R4 | 问题 / P1 | §1 DS 重试/容错锚 | **部分通过** | `TaskFailureStateAction.java:75-84` 证明 FAILED 状态收到 Retry event 后预算检查；失败侧发布 Retry event 的锚应补 `AbstractTaskStateAction.java:198-207`。工作流级 failover 测试不应表述为已逐项覆盖全部 task 状态。 |
| R5 | 问题 / P1 | §1 补数语义 | **部分通过** | 补数多实例/批次差距基本成立；应补 DS serial 由成功监听器逐日期推进、parallel 将日期拆为 N 组分别触发的语义，并说明失败后的后续日期行为不能由 success listener 单独推定。 |
| R6 | 问题 / P1 | §1 补数 DS 校验 | **部分通过** | DS validator 接受 `parallelism=0`，delegate 分片存在除零风险，而 UI 最小值为 1。列为 DS validator/UI 不一致及 Datara 必须拒绝零值的边界，不要只泛化为 Datara 新能力。 |
| R7 | 问题 / P1 | §1 优先级 DS 语义 | **不通过该处概括** | `TaskExecution.java:190-210` 中 workflow/task priority 数值小者更高，而 task-group priority 数值大者更高；需分层写出方向。项目偏好写入 `workflowInstancePriority`，不能称为覆盖节点 task priority。 |
| R8 | 问题 / P1 | §2 D1-D5 | **需重编号/拆项** | 与总体方案 §0 D1-D5（全局裁定）重号。改为 `P2-1/R6-C1..C6` 等明确局部编号；并将 D1 的 retry interval/分类退避与 attempt 实体模型拆成两个决策点。 |
| R9 | 建议 / P1 | §2 D3-D5、§3 | **有条件采纳** | 持久 batch、日期列表/时区/DST、防饥饿、项目覆盖是建议选项，不是已批准业务要求。显式标为待业务裁定的扩展，禁止据此直接扩大实施范围。 |
| R10 | 建议 / P1 | §3 验收关门 | **有条件采纳** | RED 关门方向正确，但实施输入还需映射 A1-A7（注明适用/豁免）、标准版本与阶段试点判据；为四能力分别给可判定 PASS 谓词、场景矩阵、证据命名和重跑入口。 |
| R11 | 问题 / P2 | 标题/状态 | **需修正** | 文件标题标“正式版”，正文状态为“起草稿”，统一为“起草稿”以免被误作冻结契约。 |
| R12 | 问题 / P2 | §4 测试统计 | **需修正** | `tests/test_retry_classifier.py` 实际到第 17 行；文档两处写 1–16。更新行号并维持“仅分类/退避纯函数，不覆盖生命周期”的准确边界。 |
| R13 | 建议 / P2 | §1 Retry/补数现状 | **采纳** | Retry deadline 未持久化、恢复时按当前配置重新计时有 Datara 源码依据；补数目前只有日期范围+布尔 parallel 和串行 `complementGroup` 骨架，无持久批次及每日 runId 关联。保留差距，但写清已有骨架。 |

## 2. 关键源码锚点与建议更新文本

### 2.1 Datara 人工失败恢复已经存在（R1）

- API：`datara-backend/api/instance.py:208-217` 提交 `START_FAILURE_TASKS`。
- 调度器：`datara-backend/master/scheduler.py:428-472` 将失败节点及下游非 SUCCESS 节点重置为 SUBMITTED、`attempt=1`，清理结束时间/延迟/输出并重新运行。
- 建议把 §1 容错差距“自动 retry / failover 重派 / 人工失败恢复未分开建模”改为：**“Datara 已存在人工失败任务恢复命令并重置 attempt；尚待核对其重置范围、预算语义与 DS FailedRecover 的完整等价边界，并补自动化测试。该路径不应作为从零实现项。”**
- D2 建议改为“人工失败任务恢复预算：现实现重置；裁定是否保持此行为及需补的兼容边界”，而不是对现状作二选一描述。

### 2.2 重试单位与恢复路径（R2-R4）

- 节点约束换算：`datara-backend/master/engine.py:572-588`。
- workflow `failRetryInterval` fallback：`engine.py:315-318` 原值进入名为 `retryIntervalSec` 的默认值，须单独核单位。
- Retry deadline 放在内存 timer、数据库保留状态/attempt 等，resume 按当前配置恢复：`engine.py:601-625,2201-2211`；模型字段 `common/models.py:210-222`。该差距结论可保留。
- DS 事件链补锚 `AbstractTaskStateAction.java:198-207`；现有 `TaskFailureStateAction.java:75-84` 仅覆盖收到 Retry event 后的预算判断。
- failover：`scheduler.py:56-67` 先置 `_recovered=True`；`master/failover.py:38-46` 捕获单实例异常后继续，不会上冒至 LeaderGate。建议增加可恢复失败项队列或周期性重扫，而非仅调整 `_recovered` 置位时机。该逐实例捕获也说明单实例失败不会阻断其他实例。

### 2.3 补数和优先级语义（R5-R7）

- DS backfill：`BackfillWorkflowExecutorDelegate.java:106-155` 区分 serial 与 parallel 分组；`WorkflowSuccessLifecycleListener.java:73-100` 成功后推进后续日期。失败后是否推进应按失败链路补证。
- DS 边界：`BackfillWorkflowDTOValidator.java:55-57` 只拒负数；UI `start-modal.tsx:517-523` 最小为 1；delegate `BackfillWorkflowExecutorDelegate.java:121-132,143-148` 对零分组有除零风险。
- Datara backfill：API 仅日期范围与布尔 parallel (`api/wf_definition.py:741-769`)；调度器每日展开，串行才带 `complementGroup` (`master/scheduler.py:318-360`)，可据此保留“无持久批次与 runId 关联”的缺口表述。
- DS priority：`TaskExecution.java:190-210` workflow/task 与 task-group 比较方向不同；`start-modal.tsx:199-203` 项目 preference 写入的是 `workflowInstancePriority`。`WorkflowExecutionTypeEnum.java:29-32` + `SerialCommandPriorityHandler.java:35-56` 支持 `SERIAL_PRIORITY` 是实例冲突策略，与队列权重分离。
- Datara worker 队列：`common/queue.py:99-129` 支持分档及多流读取；当前锚不足以证明严格全局优先级、公平性或无饥饿。清单对此保持“未证明”是合适的。

## 3. 其余通过项与质量边界

- 四能力（retry、容错/failover、backfill、priority）均有独立行，且六列齐全；§0 区分执行引擎 R6 与调度查询 API R6 正确。
- 相对规模 L、中低置信度可保留；修正已存在的人工失败恢复后，不能再用该项作为新增工作量依据。D1-D5 未裁定前不转人日计划。
- 清单本身是预研草案。任何建议（持久化 batch/attempt、时区 DST、防饥饿等）经业务裁定和契约冻结前，不得视为已批准规格或实现任务。
- review 没有运行测试；DS/Datara 行为结论是源代码审阅，不代表验收门禁通过。

## 4. 评审结论

**有条件通过，要求 Trae 修订 R1–R8、R11–R12 后提交复评；R9–R10 可在实施计划中闭环。** 当前草案可以作为预研记录保留，但在编号冲突、已存在人工恢复事实及 DS 关键语义修正前，**不得标记“正式版”、冻结契约或作为直接实施授权**。复评时核对修改行与以上源码锚点，并确认所有尚未批准的扩展仍标为待裁定。
