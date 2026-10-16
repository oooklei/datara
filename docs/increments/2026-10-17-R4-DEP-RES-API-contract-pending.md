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

错误响应使用稳定机器码：`DEP_PERMISSION_DENIED`、`DEP_OBJECT_NOT_FOUND`、`DEP_UPSTREAM_NOT_PUBLISHED`、`DEP_INVALID_WINDOW`、`DEP_VERSION_IMMUTABLE`、`RES_PERMISSION_DENIED`、`RES_OBJECT_NOT_FOUND`、`RES_KIND_UNKNOWN`、`RES_TYPE_NOT_ALLOWED`、`RES_SIZE_EXCEEDED`、`RES_VERSION_NOT_FOUND`、`RES_VERSION_IMMUTABLE`、`RES_BINDING_CONFLICT`。字段级校验诊断包含 `field`、`code`、`message`，不得只返回 HTTP 200 + 空映射。

## 3. 请求合同

### 3.1 依赖域（DEPENDENCY）

写入与判定请求统一承载 `groups: [{join, conditions: [...]}]`；`join` 为组内条件连接符（`AND`|`OR`）。组间连接：v1 草案原定**多组之间固定 AND**（组间不允许 OR），§7.8 按用户复刻令修正为 `group_relation: AND|OR`（复刻 DS `Dependence.relation`，DS 原生支持组间 OR）——**以 §7.8 为准**。条件项 wire 字段：`upstream_workflow_id`（必填）、`upstream_workflow_version?`（缺省=随上游最新已发布版本，判定/预演时按 `as_of` 时点解析）、`upstream_task_code?`（缺省=整工作流成功）、`date_range: {period_type, begin_offset, end_offset}`（`period_type` ∈ `hour|day|week|month`；offset 0=当前周期，-1=上一周期，按周期类型各自解释）。

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
- 20MB 上限值、`as_of` 格式口径、组间 relation（`group_relation: AND|OR`，见 §7.8）、`upstream_workflow_version` 缺省语义、绑定冲突语义为本文提请冻结项；冻结前前端按现类型面（草案语义）不动。

## 6. 当前 RED 与后续门

前端 RED 已就位：worktree `datara-web/src/views/rebuild/validation/dependency-form/dependencyApi.contract.test.ts` 与 `resource-upload/resourceApi.contract.test.ts` 断言两哨兵（`R4_DEPENDENCY_NOT_WIRED` / `R4_RESOURCE_NOT_WIRED`）rejects，主测试集保持可运行。后端实现落地且本草案经 Codex 复核冻结后，Trae 按接线计划对 10 方法做 TDD 红绿（端点 URL 与请求键形 / wire→FE 映射 / 错误归一三要素），worktree 侧无本域哨兵改名残留（`R4_*` 词形不在 X13 改名档）。若 Codex 对路由形态、错误码或待冻结项有修正，以修订后的本文为接线权威并同步 B2 总表。

## 7. v2 修订（2026-10-17，用户复刻裁定后）

用户裁定：后端重构阶段必须复刻 DolphinScheduler 依赖实现（源码 `D:\dolphinscheduler-dev\dolphinscheduler-dev`），扩展项按设计 §6.5 补建模。研读依据：`docs/increments/2026-10-17-DBX-DS-源码研读与复刻映射.md` §2/§3.1。本节为对 §2/§3.1 的增补修订，提请 Codex 复核冻结时**以本节为准**：

1. **条件项扩展**：`conditions[]` 每项新增 `kind: workflow|task|file|table_state|external_task`（缺省 `task` 向后兼容 v1）。`workflow`/`task` 为 DS `DependentItem.dependentType` 复刻映射（`task` 的 `upstream_task_code` 缺省=整工作流成功，对应 DS `DEPENDENT_ALL_TASK_CODE` 分支）；`file`/`table_state`/`external_task` 为 Datara 扩展 kind，其条件参数结构（文件路径/表名+分区状态/外部系统+任务标识）随 kind 定义，v2 先冻结 kind 枚举与分发语义，各 kind 详细字段在 BE 实现设计时补齐并再确认。
2. **条件极性**：新增 `dependResult: success|failed`（缺省 `success`）——复刻 DS 依赖上游失败也成立条件的语义。
3. **配置级策略**（保存对象级，随 groups 同级保存——字段归属对齐 DS 内部静态类 `Dependence` 的嵌套：五字段为依赖配置顶层、与 dependTaskList 同级，监督线 F2）：`check_interval_seconds`（轮询判定间隔，DS `checkInterval` 单位=秒，一致无换算）、`failure_policy: fail|waiting`（缺省 `fail`，复刻 `DEPENDENT_FAILURE_FAILURE|WAITING`）、`failure_waiting_minutes`（policy=waiting 时生效；**复刻 DS `failureWaitingTime` 单位=分钟**——`DependentParameters.java:L66-L69` 注释 Time unit is minutes，监督线 F1；字段名直接带单位防 60 倍偏差，**不做秒统一换算**——DS 前端表单即分钟粒度，换算层是纯增风险）、`timeout_seconds`（窗口关闭后未达成判超时的阈值，Datara 语义，对应注解「超时」）。
4. **时间窗双轨**：输入采纳 DS 命名窗词汇 `cycle ∈ hour|day|week|month` × `dateValue`（`currentHour|last1Hour|last24Hours|today|last7Days|thisMonth…`，全表以 DS `use-dependent.ts` CYCLE_LIST/DATE_LIST 为准）；输出窗口起止仍为 ISO 8601（§3.1 v1 的 `begin_offset/end_offset` 保留为等价计算形态，二者取一提交、服务端归一）。
5. **判定语义照搬**：DS `DependentUtils` 三态机同规则两层递归应用——组内（`join`）：AND 任一 `failed` 即失败、有 `pending` 即等待；OR 任一 `satisfied` 即通过、有 `pending` 即等待、否则失败；组间（`group_relation`，§7.8）：对各组结果按同一 AND/OR 规则再组合；整体四枚举 satisfied|pending|failed|timeout 不变。
6. **观察项**：DS `parameterPassing`（上游参数透传）与我方变量体系重叠——倾向以变量引用（R2 域）替代，随 A5 变量集成议程裁定，v2 不建模。
7. 资源域（§3.2）不受本节影响。
8. **组间 relation 复刻（监督线 #38 F1/F2 修订连带发现，2026-10-17 补）**：DS `Dependence.relation` 为**组间** relation（`DependentParameters.java:L57-L70`，DS 原生支持组间 OR）；`groups[]` 同级新增 `group_relation: AND|OR`（缺省 `AND` 向后兼容 v1 wire），服务端拼装表达式按组内 `join` 判组、再按 `group_relation` 判整体。v1 §3.1「多组之间固定 AND」草案语义就此修正，本项与 §7 整体一并复核冻结。