# R4-DEPENDENCY / R4-RESOURCE Backend API 合同（pending acceptance）

> 状态：S0 合同草案，由 Trae（前端消费面）依 B2 总表 §2/§3 与 `dependencyApi.ts`/`resourceApi.ts` 冻结类型面撰写，提请 Codex 复核冻结；冻结前不授权 R4 后半批 GREEN 接线、部署、数据库写入。本文只定义待实现合同与 RED 依据。
> 范围：依赖组件表单（DEPENDENCY）5 方法 + 资源上传与版本绑定（RESOURCE）5 方法；不把 DolphinScheduler 原生依赖/资源中心 API 直接当作 Datara API。

## 1. 参考与采用边界

- 语义来源：`docs/increments/2026-10-16-纠偏重构方案设计.md` §2.2 客户要求 #4（资源有身份/有版本/有大小与类型限制/有权限边界；工作流版本引用确定资源版本；运行时禁止隐式绑定 latest）与 #5（依赖表单参考 DolphinScheduler：选工作流/任务、周期/日期范围、AND/OR 条件组合、执行前预览最终依赖表达式与解析结果；覆盖满足/失败/超时），§5.3。
- 前端消费面权威：`docs/increments/2026-10-16-前端消费契约需求总表.md` §2/§3；前端类型面以 `.worktrees/trae-r4-red/datara-web/src/services/rebuild/dependencyApi.ts` 与 `resourceApi.ts`（签名与类型已冻结）为准，本文 wire 字段为其 snake_case 镜像。
- 包络先例：沿 `docs/increments/R4-SYNC-API-contract-pending.md` §2「沿用新 Backend `{code,msg,data}` 响应包络」。该表述与 R2 批次包络问询（心跳 #30/#31）同源，本文一并提请全域统一确认。
- 依赖判定语义参考 DolphinScheduler 3.4.3 依赖（DEPENDENT）任务模式；不采用其存储/调度实现。

## 2. API 路由及权限

依赖域所有路径使用 `/api/v1/rebuild/dependency` 前缀，资源域使用 `/api/v1/rebuild/resources` 前缀，均沿用新 Backend `{code,msg,data}` 响应包络。受保护请求使用当前 Bearer token 与 project membership；无权限、跨项目对象、无效 token 沿用既有身份 API 拒绝语义。写入类操作（保存依赖配置、上传资源、绑定资源版本）要求 `EDIT_DEFINITION`，读取与预演/判定类只读操作（候选清单、任务清单、表达式预览、依赖判定、资源与版本读取）要求 `VIEW_ALL`。资源内容凭据不回显；上传正文不入日志。

| 方法与路径 | 行为及无副作用要求 |
|---|---|
| `GET /dependency/workflows?project_id=` | 返回可选上游工作流候选 `[{workflow_id, name, latest_version}]`；`latest_version` 为最新已发布版本。 |
| `GET /dependency/workflows/{workflow_id}/tasks?project_id=&workflow_version=` | 返回工作流任务清单 `[{task_code, name}]`；`workflow_version` 缺省取最新已发布版本。 |
| `POST /dependency/preview` | 按提交的 `groups` 服务端拼装终判依赖表达式并解析各条件窗口与判定，返回 `DependencyExpressionPreview`；只读，不保存、不触发执行。 |
| `POST /dependency/saves` | 将 `groups` 随 `{project_id, workflow_id, workflow_version, task_id}` 保存为该工作流版本的依赖配置，返回 `{saved: true, version}`（version 即 workflow_version）。已发布版本拒绝改写。 |
| `POST /dependency/evaluate` | 以 `as_of`（可缺省=当前时刻）做一次依赖判定预演，返回 `DependencyExpressionPreview & {evaluated_at}`；只读，无副作用。 |
| `POST /resources/uploads` | `multipart/form-data`（字段 `project_id`、`kind`、`file`）上传资源，服务端重验扩展名与大小后生成不可变新版本，返回 `ResourceVersion`。 |
| `GET /resources?project_id=&kind=` | 返回资源元数据 `[{resource_id, name, kind, size_bytes, latest_version}]`；`kind` 过滤可缺省。 |
| `GET /resources/{resource_id}/versions?project_id=` | 返回该资源全部不可变版本 `[ResourceVersion]`。 |
| `GET /resources/{resource_id}/versions/{version}?project_id=` | 返回指定版本 `ResourceVersion`；版本不存在按稳定机器码拒绝。 |
| `POST /resources/bindings` | 将 `{project_id, workflow_id, workflow_version, task_id, resource_id, resource_version}` 显式绑定到工作流版本任务，返回 `{bound: true, binding_id}`。 |

错误响应使用稳定机器码：`DEP_PERMISSION_DENIED`、`DEP_OBJECT_NOT_FOUND`、`DEP_UPSTREAM_NOT_PUBLISHED`、`DEP_INVALID_WINDOW`、`DEP_INVALID_TIMEOUT_POLICY`、`DEP_VERSION_IMMUTABLE`、`RES_PERMISSION_DENIED`、`RES_OBJECT_NOT_FOUND`、`RES_KIND_UNKNOWN`、`RES_TYPE_NOT_ALLOWED`、`RES_SIZE_EXCEEDED`、`RES_VERSION_NOT_FOUND`、`RES_VERSION_IMMUTABLE`、`RES_BINDING_CONFLICT`。字段级校验诊断包含 `field`、`code`、`message`，不得只返回 HTTP 200 + 空映射。

## 3. 请求合同

### 3.1 依赖域（DEPENDENCY）

写入与判定请求统一承载 `groups: [{join, conditions: [...]}]`；`join` 为组内条件连接符（`AND`|`OR`）。组间连接：v1 草案原定多组固定 AND，§7.8 已按用户复刻令修订为 `group_relation: AND|OR`，复刻 DS `Dependence.relation` 的组间 AND/OR——以 §7.8 为准。条件项须显式选择 `selector: workflow|all_tasks|task`：`workflow` wire sentinel 为 `upstream_task_code=0`，`all_tasks` 为 `upstream_task_code=-1`，`task` 必须提供正数 task code；新请求不得仅凭 task code 缺省值推断选择器。旧 v1 未携带 selector 且未携带 upstream_task_code 的请求兼容解释为 `workflow`（sentinel 0）；旧 v1 显式携带 `-1` 或正数时分别解释为 `all_tasks` 或 `task`。`upstream_workflow_id` 必填，`upstream_workflow_version?` 缺省按 §7.2 的既有版本策略解析。时间窗使用互斥的两种输入：DS 复刻输入为 `cycle` + `date_value`；Datara offset 扩展输入为 `date_range: {period_type, begin_offset, end_offset}`。必须且只能提交一种，不能静默择优或把两种算法合并；v1 仅提交 date_range 的请求继续按 offset 扩展解释。

- `previewExpression` / `evaluateDependency` 返回的 `expression` 为服务端拼装的最终依赖表达式（执行前所见即执行所判）；`resolved[]` 逐条件给出 `upstream_workflow_id`、`upstream_task_code?`、`window_start`、`window_end`（ISO 8601）与 `verdict`；整体 `verdict` ∈ `satisfied|pending|failed|timeout`（四枚举，与运行实例 `status` 语义不同，不做映射）。
- `as_of` 为 ISO 8601 UTC 字符串（如 `2026-01-01T00:00:00Z`）；格式口径待冻结确认。
- `saveDependency` 保存对象是「工作流版本 × 任务」的依赖配置；同一工作流版本重复保存替换该任务草稿配置；工作流版本发布后配置不可变（`DEP_VERSION_IMMUTABLE`）。
- 上游工作流/版本不存在或未发布：`DEP_UPSTREAM_NOT_PUBLISHED`；窗口参数非法（end_offset < begin_offset 等）：`DEP_INVALID_WINDOW`。

### 3.2 资源域（RESOURCE）

- `kind` ∈ `sql|python|shell`；允许扩展名 `.sql`/`.py`/`.sh`（服务端按 kind 重验，`RES_TYPE_NOT_ALLOWED`；kind 非法 `RES_KIND_UNKNOWN`）。
- 大小上限：前端预校验常量 20MB（`20971520` 字节）为草案值，设计仅要求「有大小限制」；**提请冻结确认服务端同一上限值**，超限 `RES_SIZE_EXCEEDED`。
- `digest` 为服务端对收到字节计算的 SHA-256（小写十六进制），与共享协议 `sha256` 字段直接对应；`version` 为单资源内单调递增不可变版本号；`uploaded_at` 为 ISO 8601。版本一经生成不可改写（`RES_VERSION_IMMUTABLE`）。
- `bindResourceVersion` 的 `resource_version` 必须为具体数字版本（类型上排除 `'latest'`；服务端拒绝非数字）；绑定目标是「工作流版本 × 任务」，运行时按绑定解析到确定版本，禁止隐式 latest。同一绑定槽重复提交相同请求幂等返回原 `binding_id`，不同 payload 冲突 `RES_BINDING_CONFLICT`；对已发布工作流版本新增/改写绑定拒绝。
- 上传为标准 `multipart/form-data`；边界/字段序按 HTTP 标准，服务端不得依赖字段顺序。

## 4. 执行与结果合同

- 依赖判定输入是提交的 `groups` 快照与上游实例历史；判定只读，不得触发上游补跑、不得改写任何实例状态。`timeout` 语义为窗口已关闭而上游未达成、按配置超时判定；`pending` 为窗口尚未关闭或上游尚未完成；窗口内上游失败为 `failed`；全部条件按表达式判定通过为 `satisfied`。
- 工作流运行时的依赖判定以该运行实例固化的依赖配置（随 workflow_version 保存的内容）为准，不读用户后续编辑态。
- 资源在运行时以绑定的确定版本投喂执行器；执行器不得读取 `latest_version` 隐式解析。
- `ResourceVersion` 三元组 `{resource_id, version, digest}` 即共享协议的 `resource_version_id/sha256` 消费形态。

## 5. 本次合同不隐含的能力

- 不假设当前 Backend 已有 dependency/resources router、service、表结构或对象存储布局。
- 不隐含资源内容预览/在线编辑、跨项目资源共享、配额管理；这些超出 B2 §2/§3 前端消费面。
- 本草案不授权部署、访问 1.9、写入目标数据库或任何正式前端变更；R4 后半批 GREEN 接线在 Codex 复核冻结 + BE 实现落地后按 `2026-10-17-R系列GREEN接线计划.md` Task 4 执行。
- 20MB 上限值、`as_of` 格式口径、组间 relation（`group_relation: AND|OR`，见 §7.8）、`upstream_workflow_version` 缺省语义、绑定冲突语义、§7 v2.1 全部修订项（`failure_waiting_seconds` ×60 换算/`dependResult` 扩展定性/`parameter_passing`/`dependent_wait_timeout_*` 三字段/四组合验收）为本文提请冻结项；冻结前前端按现类型面（草案语义）不动。

## 6. 当前 RED 与后续门

前端 RED 已就位：worktree `datara-web/src/views/rebuild/validation/dependency-form/dependencyApi.contract.test.ts` 与 `resource-upload/resourceApi.contract.test.ts` 断言两哨兵（`R4_DEPENDENCY_NOT_WIRED` / `R4_RESOURCE_NOT_WIRED`）rejects，主测试集保持可运行。后端实现落地且本草案经 Codex 复核冻结后，Trae 按接线计划对 10 方法做 TDD 红绿（端点 URL 与请求键形 / wire→FE 映射 / 错误归一三要素），worktree 侧无本域哨兵改名残留（`R4_*` 词形不在 X13 改名档）。若 Codex 对路由形态、错误码或待冻结项有修正，以修订后的本文为接线权威并同步 B2 总表。

## 7. v2 修订（2026-10-17，用户复刻裁定后）

用户裁定：后端重构阶段必须复刻 DolphinScheduler 依赖实现（源码 `D:\dolphinscheduler-dev\dolphinscheduler-dev`），扩展项按设计 §6.5 补建模。研读依据：`docs/increments/2026-10-17-DBX-DS-源码研读与复刻映射.md` §2/§3.1。本节为对 §2/§3.1 的增补修订，提请 Codex 复核冻结时**以本节为准**（v2.1 修订 2026-10-17：按心跳 #41/#42 用户裁定执行第 3 项 seconds 回退；按 Codex #C43 交叉复核落第 2/4/6/9 项 D1/D4/D3/D5 修订与第 5 项四组合验收注记，各项内标注依据）：

1. **条件项扩展与 selector sentinel（D2 修订）**：新请求的 `conditions[]` 每项含 `kind: workflow|task|file|table_state|external_task`（省略时按 `task` 校验），并显式传 `selector: workflow|all_tasks|task`。`workflow`/`task` 映射 DS `DependentItem.dependentType`；对象选择与 `kind` 分开表达：DS `DEPENDENT_WORKFLOW_CODE=0` 表示整工作流实例状态，`DEPENDENT_ALL_TASK_CODE=-1` 表示工作流内全部任务成功，正数表示指定 task code（DS `Constants.java:L183-L184`、`DependentExecute.java:L149-L154`）。因此 `kind=workflow` 只允许 selector=workflow；`kind=task` 允许 selector=all_tasks 或 task。旧 v1 兼容按字段值映射：kind 与 upstream_task_code 均缺省时映射 workflow/0（保留 §3.1 已声明的整工作流成功语义）；显式 0 映射 workflow，显式 -1 映射 task/all_tasks，正数映射 task/task。新请求不得靠缺省 task code 推断 selector，也不可把旧 v1 缺省字段改解释为 -1。`file`/`table_state`/`external_task` 为 Datara 扩展 kind，条件参数结构随 kind 定义；v2 冻结 kind 枚举与分发语义，各 kind 详细字段在 BE 实现设计时补齐并再确认。
2. **条件极性（v2.1 按 D1 定性：Datara 扩展）**：新增 `dependResult: success|failed`（缺省 `success`）。**DS 定性核验（本线源码实证）**：DS 参数模型含 `dependResult` 字段（`DependentItem.java`），但执行判定路径不消费——`DependentExecute.java:L392-L416` 组合判定读 `getDependResultForItem()`，全文无 `dependentItem.getDependResult()` 调用。「依赖上游失败也成立条件」**非 DS 原生等价语义**：按 Datara 扩展验收，须单独定义单项极性转换（failed=该项按上游失败判定）、两级 AND/OR 三态合成顺序及 NON_EXEC/timeout 映射，不得标注为 DS 复刻。
3. **配置级策略**（保存对象级，随 groups 同级保存；字段归属对齐 DS 内部静态类 `Dependence`，这些策略字段均为依赖配置顶层、与 dependTaskList 同级，监督线 F2）：`check_interval_seconds`（轮询判定间隔，秒；DS `checkInterval` 单位=秒一致无换算。**DS 源码实证注记（v2.1）**：`DependentParameters.java:L47/L64` 仅声明并校验该字段（可空，若提供须为正数），后端依赖执行路径不消费它；DS UI 新建依赖任务草稿默认 `checkInterval=10` 秒（`tasks/use-dependent.ts:L33-L53`，单位见 `fields/use-dependent.ts:L509-L528`）。所以 10 秒是 UI 草稿默认而非 DS 后端轮询默认；Datara 运行时需按本契约实际消费，并明定其自有轮询语义）、`failure_policy: fail|waiting`（缺省 `fail`，复刻 `DEPENDENT_FAILURE_FAILURE|WAITING`）、**`failure_waiting_seconds`（用户裁定定案，心跳 #41/#42：坚持秒，minutes 提名不采纳；policy=waiting 时生效。实现层强制登记换算语义：DS `failureWaitingTime` 源单位=分钟（`DependentParameters.java:L66-L69` 注释 Time unit is minutes），「源分钟 ×60 → 契约秒」只接受正整数分钟、禁止隐式舍入、乘法做范围溢出校验；换算测试强制列入 R4 验收（标准稿 v3 S4 表/R4 清单换算验证行））**、`timeout_seconds`（窗口关闭后未达成判超时的阈值，Datara 语义，对应注解「超时」）。失败等待与依赖节点等待超时分开建模见第 9 项。
4. **时间窗与双输入互斥（D4 修订）**：DS 原生表单字段 `cycle` 与 `dateValue` 组合；新建草稿 cycle 默认 day、dateValue 默认 today，切换 cycle 会清空 dateValue 并要求按新 cycle 重选（`fields/use-dependent.ts:L83-L206,L448-L487`）。cycle ∈ `hour|day|week|month` 负责表单分组/值域校验；dateValue 才是运行时窗口计算输入，当前 UI 允许值按 cycle 为：hour=`currentHour|last1Hour|last2Hours|last3Hours|last24Hours`；day=`today|last1Days|last2Days|last3Days|last7Days`；week=`thisWeek|lastWeek|lastMonday|lastTuesday|lastWednesday|lastThursday|lastFriday|lastSaturday|lastSunday`；month=`thisMonth|thisMonthBegin|lastMonth|lastMonthBegin|lastMonthEnd`（日期工具另识别 `thisMonthEnd`，但当前 UI 未列出）。DS `DependentUtils.getDateIntervalList(businessDate,dateValue)` 可返回多个 DateInterval，执行端按列表顺序逐个查询，缺少候选立即 WAITING，遇到首个非 SUCCESS 即停止；整体 SUCCESS 的必要条件是该 dateValue 解析出的所有区间均 SUCCESS（`DependentUtils.java:L71-L152`、`DependentExecute.java:L124-L160`）。

   Datara 保留 v1 `date_range:{period_type,begin_offset,end_offset}` 作为独立 offset 扩展，与 DS `cycle+date_value` 互斥：每个 condition 必须提交且只提交一种完整输入；两种同时出现以 `DEP_INVALID_WINDOW` 拒绝，不能静默优先或声称算法等价。旧 v1 仅有 date_range 的请求保持 offset 扩展语义。Datara DS-mode 的 `date_value` 按工作流绑定的业务时区和本次判定 `as_of` 对应业务日期求值；输出每个区间的 ISO 8601 start/end，统一使用左闭右开 `[start,end)`，DST 按该 IANA 时区的日历边界计算，不以固定 24 小时替代自然日。preview 与 evaluate 必须使用同一解析器和结果次序；跨多个区间时全成功才整体成功，窗口候选缺失为 pending，其他首个非成功状态按 DS 递归规则返回。offset 扩展的区间生成继续按既有 offset 规则实现，不得借用 date_value 结果覆盖。
5. **判定语义照搬**：DS `DependentUtils` 三态机同规则两层递归应用——组内（`join`）：AND 任一 `failed` 即失败、有 `pending` 即等待；OR 任一 `satisfied` 即通过、有 `pending` 即等待、否则失败；组间（`group_relation`，§7.8）：对各组结果按同一 AND/OR 规则再组合；整体四枚举 satisfied|pending|failed|timeout 不变。验收须覆盖组间×组内四组合（AND/AND、AND/OR、OR/AND、OR/OR）等价案例（标准稿 v3 R4 清单组间等价行）。
6. **parameterPassing 独立建模（v2.1 按 D3 修订，原「观察项/v2 不建模」表述作废）**：DS `parameterPassing`（`DependentItem.java:L33-L38`）是独立运行时值透传能力，与模板变量解析不等价。契约条件项新增 `parameter_passing: boolean`（缺省 `false` 向后兼容）：仅在该上游依赖判定 satisfied 后，将上游 VarPool OUT 参数传递至下游运行上下文，同名参数按 DS 原选择规则处理。不得以变量引用（R2 域）静默替代；若提出全覆盖替代方案须先提交差异/失败行为/验收证据并履行标准 §5 审批。R2 变量服务与 VarPool 的存储集成可后置设计，本契约行为先冻结、R4 验收不因此省略（`DependentExecute.java:L392-L414` 消费锚）。
7. 资源域（§3.2）不受本节影响。
8. **组间 relation 复刻（监督线 #38 F1/F2 修订连带发现，2026-10-17 补）**：DS `Dependence.relation` 为**组间** relation（`DependentParameters.java:L57-L70`，DS 原生支持组间 OR）；`groups[]` 同级新增 `group_relation: AND|OR`（缺省 `AND` 向后兼容 v1 wire），服务端拼装表达式按组内 `join` 判组、再按 `group_relation` 判整体。v1 §3.1「多组之间固定 AND」草案语义就此修正，本项与 §7 整体一并复核冻结。
9. **失败等待、节点超时与系统运行上限（D6 修订）**：DS 依赖任务表单把 `failurePolicy=DEPENDENT_FAILURE_WAITING` × `failureWaitingTime`（正整数分钟）与等待依赖完成开关 `timeoutFlag` 互斥；timeoutFlag 开启时 UI 默认 `timeout=30` 分钟、`timeoutNotifyStrategy=['WARN']`，策略为可多选 WARN/FAILED，默认值和互斥校验见 `use-dependent.ts:L33-L53`、`use-dependent.ts:L551`、`fields/use-dependent-timeout.ts:L31-L105`。Failure-waiting 的截止时刻按 tracker 选择流程 scheduleTime（存在时）或当前时刻为起点，再加配置时长（`DependentTaskTracker.java:L72-L100,L123-L128`）。timeout event 由 TaskStartLifecycleEventHandler 发布，延迟从 taskInstance.submitTime 起算并加配置分钟（`TaskTimeoutLifecycleEvent.java:L48-L58`、`TaskStartLifecycleEventHandler.java:L70-L85`）；WARN 发告警但不终止，FAILED 发布 kill event，状态机持久化终态 KILL；WARNFAILED 同时发布 kill 并尝试告警（`TaskTimeoutLifecycleEventHandler.java:L67-L98`、`AbstractTaskStateAction.java:L180-L194`）。系统 max-runtime 也会独立发布 FAILED timeout event；源码没有证明它与任务 timeout 同时到期时有优先级，Datara 按下文确定性终态规则处理。

   Datara 合同保留三套不可合并的时间语义：①`failure_waiting_seconds` 为上游失败后继续等待策略的时长，起点按 scheduleTime（若有）否则本次开始判定时刻；②`dependent_wait_timeout_enabled`（缺省 false）+ `dependent_wait_timeout_seconds`（正整数秒；DS UI 的正整数分钟 ×60，溢出拒绝）+ `dependent_wait_timeout_strategies: [warn|failed, ...]`（开启时缺省 `[warn]`，至少一项，允许 warn 与 failed 同选；两项并选映射 DS `WARNFAILED`）为依赖节点等待完成的任务级 timeout；③系统 max-runtime 是平台硬上限，不复用前两种字段。①②同时开启按 `DEP_INVALID_TIMEOUT_POLICY` 拒绝。策略语义：warn 只告警；failed 终止任务并记录 `terminal_state=KILL`、`termination_reason=dependent_wait_timeout`；两者并选时同时告警并终止。系统 max-runtime 到期使用平台硬终止策略并记录 `terminal_state=KILL`、`termination_reason=system_max_runtime`。已进入终态的任务不被后续 timeout 事件改写；若两种 deadline 同时到达，以先成功提交的终态转换为准。原 `timeout_seconds` 只代表 Datara 依赖窗口关闭后仍未达成的判定阈值，不能与①②③互相代替。acceptance 必须覆盖默认/单策略/双策略、互斥、分钟到秒换算及溢出、起算点、告警/终止终态、并发 deadline 单终态与保留 termination_reason。
